"""`python -m ingest {inventory,check,fetch,backfill,verify-downloads,load}` — CLAUDE.md Commands."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from db.base import SessionLocal
from ingest import backfill as backfill_mod
from ingest import classification as classification_mod
from ingest import inventory as inventory_mod
from ingest import load_all as load_all_mod
from ingest import mirror as mirror_mod
from ingest import verify as verify_mod
from ingest.download import DOWNLOAD_DIR, download_title_zip, extract_title_xml, sha256_file
from ingest.load import LoadStats, load_release
from ingest.manifest import write_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ingest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory_parser = subparsers.add_parser(
        "inventory", help="Fetch the release-point inventory and seed release_points"
    )
    inventory_parser.add_argument(
        "--url", default=inventory_mod.PRIOR_RELEASE_POINTS_URL, help="Source page"
    )
    inventory_parser.add_argument(
        "--out", type=Path, default=inventory_mod.INVENTORY_PATH, help="Inventory JSON path"
    )
    inventory_parser.add_argument(
        "--from-file",
        type=Path,
        default=None,
        help="Seed from an existing inventory JSON instead of fetching",
    )
    inventory_parser.add_argument(
        "--no-seed", action="store_true", help="Write the JSON but don't touch the database"
    )

    check_parser = subparsers.add_parser(
        "check",
        help="Poll uscode.house.gov for new release points, record the check, "
        "and exit 10 if there is anything new",
    )
    check_parser.add_argument(
        "--url", default=inventory_mod.PRIOR_RELEASE_POINTS_URL, help="Source page"
    )
    check_parser.add_argument(
        "--out", type=Path, default=inventory_mod.INVENTORY_PATH, help="Inventory JSON path"
    )

    fetch_parser = subparsers.add_parser(
        "fetch", help="Download and unpack one title's XML at one release point"
    )
    fetch_parser.add_argument("--release", required=True, help="Release label, e.g. 119-99")
    fetch_parser.add_argument("--title", required=True, help="Title number, e.g. 16")
    fetch_parser.add_argument("--dest", type=Path, default=DOWNLOAD_DIR)
    fetch_parser.add_argument("--force", action="store_true", help="Re-download if cached")

    backfill_parser = subparsers.add_parser(
        "backfill",
        help="Resumably download every title at every release point, driven by titlesAffected",
    )
    backfill_parser.add_argument(
        "--inventory",
        type=Path,
        default=inventory_mod.INVENTORY_PATH,
        help="Inventory JSON to plan from (run `python -m ingest inventory` first)",
    )
    backfill_parser.add_argument("--dest", type=Path, default=DOWNLOAD_DIR)
    backfill_parser.add_argument(
        "--ledger", type=Path, default=None, help="Ledger path (default: <dest>/ledger.json)"
    )
    backfill_parser.add_argument(
        "--title",
        action="append",
        default=None,
        metavar="NUM",
        help="Restrict to a title; repeatable. Default: every title in the inventory",
    )
    backfill_parser.add_argument(
        "--release",
        action="append",
        default=None,
        metavar="LABEL",
        help="Restrict to a release point; repeatable",
    )
    backfill_parser.add_argument(
        "--limit", type=int, default=None, help="Stop after N new downloads (for a trial run)"
    )
    backfill_parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="Skip the oldest release point's full-title sweep (deltas only)",
    )
    backfill_parser.add_argument(
        "--retry-unavailable",
        action="store_true",
        help="Re-ask for release/title pairs the server has already denied",
    )
    backfill_parser.add_argument(
        "--attempts", type=int, default=backfill_mod.DEFAULT_ATTEMPTS, help="Retries per file"
    )
    backfill_parser.add_argument(
        "--plan-only", action="store_true", help="Print what would be fetched and exit"
    )
    backfill_parser.add_argument("--quiet", action="store_true", help="Only print the summary")

    verify_parser = subparsers.add_parser(
        "verify-downloads", help="Hash-dedupe the downloaded corpus and write the report"
    )
    verify_parser.add_argument("--dest", type=Path, default=DOWNLOAD_DIR)
    verify_parser.add_argument("--ledger", type=Path, default=None)
    verify_parser.add_argument(
        "--deep",
        action="store_true",
        help="Re-hash every file on disk instead of trusting the ledger",
    )
    verify_parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/verification"),
        help="Directory for the committed report",
    )
    verify_parser.add_argument(
        "--no-write", action="store_true", help="Print the summary without writing the report"
    )

    mirror_parser = subparsers.add_parser(
        "mirror", help="Mirror the downloaded corpus to/from S3 (ADR-0013)"
    )
    mirror_sub = mirror_parser.add_subparsers(dest="direction", required=True)

    push_parser = mirror_sub.add_parser(
        "push", help="Upload corpus + inventory + manifests, then the ledger last"
    )
    push_parser.add_argument(
        "--bucket", default=None, help=f"S3 bucket (default: ${mirror_mod.BUCKET_ENV_VAR})"
    )
    push_parser.add_argument("--dest", type=Path, default=DOWNLOAD_DIR)
    push_parser.add_argument("--dry-run", action="store_true")

    pull_parser = mirror_sub.add_parser(
        "pull", help="Fetch the mirror (or a slice), then verify against the ledger"
    )
    pull_parser.add_argument(
        "--bucket", default=None, help=f"S3 bucket (default: ${mirror_mod.BUCKET_ENV_VAR})"
    )
    pull_parser.add_argument("--dest", type=Path, default=DOWNLOAD_DIR)
    pull_parser.add_argument(
        "--title", action="append", default=None, metavar="NUM",
        help="Restrict to a title; repeatable",
    )
    pull_parser.add_argument(
        "--release", action="append", default=None, metavar="LABEL",
        help="Restrict to a release point; repeatable",
    )
    pull_parser.add_argument(
        "--no-verify", action="store_true", help="Skip hashing what was pulled"
    )

    load_all_parser = subparsers.add_parser(
        "load-all", help="Load the whole downloaded corpus, ledger-driven, resumable"
    )
    load_all_parser.add_argument("--dest", type=Path, default=DOWNLOAD_DIR)
    load_all_parser.add_argument(
        "--inventory", type=Path, default=inventory_mod.INVENTORY_PATH
    )
    load_all_parser.add_argument(
        "--title", action="append", default=None, metavar="NUM", help="Restrict; repeatable"
    )
    load_all_parser.add_argument(
        "--release", action="append", default=None, metavar="LABEL", help="Restrict; repeatable"
    )
    load_all_parser.add_argument(
        "--limit", type=int, default=None, help="Stop after N titles (trial run)"
    )
    load_all_parser.add_argument(
        "--plan-only", action="store_true", help="Print what would be loaded and exit"
    )
    load_all_parser.add_argument(
        "--defer-version-changes",
        action="store_true",
        help="Skip the per-load version-change hook (ADR-0074), deleting the "
        "change rows of every section each load touches so the follow-up sees "
        "them as uncomputed; follow the run with `python -m ingest "
        "version-changes`, which computes each section once instead of once "
        "per release point that touched it",
    )
    load_all_parser.add_argument("--quiet", action="store_true")

    verify_parser2 = subparsers.add_parser(
        "verify", help="Check loaded counts against section_release_map and the source XML"
    )
    verify_parser2.add_argument(
        "--deep", action="store_true", help="Re-parse source XML (independent recount; slow)"
    )
    verify_parser2.add_argument("--dest", type=Path, default=DOWNLOAD_DIR)
    verify_parser2.add_argument(
        "--limit", type=int, default=None, help="Check only the first N title-versions"
    )
    verify_parser2.add_argument(
        "--out", type=Path, default=Path("docs/verification")
    )
    verify_parser2.add_argument("--no-write", action="store_true")

    classification_parser = subparsers.add_parser(
        "classification",
        help="Scrape and load OLRC's Classification Tables, hash-gated and resumable",
    )
    classification_parser.add_argument(
        "--congress", type=int, default=None, help="Restrict to one congress, e.g. 118"
    )
    classification_parser.add_argument(
        "--session",
        type=int,
        default=None,
        help="Restrict to one session: 1, 2, or 0 for the 104th's whole-congress file",
    )
    classification_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch and re-load every selected file, ignoring both gates",
    )
    classification_parser.add_argument(
        "--from-file",
        type=Path,
        default=None,
        metavar="DIR",
        help="Read the index pages and the tables from DIR instead of the network "
        "(what `make ci-data` uses); a linked file DIR does not hold is skipped",
    )
    classification_parser.add_argument(
        "--cache-dir", type=Path, default=classification_mod.CACHE_DIR
    )
    classification_parser.add_argument(
        "--out",
        type=Path,
        default=classification_mod.VERIFICATION_DIR,
        help="Directory for the committed per-file verification JSON",
    )
    classification_parser.add_argument(
        "--manifest", type=Path, default=classification_mod.MANIFEST_PATH
    )
    classification_parser.add_argument(
        "--no-load", action="store_true", help="Parse and write the artifacts only"
    )
    classification_parser.add_argument("--quiet", action="store_true")

    classification_check_parser = subparsers.add_parser(
        "classification-check",
        help="Poll the Classification Tables index page, record the check, and exit "
        "10 if any table has changed",
    )
    classification_check_parser.add_argument(
        "--url", default=classification_mod.CLASSIFICATION_SOURCE_URL, help="Source page"
    )
    classification_check_parser.add_argument(
        "--cache-dir", type=Path, default=classification_mod.CACHE_DIR
    )

    version_changes_parser = subparsers.add_parser(
        "version-changes",
        help="Classify version transitions (text/notes/structure) and attribute "
        "text changes to Public Laws via the classification tables (ADR-0074)",
    )
    version_changes_parser.add_argument(
        "--title",
        action="append",
        default=None,
        metavar="NUM",
        help="Restrict to a title; repeatable. Default: every loaded title",
    )
    version_changes_parser.add_argument(
        "--recompute",
        action="store_true",
        help="Redo sections whose change rows are already complete",
    )
    version_changes_parser.add_argument(
        "--reattribute",
        action="store_true",
        help="Recompute only the attribution and law rows (what a classification "
        "table change invalidates); never touches the content flags",
    )
    version_changes_parser.add_argument(
        "--report",
        action="store_true",
        help="After the run, write docs/verification/version-changes.json from "
        "the stored rows; composes with --title/--recompute/--reattribute",
    )
    version_changes_parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Directory for the --report artifact (default: docs/verification)",
    )
    version_changes_parser.add_argument("--quiet", action="store_true")

    hf_export_parser = subparsers.add_parser(
        "hf-export",
        help="Export the corpus as Hugging Face parquet shards (ADR-0069)",
    )
    hf_export_parser.add_argument(
        "--out", type=Path, default=Path("data/hf"), help="Output directory"
    )
    hf_export_parser.add_argument(
        "--config",
        choices=("current", "versions"),
        action="append",
        default=None,
        help="Export one config (repeatable); default both",
    )
    hf_export_parser.add_argument("--batch-size", type=int, default=500)
    hf_export_parser.add_argument(
        "--limit", type=int, default=None, help="Export at most this many rows per config"
    )
    hf_export_parser.add_argument(
        "--force",
        action="store_true",
        help="Export even when the corpus fingerprint is unchanged",
    )

    hf_upload_parser = subparsers.add_parser(
        "hf-upload",
        help="Upload the exported shards (and card) to the Hugging Face dataset repo",
    )
    hf_upload_parser.add_argument("--repo", default=None, help="Dataset repo id")
    hf_upload_parser.add_argument(
        "--data-dir", type=Path, default=Path("data/hf"), help="Exported shards directory"
    )
    hf_upload_parser.add_argument(
        "--init",
        action="store_true",
        help="One-time setup: create the repo and upload the card; pushes no shards",
    )
    hf_upload_parser.add_argument(
        "--card",
        action="store_true",
        help="Also upload docs/hf/dataset-card.md as README.md",
    )
    hf_upload_parser.add_argument("--message", default=None, help="Commit message")
    hf_upload_parser.add_argument(
        "--private", action="store_true", help="Create the repo private (--init only)"
    )

    load_parser = subparsers.add_parser("load", help="Load one USLM title file")
    load_parser.add_argument("xmlfile", type=Path)
    load_parser.add_argument(
        "--release", required=True, help="Release point label, e.g. 119-102not101"
    )
    load_parser.add_argument(
        "--currency-date",
        type=date.fromisoformat,
        default=None,
        help="ISO date (YYYY-MM-DD); required the first time --release is ingested "
        "unless the release-point inventory already supplies it "
        "(source USLM files carry no currency date of their own)",
    )
    load_parser.add_argument(
        "--source-url", default=None, help="Origin URL, recorded in the provenance manifest"
    )
    load_parser.add_argument(
        "--source-zip",
        type=Path,
        default=None,
        help="The downloaded zip this XML came out of; its sha256 is what a "
        "re-download can be checked against",
    )

    args = parser.parse_args(argv)
    return {
        "inventory": _cmd_inventory,
        "check": _cmd_check,
        "fetch": _cmd_fetch,
        "backfill": _cmd_backfill,
        "verify-downloads": _cmd_verify_downloads,
        "mirror": _cmd_mirror,
        "load-all": _cmd_load_all,
        "verify": _cmd_verify,
        "classification": _cmd_classification,
        "classification-check": _cmd_classification_check,
        "version-changes": _cmd_version_changes,
        "hf-export": _cmd_hf_export,
        "hf-upload": _cmd_hf_upload,
        "load": _cmd_load,
    }[args.command](args)


def _cmd_inventory(args: argparse.Namespace) -> int:
    # Reading a file back is not a check of uscode.house.gov, and neither is a
    # run told not to touch the database, so neither writes a `source_checks`
    # row. Only a real fetch counts as having asked the source.
    if args.from_file is not None:
        entries = inventory_mod.read_inventory(args.from_file)
        print(f"read {len(entries)} release points from {args.from_file}")
        _print_span(entries)
        if args.no_seed:
            return 0
        session = SessionLocal()
        try:
            inserted, updated = inventory_mod.seed_release_points(session, entries)
            session.commit()
        except Exception as exc:
            session.rollback()
            print(f"seed failed: {exc}", file=sys.stderr)
            return 1
        finally:
            session.close()
        print(f"release_points seeded: {inserted} inserted, {updated} updated")
        return 0

    if args.no_seed:
        html = inventory_mod.fetch_inventory_html(args.url)
        entries = inventory_mod.parse_inventory(html)
        path = inventory_mod.write_inventory(entries, args.out, source_url=args.url)
        print(f"wrote {len(entries)} release points to {path}")
        _print_span(entries)
        return 0

    result = _poll(url=args.url, out_path=args.out)
    if not result.ok:
        print(f"inventory failed: {result.error}", file=sys.stderr)
        return 1
    print(f"wrote {len(result.entries)} release points to {args.out}")
    _print_span(result.entries)
    print(f"release_points seeded: {result.inserted} inserted, {result.updated} updated")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    """Poll uscode.house.gov, record the check, and say so in the exit code.

    Exit codes are the interface here, because the caller is a shell script on
    a box with no jq guarantee (deploy/update-corpus.sh):

        0   checked; nothing new
        10  checked; new release points published — run the full update
        1   the check itself failed

    The `source_checks` row is written in all three cases.
    """
    result = _poll(url=args.url, out_path=args.out)
    if not result.ok:
        print(f"check failed: {result.error}", file=sys.stderr)
        return 1

    newest = result.entries[-1]
    print(
        f"checked {args.url}: {len(result.entries)} release points, "
        f"newest {newest.label} ({newest.currency_date})"
    )
    if not result.new_labels:
        print("nothing new since the last check")
        return 0
    print(f"NEW release points ({len(result.new_labels)}): {', '.join(result.new_labels)}")
    return 10


def _poll(*, url: str, out_path: Path) -> inventory_mod.CheckResult:
    """Run one poll in its own transaction, committing the check row either way."""
    session = SessionLocal()
    try:
        result = inventory_mod.poll_source(session, url=url, out_path=out_path)
        session.commit()
        return result
    except Exception as exc:
        # A failure to *record* the check — the database being down, say. The
        # poll's own failures are already inside CheckResult.
        session.rollback()
        return inventory_mod.CheckResult(
            ok=False, entries=[], new_labels=(), error=f"{type(exc).__name__}: {exc}"
        )
    finally:
        session.close()


def _print_span(entries: list[inventory_mod.ReleasePointEntry]) -> None:
    print(
        f"oldest: {entries[0].label} ({entries[0].currency_date}); "
        f"newest: {entries[-1].label} ({entries[-1].currency_date})"
    )


def _cmd_fetch(args: argparse.Namespace) -> int:
    try:
        zip_path = download_title_zip(
            args.release, args.title, dest_dir=args.dest, force=args.force
        )
        xml_path = extract_title_xml(zip_path)
    except Exception as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1
    print(f"zip: {zip_path} ({zip_path.stat().st_size:,} bytes, sha256 {sha256_file(zip_path)})")
    print(f"xml: {xml_path} ({xml_path.stat().st_size:,} bytes)")
    print(
        f"next: uv run python -m ingest load {xml_path} --release {args.release} "
        f"--source-zip {zip_path}"
    )
    return 0


def _ledger_path(args: argparse.Namespace) -> Path:
    return args.ledger if args.ledger is not None else args.dest / "ledger.json"


def _cmd_backfill(args: argparse.Namespace) -> int:
    if not args.inventory.exists():
        print(
            f"backfill failed: {args.inventory} does not exist — "
            "run `uv run python -m ingest inventory` first",
            file=sys.stderr,
        )
        return 1

    entries = inventory_mod.read_inventory(args.inventory)
    tasks = backfill_mod.plan_backfill(
        entries,
        titles=set(args.title) if args.title else None,
        releases=set(args.release) if args.release else None,
        include_baseline=not args.no_baseline,
    )

    print(
        f"{len(entries)} release points, {len(tasks)} title-downloads planned "
        f"(naive full crawl would be {len(entries) * len(backfill_mod.baseline_titles(entries)):,})"
    )
    if args.plan_only:
        for task in tasks:
            marker = "baseline" if task.baseline else "delta"
            print(f"  {task.key:<28} {marker:<9} {task.url}")
        return 0

    ledger = backfill_mod.DownloadLedger.load(_ledger_path(args))
    if ledger.entries:
        print(f"ledger: {len(ledger.entries)} recorded — {ledger.status_counts()}")

    try:
        report = backfill_mod.run_backfill(
            tasks,
            ledger,
            dest_dir=args.dest,
            attempts=args.attempts,
            retry_unavailable=args.retry_unavailable,
            limit=args.limit,
            on_event=None if args.quiet else print,
        )
    except KeyboardInterrupt:
        ledger.save()
        print(f"\ninterrupted — ledger saved to {ledger.path}; re-run to resume", file=sys.stderr)
        return 130

    print(
        f"\nplanned {report.planned}: {report.downloaded} downloaded, "
        f"{report.cached} cached, {report.adopted} adopted, {report.skipped} skipped, "
        f"{report.unavailable} unavailable, {report.failed} failed"
    )
    print(
        f"{report.bytes_downloaded / 1e9:.2f} GB fetched in "
        f"{report.elapsed_seconds / 60:.1f} min; ledger: {ledger.path}"
    )
    if report.failures:
        print("\nfailures (re-run to retry):", file=sys.stderr)
        for key, detail in report.failures[:20]:
            print(f"  {key}: {detail}", file=sys.stderr)
        if len(report.failures) > 20:
            print(f"  … and {len(report.failures) - 20} more", file=sys.stderr)
        return 1
    return 0


def _cmd_verify_downloads(args: argparse.Namespace) -> int:
    path = _ledger_path(args)
    if not path.exists():
        print(f"verify failed: no ledger at {path}", file=sys.stderr)
        return 1

    ledger = backfill_mod.DownloadLedger.load(path)
    report = backfill_mod.verify_ledger(ledger, deep=args.deep)

    print(
        f"{report.entries} ledger entries: {report.ok} ok, "
        f"{report.unavailable} unavailable, {report.failed} failed"
    )
    print(
        f"{report.distinct_hashes:,} distinct zips over {report.total_bytes / 1e9:.2f} GB "
        f"(baseline covers {report.baseline_titles} titles)"
    )
    if report.same_title_duplicates:
        print(
            f"\n{len(report.same_title_duplicates)} title(s) republished byte-identical "
            f"at more than one release point ({report.duplicate_bytes / 1e9:.2f} GB):"
        )
        for group in report.same_title_duplicates[:10]:
            print(f"  {', '.join(group.members)}")
        if len(report.same_title_duplicates) > 10:
            print(f"  … and {len(report.same_title_duplicates) - 10} more")
    if report.missing_files:
        print(f"\n{len(report.missing_files)} ledger entries have no file on disk")
    if report.cross_title_duplicates:
        print("\nDEFECT: different titles share a zip — URL construction is collapsing:")
        for group in report.cross_title_duplicates[:10]:
            print(f"  {', '.join(group.members)}")
    if report.integrity_failures:
        print("\nDEFECT: files on disk no longer match their recorded hash:")
        for failure in report.integrity_failures[:10]:
            print(f"  {failure}")

    if not args.no_write:
        written = backfill_mod.write_verification(report, directory=args.out)
        print(f"\nreport: {written}")
    return 0 if report.sound else 1


def _cmd_mirror(args: argparse.Namespace) -> int:
    try:
        if args.direction == "push":
            mirror_mod.push(args.bucket, dest_dir=args.dest, dry_run=args.dry_run)
            print("mirror push complete (ledger uploaded last)")
            return 0
        report = mirror_mod.pull(
            args.bucket,
            dest_dir=args.dest,
            titles=set(args.title) if args.title else None,
            releases=set(args.release) if args.release else None,
            verify=not args.no_verify,
        )
    except mirror_mod.MirrorError as exc:
        print(f"mirror failed: {exc}", file=sys.stderr)
        return 1

    if not report.pulled_ledger:
        print("mirror is empty (no ledger on S3) — nothing to pull; starting fresh is fine")
        return 0
    print(f"pulled; {report.verified}/{report.entries_checked} entries verified by hash")
    if report.missing:
        print(f"missing after pull: {', '.join(report.missing[:10])}", file=sys.stderr)
    if report.mismatched:
        print(f"HASH MISMATCH: {', '.join(report.mismatched[:10])}", file=sys.stderr)
    return 0 if report.sound else 1


def _cmd_load_all(args: argparse.Namespace) -> int:
    ledger = load_all_mod.default_ledger(args.dest)
    if not ledger.entries:
        print(f"nothing to load: no ledger at {args.dest / 'ledger.json'}", file=sys.stderr)
        return 1
    entries = inventory_mod.read_inventory(args.inventory)
    tasks = load_all_mod.plan_loads(
        ledger,
        entries,
        titles=set(args.title) if args.title else None,
        releases=set(args.release) if args.release else None,
    )
    print(f"{len(tasks)} downloaded title-versions available to load")
    if args.plan_only:
        for task in tasks[:50]:
            print(f"  seq {task.seq:>4}  {task.key}")
        if len(tasks) > 50:
            print(f"  … and {len(tasks) - 50} more")
        return 0

    try:
        report = load_all_mod.run_load_all(
            tasks,
            SessionLocal,
            limit=args.limit,
            on_event=None if args.quiet else print,
            defer_version_changes=args.defer_version_changes,
        )
    except KeyboardInterrupt:
        print("\ninterrupted — re-run to resume (the database is the state)", file=sys.stderr)
        return 130

    print(
        f"\nplanned {report.planned}: {report.loaded} loaded, {report.skipped} skipped, "
        f"{report.failed} failed"
    )
    print(
        f"{report.sections_stored:,} sections stored — {report.new_versions:,} new versions, "
        f"{report.deduped_versions:,} deduped ({report.dedupe_ratio:.1%})"
    )
    print(f"elapsed {report.elapsed_seconds / 60:.1f} min")
    if report.mismatches:
        print("\nTITLE MISMATCHES (file contents disagree with the URL):", file=sys.stderr)
        for line in report.mismatches[:10]:
            print(f"  {line}", file=sys.stderr)
    if report.failures:
        print("\nfailures (re-run to retry):", file=sys.stderr)
        for key, detail in report.failures[:20]:
            print(f"  {key}: {detail}", file=sys.stderr)
        return 1
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    ledger = load_all_mod.default_ledger(args.dest) if args.deep else None
    with SessionLocal() as session:
        report = verify_mod.verify_database(
            session, deep=args.deep, ledger=ledger, limit=args.limit
        )
    print(verify_mod.summarize(report))
    if not args.no_write:
        path = verify_mod.write_report(report, directory=args.out)
        print(f"report: {path}")
    return 0 if report.sound else 1


def _cmd_classification(args: argparse.Namespace) -> int:
    """Scrape the Classification Tables and load what changed.

    Resumable without a ledger, because the registry table *is* the ledger: a
    file whose covered-law sentence still matches is skipped without a request,
    and one that is fetched is skipped anyway if its `<PRE>` text hashes the
    same. A re-run over an up-to-date database is two requests and no writes.
    """
    report = classification_mod.run_classification_load(
        SessionLocal,
        congress=args.congress,
        session_num=args.session,
        force=args.force,
        from_dir=args.from_file,
        cache_dir=args.cache_dir,
        load=not args.no_load,
        verification_dir=args.out,
        manifest_path=args.manifest,
        on_event=None if args.quiet else print,
    )

    print(
        f"\n{report.links_seen} documents linked: {report.loaded} loaded, "
        f"{report.unchanged} unchanged, {len(report.skipped)} skipped, "
        f"{len(report.failures)} failed"
    )
    print(
        f"{report.rows_written:,} rows written in {report.elapsed_seconds:.1f}s; "
        f"artifacts: {args.out}/classification-*.json, {args.manifest}"
    )
    if report.failures:
        print("\nfailures (re-run to retry):", file=sys.stderr)
        for filename, detail in report.failures:
            print(f"  {filename}: {detail}", file=sys.stderr)
        return 1
    return 0


def _cmd_classification_check(args: argparse.Namespace) -> int:
    """Poll the Classification Tables index, record the check, say so in the exit code.

    The exit codes are `check`'s, for the same reason — the caller is a shell
    script on a box with no jq guarantee (deploy/update-corpus.sh):

        0   checked; no table has changed
        10  checked; a table has changed — run `python -m ingest classification`
        1   the check itself failed

    The `classification_source_checks` row is written in all three cases.
    """
    session = SessionLocal()
    try:
        result = classification_mod.poll_classification(
            session, url=args.url, cache_dir=args.cache_dir
        )
        session.commit()
    except Exception as exc:
        # A failure to *record* the check — the database being down, say. The
        # poll's own failures are already inside the result.
        session.rollback()
        result = classification_mod.ClassificationCheckResult(
            ok=False, links=(), changed_files=(), error=f"{type(exc).__name__}: {exc}"
        )
    finally:
        session.close()

    if not result.ok:
        print(f"classification check failed: {result.error}", file=sys.stderr)
        return 1

    print(f"checked {args.url}: {len(result.links)} documents linked")
    if result.latest_covered_text:
        print(f"newest table covers: {result.latest_covered_text}")
    if not result.has_changes:
        print("nothing changed since the last load")
        return 0
    print(f"CHANGED ({len(result.changed_files)}): {', '.join(result.changed_files)}")
    return 10


def _cmd_version_changes(args: argparse.Namespace) -> int:
    """Classify version transitions and attribute them (ADR-0074).

    Runs one action — compute (the default, resumable; `--recompute` redoes
    complete sections) or `--reattribute` (attribution + law rows only, no
    XML) — and then, when `--report` is given, writes the verification
    artifact. The flags compose: `--title 16 --report` computes Title 16 and
    then reports; `--report` alone verifies everything is computed (a fast
    skip scan) and reports. The artifact is always corpus-wide — `--title`
    bounds the compute, never the count — and lands in the repository's
    `docs/verification/` whatever directory the command was run from, unless
    `--out` says otherwise.
    """
    from ingest import version_changes as version_changes_mod

    if args.reattribute and args.recompute:
        print(
            "--reattribute and --recompute are different actions: --recompute "
            "redoes the content flags (use the default compute), --reattribute "
            "only the attribution. Pick one.",
            file=sys.stderr,
        )
        return 2

    on_event = None if args.quiet else print

    try:
        if args.reattribute:
            stats = version_changes_mod.run_reattribute(
                SessionLocal, titles=args.title, on_event=on_event
            )
            print(
                f"reattributed {stats.changes:,} change rows across "
                f"{stats.sections:,} sections; {stats.laws:,} law rows"
            )
        else:
            stats = version_changes_mod.run_compute(
                SessionLocal,
                titles=args.title,
                recompute=args.recompute,
                on_event=on_event,
            )
            print(
                f"{stats.sections:,} sections computed ({stats.skipped:,} already "
                f"complete, skipped): {stats.changes:,} change rows, "
                f"{stats.laws:,} law rows, {stats.hashes_computed:,} hashes back-filled"
            )
    except version_changes_mod.UnknownTitleError as exc:
        print(f"version-changes: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted — re-run to resume (the database is the state)", file=sys.stderr)
        return 130

    if args.report:
        with SessionLocal() as session:
            path = version_changes_mod.write_report(
                session, directory=args.out or version_changes_mod.VERIFICATION_DIR
            )
        print(f"report: {path}")
    return 0


_HF_DEPS_HINT = (
    "the HF dataset pipeline needs the `dataset` dependency group: "
    "run `uv sync --group dataset` (ADR-0069)"
)


def _cmd_hf_export(args: argparse.Namespace) -> int:
    # Lazy import: pyarrow lives in the `dataset` group so the API image and a
    # plain `uv sync` don't carry it, and `load-all` keeps working without it.
    try:
        from ingest import hf_export
    except ImportError as exc:
        print(f"hf-export unavailable ({exc}): {_HF_DEPS_HINT}", file=sys.stderr)
        return 1

    configs = tuple(args.config) if args.config else hf_export.CONFIGS
    report = hf_export.export(
        args.out,
        configs=configs,
        batch_size=args.batch_size,
        limit=args.limit,
        force=args.force,
    )
    return 0 if report else 1


def _cmd_hf_upload(args: argparse.Namespace) -> int:
    try:
        from ingest import hf_upload
    except ImportError as exc:
        print(f"hf-upload unavailable ({exc}): {_HF_DEPS_HINT}", file=sys.stderr)
        return 1

    kwargs = {}
    if args.repo:
        kwargs["repo_id"] = args.repo
    if args.init:
        url = hf_upload.init_repo(private=args.private, **kwargs)
        print(f"Repo ready: {url}")
        return 0
    url = hf_upload.upload(
        data_dir=args.data_dir,
        card=args.card,
        message=args.message,
        **kwargs,
    )
    print(f"Uploaded: {url}")
    return 0


def _cmd_load(args: argparse.Namespace) -> int:
    if not args.xmlfile.exists():
        print(f"ingest failed: {args.xmlfile} does not exist", file=sys.stderr)
        return 1

    session = SessionLocal()
    try:
        stats: LoadStats = load_release(
            args.xmlfile,
            args.release,
            session,
            currency_date=args.currency_date,
            source_zip=args.source_zip,
        )
    except Exception as exc:
        session.rollback()
        print(f"ingest failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()

    manifest_path = write_manifest(
        args.release,
        args.xmlfile,
        stats,
        source_url=args.source_url,
        source_zip=args.source_zip,
    )

    print(
        f"Loaded title {stats.title_num} @ {args.release}: "
        f"{stats.sections_ingested} sections stored "
        f"({stats.new_section_versions} new, {stats.deduped_section_versions} deduped); "
        f"raw <section> elements in file: {stats.raw_section_elements}"
    )
    print(f"status counts: {stats.status_counts}")
    print(f"structure nodes: {stats.structure_nodes}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
