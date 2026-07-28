"""Mirror the downloaded corpus to and from S3 (ADR-0013).

The 3,197-file corpus costs ~9 GB of storage and ~40 hours of deliberately
polite downloading. The bytes are cheap; the download time and the etiquette
budget with uscode.house.gov are not — so once fetched, the corpus is pushed to
S3 and every later consumer (a rebuild, CI, another machine, the EC2 box that
takes over the run) pulls from the mirror at full speed and never touches OLRC.

Transport is `aws s3 sync`/`cp` via subprocess — retries, multipart, and
credentials are its solved problems, and this module adds none of its own
dependencies. Trust is *not* delegated to it: a pull re-hashes what landed
against the ledger's recorded sha256s, so the mirror is verified, never assumed
(the same stance `verify-downloads` takes toward the local disk).

Layout under `s3://{bucket}/usc/`:

    releases/{label}/xml_usc{NN}@{label}.zip   — the corpus, as on disk
    releases/ledger.json                        — pushed LAST, see push()
    uscreleasepoints.json                       — the inventory the plan came from
    manifests/                                  — provenance manifests (PLAN §11.4)
    verification/downloads.json                 — the hash-dedupe report

Concurrency rule (ADR-0013): **the ledger's writer is wherever the backfill
runs; everyone else pulls.** A handoff is push-from-the-old-machine, then
pull-on-the-new-one — never two writers.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ingest.backfill import DownloadLedger, FetchStatus
from ingest.download import DOWNLOAD_DIR, sha256_file
from ingest.inventory import INVENTORY_PATH, normalize_title_num

BUCKET_ENV_VAR = "USC_MIRROR_BUCKET"
S3_PREFIX = "usc"
VERIFICATION_PATH = Path("docs/verification/downloads.json")

#: Runs one aws-cli invocation and returns its exit code. Injected by tests.
Runner = Callable[[list[str]], int]


class MirrorError(RuntimeError):
    """An aws-cli invocation that failed, or a bucket nobody named."""


def resolve_bucket(bucket: str | None) -> str:
    """`--bucket` wins, then $USC_MIRROR_BUCKET; normalized to `s3://name`."""
    name = bucket or os.environ.get(BUCKET_ENV_VAR)
    if not name:
        raise MirrorError(
            f"no bucket: pass --bucket or set {BUCKET_ENV_VAR} (e.g. in .env or the shell)"
        )
    if not name.startswith("s3://"):
        name = f"s3://{name}"
    return name.rstrip("/")


@dataclass
class PullReport:
    """What a pull brought and whether it matches the ledger it came with."""

    pulled_ledger: bool = False
    entries_checked: int = 0
    verified: int = 0
    missing: list[str] = field(default_factory=list)
    mismatched: list[str] = field(default_factory=list)

    @property
    def sound(self) -> bool:
        return not self.missing and not self.mismatched


def push(
    bucket: str | None = None,
    *,
    dest_dir: Path = DOWNLOAD_DIR,
    inventory_path: Path = INVENTORY_PATH,
    manifest_dir: Path = Path("data/manifests"),
    verification_path: Path = VERIFICATION_PATH,
    dry_run: bool = False,
    runner: Runner | None = None,
) -> None:
    """Upload corpus, inventory, manifests, verification — then the ledger, last.

    Ordering is the robustness property: the zips sync before `ledger.json` is
    copied, so a reader of the mirror never sees a ledger that references files
    the mirror doesn't hold yet. An interrupted push leaves the *previous*
    ledger advertising the previous, complete state.
    """
    base = resolve_bucket(bucket)
    run = runner or _default_runner
    extra = ["--dryrun"] if dry_run else []

    _check_aws_cli(runner)

    if dest_dir.exists():
        run_or_raise(
            run,
            ["aws", "s3", "sync", str(dest_dir), f"{base}/{S3_PREFIX}/releases",
             "--exclude", "*.part", "--exclude", "*.tmp", "--exclude", "ledger.json",
             *extra],
        )
    if inventory_path.exists():
        run_or_raise(
            run,
            ["aws", "s3", "cp", str(inventory_path),
             f"{base}/{S3_PREFIX}/{inventory_path.name}", *extra],
        )
    if manifest_dir.exists():
        run_or_raise(
            run,
            ["aws", "s3", "sync", str(manifest_dir), f"{base}/{S3_PREFIX}/manifests", *extra],
        )
    if verification_path.exists():
        run_or_raise(
            run,
            ["aws", "s3", "cp", str(verification_path),
             f"{base}/{S3_PREFIX}/verification/{verification_path.name}", *extra],
        )

    ledger_path = dest_dir / "ledger.json"
    if ledger_path.exists():
        run_or_raise(
            run,
            ["aws", "s3", "cp", str(ledger_path),
             f"{base}/{S3_PREFIX}/releases/ledger.json", *extra],
        )


def pull(
    bucket: str | None = None,
    *,
    dest_dir: Path = DOWNLOAD_DIR,
    inventory_path: Path = INVENTORY_PATH,
    titles: set[str] | None = None,
    releases: set[str] | None = None,
    verify: bool = True,
    runner: Runner | None = None,
) -> PullReport:
    """Fetch the mirror (or a title/release slice of it), then verify by hash.

    The ledger comes down first — it is both the resume state and the checklist
    the verification runs against. A fresh, empty mirror is not an error: the
    pull reports `pulled_ledger=False` and the caller starts from nothing, which
    is exactly the first-boot case on a new download box.
    """
    base = resolve_bucket(bucket)
    run = runner or _default_runner
    report = PullReport()

    _check_aws_cli(runner)

    dest_dir.mkdir(parents=True, exist_ok=True)
    ledger_code = run(
        ["aws", "s3", "cp", f"{base}/{S3_PREFIX}/releases/ledger.json",
         str(dest_dir / "ledger.json")]
    )
    report.pulled_ledger = ledger_code == 0
    if not report.pulled_ledger:
        return report  # nothing mirrored yet — a fresh bucket, not a failure

    run(
        ["aws", "s3", "cp", f"{base}/{S3_PREFIX}/uscreleasepoints.json",
         str(inventory_path)]
    )

    sync_cmd = ["aws", "s3", "sync", f"{base}/{S3_PREFIX}/releases", str(dest_dir),
                "--exclude", "ledger.json"]
    patterns = _include_patterns(titles, releases)
    if patterns is not None:
        sync_cmd += ["--exclude", "*"]
        for pattern in patterns:
            sync_cmd += ["--include", pattern]
    run_or_raise(run, sync_cmd)

    if verify:
        _verify_pull(dest_dir, titles, releases, report)
    return report


def _verify_pull(
    dest_dir: Path,
    titles: set[str] | None,
    releases: set[str] | None,
    report: PullReport,
) -> None:
    """Every `ok` ledger entry in the pulled slice must exist and hash correctly."""
    wanted_titles = {normalize_title_num(t) for t in titles} if titles else None
    ledger = DownloadLedger.load(dest_dir / "ledger.json")
    for entry in ledger.entries.values():
        if entry.status != FetchStatus.OK:
            continue
        if wanted_titles is not None and entry.title_num not in wanted_titles:
            continue
        if releases is not None and entry.release_label not in releases:
            continue
        report.entries_checked += 1
        resolved = ledger.resolve_path(entry)
        if resolved is None or not resolved.exists():
            report.missing.append(entry.key)
            continue
        if entry.sha256 is not None and sha256_file(resolved) != entry.sha256:
            report.mismatched.append(entry.key)
            continue
        report.verified += 1


def _include_patterns(
    titles: set[str] | None, releases: set[str] | None
) -> list[str] | None:
    """aws-cli include globs for a slice; None means everything.

    Multiple `--include` flags union, so title∩release needs the product of
    per-pair patterns rather than one pattern per axis.
    """
    if titles is None and releases is None:
        return None
    normalized = sorted(normalize_title_num(t) for t in titles) if titles else None
    if normalized and releases:
        return [f"{label}/xml_usc{t}@*" for label in sorted(releases) for t in normalized]
    if normalized:
        return [f"*/xml_usc{t}@*" for t in normalized]
    assert releases is not None
    return [f"{label}/*" for label in sorted(releases)]


def run_or_raise(run: Runner, cmd: list[str]) -> None:
    code = run(cmd)
    if code != 0:
        raise MirrorError(f"exit {code}: {' '.join(cmd)}")


def _check_aws_cli(runner: Runner | None) -> None:
    if runner is None and shutil.which("aws") is None:
        raise MirrorError(
            "aws CLI not found — install it (`brew install awscli` / "
            "`dnf install awscli-2`) and configure credentials"
        )


def _default_runner(cmd: list[str]) -> int:
    return subprocess.run(cmd, check=False).returncode  # noqa: S603 - argv built above, no shell
