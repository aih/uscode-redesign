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
    parse_inventory,
    read_inventory,
    title_zip_url,
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
    """`119-102` is in the markup but commented out — it was never published; only
    `119-102not101` was."""
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
