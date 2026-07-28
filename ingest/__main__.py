"""`python -m ingest {inventory,fetch,backfill,verify-downloads,load}` — CLAUDE.md Commands."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from db.base import SessionLocal
from ingest import backfill as backfill_mod
from ingest import inventory as inventory_mod
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
        "fetch": _cmd_fetch,
        "backfill": _cmd_backfill,
        "verify-downloads": _cmd_verify_downloads,
        "load": _cmd_load,
    }[args.command](args)


def _cmd_inventory(args: argparse.Namespace) -> int:
    if args.from_file is not None:
        entries = inventory_mod.read_inventory(args.from_file)
        print(f"read {len(entries)} release points from {args.from_file}")
    else:
        html = inventory_mod.fetch_inventory_html(args.url)
        entries = inventory_mod.parse_inventory(html)
        path = inventory_mod.write_inventory(entries, args.out, source_url=args.url)
        print(f"wrote {len(entries)} release points to {path}")

    print(
        f"oldest: {entries[0].label} ({entries[0].currency_date}); "
        f"newest: {entries[-1].label} ({entries[-1].currency_date})"
    )
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
