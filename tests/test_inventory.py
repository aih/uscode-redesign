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
    merge_inventory,
    normalize_title_num,
    parse_current_release_point,
    parse_inventory,
    parse_release_point_sections,
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


# --------------------------------------------- the relaunched site (ADR-0091)


@pytest.fixture(scope="module")
def relaunched_current() -> ReleasePointEntry:
    return parse_current_release_point(
        (FIXTURES / "download_relaunch_slice.html").read_text()
    )


@pytest.fixture(scope="module")
def relaunched_prior() -> list[ReleasePointEntry]:
    return parse_inventory((FIXTURES / "priorreleasepoints_relaunch_slice.html").read_text())


def test_relaunched_current_page_reads_label_date_and_changed_titles(relaunched_current):
    """download.html's links are rooted at the site (`download/releasepoints/…`)."""
    assert relaunched_current.label == "119-120"
    assert relaunched_current.currency_date == date(2026, 10, 7)
    assert relaunched_current.titles_affected == ("31", "42")


def test_relaunched_prior_page_is_one_section_per_release_point(relaunched_prior):
    assert [entry.label for entry in relaunched_prior] == ["119-118"]
    assert relaunched_prior[0].currency_date == date(2026, 9, 30)
    assert relaunched_prior[0].seq == 0


def test_relaunched_prior_page_marks_no_changed_titles(relaunched_prior):
    assert relaunched_prior[0].titles_affected == ()


def test_sections_are_read_newest_first():
    page = "".join(
        f'<h3 class="releasepointinformation">Public Law {label} ({day})</h3>'
        f'<a href="download/releasepoints/us/pl/119/{label[4:]}/xml_usc01@{label}.zip">[XML]</a>'
        for label, day in (("119-118", "09/30/2026"), ("119-115", "09/25/2026"))
    )
    assert [entry.label for entry in parse_release_point_sections(page)] == ["119-115", "119-118"]


def test_the_retired_pages_are_a_parse_failure_not_maintenance():
    """The old addresses answer 200 with a "Page Not Found" page."""
    page = (FIXTURES / "olrc_page_not_found.html").read_text()
    with pytest.raises(InventoryParseError):
        parse_inventory(page)
    with pytest.raises(InventoryParseError):
        parse_current_release_point(page)


def _known(*labels_and_days: tuple[str, date, tuple[str, ...]]) -> list[ReleasePointEntry]:
    return [
        ReleasePointEntry(
            label=label, currency_date=day, titles_affected=titles, url="", description=label, seq=seq
        )
        for seq, (label, day, titles) in enumerate(labels_and_days)
    ]


KNOWN = _known(
    ("119-108", date(2026, 9, 11), ("26", "31", "40")),
    ("119-110", date(2026, 9, 16), ("18", "28")),
    ("119-111", date(2026, 9, 18), ("05a", "22", "42")),
)
ALL_KNOWN_TITLES = ("05a", "18", "22", "26", "28", "31", "40", "42")


def test_merge_appends_the_window_after_a_gap_and_fetches_it_in_full(
    relaunched_prior, relaunched_current
):
    published = with_current_release_point(relaunched_prior, relaunched_current)
    merged = merge_inventory(KNOWN, published)

    assert [entry.label for entry in merged] == [
        "119-108", "119-110", "119-111", "119-118", "119-120"
    ]
    assert [entry.seq for entry in merged] == [0, 1, 2, 3, 4]
    assert merged[:3] == KNOWN
    # 119-118 follows release points the source no longer lists.
    assert merged[3].titles_affected == ALL_KNOWN_TITLES
    assert "between 119-111 and this one" in merged[3].description
    # 119-120's changed titles are a delta from 119-118, which is now held.
    assert merged[4].titles_affected == ("31", "42")


def test_merge_without_a_gap_keeps_the_sources_changed_titles(relaunched_current):
    known = _known(*[(e.label, e.currency_date, e.titles_affected) for e in KNOWN],
                   ("119-118", date(2026, 9, 30), ("10",)))
    prior = _known(("119-118", date(2026, 9, 30), ()))
    merged = merge_inventory(known, with_current_release_point(prior, relaunched_current))
    assert merged[-1].label == "119-120"
    assert merged[-1].titles_affected == ("31", "42")
    # What this site recorded for 119-118 stands over the prior page's blank.
    assert merged[-2].titles_affected == ("10",)


def test_merge_fetches_in_full_a_new_release_point_with_no_changed_titles():
    prior = _known(("119-111", date(2026, 9, 18), ()), ("119-118", date(2026, 9, 30), ()))
    merged = merge_inventory(KNOWN, prior)
    assert merged[-1].titles_affected == ALL_KNOWN_TITLES
    assert "does not mark" in merged[-1].description


def test_merge_with_nothing_new_is_the_known_inventory():
    assert merge_inventory(KNOWN, _known(("119-111", date(2026, 9, 18), ()))) == KNOWN


def test_merge_with_the_full_history_page_matches_appending(entries, current):
    published = with_current_release_point(entries, current)
    assert merge_inventory(entries, published) == published


def test_merge_refuses_a_new_release_point_older_than_the_newest_held():
    stale = _known(("119-109", date(2026, 9, 12), ("01",)))
    with pytest.raises(InventoryParseError):
        merge_inventory(KNOWN, stale)


def test_merge_refuses_a_new_release_point_listed_before_an_earlier_held_one():
    published = _known(("119-112", date(2026, 9, 19), ("01",)), ("119-111", date(2026, 9, 18), ()))
    with pytest.raises(InventoryParseError, match="newer than 119-111"):
        merge_inventory(KNOWN, published)


def test_merge_refuses_held_release_points_in_another_order():
    published = _known(("119-111", date(2026, 9, 18), ()), ("119-110", date(2026, 9, 16), ()))
    with pytest.raises(InventoryParseError):
        merge_inventory(KNOWN, published)


# ------------------------------------- the page of 2026-10-23 (ADR-0094)


@pytest.fixture(scope="module")
def listed_prior() -> list[ReleasePointEntry]:
    return parse_inventory((FIXTURES / "priorreleasepoints_li_label.html").read_text())


@pytest.fixture(scope="module")
def undated_current() -> ReleasePointEntry:
    return parse_current_release_point((FIXTURES / "download_undated.html").read_text())


def test_the_listed_prior_page_reads_labels_from_the_release_point_pages(listed_prior):
    """`download/119-121.html` → `119-121`, oldest first, back to January 2026."""
    labels = [entry.label for entry in listed_prior]
    assert len(labels) == 22
    assert labels[0] == "119-73not60"
    assert labels[-4:] == ["119-117", "119-118", "119-120", "119-121"]
    assert labels.index("119-102not101") + 1 == labels.index("119-102")
    assert [entry.seq for entry in listed_prior] == list(range(22))


def test_the_listed_prior_page_spells_dates_out_and_lists_changed_titles(listed_prior):
    by_label = {entry.label: entry for entry in listed_prior}
    assert by_label["119-121"].currency_date == date(2026, 10, 9)
    assert by_label["119-117"].titles_affected == ("16", "54")
    assert by_label["119-73not60"].titles_affected == ("11a", "18", "18a", "22", "28a", "34")
    assert by_label["119-121"].url == "https://uscode.house.gov/download/119-121.html"


def test_the_undated_current_page_reads_the_date_from_its_description(undated_current):
    assert undated_current.label == "119-124"
    assert undated_current.currency_date == date(2026, 10, 15)
    assert undated_current.description.startswith("Public Law 119-124 (10/15/2026)")


def test_the_undated_current_page_reads_changed_titles_from_their_zip_links(undated_current):
    """`<div class="usctitlechanged">16 - Conservation</div>` carries no `id`."""
    assert undated_current.titles_affected == ("16", "29")


def test_a_changed_appendix_row_reads_its_title_from_its_zip_link():
    page = (
        '<h3 class="releasepointinformation">Public Law 119-130</h3>'
        "<p>All files are current through Public Law 119-130 (November 2, 2026).</p>"
        '<div class="uscitem"><div class="usctitle">5 - Government</div>'
        '<a href="download/releasepoints/us/pl/119/130/xml_usc05@119-130.zip">[XML]</a></div>'
        '<div class="uscitem"><div class="usctitleappendixchanged">Appendix</div>'
        '<a href="download/releasepoints/us/pl/119/130/xml_usc05a@119-130.zip">[XML]</a></div>'
    )
    entry = parse_current_release_point(page)
    assert entry.titles_affected == ("05a",)


DEPLOYED = _known(
    ("119-103", date(2026, 9, 2), ("01", "05")),
    ("119-108", date(2026, 9, 11), ("26", "31", "40")),
    ("119-110", date(2026, 9, 16), ("18", "28")),
    ("119-111", date(2026, 9, 18), ("22", "26", "42", "50")),
    ("119-118", date(2026, 9, 30), ALL_KNOWN_TITLES),
    ("119-120", date(2026, 10, 7), ("31", "42")),
    ("119-121", date(2026, 10, 9), ALL_KNOWN_TITLES),
)
"""What the deployed site held on 2026-10-23 from 119-103 on: every release point
the listed page names but 119-117, which the page of 2026-10-12 did not list."""


def test_merge_places_a_release_point_the_site_never_held_where_the_source_lists_it(
    listed_prior, undated_current
):
    published = with_current_release_point(listed_prior, undated_current)
    window = [entry for entry in published if entry.currency_date >= date(2026, 9, 2)]
    merged = merge_inventory(DEPLOYED, window)

    assert [entry.label for entry in merged] == [
        "119-103", "119-108", "119-110", "119-111", "119-117",
        "119-118", "119-120", "119-121", "119-124",
    ]
    assert [entry.seq for entry in merged] == list(range(9))
    # Held entries keep everything but their position.
    held = [entry for entry in merged if entry.label != "119-117"][:-1]
    assert [(e.label, e.currency_date, e.titles_affected) for e in held] == [
        (e.label, e.currency_date, e.titles_affected) for e in DEPLOYED
    ]
    # 119-117 follows 119-111 here and on the source, so its titles are a delta
    # from text this site holds.
    assert merged[4].titles_affected == ("16", "54")
    assert merged[-1].titles_affected == ("16", "29")


def test_merge_fetches_in_full_an_inserted_release_point_whose_source_predecessor_is_not_held():
    """The changed titles are a delta from the release point the source lists
    before this one; when that is not the one before it here, the delta is from
    text this site does not hold."""
    # Nothing listed before it.
    merged = merge_inventory(
        KNOWN, _known(("119-109", date(2026, 9, 12), ("01",)), ("119-110", date(2026, 9, 16), ()))
    )
    assert [entry.label for entry in merged] == ["119-108", "119-109", "119-110", "119-111"]
    assert merged[1].titles_affected == ALL_KNOWN_TITLES

    # Listed after 119-108, but 119-110, which the source no longer lists, is between.
    merged = merge_inventory(
        KNOWN,
        _known(
            ("119-108", date(2026, 9, 11), ()),
            ("119-110u1", date(2026, 9, 17), ("01",)),
            ("119-111", date(2026, 9, 18), ()),
        ),
    )
    assert [entry.label for entry in merged] == ["119-108", "119-110", "119-110u1", "119-111"]
    assert merged[2].titles_affected == ALL_KNOWN_TITLES
    assert "between 119-110 and this one" in merged[2].description


def test_merge_refuses_an_inserted_release_point_dated_before_its_new_neighbour():
    published = _known(("119-109", date(2026, 9, 1), ("01",)), ("119-110", date(2026, 9, 16), ()))
    with pytest.raises(InventoryParseError, match="older than 119-108"):
        merge_inventory(KNOWN, published)
