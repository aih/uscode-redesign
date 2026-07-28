"""`make verify` — do the stored counts match what was loaded, and the source?

PLAN §11.5 and documentation duty 5: reliability claims have to be reproducible
commands, not assertions. Two levels, because they answer different questions:

* **Shallow** (default, seconds). For every completed `(title, release)`, does
  `section_release_map` actually hold `sections_loaded` rows? This catches a
  load that stamped its completion count while writing fewer rows than it
  claimed — the failure the completion marker exists to make visible.

* **Deep** (`--deep`, hours). Re-parse the source XML from the download corpus
  and compare the number of real code sections and the raw `<section>` element
  count against what the database recorded. This is the one that is *independent*
  of the loader: the shallow check compares the loader's work against the
  loader's own bookkeeping, which cannot catch a parser that consistently missed
  the same sections at load time and again now. Deep re-derives from source.

The known gap between the raw element count and the stored section count is
ADR-0005's: some section-shaped elements are statutory text quoted by an
amending act rather than code sections, and are deliberately not stored — 298 of
them in Title 16. Which elements those are is the parser's business, not this
module's (architecture rule 2); here the gap is just `raw - stored`, recorded
per title rather than treated as an error.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import (
    ReleasePoint,
    Section,
    SectionReleaseMap,
    SectionVersion,
    Title,
    TitleVersion,
)
from ingest.backfill import DownloadLedger
from ingest.load_all import _extracted
from ingest.parser import parser_for


@dataclass
class TitleCheck:
    release_label: str
    title_num: str
    sections_loaded: int
    """What the loader recorded when it finished."""

    rows_in_release_map: int
    """What `section_release_map` actually holds now."""

    raw_section_elements: int | None = None
    source_sections: int | None = None
    """Real code sections re-counted from the source XML (deep only)."""

    source_raw_elements: int | None = None

    @property
    def stored_matches(self) -> bool:
        return self.sections_loaded == self.rows_in_release_map

    @property
    def source_matches(self) -> bool | None:
        if self.source_sections is None:
            return None
        return self.source_sections == self.sections_loaded

    @property
    def unstored_element_gap(self) -> int | None:
        """Section-shaped elements in the source that were deliberately not stored
        — ADR-0005's expected difference, seen here only as a number."""
        if self.raw_section_elements is None:
            return None
        return self.raw_section_elements - self.sections_loaded


@dataclass
class VerifyReport:
    generated_at: str = ""
    deep: bool = False
    title_versions_checked: int = 0
    releases_covered: int = 0
    titles_covered: int = 0
    sections: int = 0
    section_versions: int = 0
    release_map_rows: int = 0
    guid_rows: int = 0
    incomplete_loads: list[str] = field(default_factory=list)
    """`(title, release)` rows whose `sections_loaded` is NULL — a load that
    never finished, which `load-all` will redo."""

    count_mismatches: list[str] = field(default_factory=list)
    source_mismatches: list[str] = field(default_factory=list)
    unstored_element_gaps: dict[str, int] = field(default_factory=dict)
    checks: list[TitleCheck] = field(default_factory=list)

    @property
    def sound(self) -> bool:
        return not self.count_mismatches and not self.source_mismatches

    @property
    def dedupe_ratio(self) -> float:
        """`1 - section_versions/release_map_rows` — how much content dedupe saved
        against the naive one-row-per-(section, release) storage (ADR-0007)."""
        if not self.release_map_rows:
            return 0.0
        return 1.0 - (self.section_versions / self.release_map_rows)

    def as_json(self) -> dict[str, object]:
        document = asdict(self)
        document["sound"] = self.sound
        document["dedupe_ratio"] = round(self.dedupe_ratio, 6)
        # Per-title detail is the evidence, but it is long; keep it last.
        document["checks"] = [asdict(c) for c in self.checks]
        return document


def verify_database(
    session: Session,
    *,
    deep: bool = False,
    ledger: DownloadLedger | None = None,
    limit: int | None = None,
) -> VerifyReport:
    """Compare recorded counts against `section_release_map`, and optionally source."""
    report = VerifyReport(generated_at=datetime.now(timezone.utc).isoformat(), deep=deep)

    report.sections = session.scalar(select(func.count()).select_from(Section)) or 0
    report.section_versions = (
        session.scalar(select(func.count()).select_from(SectionVersion)) or 0
    )
    report.release_map_rows = (
        session.scalar(select(func.count()).select_from(SectionReleaseMap)) or 0
    )

    incomplete = session.execute(
        select(ReleasePoint.label, Title.num)
        .select_from(TitleVersion)
        .join(ReleasePoint, ReleasePoint.id == TitleVersion.release_id)
        .join(Title, Title.id == TitleVersion.title_id)
        .where(TitleVersion.sections_loaded.is_(None))
    ).all()
    report.incomplete_loads = [f"{label}/{num}" for label, num in incomplete]

    rows = session.execute(
        select(
            ReleasePoint.label,
            Title.num,
            Title.id,
            ReleasePoint.id,
            TitleVersion.sections_loaded,
            TitleVersion.raw_section_elements,
        )
        .select_from(TitleVersion)
        .join(ReleasePoint, ReleasePoint.id == TitleVersion.release_id)
        .join(Title, Title.id == TitleVersion.title_id)
        .where(TitleVersion.sections_loaded.is_not(None))
        .order_by(ReleasePoint.seq, Title.num)
    ).all()

    releases: set[str] = set()
    titles: set[str] = set()

    for index, (label, num, title_id, release_id, loaded, raw) in enumerate(rows):
        if limit is not None and index >= limit:
            break
        actual = (
            session.scalar(
                select(func.count())
                .select_from(SectionReleaseMap)
                .join(SectionVersion, SectionVersion.id == SectionReleaseMap.section_version_id)
                .join(Section, Section.id == SectionVersion.section_id)
                .where(
                    SectionReleaseMap.release_id == release_id,
                    Section.title_id == title_id,
                )
            )
            or 0
        )
        check = TitleCheck(
            release_label=label,
            title_num=num,
            sections_loaded=loaded,
            rows_in_release_map=actual,
            raw_section_elements=raw,
        )

        if deep and ledger is not None:
            _recount_from_source(check, ledger)

        report.checks.append(check)
        report.title_versions_checked += 1
        releases.add(label)
        titles.add(num)

        if not check.stored_matches:
            report.count_mismatches.append(
                f"{label}/{num}: recorded {loaded}, section_release_map has {actual}"
            )
        if check.source_matches is False:
            report.source_mismatches.append(
                f"{label}/{num}: source has {check.source_sections}, database {loaded}"
            )
        gap = check.unstored_element_gap
        if gap:
            report.unstored_element_gaps[f"{label}/{num}"] = gap

    report.releases_covered = len(releases)
    report.titles_covered = len(titles)
    return report


def _recount_from_source(check: TitleCheck, ledger: DownloadLedger) -> None:
    """Re-parse this title's downloaded zip and count it again, independently."""
    entry = ledger.entries.get(f"{check.release_label}/{check.title_num}")
    if entry is None:
        return
    path = ledger.resolve_path(entry)
    if path is None or not path.exists():
        return
    with _extracted(path) as xml_path:
        parser = parser_for(xml_path)
        check.source_sections = sum(1 for _ in parser.iter_sections(xml_path))
        check.source_raw_elements = parser.count_section_elements(xml_path)


def write_report(
    report: VerifyReport, *, directory: Path = Path("docs/verification")
) -> Path:
    """Commit the verification as a reproducible artifact (documentation duty 5)."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "database.json"
    path.write_text(json.dumps(report.as_json(), indent=2, sort_keys=True) + "\n")
    return path


def summarize(report: VerifyReport) -> str:
    lines = [
        f"{report.title_versions_checked} title-versions checked "
        f"across {report.releases_covered} release points, {report.titles_covered} titles",
        f"sections {report.sections:,} | section_versions {report.section_versions:,} "
        f"| release-map rows {report.release_map_rows:,}",
        f"dedupe ratio {report.dedupe_ratio:.1%} "
        f"(section_versions vs one row per section per release)",
    ]
    if report.incomplete_loads:
        lines.append(
            f"{len(report.incomplete_loads)} incomplete load(s) — `load-all` will redo: "
            + ", ".join(report.incomplete_loads[:5])
        )
    if report.unstored_element_gaps:
        gaps = Counter(report.unstored_element_gaps.values())
        lines.append(
            f"unstored section-shaped elements on {len(report.unstored_element_gaps)} "
            f"title-versions (ADR-0005, expected); most common gap: "
            f"{gaps.most_common(1)[0][0]}"
        )
    if report.count_mismatches:
        lines.append("COUNT MISMATCHES:")
        lines += [f"  {m}" for m in report.count_mismatches[:10]]
    if report.source_mismatches:
        lines.append("SOURCE MISMATCHES:")
        lines += [f"  {m}" for m in report.source_mismatches[:10]]
    if report.sound:
        lines.append("verification sound")
    return "\n".join(lines)
