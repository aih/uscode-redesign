"""Recover the Editorial Classification Change Table's history from the Wayback Machine.

OLRC publishes the ECCT as one rolling page, `classification/ecct.html`, rewritten
each session, and archives a session's table under a suffixed name
(`ecct_119-1.html`) only sometimes — the index pages linked two documents when
this was written, and `python -m ingest classification --probe-ecct` asks for the
archived names directly. What neither reaches is a session whose table was
overwritten and never archived. The Wayback Machine may hold it: every snapshot
of `ecct.html` describes the session its own explanation names
(`ingest.classification.ecct_session_from_page`).

    uv run python scripts/ecct_wayback.py                      # query, fetch, parse, write
    uv run python scripts/ecct_wayback.py --from-cache         # re-parse what was fetched

Writes:

  * `data/classification/wayback/ecct_{congress}-{session}.html` — each distinct
    snapshot, named by the session *its page* says it describes, so
    `python -m ingest classification --from-file data/classification/wayback`
    loads them as archived tables. Two snapshots of one session (the table grew
    between them) keep the later one, which is the fuller.
  * `docs/verification/ecct-history.json` — every distinct row across every
    snapshot, with the sessions and snapshot dates it was seen at.

Network is the Wayback Machine's CDX API and its `id_` raw-snapshot endpoint,
one request per snapshot under the shared ~1 req/sec throttle. Nothing here
touches uscode.house.gov.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest.classification import (  # noqa: E402
    ClassificationParseError,
    EcctEntry,
    ecct_session_from_page,
    parse_ecct,
)
from ingest.download import throttle  # noqa: E402
from ingest.inventory import USER_AGENT  # noqa: E402
from ingest.verification import write_verification_json  # noqa: E402

CDX_URL = "https://web.archive.org/cdx/search/cdx"
URL_PATTERN = "uscode.house.gov/classification/ecct*"
CACHE_DIR = Path("data/classification/wayback")
REPORT_NAME = "ecct-history.json"

Fetch = Callable[[str], str]


@dataclass(frozen=True, slots=True)
class CdxRow:
    timestamp: str
    original: str
    digest: str
    statuscode: str

    @property
    def snapshot_url(self) -> str:
        # `id_` asks for the archived bytes without the Wayback toolbar.
        return f"https://web.archive.org/web/{self.timestamp}id_/{self.original}"


def cdx_query_url(pattern: str = URL_PATTERN) -> str:
    query = urllib.parse.urlencode(
        {
            "url": pattern,
            "output": "json",
            "fl": "timestamp,original,digest,statuscode",
            "filter": "statuscode:200",
            "collapse": "digest",
        }
    )
    return f"{CDX_URL}?{query}"


def parse_cdx(body: str) -> list[CdxRow]:
    """The CDX API's JSON: a header row, then one row per capture. Collapsed on
    digest, so a page captured unchanged twenty times is one row."""
    rows = json.loads(body) if body.strip() else []
    if not rows:
        return []
    header, *captures = rows
    index = {name: position for position, name in enumerate(header)}
    return [
        CdxRow(
            timestamp=row[index["timestamp"]],
            original=row[index["original"]],
            digest=row[index["digest"]],
            statuscode=row[index["statuscode"]],
        )
        for row in captures
    ]


@dataclass(slots=True)
class Snapshot:
    timestamp: str
    original: str
    congress: int
    session: int
    entries: tuple[EcctEntry, ...]
    html: str = ""

    @property
    def filename(self) -> str:
        return f"ecct_{self.congress}-{self.session}.html"


def harvest(rows: list[CdxRow], fetch: Fetch, on_event: Callable[[str], None] | None = None) -> list[Snapshot]:
    """Fetch every capture, keep the ones that parse as an ECCT and say which
    session they describe. A capture whose page names no session is reported and
    dropped: a row with no session to belong to cannot be loaded."""
    say = on_event or (lambda _message: None)
    snapshots: list[Snapshot] = []
    for row in rows:
        html = fetch(row.snapshot_url)
        stated = ecct_session_from_page(html)
        if stated is None:
            say(f"{row.timestamp} {row.original}: no session named on the page; dropped")
            continue
        congress, session = stated
        try:
            parsed = parse_ecct(
                html,
                filename=f"ecct_{congress}-{session}.html",
                source_url=row.snapshot_url,
                congress=congress,
                session=session,
            )
        except ClassificationParseError as exc:
            say(f"{row.timestamp} {row.original}: {exc}; dropped")
            continue
        snapshots.append(
            Snapshot(row.timestamp, row.original, congress, session, parsed.entries, html)
        )
        say(f"{row.timestamp} {row.original}: {congress}-{session}, {len(parsed.entries)} rows")
    return snapshots


@dataclass(slots=True)
class HistoryRow:
    former_raw: str
    new_raw: str
    provision_affected: str
    provision_prompting: str
    sessions: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.former_raw, self.new_raw, self.provision_affected, self.provision_prompting)


def dedupe(snapshots: list[Snapshot]) -> list[HistoryRow]:
    """Every distinct row across every snapshot, in first-seen order, with the
    sessions it appeared under. The same move can be listed in two sessions'
    tables when OLRC carries a row forward; the row is one fact and is kept once."""
    rows: dict[tuple[str, str, str, str], HistoryRow] = {}
    for snapshot in sorted(snapshots, key=lambda s: s.timestamp):
        label = f"{snapshot.congress}-{snapshot.session}"
        for entry in snapshot.entries:
            row = HistoryRow(
                entry.former_raw, entry.new_raw, entry.provision_affected, entry.provision_prompting
            )
            kept = rows.setdefault(row.key, row)
            if label not in kept.sessions:
                kept.sessions.append(label)
            kept.first_seen = kept.first_seen or snapshot.timestamp
            kept.last_seen = snapshot.timestamp
    return list(rows.values())


def latest_per_session(snapshots: list[Snapshot]) -> dict[tuple[int, int], Snapshot]:
    """One snapshot per session — the latest capture, which is the fullest table."""
    chosen: dict[tuple[int, int], Snapshot] = {}
    for snapshot in sorted(snapshots, key=lambda s: s.timestamp):
        chosen[(snapshot.congress, snapshot.session)] = snapshot
    return chosen


def build_report(snapshots: list[Snapshot], rows: list[HistoryRow]) -> dict:
    return {
        "captures": len(snapshots),
        "sessions": sorted({f"{s.congress}-{s.session}" for s in snapshots}),
        "rows": len(rows),
        "by_session": {
            f"{c}-{s}": len(snapshot.entries)
            for (c, s), snapshot in sorted(latest_per_session(snapshots).items())
        },
        "history": [
            {
                "former": row.former_raw,
                "new": row.new_raw,
                "provision_affected": row.provision_affected,
                "provision_prompting": row.provision_prompting,
                "sessions": row.sessions,
                "first_seen": row.first_seen,
                "last_seen": row.last_seen,
            }
            for row in rows
        ],
    }


def _http_fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    throttle()
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, default=CACHE_DIR)
    parser.add_argument("--out", type=Path, default=Path("docs/verification"))
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="Re-parse the raw captures already under --cache instead of querying",
    )
    parser.add_argument("--pattern", default=URL_PATTERN)
    args = parser.parse_args(argv)

    raw_dir = args.cache / "captures"
    raw_dir.mkdir(parents=True, exist_ok=True)

    if args.from_cache:
        captures = sorted(raw_dir.glob("*.html"))
        rows = [
            CdxRow(path.stem.split("_", 1)[0], path.stem.split("_", 1)[1], path.stem, "200")
            for path in captures
        ]
        by_timestamp = {path.stem.split("_", 1)[0]: path for path in captures}

        def fetch(url: str) -> str:
            return by_timestamp[url.split("/web/")[1].split("id_/", 1)[0]].read_text()

    else:
        rows = parse_cdx(_http_fetch(cdx_query_url(args.pattern)))
        print(f"{len(rows)} distinct captures listed by the CDX API")

        def fetch(url: str) -> str:
            html = _http_fetch(url)
            timestamp, original = url.split("/web/")[1].split("id_/", 1)
            (raw_dir / f"{timestamp}_{original.replace('/', '_')}.html").write_text(html)
            return html

    snapshots = harvest(rows, fetch, on_event=print)
    for (congress, session), snapshot in sorted(latest_per_session(snapshots).items()):
        target = args.cache / snapshot.filename
        target.write_text(snapshot.html)
        print(f"{target}: {congress}-{session}, {len(snapshot.entries)} rows")

    history = dedupe(snapshots)
    path = write_verification_json(build_report(snapshots, history), REPORT_NAME, args.out)
    print(f"{len(history)} distinct rows across {len(snapshots)} captures → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
