"""`python -m ingest {inventory,fetch,load}` — see CLAUDE.md Commands."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from db.base import SessionLocal
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
