"""`python -m ingest load` orchestration: parse one title file into Postgres.

Dedupe rule (PLAN §3/§9.10): a section's content is identified by
`(section_id, content_hash)`. If that pair already has a `SectionVersion`, this
release is linked to the *existing* row via `section_release_map` — no new
`section_versions` row, no duplicate storage. Only genuinely new content
creates a new version, with `first_release_id` set to the release doing the
creating.

Everything here talks to `db.models` directly; it is the ingest side of the
Repository boundary (CLAUDE.md architecture rule 1 governs `api/`, not this).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from db.models import (
    GuidMap,
    ReleasePoint,
    Section,
    SectionReleaseMap,
    SectionVersion,
    Title,
    TitleVersion,
)
from ingest.parser import parser_for
from ingest.records import DocumentMeta
from ingest.release_label import parse_release_label

GUID_BATCH_SIZE = 500


class MissingCurrencyDateError(ValueError):
    """Raised when a release point is being created for the first time but no
    `--currency-date` was given. Source USLM files carry no currency date of
    their own (verified against usc16.xml) — it has to come from the caller or
    the RP inventory (PLAN.md Day 2), not from the XML."""


@dataclass
class LoadStats:
    """What one `load_release` call did, for the CLI summary and the manifest."""

    release_label: str
    title_num: str
    schema_version: str
    raw_section_elements: int
    sections_ingested: int
    new_section_versions: int
    deduped_section_versions: int
    status_counts: dict[str, int] = field(default_factory=dict)


def load_release(
    xml_path: Path,
    release_label: str,
    session: Session,
    *,
    currency_date: date | None = None,
) -> LoadStats:
    """Parse `xml_path` and load it into Postgres under `release_label`."""
    parser = parser_for(xml_path)
    meta = parser.parse_meta(xml_path)
    if not meta.doc_number:
        raise ValueError(f"{xml_path}: <docNumber> missing, cannot determine title")

    release = _get_or_create_release(session, release_label, currency_date)
    title = _get_or_create_title(session, meta)
    _get_or_create_title_version(session, title, release, xml_path, meta)
    session.commit()

    existing_sections = {
        s.identifier: s
        for s in session.scalars(select(Section).where(Section.title_id == title.id))
    }
    existing_versions: dict[int, dict[bytes, SectionVersion]] = {}
    if existing_sections:
        section_ids = [s.id for s in existing_sections.values()]
        for version in session.scalars(
            select(SectionVersion).where(SectionVersion.section_id.in_(section_ids))
        ):
            existing_versions.setdefault(version.section_id, {})[version.content_hash] = version

    status_counts: dict[str, int] = {}
    new_versions = 0
    deduped = 0
    sections_ingested = 0
    guid_rows: list[dict[str, object]] = []

    for record in parser.iter_sections(xml_path):
        section = existing_sections.get(record.identifier)
        if section is None:
            section = Section(title_id=title.id, identifier=record.identifier)
            session.add(section)
            session.flush()
            existing_sections[record.identifier] = section

        content_hash = hashlib.sha256(record.xml.encode("utf-8")).digest()
        version = existing_versions.get(section.id, {}).get(content_hash)
        if version is None:
            version = SectionVersion(
                section_id=section.id,
                first_release_id=release.id,
                content_hash=content_hash,
                xml=record.xml,
                num=record.num,
                heading=record.heading,
                status=record.status,
                seq_in_title=record.seq,
                source_credit=record.source_credit,
            )
            session.add(version)
            session.flush()
            existing_versions.setdefault(section.id, {})[content_hash] = version
            new_versions += 1
        else:
            deduped += 1

        session.execute(
            pg_insert(SectionReleaseMap)
            .values(section_version_id=version.id, release_id=release.id)
            .on_conflict_do_nothing(index_elements=["section_version_id", "release_id"])
        )

        for guid_ref in record.guid_refs:
            guid_rows.append(
                {"guid": guid_ref.guid, "release_id": release.id, "identifier": guid_ref.identifier}
            )
        if len(guid_rows) >= GUID_BATCH_SIZE:
            _flush_guid_rows(session, guid_rows)
            guid_rows.clear()
            session.commit()

        if record.status:
            status_counts[record.status] = status_counts.get(record.status, 0) + 1
        sections_ingested += 1

    if guid_rows:
        _flush_guid_rows(session, guid_rows)
    session.commit()

    raw_count = parser.count_section_elements(xml_path)

    return LoadStats(
        release_label=release_label,
        title_num=meta.doc_number,
        schema_version=meta.schema_version,
        raw_section_elements=raw_count,
        sections_ingested=sections_ingested,
        new_section_versions=new_versions,
        deduped_section_versions=deduped,
        status_counts=status_counts,
    )


def _flush_guid_rows(session: Session, rows: list[dict[str, object]]) -> None:
    stmt = pg_insert(GuidMap).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["guid"],
        set_={"release_id": stmt.excluded.release_id, "identifier": stmt.excluded.identifier},
    )
    session.execute(stmt)


def _get_or_create_release(
    session: Session, label: str, currency_date: date | None
) -> ReleasePoint:
    existing = session.scalars(
        select(ReleasePoint).where(ReleasePoint.label == label)
    ).first()
    if existing is not None:
        return existing
    if currency_date is None:
        raise MissingCurrencyDateError(
            f"release {label!r} does not exist yet and no --currency-date was given"
        )
    congress, law_num, excluded_laws = parse_release_label(label)
    max_seq = session.scalars(select(func.max(ReleasePoint.seq))).first()
    release = ReleasePoint(
        congress=congress,
        law_num=law_num,
        excluded_laws=excluded_laws,
        label=label,
        currency_date=currency_date,
        # Day-1 simplification: sequential assignment on first sight of a label.
        # Day 2's RP inventory (PLAN §6) supplies true cross-RP ordering; until
        # then this only holds within releases ingested by this command.
        seq=0 if max_seq is None else max_seq + 1,
    )
    session.add(release)
    session.flush()
    return release


def _get_or_create_title(session: Session, meta: DocumentMeta) -> Title:
    num = meta.doc_number
    assert num is not None
    existing = session.scalars(select(Title).where(Title.num == num)).first()
    if existing is not None:
        return existing
    title = Title(
        num=num,
        name=meta.doc_title or f"Title {num}",
        is_positive_law=bool(meta.is_positive_law) if meta.is_positive_law is not None else False,
    )
    session.add(title)
    session.flush()
    return title


def _get_or_create_title_version(
    session: Session,
    title: Title,
    release: ReleasePoint,
    xml_path: Path,
    meta: DocumentMeta,
) -> TitleVersion:
    existing = session.scalars(
        select(TitleVersion).where(
            TitleVersion.title_id == title.id, TitleVersion.release_id == release.id
        )
    ).first()
    if existing is not None:
        return existing
    title_version = TitleVersion(
        title_id=title.id,
        release_id=release.id,
        source_zip_sha256=_sha256_file(xml_path),
        schema_version=meta.schema_version,
    )
    session.add(title_version)
    session.flush()
    return title_version


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
