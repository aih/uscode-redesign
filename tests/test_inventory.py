"""Release-point inventory parsing, against a verbatim slice of OLRC's page.

Every assertion here is a case the real page contains — see the fixture's header
comment. Nothing in this file touches the network.
"""

from datetime import date

import pytest

from ingest.inventory import (
    InventoryParseError,
    ReleasePointEntry,
    latest_release_affecting,
    normalize_title_num,
    parse_current_release_point,
    parse_inventory,
    read_inventory,
    title_zip_url,
    with_current_release_point,
    write_inventory,
)
from tests.conftest import FIXTURES


@pytest.fixture(scope="module")
def entries() -> list[ReleasePointEntry]:
    return parse_inventory((FIXTURES / "priorreleasepoints_slice.htm").read_text())


@pytest.fixture(scope="module")
def by_label(entries: list[ReleasePointEntry]) -> dict[str, ReleasePointEntry]:
    return {entry.label: entry for entry in entries}


def test_skips_commented_out_release_points(by_label):
    """`119-102` is in the markup but commented out: OLRC comments out the current
    release point on this page (`parse_current_release_point` reads it)."""
    assert "119-102" not in by_label
    assert "119-102not101" in by_label


def test_parses_label_date_and_titles(by_label):
    current = by_label["119-102not101"]
    assert current.currency_date == date(2026, 7, 12)
    assert current.titles_affected == ("05", "16")


def test_parses_singular_title(by_label):
    assert by_label["119-100"].titles_affected == ("47",)


def test_first_date_wins_when_an_entry_carries_two(by_label):
    """118-250's text ends "…and including Public Law 119-1 (January 29, 2025)" —
    a qualifier, not the currency date."""
    assert by_label["118-250not159"].currency_date == date(2025, 1, 4)


def test_parses_unpadded_date_and_pub_l_prose(by_label):
    assert by_label["116-155"].currency_date == date(2020, 8, 8)


def test_spelled_out_date_is_used_when_there_is_no_numeric_one(by_label):
    """115-40u1 is the one entry of 385 whose only date is prose — "(effective
    July 1, 2017)". Before it was handled the release point vanished from the
    inventory silently, and it is an RP that changed Title 16."""
    entry = by_label["115-40u1"]
    assert entry.currency_date == date(2017, 7, 1)
    assert "16" in entry.titles_affected


def test_parses_u1_update_labels(by_label):
    """`118-22u1` is a distinct release point from `118-22` (gotcha: labels carry
    an optional update suffix)."""
    entry = by_label["118-22u1"]
    assert entry.currency_date == date(2023, 12, 1)
    assert entry.titles_affected == ("11a", "18a", "28a")


def test_parses_affecting_without_a_preceding_comma(by_label):
    """117-102u1's text runs "…from Pub. L. 117-81 affecting title 10.\""""
    assert by_label["117-102u1"].titles_affected == ("10",)


def test_duplicate_entries_merge_and_union_their_titles(by_label, entries):
    """113-165 is listed twice with *different* affected titles; taking either one
    alone would drop the other's."""
    assert len([e for e in entries if e.label == "113-165"]) == 1
    assert by_label["113-165"].titles_affected == ("25", "39", "49")


def test_identical_duplicate_entries_collapse(entries):
    labels = [e.label for e in entries]
    assert labels.count("115-117not91not96not97") == 1
    assert len(labels) == len(set(labels))


def test_seq_is_assigned_oldest_first_from_page_order(entries):
    """Labels don't sort and dates tie; the page's newest-first order is the
    authority, so seq counts up from the oldest entry."""
    assert [e.seq for e in entries] == list(range(len(entries)))
    assert entries[0].label == "113-165"
    assert entries[-1].label == "119-102not101"
    dates = [e.currency_date for e in entries]
    assert dates == sorted(dates)


def test_rejects_markup_it_cannot_parse():
    with pytest.raises(InventoryParseError):
        parse_inventory("<html><body>the page moved</body></html>")


def test_warns_rather_than_silently_dropping_an_undated_entry():
    html = (
        '<ul class="releasepoints">'
        '<li class="releasepoint"><a class="releasepoint" '
        'href="releasepoints/us/pl/119/99/usc-rp@119-99.htm">Public Law 119-99 '
        "(06/12/2026), affecting title 16.</a></li>"
        '<li class="releasepoint"><a class="releasepoint" '
        'href="releasepoints/us/pl/119/98/usc-rp@119-98.htm">Public Law 119-98, '
        "affecting title 16.</a></li></ul>"
    )
    with pytest.warns(UserWarning, match="119-98"):
        entries = parse_inventory(html)

    assert [e.label for e in entries] == ["119-99"]


def test_normalize_title_num():
    assert normalize_title_num("16") == "16"
    assert normalize_title_num("5") == "05"
    assert normalize_title_num("18A") == "18a"
    with pytest.raises(ValueError):
        normalize_title_num("all titles")


def test_title_zip_url_keeps_the_label_intact():
    assert title_zip_url("119-99", "16") == (
        "https://uscode.house.gov/download/releasepoints/us/pl/119/99/xml_usc16@119-99.zip"
    )
    assert title_zip_url("116-344not283u1", "5").endswith(
        "/us/pl/116/344not283u1/xml_usc05@116-344not283u1.zip"
    )


def test_latest_release_affecting_picks_the_newest_prior_change(entries, by_label):
    """PLAN Day 1 item 3: the prior RP for a demo has to be one where the title
    actually changed, not just the numerically previous one."""
    current = by_label["119-102not101"]
    prior = latest_release_affecting(entries, "16", before_seq=current.seq)
    assert prior is not None
    assert prior.label == "119-99"  # 119-100 sits between them but only changed title 47


def test_latest_release_affecting_returns_none_when_nothing_matches(entries):
    assert latest_release_affecting(entries, "44", before_seq=0) is None


def test_inventory_round_trips_through_json(entries, tmp_path):
    path = write_inventory(entries, tmp_path / "uscreleasepoints.json")
    assert read_inventory(path) == entries


# ------------------------------------------------------- the current release point


@pytest.fixture(scope="module")
def current() -> ReleasePointEntry:
    return parse_current_release_point(
        (FIXTURES / "download_current_slice.htm").read_text()
    )


def test_current_release_point_label_and_date(current):
    assert current.label == "119-108"
    assert current.currency_date == date(2026, 9, 11)
    assert current.url.endswith("/releasepoints/us/pl/119/108/usc-rp@119-108.htm")


def test_current_release_point_titles_are_the_changed_rows(current):
    """Titles 26 and 31 are marked `usctitlechanged` in the slice; 1 and 5a are not."""
    assert current.titles_affected == ("26", "31")
    assert current.description == "Public Law 119-108 (09/11/2026), affecting titles 26, 31."


def test_current_release_point_rejects_a_page_without_xml_links():
    with pytest.raises(InventoryParseError):
        parse_current_release_point("<html><body>the page moved</body></html>")


def test_current_release_point_is_appended_as_newest(entries, current):
    merged = with_current_release_point(entries, current)
    assert merged[-1].label == "119-108"
    assert merged[-1].seq == len(entries)
    assert merged[:-1] == entries


def test_current_release_point_already_listed_changes_nothing(entries):
    listed = entries[-1]
    assert with_current_release_point(entries, listed) is entries


def test_current_release_point_older_than_the_list_is_refused(entries):
    stale = ReleasePointEntry(
        label="999-1",
        currency_date=date(2000, 1, 1),
        titles_affected=(),
        url="",
        description="",
    )
    with pytest.raises(InventoryParseError):
        with_current_release_point(entries, stale)
