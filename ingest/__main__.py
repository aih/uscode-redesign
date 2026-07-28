"""`python -m ingest load <xmlfile> --release <label>` — see CLAUDE.md Commands."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from db.base import SessionLocal
from ingest.load import LoadStats, load_release
from ingest.manifest import write_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ingest")
    subparsers = parser.add_subparsers(dest="command", required=True)

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
        "(source USLM files carry no currency date of their own)",
    )
    load_parser.add_argument(
        "--source-url", default=None, help="Origin URL, recorded in the provenance manifest"
    )

    args = parser.parse_args(argv)
    if args.command == "load":
        return _cmd_load(args)
    return 1  # pragma: no cover - unreachable while "load" is the only subcommand


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
        )
    except Exception as exc:
        session.rollback()
        print(f"ingest failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()

    manifest_path = write_manifest(
        args.release, args.xmlfile, stats, source_url=args.source_url
    )

    print(
        f"Loaded title {stats.title_num} @ {args.release}: "
        f"{stats.sections_ingested} sections stored "
        f"({stats.new_section_versions} new, {stats.deduped_section_versions} deduped); "
        f"raw <section> elements in file: {stats.raw_section_elements}"
    )
    print(f"status counts: {stats.status_counts}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
