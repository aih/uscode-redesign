"""Update a release point section by section, from the classification tables.

The release-point path (`backfill` → `load-all`) loads every title OLRC marks as
changed at a release point from that title's zip. This module is a second path
for when the source does not offer those files (ADR-0095). For a release point
already in `release_points`:

1. **Plan, law by law.** Each title's base is its newest completed load before
   the release point. The laws in the window — incorporated at the release
   point and not at the base, by ADR-0074's `law_in_window` — are looked up in
   the classification tables (ADR-0067) and the ECCT, and every row naming a
   section of the title for one of them sends that section to be fetched. A law
   the loaded tables do not cover stops the plan: a table that has not reached
   a law cannot say which sections it changed.
2. **Fetch only those sections** from a `SectionSource`.
3. **Assemble the title at the release point.** Fetched sections are stored
   through the loader's own `VersionStore` (content-hash dedupe, ADR-0007);
   every other section is mapped to the version it had at the base, in the
   base's reading order, with a new section placed after its nearest preceding
   neighbour by section number. The `title_versions` row says
   `load_method='sections'` and names its base, and `sections_loaded` is
   stamped last, so an interrupted update is inert (ADR-0082).
4. **Record what each law did.** One `section_update_items` row per (section,
   law): the row that named it and what the fetch found.

The title's file, if it arrives later, replaces the assembled load
(`ingest.load._get_or_create_title_version`, `load_all.completed_pairs`).

Ingest-side code: it writes `db.models` directly (architecture rule 1 governs
`api/`). It names no USLM element: a fetched document is read by the parser its
namespace selects.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from lxml import etree
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from db.models import (
    ClassificationEntry,
    ClassificationFile,
    EcctEntry,
    ReleasePoint,
    Section,
    SectionReleaseMap,
    SectionUpdateItem,
    SectionVersion,
    Title,
    TitleVersion,
)
from ingest.classification import derive_usc_identifier
from ingest.detect import UnknownUslmSchemaError
from ingest.download import throttle
from ingest.inventory import USER_AGENT
from ingest.load import (
    GUID_BATCH_SIZE,
    SECTIONS_METHOD,
    VersionStore,
    _flush_guid_rows,
    _KnownVersion,
    _unmap_title_release,
    known_versions_statement,
    recompute_version_changes,
)
from ingest.parser import parser_for
from ingest.records import SectionRecord
from ingest.version_changes import ReleaseFacts, law_in_window
from storage.classification import identifier_variants

SECTION_URL_ENV = "USC_SECTION_URL"
"""Environment variable holding the per-section URL template, when
`--section-url` is not given."""

MAP_BATCH = 1_000
"""`section_release_map` rows per INSERT."""

OnEvent = Callable[[str], None] | None

# Outcomes recorded on `section_update_items.outcome`.
NEW_VERSION = "new-version"
UNCHANGED = "unchanged"
NEW_SECTION = "new-section"
NOT_FOUND = "not-found"

# `section_update_items.basis`.
CLASSIFICATION = "classification"
ECCT = "ecct"


class SectionUpdateError(ValueError):
    """The update cannot be planned or applied as asked."""


# ------------------------------------------------------------------ planning


@dataclass(frozen=True, slots=True)
class Reason:
    """One table row that sends a section to be fetched."""

    basis: str
    pl_congress: int
    pl_num: int
    action: str | None
    is_note: bool

    @property
    def law(self) -> str:
        return f"{self.pl_congress}-{self.pl_num}"


@dataclass
class TitlePlan:
    """What the update does to one title."""

    title_id: int
    title_num: str
    status: str
    """`ready` (sections to fetch), `unchanged` (no row names a section of the
    title for a law in its window), `loaded` (the title is already complete at
    the release point) or `no-base` (no completed load before it)."""

    base: ReleaseFacts | None = None
    sections: dict[str, list[Reason]] = field(default_factory=dict)
    """Identifier → the rows naming it, in identifier order."""

    unresolved: list[str] = field(default_factory=list)
    """Rows for a law in the window that derive no identifier (appendix rows,
    ranges), as `law: title/section`."""

    @property
    def laws(self) -> list[tuple[int, int]]:
        return sorted(
            {(r.pl_congress, r.pl_num) for reasons in self.sections.values() for r in reasons}
        )


@dataclass
class UpdatePlan:
    target: ReleaseFacts
    window_laws: list[tuple[int, int]]
    """Every law incorporated at the target and not at the oldest base."""
    uncovered_laws: list[tuple[int, int]]
    """Laws in the window no loaded classification table covers."""
    laws_without_rows: list[tuple[int, int]]
    """Covered laws in the window that classified nothing to any section."""
    titles: list[TitlePlan]

    @property
    def ok(self) -> bool:
        return not self.uncovered_laws

    @property
    def ready(self) -> list[TitlePlan]:
        return [t for t in self.titles if t.status == "ready"]

    def as_json(self) -> dict[str, Any]:
        def law(c: int, n: int) -> str:
            return f"{c}-{n}"

        return {
            "release": self.target.label,
            "window_laws": [law(*x) for x in self.window_laws],
            "uncovered_laws": [law(*x) for x in self.uncovered_laws],
            "laws_without_rows": [law(*x) for x in self.laws_without_rows],
            "titles": [
                {
                    "title": t.title_num,
                    "status": t.status,
                    "base": t.base.label if t.base else None,
                    "laws": [law(*x) for x in t.laws],
                    "sections": {
                        identifier: sorted({r.law for r in reasons})
                        for identifier, reasons in t.sections.items()
                    },
                    "unresolved": t.unresolved,
                }
                for t in self.titles
                if t.status != "unchanged"
            ],
        }


def _facts(row: ReleasePoint) -> ReleaseFacts:
    return ReleaseFacts(
        id=row.id,
        seq=row.seq,
        label=row.label,
        congress=row.congress,
        law_num=row.law_num,
        excluded=frozenset(row.excluded_laws or ()),
    )


def window_laws(
    base: ReleaseFacts, target: ReleaseFacts, last_law: dict[int, int]
) -> list[tuple[int, int]]:
    """Every law incorporated at `target` and not at `base`.

    A congress before the target's is enumerated up to the highest law number
    `last_law` knows for it (the classification tables' coverage), since a
    release point names only its own congress's last law.
    """
    laws: list[tuple[int, int]] = []
    for congress in range(base.congress, target.congress + 1):
        top = target.law_num if congress == target.congress else last_law.get(congress, 0)
        for num in range(1, top + 1):
            if law_in_window(base, target, congress, num):
                laws.append((congress, num))
    return laws


def _coverage(session: Session) -> dict[int, list[tuple[int, int]]]:
    """Congress → the law ranges the loaded Public Law tables cover."""
    ranges: dict[int, list[tuple[int, int]]] = {}
    for congress, segments in session.execute(
        select(ClassificationFile.congress, ClassificationFile.covered_ranges).where(
            ClassificationFile.kind == "pl"
        )
    ):
        for segment in segments or ():
            first, _, last = segment.partition("-")
            ranges.setdefault(congress, []).append((int(first), int(last or first)))
    return ranges


def is_covered(ranges: dict[int, list[tuple[int, int]]], congress: int, num: int) -> bool:
    return any(first <= num <= last for first, last in ranges.get(congress, ()))


def _completed_loads(session: Session, title_ids: Sequence[int]) -> dict[int, list[tuple[int, int]]]:
    """Title id → (seq, release id) of every completed load, ascending."""
    loads: dict[int, list[tuple[int, int]]] = {}
    for title_id, seq, release_id in session.execute(
        select(TitleVersion.title_id, ReleasePoint.seq, ReleasePoint.id)
        .join(ReleasePoint, ReleasePoint.id == TitleVersion.release_id)
        .where(
            TitleVersion.title_id.in_(title_ids),
            TitleVersion.sections_loaded.is_not(None),
        )
        .order_by(ReleasePoint.seq)
    ):
        loads.setdefault(title_id, []).append((seq, release_id))
    return loads


def plan_update(
    session: Session,
    label: str,
    *,
    titles: Sequence[str] | None = None,
    expected_only: bool = False,
) -> UpdatePlan:
    """Which sections of which titles the laws `label` adds name, per title.

    `expected_only` limits the plan to the titles the release point lists as
    changed (`release_points.titles_affected`), or every title when it lists
    none — what `deploy/update-corpus.sh` passes after `load-all`, so a title
    whose file loaded is `loaded` and one the source did not mark is left
    alone.
    """
    target_row = session.scalars(select(ReleasePoint).where(ReleasePoint.label == label)).first()
    if target_row is None:
        raise SectionUpdateError(
            f"release point {label!r} is not in release_points — run "
            "`python -m ingest check` (or `inventory`) first"
        )
    target = _facts(target_row)
    facts = {row.id: _facts(row) for row in session.scalars(select(ReleasePoint))}

    title_rows = session.execute(select(Title.id, Title.num)).all()
    if titles:
        wanted = {t.lower().lstrip("0") or "0" for t in titles}
        title_rows = [r for r in title_rows if r.num.lower().lstrip("0") in wanted]
        missing = wanted - {r.num.lower().lstrip("0") for r in title_rows}
        if missing:
            raise SectionUpdateError(f"no such title: {', '.join(sorted(missing))}")
    if expected_only and target_row.titles_affected:
        affected = {t.lower().lstrip("0") for t in target_row.titles_affected}
        title_rows = [r for r in title_rows if r.num.lower().lstrip("0") in affected]
    loads = _completed_loads(session, [r.id for r in title_rows])

    plans: list[TitlePlan] = []
    for row in sorted(title_rows, key=lambda r: _title_key(r.num)):
        title_loads = loads.get(row.id, [])
        if any(release_id == target.id for _seq, release_id in title_loads):
            plans.append(TitlePlan(row.id, row.num, "loaded"))
            continue
        before = [release_id for seq, release_id in title_loads if seq < target.seq]
        if not before:
            plans.append(TitlePlan(row.id, row.num, "no-base"))
            continue
        plans.append(TitlePlan(row.id, row.num, "unchanged", base=facts[before[-1]]))

    coverage = _coverage(session)
    last_law = {c: max(last for _f, last in segs) for c, segs in coverage.items() if segs}
    bases = [p.base for p in plans if p.base is not None]
    if not bases:
        return UpdatePlan(target, [], [], [], plans)
    oldest = min(bases, key=lambda b: b.seq)
    laws = window_laws(oldest, target, last_law)
    uncovered = [law for law in laws if not is_covered(coverage, *law)]

    reasons_by_title = _rows_for_laws(session, laws)
    named = {
        (reason.pl_congress, reason.pl_num)
        for rows in reasons_by_title.values()
        for _identifier, reason in rows
    }
    unresolved_by_title = _unresolved_rows(session, laws)

    by_num = {p.title_num.lower(): p for p in plans}
    existing = _existing_identifiers(session, [p.title_id for p in plans if p.base])
    for title_num, rows in reasons_by_title.items():
        plan = by_num.get(title_num)
        if plan is None or plan.base is None or plan.status != "unchanged":
            continue
        for identifier, reason in rows:
            if not law_in_window(plan.base, target, reason.pl_congress, reason.pl_num):
                continue
            identifier = existing.get(plan.title_id, {}).get(
                identifier.replace("–", "-"), identifier
            )
            plan.sections.setdefault(identifier, [])
            if reason not in plan.sections[identifier]:
                plan.sections[identifier].append(reason)
        if plan.sections:
            plan.status = "ready"
            plan.sections = dict(sorted(plan.sections.items()))
    for title_num, rows in unresolved_by_title.items():
        plan = by_num.get(title_num)
        if plan is None or plan.base is None:
            continue
        plan.unresolved = sorted(
            {
                f"{c}-{n}: {cell}"
                for c, n, cell in rows
                if law_in_window(plan.base, target, c, n)
            }
        )

    without_rows = [law for law in laws if law not in named and is_covered(coverage, *law)]
    return UpdatePlan(target, laws, uncovered, without_rows, plans)


def _title_key(num: str) -> tuple[int, str]:
    match = re.match(r"(\d+)(.*)", num)
    return (int(match.group(1)), match.group(2)) if match else (10_000, num)


def _rows_for_laws(
    session: Session, laws: Sequence[tuple[int, int]]
) -> dict[str, list[tuple[str, Reason]]]:
    """Title number → (identifier, reason) for every table row naming a section
    for one of `laws`, classification rows first and then the ECCT."""
    found: dict[str, list[tuple[str, Reason]]] = {}
    by_congress: dict[int, list[int]] = {}
    for congress, num in laws:
        by_congress.setdefault(congress, []).append(num)

    for congress, nums in by_congress.items():
        for row in session.execute(
            select(
                ClassificationEntry.usc_identifier,
                ClassificationEntry.pl_congress,
                ClassificationEntry.pl_num,
                ClassificationEntry.action,
                ClassificationEntry.is_note,
                ClassificationEntry.transfer_counterpart,
            )
            .where(
                ClassificationEntry.pl_congress == congress,
                ClassificationEntry.pl_num.in_(nums),
                ClassificationEntry.usc_identifier.is_not(None),
            )
            .order_by(ClassificationEntry.file_id, ClassificationEntry.row_seq)
        ):
            reason = Reason(CLASSIFICATION, row.pl_congress, row.pl_num, row.action, row.is_note)
            _add(found, row.usc_identifier, reason)
            # `tr to 42/290ee-10`: the section the provision moved to changes too.
            counterpart = _counterpart_identifier(row.transfer_counterpart)
            if counterpart:
                _add(found, counterpart, reason)

        for row in session.execute(
            select(EcctEntry)
            .where(
                EcctEntry.prompting_pl_congress == congress,
                EcctEntry.prompting_pl_num.in_(nums),
            )
            .order_by(EcctEntry.file_id, EcctEntry.row_seq)
        ).scalars():
            for title_num, section_norm, is_note in (
                (row.former_title_num, row.former_section_norm, row.former_is_note),
                (row.new_title_num, row.new_section_norm, row.new_is_note),
            ):
                if not title_num or not section_norm:
                    continue
                identifier = derive_usc_identifier(
                    title_num.lower(), section_norm, is_appendix=title_num.lower().endswith("a")
                )
                if identifier:
                    _add(
                        found,
                        identifier,
                        Reason(ECCT, row.prompting_pl_congress, row.prompting_pl_num, None, is_note),
                    )
    return found


def _add(found: dict[str, list[tuple[str, Reason]]], identifier: str, reason: Reason) -> None:
    match = re.match(r"/us/usc/t([0-9]+[a-z]?)/", identifier)
    if match:
        found.setdefault(match.group(1).lower(), []).append((identifier, reason))


def _counterpart_identifier(counterpart: str | None) -> str | None:
    """`42/290ee-10` → `/us/usc/t42/s290ee–10`; None for anything else."""
    if not counterpart or "/" not in counterpart:
        return None
    title_num, _, section = counterpart.partition("/")
    title_num = title_num.strip().lower()
    section = section.strip().lower().replace("–", "-")
    return derive_usc_identifier(title_num, section, is_appendix=title_num.endswith("a"))


def _unresolved_rows(
    session: Session, laws: Sequence[tuple[int, int]]
) -> dict[str, list[tuple[int, int, str]]]:
    found: dict[str, list[tuple[int, int, str]]] = {}
    wanted = set(laws)
    congresses = sorted({c for c, _ in laws})
    if not congresses:
        return found
    for row in session.execute(
        select(
            ClassificationEntry.title_num,
            ClassificationEntry.section_raw,
            ClassificationEntry.pl_congress,
            ClassificationEntry.pl_num,
        ).where(
            ClassificationEntry.pl_congress.in_(congresses),
            ClassificationEntry.usc_identifier.is_(None),
        )
    ):
        if (row.pl_congress, row.pl_num) in wanted:
            found.setdefault(row.title_num.lower(), []).append(
                (row.pl_congress, row.pl_num, f"{row.title_num}/{row.section_raw}")
            )
    return found


def _existing_identifiers(session: Session, title_ids: Sequence[int]) -> dict[int, dict[str, str]]:
    """Title id → {identifier with hyphens → identifier as stored}, so a row's
    derived spelling joins whatever dash the corpus wrote (gotcha 17)."""
    found: dict[int, dict[str, str]] = {}
    if not title_ids:
        return found
    for title_id, identifier in session.execute(
        select(Section.title_id, Section.identifier).where(Section.title_id.in_(title_ids))
    ):
        found.setdefault(title_id, {})[identifier.replace("–", "-")] = identifier
    return found


# ------------------------------------------------------------------- sources


@dataclass(frozen=True, slots=True)
class FetchedSection:
    """What a source returned for one identifier."""

    identifier: str
    records: tuple[SectionRecord, ...]
    """Every element the document publishes under the identifier — usually
    one, more where the source repeats an identifier (ADR-0021)."""
    url: str
    sha256: str
    schema_version: str


class SectionSource(Protocol):
    """Where sections come from. `fetch` returns None when the source has no
    such section."""

    name: str

    def fetch(self, identifier: str) -> FetchedSection | None: ...


def records_from_document(data: bytes, identifier: str) -> tuple[tuple[SectionRecord, ...], str]:
    """The sections in a USLM document published under `identifier`, and the
    document's schema version.

    The document can be a whole `uscDoc` or a section on its own; the root
    namespace selects the parser (ADR-0004). Anything that is not USLM raises
    `UnknownUslmSchemaError`, or `etree.XMLSyntaxError` for an HTML page.
    """
    source = io.BytesIO(data)
    parser = parser_for(source)
    variants = set(identifier_variants(identifier))
    records: list[SectionRecord] = []
    schema_version = ""
    for record in parser.iter_sections(source):
        schema_version = record.schema_version
        if record.identifier in variants:
            records.append(record)
    return tuple(records), schema_version


def section_url(template: str, identifier: str) -> str:
    """Fill a URL template from an identifier.

    Placeholders: `{identifier}` (`/us/usc/t16/s45f`, percent-encoded but for
    the slashes), `{title}` (`16`), `{section}` (`45f`, percent-encoded) and
    `{title_padded}` (`16`, `05a` — OLRC's file-naming form).
    """
    match = re.match(r"/us/usc/t([0-9]+[a-z]?)/s(.+)$", identifier)
    if not match:
        raise SectionUpdateError(f"not a section identifier: {identifier!r}")
    title, section = match.groups()
    digits = re.match(r"\d+", title).group(0)  # type: ignore[union-attr]
    padded = digits.zfill(2) + title[len(digits):]
    return template.format(
        identifier=urllib.parse.quote(identifier, safe="/"),
        title=title,
        section=urllib.parse.quote(section, safe=""),
        title_padded=padded,
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class UrlSectionSource:
    """One HTTP GET per section, from a URL template (`section_url`).

    A 404 is "no such section"; any other failure raises. Each response is
    cached under `cache_dir` by its URL's hash, so a re-run of a failed update
    fetches nothing it already has. Requests go through the download
    throttle with the project's User-Agent.
    """

    name = "section-url"

    def __init__(
        self,
        template: str,
        *,
        cache_dir: Path | None = None,
        opener: Callable[[urllib.request.Request, float], Any] | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.template = template
        self.cache_dir = cache_dir
        self.opener = opener or (lambda request, timeout: urllib.request.urlopen(request, timeout=timeout))
        self.timeout = timeout

    def fetch(self, identifier: str) -> FetchedSection | None:
        url = section_url(self.template, identifier)
        data = self._cached(url)
        if data is None:
            throttle()
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with self.opener(request, self.timeout) as response:
                    data = response.read()
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return None
                raise
            self._store(url, data)
        try:
            records, schema_version = records_from_document(data, identifier)
        except (UnknownUslmSchemaError, etree.XMLSyntaxError) as exc:
            raise SectionUpdateError(
                f"{url}: not a USLM document ({type(exc).__name__}: {exc}); "
                f"first bytes {data[:80]!r}"
            ) from exc
        if not records:
            return None
        return FetchedSection(identifier, records, url, _sha256(data), schema_version)

    def _cache_path(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()[:32]}.xml"

    def _cached(self, url: str) -> bytes | None:
        path = self._cache_path(url)
        return path.read_bytes() if path is not None and path.exists() else None

    def _store(self, url: str, data: bytes) -> None:
        path = self._cache_path(url)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)


def directory_filename(identifier: str) -> str:
    """`/us/usc/t16/s45f` → `t16-s45f.xml`: the name `DirectorySectionSource`
    reads, with the identifier's EN DASH kept."""
    return identifier.removeprefix("/us/usc/").replace("/", "-") + ".xml"


class DirectorySectionSource:
    """Sections saved as files, one per identifier (`directory_filename`). What
    a capture of the source's pages and the tests use."""

    name = "directory"

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def fetch(self, identifier: str) -> FetchedSection | None:
        for variant in identifier_variants(identifier):
            path = self.directory / directory_filename(variant)
            if path.exists():
                data = path.read_bytes()
                records, schema_version = records_from_document(data, identifier)
                if not records:
                    return None
                return FetchedSection(
                    identifier, records, path.as_uri(), _sha256(data), schema_version
                )
        return None


class TitleFileSource:
    """The planned sections of one title, read out of a title's XML file or a
    zip holding it (a per-title zip, or the all-titles zip, whose other members
    are left unread). The file is parsed once; nothing else of it is stored."""

    name = "title-file"

    def __init__(self, path: Path, title_num: str) -> None:
        self.path = path
        self.title_num = title_num
        self._records: dict[str, list[SectionRecord]] | None = None
        self._schema_version = ""
        self._sha256 = ""

    def fetch(self, identifier: str) -> FetchedSection | None:
        records = self._load()
        for variant in identifier_variants(identifier):
            if variant in records:
                return FetchedSection(
                    identifier,
                    tuple(records[variant]),
                    self.path.as_uri(),
                    self._sha256,
                    self._schema_version,
                )
        return None

    def _load(self) -> dict[str, list[SectionRecord]]:
        if self._records is not None:
            return self._records
        digest = hashlib.sha256()
        with open(self.path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        self._sha256 = digest.hexdigest()
        prefix = f"/us/usc/t{self.title_num}/"
        records: dict[str, list[SectionRecord]] = {}
        # Streamed from a file on disk, never held whole (gotcha 6): a zip
        # member is extracted to a temporary file first, since the parser
        # rewinds its source after sniffing the schema.
        with self._xml_path() as xml_path:
            for record in parser_for(xml_path).iter_sections(xml_path):
                self._schema_version = record.schema_version
                if record.identifier.startswith(prefix):
                    records.setdefault(record.identifier, []).append(record)
        self._records = records
        return records

    @contextmanager
    def _xml_path(self) -> Iterator[Path]:
        if not zipfile.is_zipfile(self.path):
            yield self.path
            return
        digits = re.match(r"\d+", self.title_num).group(0)  # type: ignore[union-attr]
        padded = digits.zfill(2) + self.title_num[len(digits):]
        member_name = f"usc{padded}.xml"
        with zipfile.ZipFile(self.path) as archive:
            member = next(
                (m for m in archive.namelist() if m.rsplit("/", 1)[-1].lower() == member_name),
                None,
            )
            if member is None:
                raise SectionUpdateError(f"{self.path}: no {member_name} in the zip")
            with tempfile.TemporaryDirectory() as tmp:
                yield Path(archive.extract(member, tmp))


# ------------------------------------------------------------------ applying


@dataclass
class TitleResult:
    title_num: str
    status: str
    """`loaded`, `failed` (a planned section was not found, nothing written) or
    `planned` (a plan-only run)."""
    base: str | None = None
    sections_fetched: int = 0
    new_versions: int = 0
    unchanged: int = 0
    new_sections: int = 0
    not_found: list[str] = field(default_factory=list)
    sections_loaded: int = 0

    def as_json(self) -> dict[str, Any]:
        return {
            "title": self.title_num,
            "status": self.status,
            "base": self.base,
            "sections_fetched": self.sections_fetched,
            "new_versions": self.new_versions,
            "unchanged": self.unchanged,
            "new_sections": self.new_sections,
            "not_found": self.not_found,
            "sections_loaded": self.sections_loaded,
        }


def section_sort_key(identifier: str) -> tuple:
    """Natural order of a section number: `s45f` < `s45f–1` < `s46` < `s100`."""
    number = identifier.rsplit("/s", 1)[-1].lower()
    return tuple(
        (0, int(token), "") if token.isdigit() else (1, 0, token)
        for token in re.findall(r"\d+|[a-z]+", number)
    )


@dataclass(slots=True)
class _Placed:
    identifier: str
    parent_identifier: str | None
    version_id: int | None = None
    """Set for a carried-forward section; None until stored for a fetched one."""
    record: SectionRecord | None = None


def assemble_order(
    base: Sequence[tuple[str, int, str | None]],
    fetched: dict[str, tuple[SectionRecord, ...]],
) -> list[_Placed]:
    """The title's sections at the release point, in reading order.

    `base` is the base release point's (identifier, version id, parent) in its
    reading order. A fetched identifier replaces every base occurrence of it
    with its records, at the first occurrence's place; one the base does not
    hold goes after the base section with the greatest section number below it
    (the first place, if none is below it), taking that neighbour's parent
    unless the fetched document carries its own ancestors.
    """
    placed: list[_Placed] = []
    seen: set[str] = set()
    for identifier, version_id, parent in base:
        if identifier in fetched:
            if identifier in seen:
                continue
            seen.add(identifier)
            for record in fetched[identifier]:
                placed.append(_Placed(identifier, _parent_of(record) or parent, None, record))
        else:
            placed.append(_Placed(identifier, parent, version_id))

    for identifier in sorted(set(fetched) - seen, key=section_sort_key):
        key = section_sort_key(identifier)
        position = 0
        best: tuple | None = None
        for index, entry in enumerate(placed):
            entry_key = section_sort_key(entry.identifier)
            if entry_key < key and (best is None or entry_key >= best):
                best = entry_key
                position = index + 1
        neighbour = placed[position - 1].parent_identifier if position else None
        for offset, record in enumerate(fetched[identifier]):
            placed.insert(
                position + offset,
                _Placed(identifier, _parent_of(record) or neighbour, None, record),
            )
    return placed


def _parent_of(record: SectionRecord) -> str | None:
    return record.ancestors[-1][1] if record.ancestors else None


def apply_plan(
    session: Session,
    plan: UpdatePlan,
    source_for: Callable[[TitlePlan], SectionSource],
    *,
    allow_not_found: bool = False,
    defer_version_changes: bool = False,
    on_event: OnEvent = None,
) -> list[TitleResult]:
    """Fetch and load every `ready` title of `plan`. Refuses a plan with
    uncovered laws."""
    if not plan.ok:
        raise SectionUpdateError(
            f"the classification tables do not cover "
            f"{', '.join(f'{c}-{n}' for c, n in plan.uncovered_laws)}, which "
            f"{plan.target.label} incorporates — run `python -m ingest classification` "
            "and plan again once the tables reach them"
        )
    say = on_event or (lambda message: None)
    results = []
    for title_plan in plan.ready:
        started = time.monotonic()
        result = apply_title(
            session,
            plan.target,
            title_plan,
            source_for(title_plan),
            allow_not_found=allow_not_found,
            defer_version_changes=defer_version_changes,
        )
        say(
            f"title {result.title_num} @ {plan.target.label}: {result.status}, "
            f"{result.sections_fetched} fetched, {result.new_versions} new, "
            f"{result.unchanged} unchanged, {result.new_sections} new sections"
            + (f", not found: {', '.join(result.not_found)}" if result.not_found else "")
            + f" ({time.monotonic() - started:.1f}s)"
        )
        results.append(result)
    return results


def apply_title(
    session: Session,
    target: ReleaseFacts,
    title_plan: TitlePlan,
    source: SectionSource,
    *,
    allow_not_found: bool = False,
    defer_version_changes: bool = False,
) -> TitleResult:
    """Fetch one title's planned sections, then write the title at `target`.

    Every fetch happens before the first write, so a section the source does
    not have leaves the database as it was — unless `allow_not_found`, which
    carries such a section's base text forward and records it `not-found`.
    """
    assert title_plan.base is not None
    base = title_plan.base
    result = TitleResult(title_plan.title_num, "failed", base=base.label)

    fetched: dict[str, FetchedSection] = {}
    for identifier in title_plan.sections:
        section = source.fetch(identifier)
        if section is None:
            result.not_found.append(identifier)
        else:
            fetched[identifier] = section
    result.sections_fetched = len(fetched)
    if result.not_found and not allow_not_found:
        return result

    title_id = title_plan.title_id
    base_rows = session.execute(
        select(Section.id, Section.identifier, SectionReleaseMap.section_version_id,
               SectionReleaseMap.parent_identifier)
        .join(SectionVersion, SectionVersion.section_id == Section.id)
        .join(SectionReleaseMap, SectionReleaseMap.section_version_id == SectionVersion.id)
        .where(Section.title_id == title_id, SectionReleaseMap.release_id == base.id)
        .order_by(SectionReleaseMap.seq_in_title, SectionVersion.id)
    ).all()
    base_identifiers = {row.identifier for row in base_rows}
    placed = assemble_order(
        [(row.identifier, row.section_version_id, row.parent_identifier) for row in base_rows],
        {identifier: section.records for identifier, section in fetched.items()},
    )

    existing_sections = {
        identifier: section_id
        for section_id, identifier in session.execute(
            select(Section.id, Section.identifier).where(Section.title_id == title_id)
        )
    }
    existing_versions: dict[int, dict[bytes, _KnownVersion]] = {}
    for section_id, version_id, content_hash, first_release_id in session.execute(
        known_versions_statement(title_id)
    ):
        existing_versions.setdefault(section_id, {})[content_hash] = _KnownVersion(
            version_id, first_release_id
        )
    base_version_of = {
        row.identifier: row.section_version_id for row in base_rows
    }

    newest_loaded_seq = session.scalar(
        select(func.max(ReleasePoint.seq))
        .select_from(TitleVersion)
        .join(ReleasePoint, ReleasePoint.id == TitleVersion.release_id)
        .where(TitleVersion.title_id == title_id, TitleVersion.sections_loaded.is_not(None))
    )
    is_newest = newest_loaded_seq is None or target.seq >= newest_loaded_seq

    title_version = session.scalars(
        select(TitleVersion).where(
            TitleVersion.title_id == title_id, TitleVersion.release_id == target.id
        )
    ).first()
    if title_version is None:
        title_version = TitleVersion(title_id=title_id, release_id=target.id)
        session.add(title_version)
    schema_versions = sorted({s.schema_version for s in fetched.values() if s.schema_version})
    title_version.load_method = SECTIONS_METHOD
    title_version.base_release_id = base.id
    title_version.schema_version = ",".join(schema_versions) or "uslm-unknown"
    title_version.source_zip_sha256 = hashlib.sha256(
        "\n".join(f"{s.url} {s.sha256}" for _i, s in sorted(fetched.items())).encode()
    ).hexdigest()
    title_version.sections_loaded = None
    title_version.raw_section_elements = None
    session.flush()
    # A re-run over an interrupted attempt starts from nothing.
    _unmap_title_release(session, title_id, target.id)
    session.execute(
        delete(SectionUpdateItem).where(
            SectionUpdateItem.release_id == target.id,
            SectionUpdateItem.title_id == title_id,
        )
    )
    session.commit()

    versions = VersionStore(
        session,
        release_id=target.id,
        release_seq=target.seq,
        release_label=target.label,
        is_newest_for_title=is_newest,
        existing_versions=existing_versions,
    )
    map_rows: list[dict[str, object]] = []
    guid_rows: list[dict[str, object]] = []
    mapped_versions: dict[int, set[int]] = {}
    outcome_of: dict[str, tuple[str, int | None, int | None]] = {}

    for seq, entry in enumerate(placed):
        section_id = existing_sections.get(entry.identifier)
        if entry.record is None:
            version_id = entry.version_id
            assert version_id is not None and section_id is not None
        else:
            if section_id is None:
                section = Section(title_id=title_id, identifier=entry.identifier)
                session.add(section)
                session.flush()
                section_id = section.id
                existing_sections[entry.identifier] = section_id
            new_before = versions.new_versions
            known = versions.store(
                entry.record,
                section_id,
                parent_identifier=entry.parent_identifier,
                seq_in_title=seq,
            )
            version_id = known.id
            if entry.identifier not in base_identifiers:
                outcome = NEW_SECTION
            elif versions.new_versions > new_before or version_id != base_version_of.get(entry.identifier):
                outcome = NEW_VERSION
            else:
                outcome = UNCHANGED
            previous = outcome_of.get(entry.identifier)
            if previous is None or outcome != UNCHANGED:
                outcome_of[entry.identifier] = (outcome, section_id, version_id)
            for guid_ref in entry.record.guid_refs:
                guid_rows.append(
                    {"guid": guid_ref.guid, "release_id": target.id, "identifier": guid_ref.identifier}
                )
        mapped_versions.setdefault(section_id, set()).add(version_id)
        map_rows.append(
            {
                "section_version_id": version_id,
                "release_id": target.id,
                "seq_in_title": seq,
                "parent_identifier": entry.parent_identifier,
            }
        )
        if len(map_rows) >= MAP_BATCH:
            _flush_map_rows(session, map_rows)
            map_rows.clear()
        if len(guid_rows) >= GUID_BATCH_SIZE:
            _flush_guid_rows(session, guid_rows)
            guid_rows.clear()
    if map_rows:
        _flush_map_rows(session, map_rows)
    if guid_rows:
        _flush_guid_rows(session, guid_rows)

    for identifier, reasons in title_plan.sections.items():
        section = fetched.get(identifier)
        outcome, section_id, version_id = outcome_of.get(
            identifier, (NOT_FOUND, existing_sections.get(identifier), None)
        )
        for reason in reasons:
            session.add(
                SectionUpdateItem(
                    release_id=target.id,
                    title_id=title_id,
                    identifier=identifier,
                    section_id=section_id,
                    pl_congress=reason.pl_congress,
                    pl_num=reason.pl_num,
                    basis=reason.basis,
                    action=reason.action,
                    is_note=reason.is_note,
                    outcome=outcome,
                    section_version_id=version_id,
                    source_url=section.url if section else None,
                )
            )
        if outcome == NEW_SECTION:
            result.new_sections += 1
        elif outcome == NEW_VERSION:
            result.new_versions += 1
        elif outcome == UNCHANGED:
            result.unchanged += 1

    # The completion marker, last (ADR-0082).
    title_version.sections_loaded = len(placed)
    session.commit()
    versions.flush_search()
    result.sections_loaded = len(placed)
    result.status = "loaded"

    if defer_version_changes:
        from ingest import version_changes

        version_changes.clear_change_rows(session, sorted(mapped_versions))
        session.commit()
    else:
        recompute_version_changes(
            session,
            title_id=title_id,
            title_num=title_plan.title_num,
            release_id=target.id,
            release_label=target.label,
            mapped_versions=mapped_versions,
            new_version_sections=versions.new_version_sections,
        )
    return result


def _flush_map_rows(session: Session, rows: list[dict[str, object]]) -> None:
    stmt = pg_insert(SectionReleaseMap).values(rows)
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["section_version_id", "release_id"],
            set_={
                "seq_in_title": stmt.excluded.seq_in_title,
                "parent_identifier": stmt.excluded.parent_identifier,
            },
        )
    )


def default_section_url() -> str | None:
    return os.environ.get(SECTION_URL_ENV) or None


def print_plan(plan: UpdatePlan, out=sys.stdout) -> None:
    """The plan, as `sections-update --plan-only` prints it."""
    def laws(values: Iterable[tuple[int, int]]) -> str:
        return ", ".join(f"{c}-{n}" for c, n in values) or "none"

    print(f"release point {plan.target.label}", file=out)
    print(f"  laws in the window: {laws(plan.window_laws)}", file=out)
    if plan.uncovered_laws:
        print(f"  NOT COVERED by the loaded tables: {laws(plan.uncovered_laws)}", file=out)
    if plan.laws_without_rows:
        print(f"  covered, classified to no section: {laws(plan.laws_without_rows)}", file=out)
    for title in plan.titles:
        if title.status == "unchanged":
            continue
        base = f" from {title.base.label}" if title.base else ""
        print(f"  title {title.title_num}: {title.status}{base}", file=out)
        for identifier, reasons in title.sections.items():
            detail = ", ".join(
                f"{r.law}{' nt' if r.is_note else ''}{' ' + r.action if r.action else ''}"
                for r in reasons
            )
            print(f"    {identifier}  [{detail}]", file=out)
        for row in title.unresolved:
            print(f"    unresolved row {row}", file=out)
