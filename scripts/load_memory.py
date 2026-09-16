"""What the loader's dedupe lookup costs in memory, before and after ADR-0082.

    uv run python scripts/load_memory.py [--title 42]
        -> docs/verification/load-memory.json

`load_release` looks up every stored version of the title once, to decide
whether each section's text is new. Until ADR-0082 that lookup selected the
`SectionVersion` rows themselves, and the rows carry the text: for title 42
that is 136,213 versions and 3.8 GB of XML held in one dictionary, which is
what the 8 GB site box killed the loader for. The lookup now selects four
small columns (`ingest.load.known_versions_statement`).

Each measurement runs in a child process so the two do not share a heap, and
reports the child's peak resident set. The "before" is the old statement,
reconstructed here rather than kept in the code. Needs a database with the
title loaded; no network.
"""

from __future__ import annotations

import argparse
import datetime
import json
import resource
import subprocess
import sys
from pathlib import Path

ARTIFACT = Path(__file__).resolve().parent.parent / "docs" / "verification" / "load-memory.json"

BEFORE = """
from sqlalchemy import select
from db.base import SessionLocal
from db.models import Section, SectionVersion, Title
with SessionLocal() as session:
    title_id = session.scalar(select(Title.id).where(Title.num == %r))
    ids = list(session.scalars(select(Section.id).where(Section.title_id == title_id)))
    held = {}
    for version in session.scalars(select(SectionVersion).where(SectionVersion.section_id.in_(ids))):
        held.setdefault(version.section_id, {})[version.content_hash] = version
    print(sum(len(v) for v in held.values()))
"""

AFTER = """
from sqlalchemy import select
from db.base import SessionLocal
from db.models import Title
from ingest.load import known_versions_statement, _KnownVersion
with SessionLocal() as session:
    title_id = session.scalar(select(Title.id).where(Title.num == %r))
    held = {}
    for section_id, version_id, content_hash, first_release_id in session.execute(
        known_versions_statement(title_id)
    ):
        held.setdefault(section_id, {})[content_hash] = _KnownVersion(version_id, first_release_id)
    print(sum(len(v) for v in held.values()))
"""


def measure(code: str) -> dict[str, int]:
    """Run `code` in a child and return its peak RSS in bytes and the row count it printed."""
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    out = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    ).stdout.strip()
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    # ru_maxrss is bytes on macOS and kilobytes on Linux, and is the maximum over
    # all waited-for children — so the larger run has to go first for the second
    # reading to mean anything. Reported per run by running each in isolation
    # below; this delta is a sanity check only.
    del before, after
    return {"versions": int(out)}


def peak_rss_bytes(code: str) -> int:
    probe = (
        "import resource, sys, platform\n"
        + code
        + "\nrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
        "print(rss if platform.system() == 'Darwin' else rss * 1024, file=sys.stderr)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], check=True, capture_output=True, text=True
    )
    return int(result.stderr.strip().splitlines()[-1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", default="42")
    parser.add_argument("--out", type=Path, default=ARTIFACT)
    args = parser.parse_args()

    report = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "title": args.title,
        "what": (
            "peak resident set of a process that runs the loader's stored-version "
            "lookup for one title, before (SectionVersion rows, text included) and "
            "after (four columns) ADR-0082"
        ),
        "runs": {},
    }
    for name, code in (("after", AFTER), ("before", BEFORE)):
        versions = measure(code % args.title)["versions"]
        rss = peak_rss_bytes(code % args.title)
        report["runs"][name] = {"versions": versions, "peak_rss_bytes": rss}
        print(f"{name:>6}: {versions:,} versions, peak RSS {rss / 1e9:.2f} GB")
    before = report["runs"]["before"]["peak_rss_bytes"]
    after = report["runs"]["after"]["peak_rss_bytes"]
    report["ratio"] = round(before / after, 1) if after else None
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
