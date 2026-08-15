"""`/api/v1/classifications/…` against a loaded database (spec §4, §6, ADR-0067).

Everything here is answerable from the CI fixture corpus — the three committed
table slices `make ci-classification-data` loads (118th 2nd session, 110th 1st,
104th whole-congress) plus the ECCT — *and* from the full 144,837-row corpus a
development box holds. That is why the assertions name rows the slices carry and
never a total: `42 U.S.C. 254c-2` has rows in both, and a different number of
them in each.

These behaviours get more than one test, because each has already been got wrong
somewhere in this project:

  * **The dash spellings.** `section_norm` holds a plain hyphen and
    `usc_identifier` holds OLRC's EN DASH (gotcha 17), so a route taking typed
    input and a route taking an identifier match different columns and both have
    to accept both spellings.
  * **404 against an empty page.** `covered_ranges` is gap-aware, so "no table
    covers this law" and "a table covers it and it classified nothing" are
    different answers with different status codes.
  * **`sort=code`.** A title number is a string and sorting it as text gives
    `1, 10, 11, 11a, 12, … 2` (gotcha 16).
  * **Rows with holes in them.** 1,533 rows derive no identifier and 6,053 cite a
    Statutes at Large page with no integer form; both are returned rather than
    filtered out, and `stat_page_labels` is what carries the second.
  * **The by-identifier route's page.** 14 identifiers carry more than its
    default 200 rows and the order is newest law first, so an unreachable second
    page loses the oldest classifications silently.
"""

from __future__ import annotations

import re

import pytest

from storage.postgres import title_sort_key
from tests.conftest import _unavailable

#: The documents `make ci-classification-data` loads, which are the ones every
#: assertion below is written against.
REQUIRED_FILES = {(118, 2), (110, 1), (104, 0)}

#: A public law inside `tbl118pl_2nd.htm`'s covered range (35-274) that appears
#: in neither the slice nor the full table — the covered-but-empty case.
COVERED_BUT_EMPTY = (118, 37)

#: Past the last law of the 118th, so no document covers it either way.
UNCOVERED = (118, 500)


@pytest.fixture(scope="session")
def classification_loaded(loaded_database) -> None:
    """Skip unless the classification tables are loaded — `make ci-classification-data`."""
    from sqlalchemy import select

    from db.base import SessionLocal
    from db.models import ClassificationFile

    with SessionLocal() as session:
        held = {
            (row.congress, row.session)
            for row in session.scalars(
                select(ClassificationFile).where(ClassificationFile.kind == "pl")
            )
        }
    missing = REQUIRED_FILES - held
    if missing:  # pragma: no cover - environment-dependent
        _unavailable(
            "classification tables not loaded for "
            + ", ".join(f"{c}/{s}" for c, s in sorted(missing))
            + " — run `make ci-classification-data`"
        )


@pytest.fixture()
def api(client, classification_loaded):
    return client


def _rows(api, url: str) -> list[dict]:
    response = api.get(url)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _every_row(api, url: str, *, page: int = 500) -> list[dict]:
    """Every row of one listing, paged. The largest file paged here is 2,987 rows."""
    collected: list[dict] = []
    offset = 0
    while True:
        body = api.get(f"{url}&limit={page}&offset={offset}").json()
        collected.extend(body["items"])
        offset += page
        assert offset < 20_000, "paging never terminated"
        if offset >= body["total"]:
            return collected


# --------------------------------------------------------------- 1. the registry


def test_the_check_source_reports_the_first_load_date_before_any_check():
    """No check row → the baseline: the date the tables were first loaded,
    flagged so the reader names a date rather than 'no record of checking'.
    No database — this is `ClassificationCheckOut.of` alone."""
    from api.schemas import CLASSIFICATION_BASELINE_CHECKED_AT, ClassificationCheckOut

    out = ClassificationCheckOut.of(None, url="https://example.test/tables.shtml")
    assert out.baseline is True
    assert out.last_checked_at == CLASSIFICATION_BASELINE_CHECKED_AT
    assert out.last_checked_at.date().isoformat() == "2026-08-13"
    assert out.ok is True, "nothing failed — nothing was attempted"
    assert out.hours_since_check is not None
    assert out.url == "https://example.test/tables.shtml"


def test_a_recorded_check_is_not_a_baseline():
    import datetime

    from api.schemas import ClassificationCheckOut
    from storage import ClassificationCheckInfo

    info = ClassificationCheckInfo(
        checked_at=datetime.datetime.now(datetime.timezone.utc),
        source_url="https://uscode.house.gov/classification/tables.shtml",
        ok=True,
        files_seen=33,
        changed_files=(),
        latest_covered_text=None,
        error=None,
    )
    out = ClassificationCheckOut.of(info, url=info.source_url)
    assert out.baseline is False
    assert out.stale is False


def test_the_registry_lists_the_documents_and_when_it_last_looked(api):
    body = api.get("/api/v1/classifications/tables").json()

    assert body["source"]["url"].endswith("/classification/tables.shtml")
    assert body["entry_total"] > 0
    held = {(f["congress"], f["session"]) for f in body["files"] if f["kind"] == "pl"}
    assert REQUIRED_FILES <= held

    # The 104th is the one whole-congress file, and the registry spells its
    # session both ways: 0 is what it holds, `all` is what the reader's URLs say.
    whole = next(f for f in body["files"] if f["congress"] == 104 and f["kind"] == "pl")
    assert whole["session"] == 0
    assert whole["session_label"] == "all"
    assert whole["covered_ranges"] == ["1-333"]


def test_the_registry_names_the_newest_public_law_table_as_current(api):
    body = api.get("/api/v1/classifications/tables").json()
    pl_files = [f for f in body["files"] if f["kind"] == "pl"]
    assert body["current"] == pl_files[0]
    assert body["current"]["congress"] == max(f["congress"] for f in pl_files)


# ------------------------------------------------------------ 2. a session page


def test_a_session_page_returns_a_page_and_the_size_of_the_whole_set(api):
    body = api.get("/api/v1/classifications/tables/118/2/entries?limit=5").json()

    assert body["limit"] == 5
    assert body["offset"] == 0
    assert body["sort"] == "pl"
    assert len(body["items"]) == 5
    assert body["total"] > 5
    assert body["file"]["source_filename"] == "tbl118pl_2nd.htm"
    # The source's own order, which is what `sort=pl` means.
    assert [row["row_seq"] for row in body["items"]] == sorted(
        row["row_seq"] for row in body["items"]
    )


def test_an_offset_moves_the_window_without_changing_the_total(api):
    first = api.get("/api/v1/classifications/tables/118/2/entries?limit=3").json()
    second = api.get(
        "/api/v1/classifications/tables/118/2/entries?limit=3&offset=3"
    ).json()

    assert first["total"] == second["total"]
    assert second["offset"] == 3
    assert [r["row_seq"] for r in first["items"]] != [
        r["row_seq"] for r in second["items"]
    ]


def test_all_and_zero_name_the_same_whole_congress_document(api):
    by_word = api.get("/api/v1/classifications/tables/104/all/entries?limit=3").json()
    by_number = api.get("/api/v1/classifications/tables/104/0/entries?limit=3").json()

    assert by_word == by_number
    assert by_word["file"]["session_label"] == "all"
    assert all(row["session_label"] == "all" for row in by_word["items"])


def test_a_session_the_mirror_does_not_hold_is_a_404(api):
    response = api.get("/api/v1/classifications/tables/42/1/entries")
    assert response.status_code == 404
    assert "congress 42" in response.json()["detail"]


def test_a_session_that_is_not_a_number_is_a_422(api):
    response = api.get("/api/v1/classifications/tables/118/second/entries")
    assert response.status_code == 422
    assert "1, 2 or all" in response.json()["detail"]


def test_the_session_page_filters_by_law_by_title_and_by_section(api):
    by_law = _rows(api, "/api/v1/classifications/tables/118/2/entries?pl=118-84&limit=50")
    assert by_law
    assert {row["pl_label"] for row in by_law} == {"118-84"}

    # The congress in the path is the default, so a bare law number means the
    # same thing as the long form.
    bare = _rows(api, "/api/v1/classifications/tables/118/2/entries?pl=84&limit=50")
    assert [row["row_seq"] for row in bare] == [row["row_seq"] for row in by_law]

    by_title = _rows(api, "/api/v1/classifications/tables/118/2/entries?title=42&limit=50")
    assert by_title
    assert {row["title_num"] for row in by_title} == {"42"}

    by_section = _rows(
        api, "/api/v1/classifications/tables/118/2/entries?title=42&section=254c-2&limit=50"
    )
    assert by_section
    assert {row["section_norm"] for row in by_section} == {"254c-2"}


def test_the_section_filter_takes_the_en_dash_spelling_too(api):
    hyphen = _rows(
        api, "/api/v1/classifications/tables/118/2/entries?title=42&section=254c-2&limit=50"
    )
    en_dash = _rows(
        api,
        "/api/v1/classifications/tables/118/2/entries?title=42&section=254c–2&limit=50",
    )
    assert hyphen == en_dash
    assert hyphen


def test_a_malformed_pl_filter_is_a_422(api):
    response = api.get("/api/v1/classifications/tables/118/2/entries?pl=not-a-law")
    assert response.status_code == 422


def test_limit_is_bounded_at_500(api):
    assert api.get("/api/v1/classifications/tables/118/2/entries?limit=500").status_code == 200
    assert api.get("/api/v1/classifications/tables/118/2/entries?limit=501").status_code == 422
    assert api.get("/api/v1/classifications/tables/118/2/entries?limit=0").status_code == 422
    assert api.get("/api/v1/classifications/tables/118/2/entries?offset=-1").status_code == 422


# ------------------------------------------------------------------ sort=code


def _title_order(api, congress: int, session: str) -> list[str]:
    """The distinct title numbers of a whole document, in `sort=code` order."""
    rows = _every_row(
        api, f"/api/v1/classifications/tables/{congress}/{session}/entries?sort=code"
    )
    seen: list[str] = []
    for row in rows:
        if not seen or seen[-1] != row["title_num"]:
            seen.append(row["title_num"])
    return seen


def test_code_order_sorts_titles_the_way_the_code_does(api):
    """`5` before `10`, and `5a` between `5` and `6` — never as text.

    Two documents, because no single one of the three the CI corpus loads holds
    all three of `5`, `5a` and `10`: the 118th's second session carries `5` and
    `10`, and the 110th's first carries `5a`, `50` and `50a`.
    """
    order_118 = _title_order(api, 118, "2")
    assert order_118 == sorted(set(order_118), key=title_sort_key)
    assert order_118.index("5") < order_118.index("10")

    order_110 = _title_order(api, 110, "1")
    assert order_110 == sorted(set(order_110), key=title_sort_key)
    # An appendix title sits directly after its parent, and before the next
    # number — which is the whole reason `title_sort_key` exists.
    assert order_110.index("5a") < order_110.index("6") < order_110.index("10")
    assert order_110.index("50") < order_110.index("50a")


def test_code_order_pages_the_same_set_it_counts(api):
    whole = _every_row(api, "/api/v1/classifications/tables/110/1/entries?sort=code")
    body = api.get(
        "/api/v1/classifications/tables/110/1/entries?sort=code&limit=5&offset=2"
    ).json()

    assert body["total"] == len(whole)
    assert [row["row_seq"] for row in body["items"]] == [
        row["row_seq"] for row in whole[2:7]
    ]


# ------------------------------------------------------------- 3. a public law


def test_a_covered_law_that_classified_nothing_is_an_empty_page(api):
    congress, law = COVERED_BUT_EMPTY
    response = api.get(f"/api/v1/classifications/pl/{congress}/{law}")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    # The covering document is still named: this is "the table is here and this
    # law is in it", not "we have nothing".
    assert body["file"]["source_filename"] == "tbl118pl_2nd.htm"
    assert body["file"]["covered_ranges"] == ["35-274"]


def test_a_law_no_table_covers_is_a_404(api):
    congress, law = UNCOVERED
    response = api.get(f"/api/v1/classifications/pl/{congress}/{law}")

    assert response.status_code == 404
    assert response.json()["detail"] == (
        f"no classification table covers Public Law {congress}-{law}"
    )


def test_a_law_route_returns_its_rows_in_source_order(api):
    body = api.get("/api/v1/classifications/pl/118/84?limit=100").json()

    assert body["items"]
    assert {row["pl_label"] for row in body["items"]} == {"118-84"}
    assert [row["row_seq"] for row in body["items"]] == sorted(
        row["row_seq"] for row in body["items"]
    )
    assert body["file"]["congress"] == 118
    assert body["file"]["session_label"] == "2"


def test_a_law_route_filters_by_provision(api):
    rows = _rows(api, "/api/v1/classifications/pl/118/84?section=2(6)&limit=100")
    assert rows
    assert all(row["pl_section_raw"].startswith("2(6)") for row in rows)


# ----------------------------------------------------------- 4. a code section


def test_the_code_route_takes_a_hyphen_and_answers_with_the_en_dash(api):
    """The two spellings, in both directions.

    A reader types `254c-2` because no keyboard has U+2013; the corpus spells
    the identifier `/us/usc/t42/s254c–2`. Both have to work and the answer has
    to carry the corpus's spelling, or the link the reader follows 404s.
    """
    hyphen = api.get("/api/v1/classifications/code/42/254c-2?limit=50").json()
    en_dash = api.get("/api/v1/classifications/code/42/254c–2?limit=50").json()
    upper = api.get("/api/v1/classifications/code/42/254C-2?limit=50").json()

    assert hyphen["items"]
    assert hyphen == en_dash == upper
    assert {row["section_norm"] for row in hyphen["items"]} == {"254c-2"}
    assert {row["usc_identifier"] for row in hyphen["items"]} == {
        "/us/usc/t42/s254c–2"
    }


def test_the_code_route_reads_newest_law_first(api):
    """42 U.S.C. 201, which three different laws classified to — 118-86, 118-84
    and 110-18, in two documents. A section with one row cannot tell a sort from
    no sort at all, which is what this test asserted until it named this one."""
    rows = _rows(api, "/api/v1/classifications/code/42/201?limit=500")
    laws = [
        (row["pl_congress"], row["pl_num"])
        for row in rows
        if row["pl_congress"] is not None
    ]

    assert len(laws) >= 3
    assert laws == sorted(laws, reverse=True)
    known = [law for law in laws if law in {(118, 86), (118, 84), (110, 18)}]
    assert known == [(118, 86), (118, 84), (110, 18)]


def test_the_code_route_can_prefix_match(api):
    exact = _rows(api, "/api/v1/classifications/code/42/254c?limit=200")
    prefixed = _rows(api, "/api/v1/classifications/code/42/254c?exact=false&limit=200")

    assert len(prefixed) > len(exact)
    assert {row["section_norm"] for row in prefixed} >= {"254c-2"}


def test_a_section_nothing_was_classified_to_is_an_empty_page(api):
    response = api.get("/api/v1/classifications/code/42/99999999")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_a_row_with_no_usc_identifier_is_returned_rather_than_dropped(api):
    """1,533 rows derive none — 1,531 of them appendix rows, by rule."""
    rows = _every_row(api, "/api/v1/classifications/tables/110/1/entries?sort=pl")
    without = [row for row in rows if row["usc_identifier"] is None]

    assert without
    assert any(row["is_appendix"] for row in without)
    # The row is whole apart from the derived path: its raw line is there.
    assert all(row["raw_line"] for row in without)


def test_stat_page_labels_carry_a_page_that_is_not_a_number(api):
    """`3009-589` is one page of 110 Stat., not the range 3009 to 589.

    `stat_pages ARRAY(Integer)` cannot hold it and is empty for the 6,053 rows
    like it, so `stat_page_labels` is the column a display reads.
    """
    rows = _rows(api, "/api/v1/classifications/code/8/1229a?limit=50")
    assert rows

    labels = {label for row in rows for label in row["stat_page_labels"]}
    assert any(re.fullmatch(r"3009-\d+", label) for label in labels)

    lettered = [
        row
        for row in rows
        if any(not label.isdigit() for label in row["stat_page_labels"])
    ]
    assert lettered
    assert all(row["stat_pages"] == [] for row in lettered)


# ------------------------------------------------------------ 4b. a whole title


def test_the_title_route_answers_for_a_title_with_no_section(api):
    rows = _rows(api, "/api/v1/classifications/code/42?limit=500")

    assert rows
    assert {row["title_num"] for row in rows} == {"42"}


def test_the_title_route_holds_more_than_any_one_section_of_it(api):
    """The title is the union of its sections, so it cannot be smaller than the
    busiest one — and a title route that quietly filtered by something else
    would show here."""
    title = api.get("/api/v1/classifications/code/42?limit=1").json()
    section = api.get("/api/v1/classifications/code/42/254c-2?limit=1").json()

    assert section["total"] > 0
    assert title["total"] > section["total"]


def test_the_title_route_reads_newest_law_first(api):
    laws = [
        (row["pl_congress"], row["pl_num"])
        for row in _rows(api, "/api/v1/classifications/code/42?limit=500")
        if row["pl_congress"] is not None
    ]

    assert len(laws) >= 3
    assert laws == sorted(laws, reverse=True)


def test_the_title_route_narrows_to_one_congress(api):
    rows = _rows(api, "/api/v1/classifications/code/42?congress=110&limit=500")

    assert rows
    assert {row["pl_congress"] for row in rows} == {110}


def test_the_title_route_pages_without_changing_the_total(api):
    first = api.get("/api/v1/classifications/code/42?limit=2").json()
    second = api.get("/api/v1/classifications/code/42?limit=2&offset=2").json()

    assert first["total"] == second["total"]
    assert first["items"] != second["items"]
    assert second["offset"] == 2


def test_a_title_nothing_was_classified_to_is_an_empty_page(api):
    response = api.get("/api/v1/classifications/code/99")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


# ------------------------------------------------------------- 5. an identifier


def test_the_identifier_route_matches_both_dash_spellings(api):
    en_dash = api.get(
        "/api/v1/classifications/us/usc/t42/s254c–2"
    ).json()
    hyphen = api.get("/api/v1/classifications/us/usc/t42/s254c-2").json()

    assert en_dash["items"]
    assert en_dash == hyphen
    assert {row["usc_identifier"] for row in en_dash["items"]} == {
        "/us/usc/t42/s254c–2"
    }


def test_the_identifier_route_defaults_to_200_rows(api):
    body = api.get("/api/v1/classifications/us/usc/t18/s3551").json()
    assert body["limit"] == 200
    assert body["offset"] == 0
    assert body["file"] is None
    assert len(body["items"]) <= 200


def test_the_identifier_route_can_reach_past_its_default_page(api):
    """A section's history runs past 200 rows — 14 identifiers do, and
    `/us/usc/t10/s113` carries 412 — and the order is newest law first, so an
    unreachable second page would be the oldest classifications silently gone.
    """
    route = "/api/v1/classifications/us/usc/t42/s201"
    whole = _rows(api, f"{route}?limit=500")
    assert len(whole) >= 3, "need a section with enough history to page"

    first = api.get(f"{route}?limit=2").json()
    second = api.get(f"{route}?limit=2&offset=2").json()

    assert first["total"] == second["total"] == len(whole)
    assert second["offset"] == 2
    assert first["items"] == whole[:2]
    assert second["items"] == whole[2:4]
    # The last row of the history is reachable, which a fixed page would hide —
    # and it is the oldest, since the order is newest law first.
    last = api.get(f"{route}?limit=1&offset={len(whole) - 1}").json()
    assert last["items"] == whole[-1:]


def test_the_identifier_routes_limit_is_bounded_at_500(api):
    assert api.get("/api/v1/classifications/us/usc/t18/s3551?limit=500").status_code == 200
    assert api.get("/api/v1/classifications/us/usc/t18/s3551?limit=501").status_code == 422


def test_an_identifier_nothing_classifies_to_is_an_empty_page(api):
    response = api.get("/api/v1/classifications/us/usc/t99/s1")
    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total": 0,
        "limit": 200,
        "offset": 0,
        "sort": None,
        "file": None,
    }


# ---------------------------------------------------------------- 6. the lookup


def test_suggest_reads_public_law_shorthand(api):
    body = api.get("/api/v1/classifications/suggest?q=118-35").json()
    [suggestion] = body["suggestions"]

    assert suggestion["kind"] == "pl"
    assert suggestion["label"] == "Public Law 118-35"
    assert suggestion["congress"] == 118
    assert suggestion["session"] == 2
    assert suggestion["session_label"] == "2"
    assert suggestion["pl"] == "118-35"
    assert suggestion["pl_section"] is None
    assert suggestion["href"] == "/classification/118/2?pl=118-35"


def test_suggest_carries_a_provision_of_the_law_into_the_filter(api):
    body = api.get("/api/v1/classifications/suggest?q=118-35 101").json()
    [suggestion] = body["suggestions"]

    assert suggestion["pl_section"] == "101"
    assert suggestion["href"] == "/classification/118/2?pl=118-35&pl_section=101"
    assert suggestion["label"] == "Public Law 118-35 § 101"


@pytest.mark.parametrize(
    "query", ["pl 118-35", "PL 118-35", "Pub. L. 118-35", "Public Law 118-35"]
)
def test_suggest_reads_the_written_forms_of_a_public_law(api, query):
    body = api.get("/api/v1/classifications/suggest", params={"q": query}).json()
    assert [s["pl"] for s in body["suggestions"] if s["kind"] == "pl"] == ["118-35"]


def test_suggest_declines_a_law_no_table_covers(api):
    congress, law = UNCOVERED
    body = api.get(
        "/api/v1/classifications/suggest", params={"q": f"{congress}-{law}"}
    ).json()
    assert [s for s in body["suggestions"] if s["kind"] == "pl"] == []


def test_suggest_sends_a_resolvable_citation_to_the_sections_notes(api):
    """The citation half is `citeparse`, server-side. There is one citation
    parser in this project and it is in Python."""
    body = api.get("/api/v1/classifications/suggest?q=16 USC 45f").json()
    notes = [s for s in body["suggestions"] if s["kind"] == "section-notes"]

    assert len(notes) == 1
    assert notes[0]["identifier"] == "/us/usc/t16/s45f"
    assert notes[0]["fragment"] == "#section-notes"
    assert notes[0]["href"] == "/us/usc/t16/s45f#section-notes"
    assert notes[0]["title_num"] == "16"
    assert notes[0]["section"] == "45f"


def test_suggest_offers_the_classification_rows_for_a_section(api):
    body = api.get("/api/v1/classifications/suggest?q=42 USC 254c-2").json()
    rows = [s for s in body["suggestions"] if s["kind"] == "section-classifications"]

    assert len(rows) == 1
    assert rows[0]["title_num"] == "42"
    assert rows[0]["section"] == "254c-2"
    assert rows[0]["count"] > 0
    assert rows[0]["href"] == "/classification?title=42&section=254c-2"


def test_suggest_offers_the_rows_for_a_section_that_has_none(api):
    """The two readings of a citation are the same pair of choices every time.

    16 U.S.C. § 201 is in the Code and no table has a row for it — a section
    last amended before the 104th Congress, which is the case the destination
    page exists to explain and to link the notes from. Offering the choice only
    when rows exist would make the empty answer unreachable.
    """
    body = api.get("/api/v1/classifications/suggest?q=16 USC 201").json()
    rows = [s for s in body["suggestions"] if s["kind"] == "section-classifications"]

    assert [s["kind"] for s in body["suggestions"]] == [
        "section-notes",
        "section-classifications",
    ]
    assert rows[0]["count"] == 0
    assert rows[0]["href"] == "/classification?title=16&section=201"


@pytest.mark.parametrize("query", ["42 usc", "42 U.S.C.", "title 42", "TITLE 42"])
def test_suggest_reads_a_title_with_no_section(api, query):
    body = api.get("/api/v1/classifications/suggest", params={"q": query}).json()
    [suggestion] = [
        s for s in body["suggestions"] if s["kind"] == "title-classifications"
    ]

    assert suggestion["title_num"] == "42"
    assert suggestion["section"] is None
    assert suggestion["count"] > 0
    assert suggestion["href"] == "/classification?title=42"


def test_suggest_scoped_title_counts_the_rows_in_that_table_first(api):
    body = api.get(
        "/api/v1/classifications/suggest",
        params={"q": "42 usc", "congress": 118, "session": "2"},
    ).json()
    kinds = [s["kind"] for s in body["suggestions"]]
    assert kinds.index("title-in-table") < kinds.index("title-classifications")

    [scoped] = [s for s in body["suggestions"] if s["kind"] == "title-in-table"]
    assert scoped["congress"] == 118
    assert scoped["session_label"] == "2"
    assert scoped["title_num"] == "42"
    assert scoped["count"] > 0
    assert scoped["href"] == "/classification/118/2?title=42"


def test_suggest_a_title_no_table_has_classified_to_offers_nothing(api):
    """Title 99 is not a title of the Code, and the answer is an empty list
    rather than a link to a view with no rows in it."""
    body = api.get("/api/v1/classifications/suggest?q=title 99").json()
    assert body["suggestions"] == []


def test_suggest_answers_nothing_for_a_string_that_is_neither(api):
    body = api.get("/api/v1/classifications/suggest?q=conservation easements").json()
    assert body["suggestions"] == []
    assert body["query"] == "conservation easements"


# ------------------------------------------------- 6a. the lookup, table-scoped


def test_suggest_scoped_reads_a_bare_law_number_as_the_scoped_congress(api):
    body = api.get(
        "/api/v1/classifications/suggest",
        params={"q": "35", "congress": 118, "session": "2"},
    ).json()
    [suggestion] = [s for s in body["suggestions"] if s["kind"] == "pl"]

    assert suggestion["pl"] == "118-35"
    assert suggestion["href"] == "/classification/118/2?pl=118-35"


def test_suggest_scoped_carries_a_bare_provision_into_the_filter(api):
    body = api.get(
        "/api/v1/classifications/suggest",
        params={"q": "35 101", "congress": 118, "session": "2"},
    ).json()
    [suggestion] = [s for s in body["suggestions"] if s["kind"] == "pl"]

    assert suggestion["pl_section"] == "101"
    assert suggestion["href"] == "/classification/118/2?pl=118-35&pl_section=101"


def test_suggest_unscoped_reads_nothing_in_a_bare_number(api):
    """`35` names a law only when the request says which congress."""
    body = api.get("/api/v1/classifications/suggest?q=35").json()
    assert body["suggestions"] == []


def test_suggest_scoped_full_shorthand_still_names_its_own_congress(api):
    """`110-85` typed on the 118th's page is the 110th's law, not the 118th's."""
    body = api.get(
        "/api/v1/classifications/suggest",
        params={"q": "110-85", "congress": 118, "session": "2"},
    ).json()
    pls = [s for s in body["suggestions"] if s["kind"] == "pl"]
    assert [s["pl"] for s in pls] == ["110-85"]
    assert pls[0]["href"].startswith("/classification/110/1?")


def test_suggest_scoped_citation_counts_the_rows_in_that_table_first(api):
    body = api.get(
        "/api/v1/classifications/suggest",
        params={"q": "42 USC 254c-2", "congress": 118, "session": "2"},
    ).json()
    kinds = [s["kind"] for s in body["suggestions"]]
    assert "section-in-table" in kinds
    assert kinds.index("section-in-table") < kinds.index("section-classifications")

    [scoped] = [s for s in body["suggestions"] if s["kind"] == "section-in-table"]
    assert scoped["congress"] == 118
    assert scoped["session_label"] == "2"
    assert scoped["title_num"] == "42"
    assert scoped["section"] == "254c-2"
    assert scoped["count"] > 0
    assert scoped["href"] == "/classification/118/2?title=42&section=254c-2"


def test_suggest_scoped_citation_with_no_rows_in_that_table_offers_none(api):
    """The corpus-wide suggestions still answer; only the in-table one is
    absent. 42 U.S.C. 254c-2's rows are the 118th's — the 104th's file holds
    none."""
    body = api.get(
        "/api/v1/classifications/suggest",
        params={"q": "42 USC 254c-2", "congress": 104, "session": "all"},
    ).json()
    kinds = [s["kind"] for s in body["suggestions"]]
    assert "section-in-table" not in kinds
    assert "section-classifications" in kinds


def test_suggest_scope_naming_no_held_table_scopes_nothing(api):
    body = api.get(
        "/api/v1/classifications/suggest",
        params={"q": "35", "congress": 99, "session": "1"},
    ).json()
    assert body["suggestions"] == []


def test_suggest_never_reads_a_citation_as_a_bare_law(api):
    """`16 usc 3831` parses as a citation, so the bare-number reading is never
    tried — no `Public Law 118-16 § usc 3831`."""
    body = api.get(
        "/api/v1/classifications/suggest",
        params={"q": "16 usc 3831", "congress": 118, "session": "2"},
    ).json()
    assert [s for s in body["suggestions"] if s["kind"] == "pl"] == []


# ------------------------------------------------------------------ 7. the ECCT


def test_the_ecct_route_returns_the_whole_table(api):
    body = api.get("/api/v1/classifications/ecct").json()

    assert body["total"] == len(body["items"])
    assert body["items"]
    row = body["items"][0]
    assert row["former_raw"] and row["new_raw"]
    assert row["congress"] == max(entry["congress"] for entry in body["items"])


def test_the_ecct_route_filters_by_congress(api):
    body = api.get("/api/v1/classifications/ecct?congress=119").json()
    assert body["items"]
    assert {row["congress"] for row in body["items"]} == {119}

    empty = api.get("/api/v1/classifications/ecct?congress=104").json()
    assert empty == {"items": [], "total": 0}


# ---------------------------------------------------------------- cache policy


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/classifications/tables",
        "/api/v1/classifications/tables/118/2/entries?limit=1",
        "/api/v1/classifications/pl/118/84?limit=1",
        "/api/v1/classifications/code/42/254c-2?limit=1",
        "/api/v1/classifications/us/usc/t18/s3551",
        "/api/v1/classifications/suggest?q=118-35",
        "/api/v1/classifications/ecct",
    ],
)
def test_every_classification_route_revalidates(api, url):
    """Nothing here is pinned to a release point, and an old table can be
    editorially corrected — which is what the ECCT documents. So none of these
    answers is `immutable`."""
    from params import REVALIDATE

    assert api.get(url).headers["cache-control"] == REVALIDATE
