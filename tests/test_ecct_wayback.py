"""The Wayback harvest script's pure parts (`scripts/ecct_wayback.py`).

The network half — the CDX query and the raw-snapshot fetch — is not tested;
what is, is that a CDX answer becomes captures, that captures become snapshots
dated by their own page, and that the same row seen in two sessions' tables is
one row of history.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tests.conftest import FIXTURES, REPO_ROOT

_SPEC = importlib.util.spec_from_file_location(
    "ecct_wayback", REPO_ROOT / "scripts" / "ecct_wayback.py"
)
wayback = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
# A `slots=True` dataclass under `from __future__ import annotations` resolves
# its module through sys.modules, so the script has to be registered first.
sys.modules[_SPEC.name] = wayback
_SPEC.loader.exec_module(wayback)


@pytest.fixture(scope="module")
def ecct_html() -> str:
    return (FIXTURES / "ecct.html").read_text()


def test_the_cdx_answer_becomes_captures_without_trusting_column_order():
    body = json.dumps(
        [
            ["original", "timestamp", "digest", "statuscode"],
            ["uscode.house.gov/classification/ecct.html", "20240115120000", "ABC", "200"],
            ["uscode.house.gov/classification/ecct.html", "20250301000000", "DEF", "200"],
        ]
    )
    rows = wayback.parse_cdx(body)
    assert [row.timestamp for row in rows] == ["20240115120000", "20250301000000"]
    assert rows[0].snapshot_url == (
        "https://web.archive.org/web/20240115120000id_/uscode.house.gov/classification/ecct.html"
    )
    assert wayback.parse_cdx("") == []


def test_the_query_collapses_on_digest_and_keeps_only_200s():
    url = wayback.cdx_query_url()
    assert "collapse=digest" in url and "filter=statuscode%3A200" in url
    assert "ecct%2A" in url


def test_captures_are_dated_by_their_own_page_and_deduped_across_sessions(ecct_html):
    older = ecct_html.replace("119th Congress, 2nd Session", "118th Congress, 1st Session")
    pages = {
        "https://web.archive.org/web/20230601000000id_/uscode.house.gov/classification/ecct.html": older,
        "https://web.archive.org/web/20230901000000id_/uscode.house.gov/classification/ecct.html": older,
        "https://web.archive.org/web/20260801000000id_/uscode.house.gov/classification/ecct.html": ecct_html,
        "https://web.archive.org/web/20260802000000id_/uscode.house.gov/classification/ecct.html": (
            "<html><body><p>nothing here</p></body></html>"
        ),
    }
    rows = [
        wayback.CdxRow(url.split("/web/")[1][:14], "uscode.house.gov/classification/ecct.html", str(i), "200")
        for i, url in enumerate(pages)
    ]
    events: list[str] = []
    snapshots = wayback.harvest(rows, lambda url: pages[url], on_event=events.append)

    assert [(s.congress, s.session) for s in snapshots] == [(118, 1), (118, 1), (119, 2)]
    assert any("no session named" in event for event in events)

    history = wayback.dedupe(snapshots)
    # The fixture's one row appears in both sessions' tables: one fact, two sessions.
    assert len(history) == 1
    assert history[0].sessions == ["118-1", "119-2"]
    assert history[0].first_seen == "20230601000000" and history[0].last_seen == "20260801000000"

    latest = wayback.latest_per_session(snapshots)
    assert latest[(118, 1)].timestamp == "20230901000000"
    assert latest[(118, 1)].filename == "ecct_118-1.html"

    report = wayback.build_report(snapshots, history)
    assert report["by_session"] == {"118-1": 1, "119-2": 1}
    assert report["captures"] == 3 and report["rows"] == 1
