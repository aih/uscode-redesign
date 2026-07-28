"""Bulk load of the downloaded corpus, driven by the download ledger.

`load_release` handles one title at one release point (ADR-0007's dedupe, the
TOC pass, guid_map, the release map). This walks the whole corpus with it:
every `ok` entry in `data/releases/ledger.json`, in inventory `seq` order —
oldest release point first, so the baseline sweep lands before the deltas that
assume it and `first_release_id` always ends up on the earliest release that
carried a given text (ADR-0008).

Three properties it has to have, because this run is hours long:

* **Resumable, with the database as the only state.** There is no second ledger
  to drift: `title_versions.sections_loaded` is written last, so a (title,
  release) counts as loaded only when it finished. A crash mid-title leaves NULL
  and the pair is redone from the top — `load_release` is idempotent by
  construction (content-hash dedupe plus upserts), so redoing costs time, never
  duplicate rows.
* **Bounded disk.** The zips are ~9 GB; their XML is several times that. Each
  title is extracted to a temporary directory, loaded, and deleted, so the
  corpus never doubles on disk.
* **Bounded memory.** One session per title, closed after — the identity map
  from a 5,000-section title does not survive into the next one. Parsers already
  stream (gotcha 6).

The one cross-check worth doing while here: the ledger's title number comes from
the URL, and the loaded title number comes from `<docNumber>` inside the XML. If
they disagree, the wrong file is filed under that name — reported as a mismatch,
never silently accepted.
"""

from __future__ import annotations

import tempfile
import time
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ReleasePoint, Title, TitleVersion
from ingest.backfill import DownloadLedger, LedgerEntry
from ingest.download import DOWNLOAD_DIR, FetchStatus
from ingest.inventory import ReleasePointEntry, normalize_title_num
from ingest.load import LoadStats, load_release
from ingest.manifest import write_manifest


@dataclass(frozen=True, slots=True)
class LoadTask:
    release_label: str
    title_num: str
    seq: int
    zip_path: Path

    @property
    def key(self) -> str:
        return f"{self.release_label}/{self.title_num}"


@dataclass
class LoadAllReport:
    planned: int = 0
    loaded: int = 0
    skipped: int = 0
    """Already complete in the database — the resume path."""

    failed: int = 0
    sections_stored: int = 0
    new_versions: int = 0
    deduped_versions: int = 0
    elapsed_seconds: float = 0.0
    failures: list[tuple[str, str]] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)
    """Ledger title number != `<docNumber>` in the file it points at."""

    @property
    def dedupe_ratio(self) -> float:
        """Share of loaded sections that reused an existing version — the headline
        number for whether content dedupe is doing its job (ADR-0007)."""
        total = self.new_versions + self.deduped_versions
        return self.deduped_versions / total if total else 0.0


def plan_loads(
    ledger: DownloadLedger,
    entries: list[ReleasePointEntry],
    *,
    titles: set[str] | None = None,
    releases: set[str] | None = None,
) -> list[LoadTask]:
    """Every downloaded title, in inventory `seq` order (oldest release first).

    Release points the inventory doesn't know are skipped rather than guessed at:
    `seq` is what defines "oldest first", and a label with no `seq` has no place
    in the order.
    """
    seq_by_label = {entry.label: entry.seq for entry in entries}
    wanted = {normalize_title_num(t) for t in titles} if titles else None
    tasks: list[LoadTask] = []

    for entry in ledger.entries.values():
        if entry.status != FetchStatus.OK:
            continue
        if wanted is not None and entry.title_num not in wanted:
            continue
        if releases is not None and entry.release_label not in releases:
            continue
        seq = seq_by_label.get(entry.release_label)
        if seq is None:
            continue
        path = ledger.resolve_path(entry)
        if path is None or not path.exists():
            continue
        tasks.append(
            LoadTask(
                release_label=entry.release_label,
                title_num=entry.title_num,
                seq=seq,
                zip_path=path,
            )
        )

    tasks.sort(key=lambda t: (t.seq, t.title_num))
    return tasks


def completed_pairs(session: Session) -> set[tuple[str, str]]:
    """`(release_label, title_num)` pairs whose load finished, keyed in the
    ledger's vocabulary.

    `sections_loaded IS NOT NULL` is the whole test — see the column's docstring.

    `Title.num` is the *URL* form, taken from `<docNumber>`: `1`, `16`, and what
    `/us/usc/t1/...` resolves against. The ledger and every OLRC filename use the
    *file-naming* form: `01`, `16`, `05a`. Normalizing here is what lets resume
    recognize its own work — comparing the two raw would never match a
    single-digit title, and `load-all` would reload titles 1-9 on every run,
    forever.
    """
    rows = session.execute(
        select(ReleasePoint.label, Title.num)
        .select_from(TitleVersion)
        .join(ReleasePoint, ReleasePoint.id == TitleVersion.release_id)
        .join(Title, Title.id == TitleVersion.title_id)
        .where(TitleVersion.sections_loaded.is_not(None))
    ).all()
    return {(label, _file_form(num)) for label, num in rows}


def _file_form(title_num: str) -> str:
    """`Title.num` (URL form) → the ledger's file-naming form; unchanged if it
    isn't a title number we recognize, so an oddity shows up as a mismatch rather
    than an exception."""
    try:
        return normalize_title_num(title_num)
    except ValueError:
        return title_num


def run_load_all(
    tasks: list[LoadTask],
    session_factory: Callable[[], Session],
    *,
    limit: int | None = None,
    write_manifests: bool = True,
    on_event: Callable[[str], None] | None = None,
) -> LoadAllReport:
    """Load every task not already complete. Safe to re-run; safe to interrupt."""
    report = LoadAllReport(planned=len(tasks))
    started = time.monotonic()
    say = on_event or (lambda message: None)

    with session_factory() as session:
        done = completed_pairs(session)

    for task in tasks:
        if (task.release_label, task.title_num) in done:
            report.skipped += 1
            continue
        if limit is not None and report.loaded >= limit:
            report.skipped += 1
            continue

        try:
            with _extracted(task.zip_path) as xml_path:
                # One session per title: the identity map of a 5,000-section load
                # must not survive into the next one.
                with session_factory() as session:
                    stats: LoadStats = load_release(
                        xml_path,
                        task.release_label,
                        session,
                        source_zip=task.zip_path,
                    )
                if write_manifests:
                    write_manifest(
                        task.release_label,
                        xml_path,
                        stats,
                        source_url=None,
                        source_zip=task.zip_path,
                    )
        except Exception as exc:  # one bad title must not end the run
            report.failed += 1
            report.failures.append((task.key, f"{type(exc).__name__}: {exc}"))
            say(f"FAIL  {task.key} — {type(exc).__name__}: {exc}")
            continue

        if _file_form(stats.title_num) != task.title_num:
            # The URL said one title; <docNumber> says another. Compared in the
            # file-naming form, so `1` vs `01` is not a finding — a real swap is.
            report.mismatches.append(
                f"{task.key}: file contains title {stats.title_num}"
            )
            say(f"MISMATCH {task.key} — file contains title {stats.title_num}")

        report.loaded += 1
        report.sections_stored += stats.sections_ingested
        report.new_versions += stats.new_section_versions
        report.deduped_versions += stats.deduped_section_versions
        say(
            f"load  {task.key} — {stats.sections_ingested} sections "
            f"({stats.new_section_versions} new, {stats.deduped_section_versions} deduped)"
        )

    report.elapsed_seconds = time.monotonic() - started
    return report


@contextmanager
def _extracted(zip_path: Path) -> Iterator[Path]:
    """Unpack a title zip into a temp dir that is removed on the way out.

    Keeps peak disk at one title's XML rather than the whole corpus's.
    """
    with tempfile.TemporaryDirectory(prefix="usc-load-") as directory:
        with zipfile.ZipFile(zip_path) as archive:
            members = [n for n in archive.namelist() if n.lower().endswith(".xml")]
            if len(members) != 1:
                raise ValueError(f"{zip_path}: expected one .xml member, found {members}")
            yield Path(archive.extract(members[0], path=directory))


def default_ledger(dest_dir: Path = DOWNLOAD_DIR) -> DownloadLedger:
    return DownloadLedger.load(dest_dir / "ledger.json")


__all__ = [
    "LedgerEntry",
    "LoadAllReport",
    "LoadTask",
    "completed_pairs",
    "default_ledger",
    "plan_loads",
    "run_load_all",
]
