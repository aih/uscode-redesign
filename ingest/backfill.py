"""Resumable bulk download of every title at every release point.

`downloadusc.py` in loadusc-xcitedb did this as one unattended pass with no
memory: interrupt it and the next run re-walked everything, trusting only
"directory exists" to decide what to skip. At ~3,200 files and tens of
gigabytes over a polite 1 req/sec link, a run is hours long and *will* be
interrupted, so the state has to survive the process.

Three ideas carry the design:

1. **`titlesAffected` is the plan.** Every release point republishes all ~58
   titles, but the inventory says which ones actually changed (CLAUDE.md gotcha
   10). Downloading only those turns 382 × 58 = 22,156 files into 3,146 — with
   the oldest release point fetched in full as the baseline, because
   `titlesAffected` describes a *delta* and a delta needs something to apply to.
   That baseline is what makes the retrieval rule work: a request for an RP that
   was never ingested is answerable from the newest ingested RP at or before it,
   which is only true if some earlier RP has the title at all.

2. **The ledger is a cache; the disk is the truth.** Every outcome is recorded in
   `data/releases/ledger.json`, but a missing record never means a missing file —
   on resume, a zip on disk with no ledger entry is re-hashed and adopted. So a
   ledger deleted, corrupted, or lost to a `kill -9` costs one hashing pass, not
   a re-download.

3. **Hash-dedupe is the verification step, not a storage trick.** Content dedupe
   proper happens at ingest, over guid-stripped section text (ADR-0007); these
   zips would never collapse anyway, since guids regenerate per release point and
   zip members carry timestamps. What identical bytes across two *different*
   (release, title) pairs actually prove is that something addressed the same
   file twice — the failure mode this downloader is most exposed to, given that
   every URL is constructed by string substitution. See `verify_ledger`.

ADR-0012 records what was reused from the original and what changed.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ingest.download import (
    DEFAULT_ATTEMPTS,
    DOWNLOAD_DIR,
    FetchStatus,
    Opener,
    fetch_zip,
    sha256_file,
    zip_target,
)
from ingest.inventory import ReleasePointEntry, normalize_title_num, title_zip_url

LEDGER_PATH = DOWNLOAD_DIR / "ledger.json"
LEDGER_VERSION = 1


@dataclass(frozen=True, slots=True)
class DownloadTask:
    release_label: str
    title_num: str
    seq: int
    """The release point's global ordering, so a run always goes oldest first."""

    baseline: bool = False
    """True for the oldest release point's full-title sweep, where the title is
    fetched because nothing earlier has it — not because it changed."""

    @property
    def key(self) -> str:
        return f"{self.release_label}/{self.title_num}"

    @property
    def url(self) -> str:
        return title_zip_url(self.release_label, self.title_num)


@dataclass
class LedgerEntry:
    """One (release, title) outcome. Serialized as-is into the ledger JSON."""

    release_label: str
    title_num: str
    status: str
    url: str
    path: str | None = None
    """Relative to the corpus directory (`data/releases/`), so a ledger pushed to
    the mirror resolves on any machine. Absolute paths from ledgers written before
    this rule still resolve — see `resolve_path`."""
    sha256: str | None = None
    bytes: int = 0
    http_status: int | None = None
    attempts: int = 0
    baseline: bool = False
    recorded_at: str = ""
    detail: str = ""

    @property
    def key(self) -> str:
        return f"{self.release_label}/{self.title_num}"

    @property
    def ok(self) -> bool:
        return self.status == FetchStatus.OK


class DownloadLedger:
    """Resumable record of what has been fetched, atomically persisted.

    Rewritten in full on each save (a few MB at 3,200 entries) rather than
    appended to: a whole-file `os.replace` is atomic on POSIX, so the ledger is
    never observed half-written, which an append-and-compact scheme would have to
    handle explicitly for the sake of writes that cost nothing next to a 5 MB
    download.
    """

    def __init__(self, path: Path = LEDGER_PATH):
        self.path = path
        self.entries: dict[str, LedgerEntry] = {}

    @classmethod
    def load(cls, path: Path = LEDGER_PATH) -> "DownloadLedger":
        ledger = cls(path)
        if not path.exists():
            return ledger
        document = json.loads(path.read_text())
        for record in document.get("entries", []):
            entry = LedgerEntry(**record)
            if entry.path is not None and Path(entry.path).is_absolute():
                # Ledgers written before paths went relative recorded the writing
                # machine's absolute paths. The layout contract has always been
                # {dest}/{label}/{filename}, so the last two parts are the truth.
                entry.path = str(Path(*Path(entry.path).parts[-2:]))
            ledger.entries[entry.key] = entry
        return ledger

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "ledger_version": LEDGER_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(self.entries),
            "entries": [asdict(e) for e in self._sorted()],
        }
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(document, indent=2) + "\n")
        os.replace(temporary, self.path)
        return self.path

    def record(self, entry: LedgerEntry) -> None:
        entry.recorded_at = datetime.now(timezone.utc).isoformat()
        self.entries[entry.key] = entry

    def get(self, task: DownloadTask) -> LedgerEntry | None:
        return self.entries.get(task.key)

    def resolve_path(self, entry: LedgerEntry) -> Path | None:
        """An entry's file on *this* machine: relative paths resolve against the
        ledger's own directory, so the same ledger works wherever it lands."""
        if entry.path is None:
            return None
        path = Path(entry.path)
        return path if path.is_absolute() else self.path.parent / path

    def _sorted(self) -> list[LedgerEntry]:
        return sorted(self.entries.values(), key=lambda e: (e.release_label, e.title_num))

    def status_counts(self) -> dict[str, int]:
        return dict(Counter(e.status for e in self.entries.values()))

    def total_bytes(self) -> int:
        return sum(e.bytes for e in self.entries.values())


@dataclass
class BackfillReport:
    planned: int = 0
    downloaded: int = 0
    cached: int = 0
    adopted: int = 0
    """Zips found on disk with no ledger entry, re-hashed and taken as done."""

    skipped: int = 0
    unavailable: int = 0
    failed: int = 0
    bytes_downloaded: int = 0
    elapsed_seconds: float = 0.0
    failures: list[tuple[str, str]] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.failed == 0


def baseline_titles(entries: Iterable[ReleasePointEntry]) -> tuple[str, ...]:
    """Every title the inventory has ever seen changed, normalized and sorted.

    Derived from the data rather than hard-coded to 1–54: against the current
    inventory this yields 58 — the 53 numbered titles that exist (there is no
    Title 53) plus the five appendix titles `05a`, `11a`, `18a`, `28a`, `50a`
    that CLAUDE.md gotcha 7 calls out as separate files.

    The one thing this cannot see is a title that never changed across the whole
    inventory; such a title would have to be added by hand. None exists today,
    and `verify_ledger` reports the baseline's title count so a future gap is
    visible rather than silent.
    """
    seen: set[str] = set()
    for entry in entries:
        seen.update(normalize_title_num(t) for t in entry.titles_affected)
    return tuple(sorted(seen))


def plan_backfill(
    entries: list[ReleasePointEntry],
    *,
    titles: set[str] | None = None,
    releases: set[str] | None = None,
    include_baseline: bool = True,
) -> list[DownloadTask]:
    """Expand the inventory into the list of (release, title) zips to fetch.

    Oldest release point first, so an interrupted run always leaves a *prefix* of
    history complete rather than a scatter, and so the baseline lands before
    anything that depends on it.
    """
    ordered = sorted(entries, key=lambda e: e.seq)
    if not ordered:
        return []

    wanted = {normalize_title_num(t) for t in titles} if titles else None
    tasks: list[DownloadTask] = []
    seen: set[str] = set()

    for index, entry in enumerate(ordered):
        if releases is not None and entry.label not in releases:
            continue
        if index == 0 and include_baseline:
            # The oldest release point is a full snapshot, not a delta.
            entry_titles = baseline_titles(ordered)
            baseline = True
        else:
            entry_titles = tuple(normalize_title_num(t) for t in entry.titles_affected)
            baseline = False

        for title_num in entry_titles:
            if wanted is not None and title_num not in wanted:
                continue
            task = DownloadTask(
                release_label=entry.label,
                title_num=title_num,
                seq=entry.seq,
                baseline=baseline,
            )
            if task.key in seen:
                continue
            seen.add(task.key)
            tasks.append(task)
    return tasks


def run_backfill(
    tasks: list[DownloadTask],
    ledger: DownloadLedger,
    *,
    dest_dir: Path = DOWNLOAD_DIR,
    attempts: int = DEFAULT_ATTEMPTS,
    retry_unavailable: bool = False,
    limit: int | None = None,
    save_every: int = 1,
    opener: Opener | None = None,
    on_event: Callable[[str], None] | None = None,
) -> BackfillReport:
    """Work the plan, skipping what the ledger already settles. Safe to re-run.

    `retry_unavailable` re-attempts release/title pairs the server has already
    denied. Off by default: an `unavailable` is an answer about what OLRC
    publishes, and re-asking 3,000 times a run is exactly the impoliteness the
    etiquette rule exists to prevent.
    """
    report = BackfillReport(planned=len(tasks))
    started = time.monotonic()
    say = on_event or (lambda message: None)
    completed_since_save = 0

    for task in tasks:
        if limit is not None and report.downloaded >= limit:
            report.skipped += 1
            continue

        target = zip_target(task.release_label, task.title_num, dest_dir=dest_dir)
        existing = ledger.get(task)
        if existing is not None and _settled(
            existing, target, retry_unavailable=retry_unavailable
        ):
            report.skipped += 1
            if existing.status == FetchStatus.UNAVAILABLE:
                report.unavailable += 1
            continue

        # A file on disk with no ledger entry: adopt it rather than re-download.
        # This is what makes a lost or deleted ledger cheap.
        if existing is None and target.exists():
            entry = LedgerEntry(
                release_label=task.release_label,
                title_num=task.title_num,
                status=str(FetchStatus.OK),
                url=task.url,
                path=str(target.relative_to(dest_dir)),
                sha256=sha256_file(target),
                bytes=target.stat().st_size,
                baseline=task.baseline,
                detail="adopted from disk",
            )
            ledger.record(entry)
            report.adopted += 1
            say(f"adopt  {task.key} ({entry.bytes:,} bytes)")
            completed_since_save += 1
        else:
            result = fetch_zip(task.url, target, attempts=attempts, opener=opener)
            entry = LedgerEntry(
                release_label=task.release_label,
                title_num=task.title_num,
                status=str(result.status),
                url=task.url,
                path=str(result.path.relative_to(dest_dir)) if result.path else None,
                sha256=result.sha256,
                bytes=result.bytes,
                http_status=result.http_status,
                attempts=result.attempts,
                baseline=task.baseline,
                detail=result.detail,
            )
            ledger.record(entry)
            completed_since_save += 1

            if result.status is FetchStatus.OK:
                if result.cached:
                    report.cached += 1
                    say(f"cached {task.key} ({entry.bytes:,} bytes)")
                else:
                    report.downloaded += 1
                    report.bytes_downloaded += result.bytes
                    say(f"get    {task.key} ({entry.bytes:,} bytes)")
            elif result.status is FetchStatus.UNAVAILABLE:
                report.unavailable += 1
                say(f"none   {task.key} — {result.detail}")
            else:
                report.failed += 1
                report.failures.append((task.key, result.detail))
                say(f"FAIL   {task.key} — {result.detail}")

        if completed_since_save >= save_every:
            ledger.save()
            completed_since_save = 0

    if completed_since_save:
        ledger.save()
    report.elapsed_seconds = time.monotonic() - started
    return report


def _settled(entry: LedgerEntry, target: Path, *, retry_unavailable: bool) -> bool:
    """Whether a ledger entry means "don't ask again this run".

    The existence check is against where the file belongs *on this machine* —
    never against the recorded path string, which may have been written on
    another machine before the ledger travelled through the mirror."""
    if entry.status == FetchStatus.OK:
        return target.exists()
    if entry.status == FetchStatus.UNAVAILABLE:
        return not retry_unavailable
    return False  # `failed` is always worth another try


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------


@dataclass
class DuplicateGroup:
    sha256: str
    bytes: int
    members: list[str]

    @property
    def titles(self) -> set[str]:
        return {key.split("/", 1)[1] for key in self.members}

    @property
    def cross_title(self) -> bool:
        return len(self.titles) > 1


@dataclass
class VerificationReport:
    """What hash-dedupe over the downloaded corpus proves, and what it flags."""

    generated_at: str = ""
    entries: int = 0
    ok: int = 0
    unavailable: int = 0
    failed: int = 0
    distinct_hashes: int = 0
    total_bytes: int = 0
    duplicate_bytes: int = 0
    baseline_titles: int = 0
    same_title_duplicates: list[DuplicateGroup] = field(default_factory=list)
    cross_title_duplicates: list[DuplicateGroup] = field(default_factory=list)
    integrity_failures: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)

    @property
    def sound(self) -> bool:
        """Cross-title duplicates and integrity failures are defects; identical
        republications of the *same* title are a finding about OLRC, not a bug."""
        return not self.cross_title_duplicates and not self.integrity_failures

    def as_json(self) -> dict[str, object]:
        document = asdict(self)
        document["sound"] = self.sound
        return document


def verify_ledger(ledger: DownloadLedger, *, deep: bool = False) -> VerificationReport:
    """Hash-dedupe the downloaded corpus and report what the collisions mean.

    Two very different findings come out of the same grouping:

    * **Same title, different release points, identical bytes.** OLRC listed the
      title in `titlesAffected` but republished it unchanged. Real and expected
      at low rates; it is also the signature of the `u1` hazard — `118-22u1` and
      `118-22` are *different* release points, and if their files ever hash
      alike, one label is being served the other's content. Reported, not failed.

    * **Different titles, identical bytes.** Two distinct titles cannot have the
      same zip. This means URL construction collapsed two addresses into one —
      the single most likely way this downloader breaks, since every URL comes
      from string substitution on a label. Fails the report.

    `deep` re-hashes every file on disk instead of trusting the ledger, which is
    what makes the report a reproducible artifact rather than a restatement of
    what the downloader already believed (PLAN §11.5).
    """
    report = VerificationReport(generated_at=datetime.now(timezone.utc).isoformat())
    by_hash: dict[str, list[str]] = defaultdict(list)
    sizes: dict[str, int] = {}

    for entry in sorted(ledger.entries.values(), key=lambda e: (e.release_label, e.title_num)):
        report.entries += 1
        if entry.status == FetchStatus.UNAVAILABLE:
            report.unavailable += 1
            continue
        if entry.status == FetchStatus.FAILED:
            report.failed += 1
            continue
        report.ok += 1
        report.total_bytes += entry.bytes

        digest = entry.sha256
        resolved = ledger.resolve_path(entry)
        if resolved is None or not resolved.exists():
            report.missing_files.append(entry.key)
            continue
        if deep:
            recomputed = sha256_file(resolved)
            if entry.sha256 is not None and recomputed != entry.sha256:
                report.integrity_failures.append(
                    f"{entry.key}: ledger {entry.sha256[:12]}… != disk {recomputed[:12]}…"
                )
            digest = recomputed
        if digest is None:
            continue
        by_hash[digest].append(entry.key)
        sizes[digest] = entry.bytes

    report.distinct_hashes = len(by_hash)
    report.baseline_titles = len({e.title_num for e in ledger.entries.values() if e.baseline})

    for digest, members in sorted(by_hash.items()):
        if len(members) < 2:
            continue
        group = DuplicateGroup(sha256=digest, bytes=sizes[digest], members=sorted(members))
        report.duplicate_bytes += sizes[digest] * (len(members) - 1)
        if group.cross_title:
            report.cross_title_duplicates.append(group)
        else:
            report.same_title_duplicates.append(group)

    return report


def write_verification(
    report: VerificationReport, *, directory: Path = Path("docs/verification")
) -> Path:
    """Commit the hash-dedupe report as a reproducible artifact (documentation duty 5)."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "downloads.json"
    path.write_text(json.dumps(report.as_json(), indent=2, sort_keys=True) + "\n")
    return path
