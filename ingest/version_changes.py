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
backfill recovers missing hashes through `parser_for_namespace` and the
parser's `plain_text()`/`notes_text()`.
"""

from __future__ import annotations

import datetime
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence, TypeVar

from lxml import etree
from sqlalchemy import bindparam, delete, func, select, update
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
from ingest.classification import PL_CITATION_RE
from ingest.parser import parser_for_namespace
from ingest.records import notes_hash_of, squash, text_hash_of
from ingest.verification import VERIFICATION_DIR, write_verification_json
from storage.classification import identifier_variants

REPORT_NAME = "version-changes.json"

SECTION_BATCH = 200
"""Sections per transaction. Each section's fragments are parsed one at a time
(gotcha 6); the batch only bounds how much bookkeeping a commit covers."""

HASH_UPDATE_BATCH = 200
"""Computed hashes buffered before one executemany UPDATE — the hash values,
never the fragments, which stream one at a time."""

ID_CHUNK = 5_000
"""Ids per `IN (...)`. Postgres refuses a statement carrying more than 65,535
bind parameters, and the id lists here are per-title: Title 42's 136,213
version groups are one hash backfill and would exceed it on their own."""

OnEvent = Callable[[str], None] | None

_T = TypeVar("_T")


def _chunked(values: Sequence[_T], size: int = ID_CHUNK) -> Iterable[Sequence[_T]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


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
    """The `Pub. L. C-N` citations a source credit carries, as (congress, num).

    Read through `ingest.classification.PL_CITATION_RE` — one pattern owns the
    citation shape, and it is dash-tolerant because the corpus writes source
    credits with an EN DASH (gotcha 17) while the ECCT writes a hyphen.
    """
    if not source_credit:
        return frozenset()
    return frozenset(
        (int(c), int(n)) for c, n in PL_CITATION_RE.findall(source_credit)
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
    """One law attributed to a transition, as the two signals found it.

    Both classification flags are positive statements about what was found —
    `note_classification` and `text_classification` — so a law nothing
    classified is simply neither, and no consumer has to remember that a
    default means "unknown".
    """

    note_classification: bool = False
    text_classification: bool = False
    in_source_credit: bool = False
    actions: set[str] = field(default_factory=set)

    @property
    def in_classification(self) -> bool:
        return self.note_classification or self.text_classification

    @property
    def is_note_classification(self) -> bool:
        """Only note rows name this law — worth showing as such against a text
        transition."""
        return self.note_classification and not self.text_classification


@dataclass(slots=True)
class ComputeStats:
    sections: int = 0
    skipped: int = 0
    changes: int = 0
    laws: int = 0
    hashes_computed: int = 0
    mapless_versions: int = 0
    """Version groups no release maps, which only a manual deletion produces
    (0 corpus-wide, measured). Counted rather than passed over: their release
    range is invented from `first_release_id` and their neighbours' windows
    rest on it."""

    def add(self, other: "ComputeStats") -> None:
        self.sections += other.sections
        self.skipped += other.skipped
        self.changes += other.changes
        self.laws += other.laws
        self.hashes_computed += other.hashes_computed
        self.mapless_versions += other.mapless_versions


def _ensure_hashes(session: Session, version_ids: Iterable[int]) -> int:
    """Fill `text_hash`/`notes_hash` on versions that lack them.

    One fragment in memory at a time: the rows stream through a server-side
    cursor (`yield_per`), each fragment is encoded once, parsed once — the
    parser chosen from the parsed root's own namespace, so nothing re-reads
    the bytes — and released before the next (gotcha 6: Title 42 fragments
    run to hundreds of KB and a section can hold 400 versions). The computed
    hashes are 64 bytes a row and are flushed as one executemany UPDATE per
    `HASH_UPDATE_BATCH`.
    """
    ids = list(version_ids)
    if not ids:
        return 0
    computed = 0
    updates: list[dict[str, object]] = []
    for chunk in _chunked(ids):
        rows = session.execute(
            select(SectionVersion.id, SectionVersion.xml)
            .where(SectionVersion.id.in_(chunk))
            .execution_options(yield_per=50)
        )
        for row in rows:
            root = etree.fromstring(row.xml.encode("utf-8"))
            parser = parser_for_namespace(etree.QName(root).namespace)
            updates.append(
                {
                    "b_id": row.id,
                    "b_text": text_hash_of(parser.plain_text(root)),
                    "b_notes": notes_hash_of(parser.notes_text(root)),
                }
            )
            computed += 1
            if len(updates) >= HASH_UPDATE_BATCH:
                _flush_hash_updates(session, updates)
    _flush_hash_updates(session, updates)
    return computed


def _flush_hash_updates(session: Session, updates: list[dict[str, object]]) -> None:
    if not updates:
        return
    # On the Core connection, not the ORM session: nothing holds these rows as
    # ORM instances, and Session.execute would read an executemany UPDATE as
    # "bulk update by primary key" and demand the key under its own name.
    session.connection().execute(
        update(SectionVersion.__table__)
        .where(SectionVersion.__table__.c.id == bindparam("b_id"))
        .values(text_hash=bindparam("b_text"), notes_hash=bindparam("b_notes")),
        updates,
    )
    updates.clear()


def _groups_for_sections(
    session: Session, section_ids: Sequence[int], releases: dict[int, ReleaseFacts]
) -> tuple[dict[int, list[_Group]], int]:
    """Every section's version groups, ordered by earliest mapped release, and
    a count of the groups no release maps.

    A version no release maps to (which only a manual deletion produces — 0
    corpus-wide) falls back to its own `first_release_id` for both ends rather
    than being dropped, since dropping it would silently shift every later
    transition's departure. The invented range is a fact about the database
    rather than about the Code, so it is counted and reported instead of being
    passed over in silence.
    """
    seq_of = {facts.id: facts.seq for facts in releases.values()}
    release_at_seq = {facts.seq: facts.id for facts in releases.values()}

    ranges: dict[int, tuple[int, int]] = {}
    for chunk in _chunked(section_ids):
        ranges.update(
            (vid, (lo, hi))
            for vid, lo, hi in session.execute(
                select(
                    SectionReleaseMap.section_version_id,
                    func.min(ReleasePoint.seq),
                    func.max(ReleasePoint.seq),
                )
                .join(ReleasePoint, ReleasePoint.id == SectionReleaseMap.release_id)
                .where(SectionReleaseMap.section_version_id.in_(
                    select(SectionVersion.id).where(SectionVersion.section_id.in_(chunk))
                ))
                .group_by(SectionReleaseMap.section_version_id)
            )
        )

    mapless = 0
    grouped: dict[int, list[_Group]] = {sid: [] for sid in section_ids}
    version_rows = [
        row
        for chunk in _chunked(section_ids)
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
            ).where(SectionVersion.section_id.in_(chunk))
        )
    ]
    for row in version_rows:
        span = ranges.get(row.id)
        if span is None:
            mapless += 1
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
    return grouped, mapless


def _window_is_unreliable(
    groups: Sequence[_Group], index: int, departing: _Group
) -> bool:
    """Whether the transition into `groups[index]` spans an era of some third
    group — the `concurrent` test.

    Two shapes, one meaning: the window arithmetic cannot be trusted here.

      * The departing group is still mapped at or after the arriving group's
        first release. Equality is the ADR-0021 case — the source published
        several elements under one identifier at one release point.
      * Some *other* group is mapped inside the window. Content that recurs
        (a converter serialization flip-flop, or a genuine revert) maps a
        later run of releases to an earlier group, so the interval between a
        departure and an arrival can cover releases where a third group's text
        was the one in force. Only the first transition of such a pair used to
        be flagged, and the successor's window silently ran across the revert
        era.
    """
    arriving = groups[index]
    if departing.last_seq >= arriving.first_seq:
        return True
    lo, hi = departing.last_seq, arriving.first_seq
    return any(
        other.first_seq <= hi and other.last_seq >= lo
        for position, other in enumerate(groups)
        if position != index and other.version_id != departing.version_id
    )


@dataclass(slots=True)
class _SectionContext:
    """What both compute paths need to know about a batch of sections: which
    classification rows name each one, and where its title's completed loads
    fall (the departing end of a mid-corpus `initial` window)."""

    classification: dict[int, list[tuple[int, int, bool, str]]]
    title_loads: dict[int, list[tuple[int, int]]]
    title_of: dict[int, int]
    section_ids: list[int]

    def rows(self, section_id: int) -> Sequence[tuple[int, int, bool, str]]:
        return self.classification.get(section_id, ())

    def loads(self, section_id: int) -> Sequence[tuple[int, int]]:
        return self.title_loads[self.title_of[section_id]]

    def initial_departure(
        self, section_id: int, arriving_seq: int, releases: dict[int, ReleaseFacts]
    ) -> ReleaseFacts | None:
        """The release a first group's window departs from — the title's newest
        completed load below the arrival. A section present at the title's
        earliest loaded release gets none: an unbounded window would attribute
        every law ever enacted."""
        departing_id = _latest_load_before(self.loads(section_id), arriving_seq)
        return releases[departing_id] if departing_id is not None else None


def _section_context(session: Session, section_ids: Sequence[int]) -> _SectionContext:
    sections = [
        row
        for chunk in _chunked(section_ids)
        for row in session.execute(
            select(Section.id, Section.identifier, Section.title_id).where(
                Section.id.in_(chunk)
            )
        )
    ]
    title_loads: dict[int, list[tuple[int, int]]] = {}
    for row in sections:
        if row.title_id not in title_loads:
            title_loads[row.title_id] = _title_load_seqs(session, row.title_id)
    return _SectionContext(
        classification=_classification_rows(
            session, {row.id: row.identifier for row in sections}
        ),
        title_loads=title_loads,
        title_of={row.id: row.title_id for row in sections},
        section_ids=[row.id for row in sections],
    )


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
    variants = list(variant_to_section)
    for chunk in _chunked(variants):
        for row in session.execute(
            select(
                ClassificationEntry.usc_identifier,
                ClassificationEntry.pl_congress,
                ClassificationEntry.pl_num,
                ClassificationEntry.is_note,
                ClassificationEntry.action,
            ).where(
                ClassificationEntry.usc_identifier.in_(chunk),
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
        if is_note:
            law.note_classification = True
        else:
            law.text_classification = True
        law.actions.add(action)

    for congress, num in credit_laws(to_credit) - credit_laws(from_credit):
        if not law_in_window(departing, arriving, congress, num):
            continue
        laws.setdefault((congress, num), _Law()).in_source_credit = True

    classified = any(law.text_classification for law in laws.values())
    return ("classified" if classified else "none"), laws


def _insert_law_rows(
    session: Session, change_id: int, laws: dict[tuple[int, int], _Law]
) -> int:
    """The `section_version_change_laws` rows for one transition, in law order.
    Both compute paths write them the same way."""
    for (congress, num), law in sorted(laws.items()):
        session.add(
            SectionVersionChangeLaw(
                change_id=change_id,
                pl_congress=congress,
                pl_num=num,
                in_classification=law.in_classification,
                is_note_classification=law.is_note_classification,
                in_source_credit=law.in_source_credit,
                classification_actions=sorted(law.actions),
            )
        )
    return len(laws)


def compute_for_sections(
    session: Session,
    section_ids: Sequence[int],
    *,
    on_event: OnEvent = None,
) -> ComputeStats:
    """Delete and re-insert change rows for `section_ids`. Flushes, never
    commits — the caller owns the transaction (the CLI commits per batch, the
    `load_release` hook commits with the load, tests roll back).

    The release facts are read here rather than passed in: a compute run is
    long and the daily poll can seed a new release point under it, which a
    snapshot taken once at the top would `KeyError` on.
    """
    stats = ComputeStats()
    if not section_ids:
        return stats
    releases = _release_facts(session)
    context = _section_context(session, section_ids)

    missing: list[int] = []
    for chunk in _chunked(list(section_ids)):
        missing.extend(
            session.scalars(
                select(SectionVersion.id).where(
                    SectionVersion.section_id.in_(chunk),
                    (SectionVersion.text_hash.is_(None))
                    | (SectionVersion.notes_hash.is_(None)),
                )
            )
        )
    stats.hashes_computed += _ensure_hashes(session, missing)

    grouped, stats.mapless_versions = _groups_for_sections(
        session, context.section_ids, releases
    )

    for chunk in _chunked(list(section_ids)):
        session.execute(
            delete(SectionVersionChange).where(SectionVersionChange.section_id.in_(chunk))
        )

    now = datetime.datetime.now(datetime.timezone.utc)
    pending: list[tuple[SectionVersionChange, dict[tuple[int, int], _Law]]] = []
    for section_id, groups in grouped.items():
        if not groups:
            continue
        stats.sections += 1
        section_cls = context.rows(section_id)
        prev: _Group | None = None
        for index, group in enumerate(groups):
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
                departing = context.initial_departure(
                    section_id, group.first_seq, releases
                )
                from_credit = None
            else:
                text_changed = group.text_hash != prev.text_hash
                notes_changed = (group.notes_hash != prev.notes_hash) or (
                    squash(group.source_credit) != squash(prev.source_credit)
                )
                change_kind = (
                    "text" if text_changed else "notes" if notes_changed else "structure"
                )
                # Whitespace-removed like every other comparison here, so a
                # converter-era boundary space inside a heading is not a
                # heading change (ADR-0074 notes the deviation from the
                # spec's "whitespace-collapsed" wording).
                heading_changed = squash(group.heading) != squash(prev.heading)
                status_changed = (group.status or None) != (prev.status or None)
                concurrent = _window_is_unreliable(groups, index, prev)
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
        stats.laws += _insert_law_rows(session, change.id, laws)
    session.flush()
    if stats.mapless_versions and on_event:
        on_event(
            f"WARNING: {stats.mapless_versions:,} version groups that no release "
            "maps; their release range is taken from `first_release_id` and "
            "their neighbours' windows rest on it"
        )
    return stats


def compute_in_batches(
    session: Session,
    section_ids: Sequence[int],
    *,
    batch_size: int = SECTION_BATCH,
    on_event: OnEvent = None,
) -> ComputeStats:
    """`compute_for_sections` in committed batches over one session.

    What a caller that already owns a session uses for a set larger than a
    batch — the `load_release` hook. One transaction per batch, so a failure
    part-way leaves the batches before it committed rather than rolling the
    whole title back, and no statement carries an unbounded `IN (...)`.
    """
    total = ComputeStats()
    ids = list(section_ids)
    for batch in _chunked(ids, batch_size):
        total.add(compute_for_sections(session, batch, on_event=on_event))
        session.commit()
    return total


# -------------------------------------------------------- the incremental hook


def sections_needing_recompute(
    session: Session,
    *,
    title_id: int,
    release_id: int,
    mapped_versions: dict[int, set[int]],
    new_version_sections: set[int],
) -> set[int]:
    """Which of a load's sections can actually have different change rows.

    A release point republishes every title, so a load maps nearly every
    section of it — 91% of them to the version group they were already on
    (ADR-0007). Recomputing all of them costs a whole-title pass per load (27s
    for Title 42, measured), and for all but a few it rewrites the rows it just
    deleted. A section is in the set when:

      1. it gained a new version group at this release;
      2. it has a version group no change row covers — what an interrupted
         earlier load leaves, and what a corpus loaded before ADR-0074 is
         entirely made of;
      3. the group it maps to here is not the group it mapped to at the
         title's previous completed load — it moved, so both windows move;
      4. that group departs into a successor (some change row names it as
         `from_version_id`). Extending the range of a group that is not the
         section's last one moves its successor's window: the recurrence case
         ADR-0074 records, where content comes back and a later release maps
         to an earlier group.

    Everything else gains a release at the top of its last group's range,
    which no window reads.

    **A load that is not the title's newest returns every section of the
    title.** Inserting a release below the top can lower a group's first
    mapped release (which reorders the groups), and it joins the title's load
    history, which is where a mid-corpus `initial` window departs from — for
    sections this load never touched.
    """
    if not mapped_versions:
        return set()
    loads = _title_load_seqs(session, title_id)
    release_seq = next((seq for seq, rid in loads if rid == release_id), None)
    is_newest = release_seq is not None and release_seq == loads[-1][0]
    if not is_newest:
        return set(
            session.scalars(select(Section.id).where(Section.title_id == title_id))
        )

    need = set(new_version_sections)
    section_ids = list(mapped_versions)
    version_ids = sorted({vid for group in mapped_versions.values() for vid in group})

    for chunk in _chunked(section_ids):
        need.update(
            session.scalars(
                select(SectionVersion.section_id)
                .outerjoin(
                    SectionVersionChange,
                    SectionVersionChange.to_version_id == SectionVersion.id,
                )
                .where(
                    SectionVersion.section_id.in_(chunk),
                    SectionVersionChange.id.is_(None),
                )
                .distinct()
            )
        )

    previous_id = _latest_load_before(loads, release_seq)
    previous: dict[int, set[int]] = {}
    if previous_id is not None:
        for section_id, version_id in session.execute(
            select(SectionVersion.section_id, SectionReleaseMap.section_version_id)
            .join(
                SectionVersion,
                SectionVersion.id == SectionReleaseMap.section_version_id,
            )
            .join(Section, Section.id == SectionVersion.section_id)
            .where(
                Section.title_id == title_id,
                SectionReleaseMap.release_id == previous_id,
            )
        ):
            previous.setdefault(section_id, set()).add(version_id)
    need.update(
        section_id
        for section_id, versions in mapped_versions.items()
        if previous.get(section_id, set()) != versions
    )

    for chunk in _chunked(version_ids):
        need.update(
            session.scalars(
                select(SectionVersionChange.section_id)
                .where(SectionVersionChange.from_version_id.in_(chunk))
                .distinct()
            )
        )
    return need


def clear_change_rows(session: Session, section_ids: Sequence[int]) -> int:
    """Delete every change row of `section_ids` and commit.

    What a failed incremental hook leaves behind, so the failure survives the
    process that printed the warning. The resume skip is a count equality
    (`_complete_section_ids`), which cannot see a *stale* row — but it can see
    a missing one, so a section with no rows is recomputed by the next
    `version-changes` run, the next load that touches it, or the repair pass
    `deploy/update-corpus.sh` runs after every load. Deleting rows to record a
    failure is safe because they are derived: `--recompute` rebuilds any of
    them from the corpus at any time.
    """
    removed = 0
    for chunk in _chunked(list(section_ids)):
        result = session.execute(
            delete(SectionVersionChange).where(SectionVersionChange.section_id.in_(chunk))
        )
        removed += result.rowcount or 0
    session.commit()
    return removed


# ------------------------------------------------------------------- CLI runs


class UnknownTitleError(ValueError):
    """`--title` named something no loaded title answers to. Raised rather than
    silently selecting nothing: `--title 42a` is a typo, and a run that does
    nothing and exits 0 reads exactly like a run that had nothing to do."""


def _title_ids(session: Session, titles: Sequence[str] | None) -> list[tuple[int, str]]:
    rows = session.execute(select(Title.id, Title.num)).all()
    if titles is not None:
        wanted = set(titles)
        unknown = sorted(wanted - {row.num for row in rows})
        if unknown:
            raise UnknownTitleError(
                f"no loaded title numbered {', '.join(unknown)} "
                "(titles are the URL form — `5a`, not `05a`)"
            )
        rows = [row for row in rows if row.num in wanted]
    from storage.postgres import title_sort_key  # the documented sorter (gotcha 16)

    return sorted(((row.id, row.num) for row in rows), key=lambda r: title_sort_key(r[1]))


def _classification_tables_are_empty(session: Session) -> bool:
    return session.scalar(select(ClassificationEntry.id).limit(1)) is None


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

    Per-title batches with a commit per `SECTION_BATCH` sections; a section
    whose change rows already number its version groups is skipped unless
    `recompute` (`_complete_section_ids` — the count equality, not "the newest
    group has a row"). Safe to interrupt: the database is the state.

    **A section computed before the classification tables were loaded is one
    of the skipped.** Its rows are complete and its attribution is `none`,
    which is indistinguishable from a text change no statute is recorded for.
    The run says so when the tables are empty; `--reattribute` is the repair
    and parses no XML.
    """
    total = ComputeStats()
    started = time.monotonic()
    with session_factory() as session:
        title_rows = _title_ids(session, titles)
        if _classification_tables_are_empty(session):
            warning = (
                "WARNING: classification_entries is empty — every transition "
                "computed by this run will be attributed `none`. Load the tables "
                "(`python -m ingest classification`) and then "
                "`version-changes --reattribute`; a plain re-run skips these "
                "sections as complete."
            )
            print(warning, file=sys.stderr)
            if on_event:
                on_event(warning)

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
                stats = compute_for_sections(session, batch, on_event=on_event)
                session.commit()
            title_stats.add(stats)
            if on_event and start and start % (SECTION_BATCH * 10) == 0:
                # Progress inside a title, not only after it: Title 42's 8,939
                # sections were one silent run.
                on_event(
                    f"title {title_num}: {title_stats.sections:,}/{len(todo):,} "
                    f"sections, {title_stats.changes:,} change rows "
                    f"({time.monotonic() - started:.0f}s elapsed)"
                )
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
                stats = _reattribute_sections(session, batch, _release_facts(session))
                session.commit()
            total.add(stats)
        if on_event and section_ids:
            on_event(f"title {title_num}: reattributed {len(section_ids)} sections")
    return total


def _reattribute_sections(
    session: Session, section_ids: Sequence[int], releases: dict[int, ReleaseFacts]
) -> ComputeStats:
    stats = ComputeStats()
    context = _section_context(session, section_ids)

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
            departing = context.initial_departure(
                change.section_id, arriving.seq, releases
            )
        attribution, laws = _attribute(
            context.rows(change.section_id),
            departing,
            arriving,
            credit_of.get(change.from_version_id),
            credit_of.get(change.to_version_id),
        )
        change.attribution = attribution
        stats.laws += _insert_law_rows(session, change.id, laws)
    stats.sections = len(context.section_ids)
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
    """The artifact, always corpus-wide.

    `--title` bounds what a run *computes*, never what the report counts: the
    numbers are read from the stored rows, so a report taken after a
    single-title run describes the whole corpus as it then stands, with
    `sections_covered` saying how much of it has been computed at all.
    """
    return write_verification_json(build_report(session), REPORT_NAME, directory)
