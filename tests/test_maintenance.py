"""uscode.house.gov's maintenance notice is reported as maintenance.

While OLRC maintains the site its pages answer with a notice, and every parser
that reads one used to report that the markup had probably changed. The notice
page OLRC served on 2026-10-03 is `tests/fixtures/maintenance_notice.htm`;
the others are composed variants of the same shape, a sentence in an otherwise
empty page or the body of a 503.
"""

import datetime
import email.message
import io
import urllib.error

import pytest

from api.schemas import (
    MAINTENANCE_ERROR_PREFIX,
    ClassificationCheckOut,
    SourceCheckOut,
)
from ingest import classification as classification_mod
from ingest import inventory as inventory_mod
from ingest.classification import ClassificationParseError, parse_tables_index
from ingest.inventory import (
    InventoryParseError,
    parse_current_release_point,
    parse_inventory,
)
from ingest.maintenance import SourceUnderMaintenance, maintenance_notice
from storage.classification import ClassificationCheckInfo
from storage.repository import SourceCheckInfo
from tests.conftest import FIXTURES

NOTICES = [
    (
        "<html><head><title>Office of the Law Revision Counsel</title></head><body>"
        "<div id='banner'>United States Code</div>"
        "<p>The website is currently undergoing scheduled maintenance. "
        "Please check back later.</p></body></html>",
        "The website is currently undergoing scheduled maintenance.",
    ),
    (
        "<html><body><h1>Site Maintenance</h1>"
        "<p>uscode.house.gov is under maintenance and will return on Monday.</p>"
        "</body></html>",
        "uscode.house.gov is under maintenance and will return on Monday.",
    ),
    (
        "<html><body><p>This site is temporarily unavailable due to maintenance.</p>"
        "<script>var maintenance = true;</script></body></html>",
        "This site is temporarily unavailable due to maintenance.",
    ),
    (
        "<html><body><p>We&rsquo;re down for maintenance</p></body></html>",
        "We’re down for maintenance",
    ),
]

SOURCE_PAGES = [
    "priorreleasepoints_slice.htm",
    "download_current_slice.htm",
    "tables_slice.shtml",
    "priortables_slice.shtml",
    "tbl118pl_2nd_slice.htm",
    "ecct.html",
]


@pytest.mark.parametrize(("page", "sentence"), NOTICES)
def test_finds_the_sentence_that_announces_maintenance(page, sentence):
    assert maintenance_notice(page) == sentence


LIVE_NOTICE = (FIXTURES / "maintenance_notice.htm").read_text()


def test_finds_the_notice_uscode_house_gov_served():
    """The page's text as served on 2026-10-03, in reconstructed markup."""
    assert maintenance_notice(LIVE_NOTICE) == "Site is currently under maintenance"


@pytest.mark.parametrize(
    "parse",
    [parse_inventory, parse_current_release_point, parse_tables_index],
    ids=["prior release points", "current release point", "classification index"],
)
def test_every_poll_reports_the_notice_uscode_house_gov_served(parse):
    with pytest.raises(
        SourceUnderMaintenance, match="Site is currently under maintenance"
    ):
        parse(LIVE_NOTICE)


@pytest.mark.parametrize("name", SOURCE_PAGES)
def test_a_real_source_page_is_not_a_notice(name):
    assert maintenance_notice((FIXTURES / name).read_text(errors="replace")) is None


def test_a_page_that_merely_changed_is_not_a_notice():
    assert maintenance_notice("<html><body>the page moved</body></html>") is None


def test_maintenance_in_a_script_or_comment_is_not_a_notice():
    page = (
        "<html><body><!-- scheduled maintenance banner goes here -->"
        "<script>if (underMaintenance) { show('site maintenance is on') }</script>"
        "</body></html>"
    )
    assert maintenance_notice(page) is None


def test_a_long_notice_is_cut():
    page = "<p>The site is under maintenance " + "and more " * 100 + ".</p>"
    notice = maintenance_notice(page)
    assert notice is not None
    assert len(notice) == 300
    assert notice.endswith("…")


# -------------------------------------------------------------- the parsers


def test_the_inventory_reports_maintenance_rather_than_changed_markup():
    with pytest.raises(SourceUnderMaintenance) as raised:
        parse_inventory(NOTICES[0][0])
    assert raised.value.url == inventory_mod.PRIOR_RELEASE_POINTS_URL
    assert "under maintenance" in str(raised.value)
    assert "scheduled maintenance" in str(raised.value)
    assert "markup" not in str(raised.value)


def test_the_current_release_point_reports_maintenance():
    with pytest.raises(SourceUnderMaintenance) as raised:
        parse_current_release_point(NOTICES[1][0])
    assert raised.value.url == inventory_mod.CURRENT_RELEASE_POINT_URL


def test_the_classification_index_reports_maintenance():
    with pytest.raises(SourceUnderMaintenance):
        parse_tables_index(NOTICES[0][0])


def test_a_classification_table_reports_maintenance():
    with pytest.raises(SourceUnderMaintenance):
        classification_mod._extract_pre(NOTICES[0][0], "tbl119pl_2nd.htm")


def test_changed_markup_is_still_reported_as_changed_markup():
    with pytest.raises(InventoryParseError, match="probably changed"):
        parse_inventory("<html><body>the page moved</body></html>")
    with pytest.raises(ClassificationParseError, match="probably changed"):
        parse_tables_index("<html><body>the page moved</body></html>")


def _http_error(url: str, status: int, body: str) -> urllib.error.HTTPError:
    headers = email.message.Message()
    headers["Content-Type"] = "text/html; charset=utf-8"
    return urllib.error.HTTPError(
        url, status, "Service Unavailable", headers, io.BytesIO(body.encode())
    )


def test_a_503_carrying_the_notice_is_maintenance(monkeypatch):
    url = inventory_mod.PRIOR_RELEASE_POINTS_URL

    def fail(request, timeout):
        raise _http_error(url, 503, NOTICES[1][0])

    monkeypatch.setattr(inventory_mod.urllib.request, "urlopen", fail)
    with pytest.raises(SourceUnderMaintenance) as raised:
        inventory_mod.fetch_inventory_html(url)
    assert raised.value.url == url


def test_a_503_without_the_notice_is_the_http_error(monkeypatch):
    url = inventory_mod.PRIOR_RELEASE_POINTS_URL

    def fail(request, timeout):
        raise _http_error(url, 503, "<html><body>Service Unavailable</body></html>")

    monkeypatch.setattr(inventory_mod.urllib.request, "urlopen", fail)
    with pytest.raises(urllib.error.HTTPError):
        inventory_mod.fetch_inventory_html(url)


def test_a_classification_fetch_503_carrying_the_notice_is_maintenance(
    monkeypatch, tmp_path
):
    url = classification_mod.CLASSIFICATION_SOURCE_URL
    monkeypatch.setattr(classification_mod, "throttle", lambda: None)

    def fail(request, timeout):
        raise _http_error(url, 503, NOTICES[0][0])

    with pytest.raises(SourceUnderMaintenance):
        classification_mod.fetch_classification_page(
            url, cache_dir=tmp_path, opener=fail
        )
    assert list(tmp_path.iterdir()) == []


# -------------------------------------------------------------- the status API


def test_the_recorded_error_carries_the_prefix_the_api_reads():
    """`poll_source` records `f"{type(exc).__name__}: {exc}"`."""
    exc = SourceUnderMaintenance("https://uscode.house.gov/x", "Down for maintenance")
    assert f"{type(exc).__name__}: {exc}".startswith(MAINTENANCE_ERROR_PREFIX)


NOW = datetime.datetime(2026, 10, 3, 12, 0, tzinfo=datetime.timezone.utc)


def _source_check(error: str | None) -> SourceCheckInfo:
    return SourceCheckInfo(
        checked_at=NOW,
        source_url=inventory_mod.PRIOR_RELEASE_POINTS_URL,
        ok=error is None,
        release_points_seen=None,
        new_labels=(),
        latest_label=None,
        latest_currency_date=None,
        error=error,
    )


def test_the_status_says_when_the_source_was_under_maintenance():
    error = (
        f"SourceUnderMaintenance: {SourceUnderMaintenance('u', 'Down for maintenance')}"
    )
    out = SourceCheckOut.of(_source_check(error), url="u")
    assert out.under_maintenance
    assert not out.ok


@pytest.mark.parametrize(
    "error",
    [None, "InventoryParseError: no release points found", "URLError: timed out"],
)
def test_the_status_does_not_call_other_failures_maintenance(error):
    assert not SourceCheckOut.of(_source_check(error), url="u").under_maintenance


def test_the_classification_status_says_when_the_source_was_under_maintenance():
    check = ClassificationCheckInfo(
        checked_at=NOW,
        source_url=classification_mod.CLASSIFICATION_SOURCE_URL,
        ok=False,
        files_seen=None,
        changed_files=(),
        latest_covered_text=None,
        error="SourceUnderMaintenance: uscode.house.gov is under maintenance",
    )
    out = ClassificationCheckOut.of(check, url=check.source_url)
    assert out.under_maintenance
