"""Export the loaded corpus as the Hugging Face dataset's parquet shards (ADR-0069).

Two configs, written under `--out` (default `data/hf/`, gitignored):

  * `current/`  — one row per section at the newest release point it appears at
                  (~66k rows).
  * `versions/` — one row per deduped section version, with the release range
                  and list it was published at (~490k rows).

Both passes stream on a server-side cursor (the `yield_per` pattern documented
in `ingest/reindex_search.py` — buffering 490k XML fragments client-side is an
OOM). Release ranges come from aggregating `section_release_map` in Postgres,
never from `first_release_id`, which an incremental load can leave higher than
the earliest mapped release (ADR-0066).

`data/hf/manifest.json` records the corpus fingerprint each export was taken
from; an export against an unchanged fingerprint is a no-op unless `--force`.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import pyarrow as pa
import pyarrow.parquet as pq
from lxml import etree
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from db.models import (
    ReleasePoint,
    Section,
    SectionReleaseMap,
    SectionVersion,
    StructureNode,
    Title,
    TitleVersion,
)
from ingest.parser import parser_for_fragment
from ingest.reindex_search import _colliding_doc_ids

DEFAULT_OUT = Path("data/hf")
MANIFEST_NAME = "manifest.json"
CONFIGS = ("current", "versions")
SHARD_ROWS = 25_000
_BATCH_ROWS = 1_000  # rows per parquet row group (~20 KB of XML each)

_ANCESTOR = pa.struct(
    [
        ("identifier", pa.string()),
        ("level", pa.string()),
        ("num", pa.string()),
        ("heading", pa.string()),
    ]
)
_NOTE = pa.struct(
    [
        ("topic", pa.string()),
        ("role", pa.string()),
        ("heading", pa.string()),
        ("text", pa.large_string()),
    ]
)

_SHARED_FIELDS: list[tuple[str, pa.DataType]] = [
    ("identifier", pa.string()),
    ("citation", pa.string()),
    ("title", pa.string()),
    ("title_name", pa.string()),
    ("title_is_positive_law", pa.bool_()),
    ("num", pa.string()),
    ("num_value", pa.string()),
    ("heading", pa.string()),
    ("status", pa.string()),
    ("text", pa.large_string()),
    ("xml", pa.large_string()),
    ("source_credit", pa.string()),
    ("notes", pa.list_(_NOTE)),
    ("content_hash", pa.string()),
]

CURRENT_SCHEMA = pa.schema(
    [
        *_SHARED_FIELDS,
        ("parent_identifier", pa.string()),
        ("ancestors", pa.list_(_ANCESTOR)),
        ("seq_in_title", pa.int32()),
        ("uslm_schema", pa.string()),
        ("release_label", pa.string()),
        ("release_seq", pa.int32()),
        ("currency_date", pa.date32()),
        ("release_congress", pa.int32()),
        ("release_law", pa.int32()),
        ("release_update", pa.int32()),
        ("release_excluded_laws", pa.list_(pa.int32())),
        ("text_since", pa.string()),
    ]
)

VERSIONS_SCHEMA = pa.schema(
    [
        *_SHARED_FIELDS,
        ("uslm_version", pa.string()),
        ("first_release", pa.string()),
        ("first_release_seq", pa.int32()),
        ("first_currency_date", pa.date32()),
        ("last_release", pa.string()),
        ("last_release_seq", pa.int32()),
        ("last_currency_date", pa.date32()),
        ("releases", pa.list_(pa.string())),
        ("release_count", pa.int32()),
        ("is_current", pa.bool_()),
        ("identifier_collision", pa.bool_()),
        ("parent_identifier", pa.string()),
        ("seq_in_title", pa.int32()),
    ]
)

_FLAT_SECTION = re.compile(r"^/us/usc/t(\d+)/s([^/]+)$")
_LEAKED_SIGIL = re.compile(r"^\s*§\s*")
"""Four corpus identifiers embed a literal `§ ` in the section segment
(`/us/usc/t2/s § 112g` — a converter quirk, narrow no-break space and
all); the designator and citation strip it."""


def citation_for(identifier: str) -> str | None:
    """`/us/usc/t16/s45f` → `16 U.S.C. § 45f`; None for any other shape.

    Appendix and act-style identifiers (`/us/usc/t5a/pl/92/463/s1`) get no
    citation: the flat `5 U.S.C. App.` forms are ones the corpus itself cannot
    resolve (CLAUDE.md open debt), and a citation the source would 404 on is
    worse than none. Section numbers keep their U+2013 en dash exactly as OLRC
    writes them (gotcha 17).
    """
    match = _FLAT_SECTION.match(identifier)
    if not match:
        return None
    number = _LEAKED_SIGIL.sub("", match.group(2))
    return f"{match.group(1)} U.S.C. § {number}"


def _num_value(identifier: str) -> str | None:
    """The machine designator, read off a *section* identifier's last segment —
    `section_versions` does not store `<num @value>` separately."""
    last = identifier.rsplit("/", 1)[-1]
    if last.startswith("s") and len(last) > 1:
        return _LEAKED_SIGIL.sub("", last[1:])
    return None


def fingerprint(session) -> dict[str, Any]:
    """What the corpus looked like when an export ran — the no-op gate.

    The newest *loaded* release (a `title_versions` row with `sections_loaded`
    set, the load-complete marker) plus the three table counts. Any new release
    point, section or version moves it.
    """
    newest = session.execute(
        select(ReleasePoint.label, ReleasePoint.seq, ReleasePoint.currency_date)
        .join(TitleVersion, TitleVersion.release_id == ReleasePoint.id)
        .where(TitleVersion.sections_loaded.is_not(None))
        .order_by(ReleasePoint.seq.desc())
        .limit(1)
    ).one_or_none()
    counts = session.execute(
        select(
            select(func.count()).select_from(Section).scalar_subquery(),
            select(func.count()).select_from(SectionVersion).scalar_subquery(),
            select(func.count()).select_from(SectionReleaseMap).scalar_subquery(),
        )
    ).one()
    return {
        "newest_release": (
            {
                "label": newest[0],
                "seq": newest[1],
                "currency_date": newest[2].isoformat(),
            }
            if newest
            else None
        ),
        "counts": {
            "sections": counts[0],
            "section_versions": counts[1],
            "map_rows": counts[2],
        },
    }


# --------------------------------------------------------------------- queries

MappedRelease = aliased(ReleasePoint)
FirstRP = aliased(ReleasePoint)
LastRP = aliased(ReleasePoint)
TextSinceRP = aliased(ReleasePoint)


def _range_subquery(with_labels: bool):
    """Per-version aggregation over the (version, release) map: the seq range,
    the count, and (for the versions config) every label in inventory order.
    Runs in Postgres — a Python-side dict over 5.4M map rows is the alternative,
    declined for memory."""
    rp = aliased(ReleasePoint)
    columns = [
        SectionReleaseMap.section_version_id.label("version_id"),
        func.min(rp.seq).label("first_seq"),
        func.max(rp.seq).label("last_seq"),
        func.count().label("release_count"),
    ]
    if with_labels:
        from sqlalchemy.dialects.postgresql import aggregate_order_by

        columns.append(
            func.array_agg(aggregate_order_by(rp.label, rp.seq)).label("labels")
        )
    return (
        select(*columns)
        .join(rp, rp.id == SectionReleaseMap.release_id)
        .group_by(SectionReleaseMap.section_version_id)
        .subquery()
    )


def _current_query():
    """The version each section carries at the newest release point it appears
    at — `DISTINCT ON` over the map ordered by the inventory's global `seq`
    (labels don't sort, gotcha 4), with `SectionVersion.id` as a deterministic
    tiebreak for the ADR-0021 twins that share one (section, release)."""
    ranges = _range_subquery(with_labels=False)
    return (
        select(
            Section.identifier.label("identifier"),
            Title.num.label("title_num"),
            Title.name.label("title_name"),
            Title.is_positive_law.label("title_is_positive_law"),
            Title.id.label("title_id"),
            SectionVersion.num.label("num"),
            SectionVersion.heading.label("heading"),
            SectionVersion.status.label("status"),
            SectionVersion.source_credit.label("source_credit"),
            SectionVersion.xml.label("xml"),
            SectionVersion.content_hash.label("content_hash"),
            SectionReleaseMap.parent_identifier.label("parent_identifier"),
            SectionReleaseMap.seq_in_title.label("seq_in_title"),
            MappedRelease.label.label("release_label"),
            MappedRelease.seq.label("release_seq"),
            MappedRelease.currency_date.label("currency_date"),
            MappedRelease.congress.label("release_congress"),
            MappedRelease.law_num.label("release_law"),
            MappedRelease.update_num.label("release_update"),
            MappedRelease.excluded_laws.label("release_excluded_laws"),
            TitleVersion.schema_version.label("uslm_schema"),
            TextSinceRP.label.label("text_since"),
        )
        .select_from(SectionReleaseMap)
        .join(SectionVersion, SectionVersion.id == SectionReleaseMap.section_version_id)
        .join(Section, Section.id == SectionVersion.section_id)
        .join(Title, Title.id == Section.title_id)
        .join(MappedRelease, MappedRelease.id == SectionReleaseMap.release_id)
        .outerjoin(
            TitleVersion,
            (TitleVersion.title_id == Section.title_id)
            & (TitleVersion.release_id == MappedRelease.id),
        )
        .outerjoin(ranges, ranges.c.version_id == SectionVersion.id)
        .outerjoin(TextSinceRP, TextSinceRP.seq == ranges.c.first_seq)
        .distinct(SectionVersion.section_id)
        .order_by(
            SectionVersion.section_id,
            MappedRelease.seq.desc(),
            SectionVersion.id.desc(),
        )
    )


def _current_ordered():
    """The current rows in reading order — title, then `seq_in_title`. The
    `DISTINCT ON` inner query must order by its distinct key, so the reading
    order goes on a wrapper."""
    inner = _current_query().subquery()
    return select(inner).order_by(inner.c.title_id, inner.c.seq_in_title)


def _versions_query():
    """Every deduped version, its release range read off the map aggregation,
    and the placement it had at its first *mapped* release. All the joins past
    the title are outer ones: an ADR-0021 twin can have no map row at all, and
    then has no range, no placement and no release columns."""
    ranges = _range_subquery(with_labels=True)
    return (
        select(
            Section.identifier.label("identifier"),
            Title.num.label("title_num"),
            Title.name.label("title_name"),
            Title.is_positive_law.label("title_is_positive_law"),
            SectionVersion.id.label("version_id"),
            SectionVersion.first_release_id.label("first_release_id"),
            SectionVersion.num.label("num"),
            SectionVersion.heading.label("heading"),
            SectionVersion.status.label("status"),
            SectionVersion.source_credit.label("source_credit"),
            SectionVersion.xml.label("xml"),
            SectionVersion.content_hash.label("content_hash"),
            ranges.c.first_seq.label("first_release_seq"),
            ranges.c.last_seq.label("last_release_seq"),
            ranges.c.release_count.label("release_count"),
            ranges.c.labels.label("releases"),
            FirstRP.label.label("first_release"),
            FirstRP.currency_date.label("first_currency_date"),
            LastRP.label.label("last_release"),
            LastRP.currency_date.label("last_currency_date"),
            SectionReleaseMap.parent_identifier.label("parent_identifier"),
            SectionReleaseMap.seq_in_title.label("seq_in_title"),
        )
        .select_from(SectionVersion)
        .join(Section, Section.id == SectionVersion.section_id)
        .join(Title, Title.id == Section.title_id)
        .outerjoin(ranges, ranges.c.version_id == SectionVersion.id)
        .outerjoin(FirstRP, FirstRP.seq == ranges.c.first_seq)
        .outerjoin(LastRP, LastRP.seq == ranges.c.last_seq)
        .outerjoin(
            SectionReleaseMap,
            (SectionReleaseMap.section_version_id == SectionVersion.id)
            & (SectionReleaseMap.release_id == FirstRP.id),
        )
        .order_by(SectionVersion.id)
    )


# ------------------------------------------------------------------- row build


def _structure_maps(session) -> tuple[dict, dict]:
    """`structure_nodes` in memory (~10k rows): by id for parent walks, by
    identifier for entry. The unversioned newest-release view, said in the card."""
    by_id: dict[int, tuple] = {}
    by_identifier: dict[str, tuple] = {}
    rows = session.execute(
        select(
            StructureNode.id,
            StructureNode.identifier,
            StructureNode.level,
            StructureNode.num_value,
            StructureNode.heading,
            StructureNode.parent_id,
        )
    )
    for row in rows:
        by_id[row[0]] = row
        by_identifier[row[1]] = row
    return by_id, by_identifier


def _ancestors(
    parent_identifier: str | None, by_id: dict, by_identifier: dict
) -> list[dict]:
    chain: list[dict] = []
    row = by_identifier.get(parent_identifier) if parent_identifier else None
    while row is not None:
        chain.append(
            {
                "identifier": row[1],
                "level": row[2],
                "num": row[3],
                "heading": row[4],
            }
        )
        row = by_id.get(row[5]) if row[5] is not None else None
    chain.reverse()
    return chain


def _extract(xml: str) -> tuple[Any, str, list[dict]]:
    parser = parser_for_fragment(xml)
    root = etree.fromstring(xml)  # parsed once, shared by both extractions
    notes = [
        {"topic": n.topic, "role": n.role, "heading": n.heading, "text": n.text}
        for n in parser.notes_text(root)
    ]
    return parser, parser.plain_text(root), notes


def _shared_columns(identifier: str, row, text: str, notes: list[dict]) -> dict:
    return {
        "identifier": identifier,
        "citation": citation_for(identifier),
        "title": row.title_num,
        "title_name": row.title_name,
        "title_is_positive_law": row.title_is_positive_law,
        "num": row.num,
        "num_value": _num_value(identifier),
        "heading": row.heading,
        "status": row.status,
        "text": text,
        "xml": row.xml,
        "source_credit": row.source_credit,
        "notes": notes,
        "content_hash": row.content_hash.hex(),
    }


def _current_rows(session, batch_size: int, limit: int | None) -> Iterator[dict]:
    by_id, by_identifier = _structure_maps(session)
    stmt = _current_ordered()
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = session.execute(
        stmt.execution_options(stream_results=True, yield_per=batch_size)
    )
    for row in rows:
        _, text, notes = _extract(row.xml)
        yield {
            **_shared_columns(row.identifier, row, text, notes),
            "parent_identifier": row.parent_identifier,
            "ancestors": _ancestors(row.parent_identifier, by_id, by_identifier),
            "seq_in_title": row.seq_in_title,
            "uslm_schema": row.uslm_schema,
            "release_label": row.release_label,
            "release_seq": row.release_seq,
            "currency_date": row.currency_date,
            "release_congress": row.release_congress,
            "release_law": row.release_law,
            "release_update": row.release_update,
            "release_excluded_laws": list(row.release_excluded_laws or []),
            "text_since": row.text_since,
        }


def _versions_rows(
    session, batch_size: int, limit: int | None, current_ids: set[int]
) -> Iterator[dict]:
    collisions = _colliding_doc_ids(session)
    stmt = _versions_query()
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = session.execute(
        stmt.execution_options(stream_results=True, yield_per=batch_size)
    )
    for row in rows:
        parser, text, notes = _extract(row.xml)
        yield {
            **_shared_columns(row.identifier, row, text, notes),
            "uslm_version": str(parser.uslm_version),
            "first_release": row.first_release,
            "first_release_seq": row.first_release_seq,
            "first_currency_date": row.first_currency_date,
            "last_release": row.last_release,
            "last_release_seq": row.last_release_seq,
            "last_currency_date": row.last_currency_date,
            "releases": list(row.releases or []),
            "release_count": row.release_count or 0,
            "is_current": row.version_id in current_ids,
            "identifier_collision": (row.identifier, row.first_release_id)
            in collisions,
            "parent_identifier": row.parent_identifier,
            "seq_in_title": row.seq_in_title,
        }


# --------------------------------------------------------------------- writing


class _ShardWriter:
    """Buffered parquet writing with shard rotation and final renames.

    Rows buffer into `_BATCH_ROWS` row groups; a shard closes at `shard_rows`
    and the temp files are renamed `train-{i:05d}-of-{n:05d}.parquet` once the
    total is known.
    """

    def __init__(self, out_dir: Path, schema: pa.Schema, shard_rows: int = SHARD_ROWS):
        self.out_dir = out_dir
        self.schema = schema
        self.shard_rows = shard_rows
        self.buffer: list[dict] = []
        self.rows_total = 0
        self.rows_in_shard = 0
        self.tmp_paths: list[Path] = []
        self.writer: pq.ParquetWriter | None = None
        out_dir.mkdir(parents=True, exist_ok=True)

    def add(self, row: dict) -> None:
        self.buffer.append(row)
        if len(self.buffer) >= _BATCH_ROWS:
            self._flush()

    def _flush(self) -> None:
        if not self.buffer:
            return
        if self.writer is not None and self.rows_in_shard >= self.shard_rows:
            self.writer.close()
            self.writer = None
        if self.writer is None:
            tmp = self.out_dir / f"train-tmp-{len(self.tmp_paths):05d}.parquet"
            self.tmp_paths.append(tmp)
            self.writer = pq.ParquetWriter(tmp, self.schema, compression="zstd")
            self.rows_in_shard = 0
        table = pa.Table.from_pylist(self.buffer, schema=self.schema)
        self.writer.write_table(table)
        self.rows_total += len(self.buffer)
        self.rows_in_shard += len(self.buffer)
        self.buffer.clear()

    def close(self) -> list[dict]:
        self._flush()
        if self.writer is not None:
            self.writer.close()
            self.writer = None
        total = len(self.tmp_paths)
        shards: list[dict] = []
        for index, tmp in enumerate(self.tmp_paths):
            final = self.out_dir / f"train-{index:05d}-of-{total:05d}.parquet"
            tmp.rename(final)
            digest = hashlib.sha256(final.read_bytes()).hexdigest()
            shards.append(
                {"name": final.name, "bytes": final.stat().st_size, "sha256": digest}
            )
        return shards


def _clear_shards(config_dir: Path) -> None:
    if config_dir.exists():
        for stale in config_dir.glob("*.parquet"):
            stale.unlink()


def _git_commit() -> str | None:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            or None
        )
    except (OSError, subprocess.CalledProcessError):
        return None


# ---------------------------------------------------------------------- export


@dataclass(frozen=True, slots=True)
class ExportReport:
    unchanged: bool
    manifest_path: Path
    rows: dict[str, int]


def read_manifest(out_dir: Path = DEFAULT_OUT) -> dict | None:
    path = out_dir / MANIFEST_NAME
    if not path.exists():
        return None
    return json.loads(path.read_text())


def export(
    out_dir: Path = DEFAULT_OUT,
    *,
    configs: tuple[str, ...] = CONFIGS,
    batch_size: int = 500,
    limit: int | None = None,
    force: bool = False,
    session=None,
    on_event=print,
) -> ExportReport:
    unknown = set(configs) - set(CONFIGS)
    if unknown:
        raise ValueError(f"unknown configs: {sorted(unknown)}")

    owns_session = session is None
    if owns_session:
        from db.base import SessionLocal

        session = SessionLocal()
    try:
        current_fingerprint = fingerprint(session)
        manifest = read_manifest(out_dir)
        if (
            not force
            and limit is None
            and manifest is not None
            and manifest.get("fingerprint") == current_fingerprint
            and set(configs) <= set(manifest.get("configs", {}))
        ):
            newest = (current_fingerprint.get("newest_release") or {}).get("label")
            on_event(f"Nothing changed since {newest}; skipping (--force overrides).")
            return ExportReport(
                unchanged=True,
                manifest_path=out_dir / MANIFEST_NAME,
                rows={
                    name: entry["rows"]
                    for name, entry in manifest.get("configs", {}).items()
                },
            )

        results: dict[str, dict] = {}

        if "current" in configs:
            on_event("Exporting config `current`…")
            _clear_shards(out_dir / "current")
            writer = _ShardWriter(out_dir / "current", CURRENT_SCHEMA)
            for count, row in enumerate(_current_rows(session, batch_size, limit), 1):
                writer.add(row)
                if count % 5000 == 0:
                    on_event(f"  {count} rows")
            shards = writer.close()
            results["current"] = {"rows": writer.rows_total, "shards": shards}
            on_event(f"  current: {writer.rows_total} rows")

        if "versions" in configs:
            on_event("Exporting config `versions`…")
            on_event("  collecting current version ids…")
            current_ids = _current_ids(session)
            on_event(f"  {len(current_ids)} current versions")
            _clear_shards(out_dir / "versions")
            writer = _ShardWriter(out_dir / "versions", VERSIONS_SCHEMA)
            rows_iter = _versions_rows(session, batch_size, limit, current_ids)
            for count, row in enumerate(rows_iter, 1):
                writer.add(row)
                if count % 5000 == 0:
                    on_event(f"  {count} rows")
            shards = writer.close()
            results["versions"] = {"rows": writer.rows_total, "shards": shards}
            on_event(f"  versions: {writer.rows_total} rows")

        merged_configs = dict((manifest or {}).get("configs", {}))
        merged_configs.update(results)
        payload = {
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "git_commit": _git_commit(),
            "fingerprint": current_fingerprint,
            "partial": limit is not None,
            "configs": merged_configs,
        }
        manifest_path = out_dir / MANIFEST_NAME
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(payload, indent=2) + "\n")
        on_event(f"Manifest: {manifest_path}")
        return ExportReport(
            unchanged=False,
            manifest_path=manifest_path,
            rows={name: entry["rows"] for name, entry in results.items()},
        )
    finally:
        if owns_session:
            session.close()


def _current_ids(session) -> set[int]:
    """The version ids the `current` config exports — `is_current` for the
    versions config, the same technique as `reindex_search._index_sections`."""
    stmt = (
        select(SectionVersion.id)
        .select_from(SectionReleaseMap)
        .join(SectionVersion, SectionVersion.id == SectionReleaseMap.section_version_id)
        .join(MappedRelease, MappedRelease.id == SectionReleaseMap.release_id)
        .distinct(SectionVersion.section_id)
        .order_by(
            SectionVersion.section_id,
            MappedRelease.seq.desc(),
            SectionVersion.id.desc(),
        )
    )
    return {
        row[0]
        for row in session.execute(
            stmt.execution_options(stream_results=True, yield_per=5000)
        )
    }
