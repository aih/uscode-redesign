"""Classify every version transition and attribute text changes to Public Laws.

Phase V1 of `docs/version-semantics-spec.md` (ADR-0074). The version timeline
groups a section's history by ADR-0007's guid-stripped content hash, which
records a new version whenever the XML changed at all; measured on the loaded
corpus, 72.7% of transitions change no text and no notes. This module writes
one `section_version_changes` row per stored version group saying what kind of
change its arrival was — `text` / `notes` / `structure`, or `initial` for the
section's first group — and, for changes the OLRC classification tables
(ADR-0067) record a statute for, `section_version_change_laws` rows naming the
laws.

The rules, exactly as the spec states them:

- **Ordering.** Groups are ordered by the earliest release each is mapped to
  in `section_release_map` (`min(release_points.seq)`), tie-broken by version
  id — never by `first_release_id`, which an incremental load attaches earlier
  releases to without lowering (ADR-0066).
- **Window.** A transition spans from the last release mapped to the departing
  group to the first release mapped to the arriving group.
- **Attribution.** A law L = (congress, num) is in a transition's window iff L
  is incorporated at the arriving release and not at the departing one, where
  incorporated(RP, L) means L ≤ (RP.congress, RP.law_num) and L is not in
  RP.excluded_laws. Label-interval matching would miss every `not`-law
  incorporation — the text change between `116-344not283u1` and `116-344` is
  Pub. L. 116-283 entering, a law below both labels. Classification rows are
  matched by `usc_identifier IN identifier_variants(identifier)` because the
  corpus spells 5,697 sections with an EN DASH (gotcha 17).

Comparison is whitespace-insensitive (`ingest.records.text_hash_of`); the
recorded cost is that a genuine whitespace-only statutory change classifies as
structure-only, which is also how the reader's redline treats it (ADR-0026).

This is ingest-side code: it writes `db.models` directly (architecture rule 1
governs `api/`, not this) and knows no USLM element names of its own — the
backfill recovers missing hashes through `parser_for_fragment(xml)` and the
parser's `plain_text()`/`notes_text()`.
"""

from __future__ import annotations

import datetime
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from lxml import etree
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from db.models import (
    ClassificationEntry,
    ReleasePoint,
    Section,
    SectionReleaseMap,
    SectionVersion,
    SectionVersionChange,
    SectionVersionChangeLaw,
    Title,
    TitleVersion,
)
from ingest.parser import parser_for_fragment
from ingest.records import notes_hash_of, text_hash_of
from storage.classification import identifier_variants

VERIFICATION_DIR = Path("docs/verification")
REPORT_NAME = "version-changes.json"

SECTION_BATCH = 200
"""Sections per transaction. Each section's fragments are parsed one at a time
(gotcha 6); the batch only bounds how much bookkeeping a commit covers."""

# `Pub. L. 92–463` — the corpus writes the citation with an EN DASH; accept the
# hyphen too for anything that survived a round trip through a dash-folding
# system.
_PL_CITATION = re.compile(r"Pub\.\s*L\.\s*(\d{1,3})[–‑-](\d{1,4})")

OnEvent = Callable[[str], None] | None


# --------------------------------------------------------------------- windows


@dataclass(frozen=True, slots=True)
class ReleaseFacts:
    """What the window arithmetic needs to know about one release point."""

    id: int
    seq: int
    label: str
    congress: int
    law_num: int
    excluded: frozenset[int]


def incorporated(rp: ReleaseFacts, congress: int, law_num: int) -> bool:
    """Whether Pub. L. `congress`-`law_num` is incorporated at `rp`.

    L ≤ (RP.congress, RP.law_num) and L not excluded. `excluded_laws` holds law
    numbers of the release point's own congress (`119-102not101` excludes
    119-101 and no other congress's 101).
    """
    if (congress, law_num) > (rp.congress, rp.law_num):
        return False
    if congress == rp.congress and law_num in rp.excluded:
        return False
    return True


def law_in_window(
    departing: ReleaseFacts | None, arriving: ReleaseFacts, congress: int, law_num: int
) -> bool:
    """Newly incorporated across the transition: in at `arriving`, not at
    `departing`. With no departing release there is no window — an unbounded
    "everything ever enacted" would attribute every law, so nothing matches."""
    if departing is None:
        return False
    return incorporated(arriving, congress, law_num) and not incorporated(
        departing, congress, law_num
    )


def credit_laws(source_credit: str | None) -> frozenset[tuple[int, int]]:
    """The `Pub. L. C-N` citations a source credit carries, as (congress, num)."""
    if not source_credit:
        return frozenset()
    return frozenset(
        (int(c), int(n)) for c, n in _PL_CITATION.findall(source_credit)
    )


def _release_facts(session: Session) -> dict[int, ReleaseFacts]:
    return {
        row.id: ReleaseFacts(
            id=row.id,
            seq=row.seq,
            label=row.label,
            congress=row.congress,
            law_num=row.law_num,
            excluded=frozenset(row.excluded_laws or ()),
        )
        for row in session.execute(
            select(
                ReleasePoint.id,
                ReleasePoint.seq,
                ReleasePoint.label,
                ReleasePoint.congress,
                ReleasePoint.law_num,
                ReleasePoint.excluded_laws,
            )
        )
    }


def _title_load_seqs(session: Session, title_id: int) -> list[tuple[int, int]]:
    """(seq, release_id) of every *completed* load of this title, ascending.

    The departing end of a mid-corpus `initial` window: a section absent from
    the title's previous loaded release and present now arrived somewhere in
    between, so a `new` classification row can attribute its creation.
    """
    rows = session.execute(
        select(ReleasePoint.seq, ReleasePoint.id)
        .select_from(TitleVersion)
        .join(ReleasePoint, ReleasePoint.id == TitleVersion.release_id)
        .where(
            TitleVersion.title_id == title_id,
            TitleVersion.sections_loaded.is_not(None),
        )
        .order_by(ReleasePoint.seq)
    ).all()
    return [(seq, rid) for seq, rid in rows]


def _latest_load_before(loads: Sequence[tuple[int, int]], seq: int) -> int | None:
    """release_id of the newest completed load strictly below `seq`."""
    found: int | None = None
    for load_seq, release_id in loads:
        if load_seq >= seq:
            break
        found = release_id
    return found


# ---------------------------------------------------------------- per section


@dataclass(slots=True)
class _Group:
    """One version group of a section with its mapped-release range."""

    version_id: int
    text_hash: bytes | None
    notes_hash: bytes | None
    heading: str | None
    status: str | None
    source_credit: str | None
    first_seq: int
    last_seq: int
    first_release_id: int
    last_release_id: int


@dataclass(slots=True)
class _Law:
    in_classification: bool = False
    note_only: bool = True
    in_source_credit: bool = False
    actions: set[str] = field(default_factory=set)


@dataclass(slots=True)
class ComputeStats:
    sections: int = 0
    skipped: int = 0
    changes: int = 0
    laws: int = 0
    hashes_computed: int = 0

    def add(self, other: "ComputeStats") -> None:
        self.sections += other.sections
        self.skipped += other.skipped
        self.changes += other.changes
        self.laws += other.laws
        self.hashes_computed += other.hashes_computed


def _squash(value: str | None) -> str:
    return "".join((value or "").split())


def _collapse(value: str | None) -> str:
    return " ".join((value or "").split())


def _ensure_hashes(session: Session, version_ids: Iterable[int]) -> int:
    """Fill `text_hash`/`notes_hash` on versions that lack them.

    One fragment in memory at a time: each is fetched, parsed once, hashed and
    released before the next (gotcha 6 — Title 42 fragments run to hundreds of
    KB and a section can hold 400 versions).
    """
    computed = 0
    for version_id in version_ids:
        xml = session.execute(
            select(SectionVersion.xml).where(SectionVersion.id == version_id)
        ).scalar_one()
        parser = parser_for_fragment(xml)
        root = etree.fromstring(xml.encode("utf-8"))
        session.execute(
            update(SectionVersion)
            .where(SectionVersion.id == version_id)
            .values(
                text_hash=text_hash_of(parser.plain_text(root)),
                notes_hash=notes_hash_of(parser.notes_text(root)),
            )
        )
        computed += 1
    return computed


def _groups_for_sections(
    session: Session, section_ids: Sequence[int], releases: dict[int, ReleaseFacts]
) -> dict[int, list[_Group]]:
    """Every section's version groups, ordered by earliest mapped release.

    A version no release maps to (which a half-finished load can leave) falls
    back to its own `first_release_id` for both ends rather than being dropped
    — dropping it would silently shift every later transition's departure.
    """
    seq_of = {facts.id: facts.seq for facts in releases.values()}
    release_at_seq = {facts.seq: facts.id for facts in releases.values()}

    ranges: dict[int, tuple[int, int]] = {
        vid: (lo, hi)
        for vid, lo, hi in session.execute(
            select(
                SectionReleaseMap.section_version_id,
                func.min(ReleasePoint.seq),
                func.max(ReleasePoint.seq),
            )
            .join(ReleasePoint, ReleasePoint.id == SectionReleaseMap.release_id)
            .where(SectionReleaseMap.section_version_id.in_(
                select(SectionVersion.id).where(SectionVersion.section_id.in_(section_ids))
            ))
            .group_by(SectionReleaseMap.section_version_id)
        )
    }

    grouped: dict[int, list[_Group]] = {sid: [] for sid in section_ids}
    for row in session.execute(
        select(
            SectionVersion.id,
            SectionVersion.section_id,
            SectionVersion.text_hash,
            SectionVersion.notes_hash,
            SectionVersion.heading,
            SectionVersion.status,
            SectionVersion.source_credit,
            SectionVersion.first_release_id,
        ).where(SectionVersion.section_id.in_(section_ids))
    ):
        span = ranges.get(row.id)
        if span is None:
            fallback = seq_of[row.first_release_id]
            span = (fallback, fallback)
        grouped[row.section_id].append(
            _Group(
                version_id=row.id,
                text_hash=row.text_hash,
                notes_hash=row.notes_hash,
                heading=row.heading,
                status=row.status,
                source_credit=row.source_credit,
                first_seq=span[0],
                last_seq=span[1],
                first_release_id=release_at_seq[span[0]],
                last_release_id=release_at_seq[span[1]],
            )
        )
    for groups in grouped.values():
        groups.sort(key=lambda g: (g.first_seq, g.version_id))
    return grouped


def _classification_rows(
    session: Session, identifiers: dict[int, str]
) -> dict[int, list[tuple[int, int, bool, str]]]:
    """Per section: (pl_congress, pl_num, is_note, action) of every
    classification row naming it, matched through `identifier_variants`."""
    variant_to_section: dict[str, int] = {}
    for section_id, identifier in identifiers.items():
        for variant in identifier_variants(identifier):
            variant_to_section[variant] = section_id
    if not variant_to_section:
        return {}
    rows: dict[int, list[tuple[int, int, bool, str]]] = {}
    for row in session.execute(
        select(
            ClassificationEntry.usc_identifier,
            ClassificationEntry.pl_congress,
            ClassificationEntry.pl_num,
            ClassificationEntry.is_note,
            ClassificationEntry.action,
        ).where(
            ClassificationEntry.usc_identifier.in_(variant_to_section),
            ClassificationEntry.pl_congress.is_not(None),
            ClassificationEntry.pl_num.is_not(None),
        )
    ):
        section_id = variant_to_section[row.usc_identifier]
        rows.setdefault(section_id, []).append(
            (row.pl_congress, row.pl_num, row.is_note, row.action or "")
        )
    return rows


def _attribute(
    cls_rows: Sequence[tuple[int, int, bool, str]],
    departing: ReleaseFacts | None,
    arriving: ReleaseFacts,
    from_credit: str | None,
    to_credit: str | None,
) -> tuple[str, dict[tuple[int, int], _Law]]:
    """The transition's attributed laws and the `attribution` value.

    `classified` needs at least one non-note classification row in the window
    (finding 5: structure-only transitions match at 0%, so the signal is
    clean). A law only a note row names, or one only newly present in the
    source credit, still gets a law row — flagged as what it is — but does not
    make the transition `classified`.
    """
    laws: dict[tuple[int, int], _Law] = {}
    for congress, num, is_note, action in cls_rows:
        if not law_in_window(departing, arriving, congress, num):
            continue
        law = laws.setdefault((congress, num), _Law())
        law.in_classification = True
        if not is_note:
            law.note_only = False
        law.actions.add(action)

    for congress, num in credit_laws(to_credit) - credit_laws(from_credit):
        if not law_in_window(departing, arriving, congress, num):
            continue
        laws.setdefault((congress, num), _Law()).in_source_credit = True

    classified = any(law.in_classification and not law.note_only for law in laws.values())
    return ("classified" if classified else "none"), laws


def compute_for_sections(
    session: Session,
    section_ids: Sequence[int],
    *,
    releases: dict[int, ReleaseFacts] | None = None,
    on_event: OnEvent = None,
) -> ComputeStats:
    """Delete and re-insert change rows for `section_ids`. Flushes, never
    commits — the caller owns the transaction (the CLI commits per batch, the
    `load_release` hook commits with the load, tests roll back)."""
    stats = ComputeStats()
    if not section_ids:
        return stats
    releases = releases if releases is not None else _release_facts(session)

    sections = session.execute(
        select(Section.id, Section.identifier, Section.title_id).where(
            Section.id.in_(section_ids)
        )
    ).all()
    identifiers = {row.id: row.identifier for row in sections}
    title_loads: dict[int, list[tuple[int, int]]] = {}
    for row in sections:
        if row.title_id not in title_loads:
            title_loads[row.title_id] = _title_load_seqs(session, row.title_id)
    title_of = {row.id: row.title_id for row in sections}

    missing = session.scalars(
        select(SectionVersion.id).where(
            SectionVersion.section_id.in_(section_ids),
            (SectionVersion.text_hash.is_(None)) | (SectionVersion.notes_hash.is_(None)),
        )
    ).all()
    stats.hashes_computed += _ensure_hashes(session, missing)

    grouped = _groups_for_sections(session, [row.id for row in sections], releases)
    cls_rows = _classification_rows(session, identifiers)

    session.execute(
        delete(SectionVersionChange).where(SectionVersionChange.section_id.in_(section_ids))
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    pending: list[tuple[SectionVersionChange, dict[tuple[int, int], _Law]]] = []
    for section_id, groups in grouped.items():
        if not groups:
            continue
        stats.sections += 1
        section_cls = cls_rows.get(section_id, ())
        loads = title_loads[title_of[section_id]]
        prev: _Group | None = None
        for group in groups:
            arriving = releases[group.first_release_id]
            if prev is None:
                change_kind = "initial"
                text_changed = notes_changed = heading_changed = status_changed = False
                concurrent = False
                window_from_id = None
                # A section arriving mid-corpus was created between the
                # title's previous loaded release and this one; that window
                # can attribute the creation. The stored column stays NULL —
                # the schema ties it to `from_version_id` — and
                # `--reattribute` re-derives the same departure from the
                # title's load history.
                departing = None
                departing_id = _latest_load_before(loads, group.first_seq)
                if departing_id is not None:
                    departing = releases[departing_id]
                from_credit = None
            else:
                text_changed = group.text_hash != prev.text_hash
                notes_changed = (group.notes_hash != prev.notes_hash) or (
                    _squash(group.source_credit) != _squash(prev.source_credit)
                )
                change_kind = (
                    "text" if text_changed else "notes" if notes_changed else "structure"
                )
                heading_changed = _collapse(group.heading) != _collapse(prev.heading)
                status_changed = (group.status or None) != (prev.status or None)
                concurrent = prev.last_seq > group.first_seq
                window_from_id = prev.last_release_id
                departing = releases[window_from_id]
                from_credit = prev.source_credit

            attribution, laws = _attribute(
                section_cls, departing, arriving, from_credit, group.source_credit
            )
            change = SectionVersionChange(
                section_id=section_id,
                to_version_id=group.version_id,
                from_version_id=prev.version_id if prev else None,
                window_from_release_id=window_from_id,
                window_to_release_id=group.first_release_id,
                change_kind=change_kind,
                text_changed=text_changed,
                notes_changed=notes_changed,
                heading_changed=heading_changed,
                status_changed=status_changed,
                concurrent=concurrent,
                attribution=attribution,
                computed_at=now,
            )
            session.add(change)
            pending.append((change, laws))
            prev = group

    session.flush()
    for change, laws in pending:
        stats.changes += 1
        for (congress, num), law in sorted(laws.items()):
            session.add(
                SectionVersionChangeLaw(
                    change_id=change.id,
                    pl_congress=congress,
                    pl_num=num,
                    in_classification=law.in_classification,
                    is_note_classification=law.in_classification and law.note_only,
                    in_source_credit=law.in_source_credit,
                    classification_actions=sorted(law.actions),
                )
            )
            stats.laws += 1
    session.flush()
    return stats


# ------------------------------------------------------------------- CLI runs


def _title_ids(session: Session, titles: Sequence[str] | None) -> list[tuple[int, str]]:
    rows = session.execute(select(Title.id, Title.num)).all()
    if titles is not None:
        wanted = set(titles)
        rows = [row for row in rows if row.num in wanted]
    from storage.postgres import title_sort_key  # the documented sorter (gotcha 16)

    return sorted(((row.id, row.num) for row in rows), key=lambda r: title_sort_key(r[1]))


def _complete_section_ids(session: Session, title_id: int) -> set[int]:
    """Sections whose change rows already cover every version group — the
    resume skip: a new version group breaks the count equality."""
    version_counts = dict(
        session.execute(
            select(SectionVersion.section_id, func.count())
            .join(Section, Section.id == SectionVersion.section_id)
            .where(Section.title_id == title_id)
            .group_by(SectionVersion.section_id)
        ).all()
    )
    change_counts = dict(
        session.execute(
            select(SectionVersionChange.section_id, func.count())
            .join(Section, Section.id == SectionVersionChange.section_id)
            .where(Section.title_id == title_id)
            .group_by(SectionVersionChange.section_id)
        ).all()
    )
    return {
        section_id
        for section_id, count in version_counts.items()
        if change_counts.get(section_id) == count
    }


def run_compute(
    session_factory,
    *,
    titles: Sequence[str] | None = None,
    recompute: bool = False,
    on_event: OnEvent = None,
) -> ComputeStats:
    """Compute change rows for the whole corpus (or `titles`), resumably.

    Per-title batches with a commit per `SECTION_BATCH` sections; sections
    whose newest group already has a change row are skipped unless
    `recompute`. Safe to interrupt — the database is the state.
    """
    total = ComputeStats()
    started = time.monotonic()
    with session_factory() as session:
        title_rows = _title_ids(session, titles)
        releases = _release_facts(session)

    for title_id, title_num in title_rows:
        with session_factory() as session:
            section_ids = session.scalars(
                select(Section.id).where(Section.title_id == title_id).order_by(Section.id)
            ).all()
            done = set() if recompute else _complete_section_ids(session, title_id)
        todo = [sid for sid in section_ids if sid not in done]
        total.skipped += len(section_ids) - len(todo)
        if not todo:
            if on_event:
                on_event(f"title {title_num}: all {len(section_ids)} sections computed")
            continue
        title_stats = ComputeStats()
        for start in range(0, len(todo), SECTION_BATCH):
            batch = todo[start : start + SECTION_BATCH]
            with session_factory() as session:
                stats = compute_for_sections(
                    session, batch, releases=releases, on_event=on_event
                )
                session.commit()
            title_stats.add(stats)
        total.add(title_stats)
        if on_event:
            on_event(
                f"title {title_num}: {title_stats.sections} sections, "
                f"{title_stats.changes} change rows, {title_stats.laws} law rows, "
                f"{title_stats.hashes_computed} hashes computed "
                f"({time.monotonic() - started:.0f}s elapsed)"
            )
    return total


def run_reattribute(
    session_factory,
    *,
    titles: Sequence[str] | None = None,
    on_event: OnEvent = None,
) -> ComputeStats:
    """Recompute attribution only: the `attribution` column and the law child
    rows, never the content flags. What the classification poll path runs
    after a table changes — no XML is parsed, so this is minutes, not hours.
    """
    total = ComputeStats()
    with session_factory() as session:
        title_rows = _title_ids(session, titles)
        releases = _release_facts(session)

    for title_id, title_num in title_rows:
        with session_factory() as session:
            section_ids = session.scalars(
                select(SectionVersionChange.section_id)
                .join(Section, Section.id == SectionVersionChange.section_id)
                .where(Section.title_id == title_id)
                .distinct()
                .order_by(SectionVersionChange.section_id)
            ).all()
        for start in range(0, len(section_ids), SECTION_BATCH):
            batch = section_ids[start : start + SECTION_BATCH]
            with session_factory() as session:
                stats = _reattribute_sections(session, batch, releases)
                session.commit()
            total.add(stats)
        if on_event and section_ids:
            on_event(f"title {title_num}: reattributed {len(section_ids)} sections")
    return total


def _reattribute_sections(
    session: Session, section_ids: Sequence[int], releases: dict[int, ReleaseFacts]
) -> ComputeStats:
    stats = ComputeStats()
    sections = session.execute(
        select(Section.id, Section.identifier, Section.title_id).where(
            Section.id.in_(section_ids)
        )
    ).all()
    identifiers = {row.id: row.identifier for row in sections}
    cls_rows = _classification_rows(session, identifiers)
    title_loads: dict[int, list[tuple[int, int]]] = {}
    for row in sections:
        if row.title_id not in title_loads:
            title_loads[row.title_id] = _title_load_seqs(session, row.title_id)
    title_of = {row.id: row.title_id for row in sections}

    credit_of: dict[int | None, str | None] = {None: None}
    changes = session.scalars(
        select(SectionVersionChange).where(
            SectionVersionChange.section_id.in_(section_ids)
        )
    ).all()
    version_ids = {c.to_version_id for c in changes} | {
        c.from_version_id for c in changes if c.from_version_id is not None
    }
    if version_ids:
        credit_of.update(
            session.execute(
                select(SectionVersion.id, SectionVersion.source_credit).where(
                    SectionVersion.id.in_(version_ids)
                )
            ).all()
        )

    session.execute(
        delete(SectionVersionChangeLaw).where(
            SectionVersionChangeLaw.change_id.in_([c.id for c in changes])
        )
    )
    for change in changes:
        stats.changes += 1
        arriving = releases[change.window_to_release_id]
        if change.window_from_release_id is not None:
            departing = releases[change.window_from_release_id]
        else:
            loads = title_loads[title_of[change.section_id]]
            departing_id = _latest_load_before(loads, arriving.seq)
            departing = releases[departing_id] if departing_id is not None else None
        attribution, laws = _attribute(
            cls_rows.get(change.section_id, ()),
            departing,
            arriving,
            credit_of.get(change.from_version_id),
            credit_of.get(change.to_version_id),
        )
        change.attribution = attribution
        for (congress, num), law in sorted(laws.items()):
            session.add(
                SectionVersionChangeLaw(
                    change_id=change.id,
                    pl_congress=congress,
                    pl_num=num,
                    in_classification=law.in_classification,
                    is_note_classification=law.in_classification and law.note_only,
                    in_source_credit=law.in_source_credit,
                    classification_actions=sorted(law.actions),
                )
            )
            stats.laws += 1
    stats.sections = len(sections)
    session.flush()
    return stats


# -------------------------------------------------------------------- report


def build_report(session: Session) -> dict:
    """Corpus-wide totals from the stored change rows — the § What was
    measured table's prediction, reproduced rather than sampled."""
    kind_counts = dict(
        session.execute(
            select(SectionVersionChange.change_kind, func.count()).group_by(
                SectionVersionChange.change_kind
            )
        ).all()
    )
    transitions = sum(v for k, v in kind_counts.items() if k != "initial")
    text_total = kind_counts.get("text", 0)
    text_classified = session.scalar(
        select(func.count()).where(
            SectionVersionChange.change_kind == "text",
            SectionVersionChange.attribution == "classified",
        )
    )
    concurrent = session.scalar(
        select(func.count()).where(SectionVersionChange.concurrent.is_(True))
    )
    law_rows = session.scalar(select(func.count()).select_from(SectionVersionChangeLaw))
    sections_covered = session.scalar(
        select(func.count(func.distinct(SectionVersionChange.section_id)))
    )
    versions_hashed = session.scalar(
        select(func.count()).where(SectionVersion.text_hash.is_not(None))
    )
    versions_total = session.scalar(select(func.count()).select_from(SectionVersion))

    per_title_rows = session.execute(
        select(
            Title.num,
            SectionVersionChange.change_kind,
            func.count(),
        )
        .select_from(SectionVersionChange)
        .join(Section, Section.id == SectionVersionChange.section_id)
        .join(Title, Title.id == Section.title_id)
        .group_by(Title.num, SectionVersionChange.change_kind)
    ).all()
    classified_by_title = dict(
        session.execute(
            select(Title.num, func.count())
            .select_from(SectionVersionChange)
            .join(Section, Section.id == SectionVersionChange.section_id)
            .join(Title, Title.id == Section.title_id)
            .where(
                SectionVersionChange.change_kind == "text",
                SectionVersionChange.attribution == "classified",
            )
            .group_by(Title.num)
        ).all()
    )
    per_title: dict[str, dict] = {}
    for num, kind, count in per_title_rows:
        per_title.setdefault(num, {"by_kind": {}})["by_kind"][kind] = count
    for num, entry in per_title.items():
        text = entry["by_kind"].get("text", 0)
        classified = classified_by_title.get(num, 0)
        entry["text_classified"] = classified
        entry["text_classified_share"] = round(classified / text, 4) if text else None

    from storage.postgres import title_sort_key

    def share(count: int) -> float | None:
        return round(count / transitions, 4) if transitions else None

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sections_covered": sections_covered,
        "version_groups_hashed": versions_hashed,
        "version_groups_total": versions_total,
        "change_rows": sum(kind_counts.values()),
        "transitions": transitions,
        "by_kind": {
            kind: {"count": count, "share": share(count) if kind != "initial" else None}
            for kind, count in sorted(kind_counts.items())
        },
        "text_classified": text_classified,
        "text_classified_share": (
            round(text_classified / text_total, 4) if text_total else None
        ),
        "concurrent": concurrent,
        "law_rows": law_rows,
        "per_title": {
            num: per_title[num]
            for num in sorted(per_title, key=title_sort_key)
        },
    }


def write_report(session: Session, directory: Path = VERIFICATION_DIR) -> Path:
    report = build_report(session)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / REPORT_NAME
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path
