"""Classification-table parsing, against verbatim slices of OLRC's own pages.

Every assertion here is a case the real files contain — see each fixture's header
comment for what was kept and why. One test per hazard in
`docs/classification-spec.md` §1, plus the identifier-derivation rules. Nothing in
this file touches the network or a database.

`tests/fixtures/ecct.html` is the full page rather than a slice: the ECCT is one
small malformed table inside the site's chrome, and the chrome is part of what the
parser has to walk past.
"""

import warnings
from datetime import date

import pytest

from ingest.classification import (
    ClassificationEntry,
    ClassificationParseError,
    ParsedClassificationFile,
    TableLink,
    column_offsets,
    derive_usc_identifier,
    law_in_ranges,
    normalize_section,
    parse_classification_file,
    parse_covered_laws,
    parse_description,
    parse_ecct,
    parse_stat_pages,
    parse_tables_index,
)
from tests.conftest import FIXTURES


def _parse(fixture: str, filename: str) -> ParsedClassificationFile:
    """Parse a slice under the real file's name — the name carries congress and
    session, and the slice is a slice of that file."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a clean file must warn about nothing
        return parse_classification_file(
            (FIXTURES / fixture).read_text(), filename=filename
        )


@pytest.fixture(scope="module")
def modern() -> ParsedClassificationFile:
    return _parse("tbl118pl_2nd_slice.htm", "tbl118pl_2nd.htm")


@pytest.fixture(scope="module")
def older() -> ParsedClassificationFile:
    return _parse("tbl110pl_1st_slice.htm", "tbl110pl_1st.htm")


@pytest.fixture(scope="module")
def oldest() -> ParsedClassificationFile:
    return _parse("tbl104pl_slice.htm", "tbl104pl.htm")


HEADER = "Title Section      Description      Pub. L.  Sec.                  138 Stat."
RULER = "-------------      -----------      -------------                  ---------"
MODERN_OFFSETS = (0, 6, 19, 36, 45, 67)


def _line(
    title: str,
    section: str,
    description: str,
    pl: str,
    section_of_law: str,
    stat: str,
    *,
    offsets: tuple[int, ...] = MODERN_OFFSETS,
) -> str:
    """One fixed-width row, each cell laid out at the column it belongs to.

    Built rather than typed: a row whose columns are a character out is the exact
    defect several of the tests below are about, so the alignment cannot be left to
    counting spaces by eye.
    """
    line = ""
    for value, at in zip((title, section, description, pl, section_of_law, stat), offsets):
        line = line.ljust(at) + value
    return line


def _page(*lines: str, header: str = HEADER) -> str:
    body = "\n".join(lines)
    return f"<html><body><pre>\n U. S. Code\n{header}\n{RULER}\n{body}\n</pre></body></html>"


def _row(parsed: ParsedClassificationFile, raw_fragment: str) -> ClassificationEntry:
    matches = [e for e in parsed.entries if raw_fragment in e.raw_line]
    assert len(matches) == 1, f"{raw_fragment!r} matched {len(matches)} rows"
    return matches[0]


# --- entry pages -----------------------------------------------------------------


@pytest.fixture(scope="module")
def current_links() -> list[TableLink]:
    return parse_tables_index((FIXTURES / "tables_slice.shtml").read_text())


@pytest.fixture(scope="module")
def prior_links() -> list[TableLink]:
    return parse_tables_index((FIXTURES / "priortables_slice.shtml").read_text())


def test_index_keeps_public_law_order_and_drops_code_order(current_links, prior_links):
    """`cd` files are the same rows resorted and the PDF variants are the same file
    again; only `pl` HTML is scraped."""
    filenames = [link.filename for link in current_links + prior_links]
    assert not [name for name in filenames if "cd" in name or name.endswith(".pdf")]
    assert "tbl119pl_2nd.htm" in filenames
    assert "tbl109pl_1st.htm" in filenames


def test_index_reads_a_gap_written_inline(current_links):
    """"Public Law 119-70 and Public Laws 119-74 through 119-102" — 119-71 through
    119-73 were classified in the *first* session's table."""
    link = next(link for link in current_links if link.filename == "tbl119pl_2nd.htm")
    assert link.covered_laws_text == (
        "Public Law 119-70 and Public Laws 119-74 through 119-102"
    )
    assert link.covered_ranges == ("70-70", "74-102")
    assert (link.first_law, link.last_law) == (70, 102)
    assert law_in_ranges(70, link.covered_ranges)
    assert not law_in_ranges(72, link.covered_ranges)


def test_index_reads_a_gap_written_across_line_breaks(current_links):
    """The 119th 1st session's cell writes its second range on its own `<br/>` line."""
    link = next(link for link in current_links if link.filename == "tbl119pl_1st.htm")
    assert link.covered_laws_text == (
        "Public Laws 119-1 through 119-69 and 119-71 through 119-73"
    )
    assert link.covered_ranges == ("1-69", "71-73")


def test_index_stops_before_the_sorted_in_public_law_order_line(prior_links):
    """The words "Public Law" appear again between the range and the link, and a
    nearest-preceding-match search picks that up instead of the range."""
    link = next(link for link in prior_links if link.filename == "tbl118pl_2nd.htm")
    assert link.covered_laws_text == "Public Laws 118-35 to 118-274"


def test_index_reads_the_109ths_footnoted_gap_and_lone_law(prior_links):
    """109-173 was enacted in the 2nd session and classified in the 1st session's
    table; the page says so with a second range of one law and a `*` footnote."""
    second = next(link for link in prior_links if link.filename == "tbl109pl_2nd.htm")
    first = next(link for link in prior_links if link.filename == "tbl109pl_1st.htm")
    assert second.covered_ranges == ("170-172", "174-482")
    assert first.covered_ranges == ("1-169", "173-173")
    assert law_in_ranges(173, first.covered_ranges)


def test_the_104th_is_one_whole_congress_file(prior_links):
    """One file for both sessions, and a filename with no session in it. Session 0
    says "whole congress" rather than inventing one the source does not claim."""
    link = next(link for link in prior_links if link.filename == "tbl104pl.htm")
    assert (link.congress, link.session) == (104, 0)
    assert link.covered_ranges == ("1-333",)


def test_index_finds_both_ecct_links_and_dates_the_unsuffixed_one(current_links):
    """`ecct_119-1.html` names its session; `ecct.html` is the current one and names
    it only in the sentence that links it."""
    eccts = {link.filename: link for link in current_links if link.kind == "ecct"}
    assert set(eccts) == {"ecct.html", "ecct_119-1.html"}
    assert (eccts["ecct.html"].congress, eccts["ecct.html"].session) == (119, 2)
    assert (eccts["ecct_119-1.html"].congress, eccts["ecct_119-1.html"].session) == (119, 1)


def test_an_entry_page_with_no_tables_is_a_parse_error():
    with pytest.raises(ClassificationParseError):
        parse_tables_index("<html><body><p>Nothing here.</p></body></html>")


def test_covered_laws_accepts_both_through_and_to():
    assert parse_covered_laws("Public Laws 118-35 to 118-274")[0] == ("35-274",)
    assert parse_covered_laws("Public Laws 118-35 through 118-274")[0] == ("35-274",)
    assert parse_covered_laws("no laws here") == ((), None, None)


def test_table_links_round_trip_through_json(current_links):
    for link in current_links:
        assert TableLink.from_json(link.as_json()) == link


# --- hazard 1: column offsets come from the header line ---------------------------


def test_column_offsets_differ_by_vintage(modern, older, oldest):
    """The ruler under the header merges Title and Section into one dash group and
    can only ever give five offsets. The header gives six, and they move."""
    assert modern.column_offsets == (0, 6, 19, 36, 45, 67)
    assert older.column_offsets == (0, 6, 19, 36, 45, 67)
    assert oldest.column_offsets == (0, 6, 20, 42, 51, 68)


def test_a_boundary_the_files_own_rows_disagree_with_is_moved():
    """Measured over all 31 published tables: `tbl112pl_2nd.htm` and
    `tbl113pl_1st.htm` start their Sec. column one character to the left of where
    their header puts it. Read from the header alone, the Pub. L. cell of every row
    in those files ends in the first digit of the Sec. cell, and the guard against
    inventing a truncated law number left 3,717 rows with no public law at all."""
    shifted = [(0, 6, 19, 36, 44, 67)]
    parsed = parse_classification_file(
        _page(
            *(
                _line("42", f"50{n:02d}", "nt new", "113-2", f"1101({n})", "39", offsets=shifted[0])
                for n in range(25)
            )
        ),
        filename="tbl113pl_1st.htm",
    )

    assert parsed.column_offsets == (0, 6, 19, 36, 44, 67)
    assert {(row.pl_congress, row.pl_num) for row in parsed.entries} == {(113, 2)}
    assert parsed.entries[0].pl_section_raw == "1101(0)"
    assert parsed.warnings == ()


def test_a_file_too_small_to_measure_keeps_the_headers_answer():
    """One row that overruns is 100% of a one-row file. The smallest published
    table is 517 rows, so this only ever applies to a fragment."""
    parsed = parse_classification_file(
        _page(_line("42", "5121", "nt new", "113-2", "1101(a)", "39", offsets=(0, 6, 19, 36, 44, 67))),
        filename="tbl113pl_1st.htm",
    )
    assert parsed.column_offsets[4] == 45


def test_a_boundary_a_few_rows_overrun_is_left_where_the_header_put_it(modern, older, oldest):
    """Cells overrun their column legitimately (hazard 2), so the signal is the
    share of rows and not any single one — the worst legitimate overrun in the
    corpus is 3% of a file's rows."""
    assert modern.column_offsets[4] == 45
    assert older.column_offsets[4] == 45
    assert oldest.column_offsets[4] == 51


def test_a_missing_header_token_is_a_parse_error():
    """Guessing the offsets would put plausible garbage in every row of the file."""
    with pytest.raises(ClassificationParseError, match="Description"):
        column_offsets("Title Section      Pub. L.  Sec.        138 Stat.")


def test_a_page_with_no_pre_block_is_a_parse_error():
    with pytest.raises(ClassificationParseError, match="no <pre>"):
        parse_classification_file(
            "<html><body>Service unavailable</body></html>", filename="tbl118pl_2nd.htm"
        )


def test_a_pre_block_with_no_rows_is_a_parse_error():
    """Zero rows means the markup changed, not that a congress classified nothing."""
    page = (
        "<html><body><pre>\n U. S. Code\n"
        "Title Section      Description      Pub. L.  Sec.                  138 Stat.\n"
        "-------------      -----------      -------------                  ---------\n"
        "</pre></body></html>"
    )
    with pytest.raises(ClassificationParseError, match="no rows parsed"):
        parse_classification_file(page, filename="tbl118pl_2nd.htm")


def test_the_stat_volume_comes_from_the_column_header(modern, oldest):
    """`138 Stat.` gives every row of the 118th's second session its volume. The
    104th spans two volumes, writes `Stat. Page`, and so has none."""
    assert modern.stat_volume == 138
    assert all(entry.stat_volume == 138 for entry in modern.entries)
    assert oldest.stat_volume is None
    assert all(entry.stat_volume is None for entry in oldest.entries)


def test_the_prepared_date_is_read_from_the_head(modern, older, oldest):
    assert modern.prepared_date == date(2025, 1, 6)
    assert older.prepared_date == date(2009, 1, 8)
    # "November  12, 1996" — two spaces, and above it a "last updated" line this
    # file carries and the later ones do not.
    assert oldest.prepared_date == date(1996, 11, 12)


def test_the_104ths_unclosed_lowercase_pre_ends_at_the_enclosing_div(oldest):
    """That file opens `<pre>` above its own title page and never closes it."""
    assert oldest.row_count == 58
    assert oldest.entries[-1].raw_line.startswith("16")
    assert "</div>" not in oldest.entries[-1].raw_line


# --- hazard 2: cells run into their neighbours ------------------------------------


def test_a_description_running_into_the_pub_l_column(modern):
    """`tr to 42/290ee-10118-84` — a 17-character description and `118-84` with no
    space between them."""
    row = _row(modern, "tr to 42/290ee-10118-84")
    assert row.description_raw == "tr to 42/290ee-10"
    assert (row.pl_congress, row.pl_num) == (118, 84)
    assert row.action == "tr to"
    assert row.transfer_counterpart == "42/290ee-10"
    assert row.pl_section_raw == "2(6), (7)"


def test_an_act_name_running_into_the_pub_l_column(older):
    """`Ethics Act nt new110-24` — the same collision on an appendix row."""
    row = _row(older, "Ethics Act nt new110-24")
    assert row.description_raw == "Ethics Act nt new"
    assert (row.pl_congress, row.pl_num) == (110, 24)
    assert (row.act_name, row.is_note, row.action) == ("Ethics Act", True, "new")


def test_a_quoted_section_running_into_the_stat_column(modern):
    """`1649(a) "Subchapter III"` is 24 characters in a 22-character column, so the
    fixed-width Stat. cell reads `I" 2194`."""
    row = _row(modern, '"Subchapter III"')
    assert row.pl_section_raw == "1649(a)"
    assert row.new_section_quote == "Subchapter III"
    assert row.stat_pages == (2194,)


def test_a_row_whose_pub_l_cell_will_not_parse_is_kept_and_warned_about():
    """Never dropped: a dropped row is invisible and a null one is a question
    somebody can answer later."""
    page = (
        "<html><body><pre>\n U. S. Code\n"
        "Title Section      Description      Pub. L.  Sec.                  138 Stat.\n"
        "-------------      -----------      -------------                  ---------\n"
        "18    3551         nt               118-35   101(3)                   3\n"
        "18    3552         nt               nonsense 101(4)                   4\n"
        "</pre></body></html>"
    )
    with pytest.warns(UserWarning, match="no parseable Pub. L. cell"):
        parsed = parse_classification_file(page, filename="tbl118pl_2nd.htm")
    assert parsed.row_count == 2
    assert parsed.entries[1].pl_congress is None
    assert parsed.entries[1].raw_line.endswith("4")
    assert len(parsed.warnings) == 1


def test_a_description_overrunning_past_the_sec_column_will_not_invent_a_law():
    """The re-split reads the region between Description and Sec., so a description
    long enough to push the Pub. L. number past that boundary leaves only the head of
    the number there — `118-274` as `118-2`, which parses. The row keeps a null law
    and a warning instead of another law's number."""
    page = (
        "<html><body><pre>\n U. S. Code\n"
        "Title Section      Description      Pub. L.  Sec.                  138 Stat.\n"
        "-------------      -----------      -------------                  ---------\n"
        "18    3551         tr to 42/290eeee-101a118-274 101(3)                3\n"
        "</pre></body></html>"
    )
    with pytest.warns(UserWarning, match="Pub. L. number is cut off"):
        parsed = parse_classification_file(page, filename="tbl118pl_2nd.htm")
    assert parsed.row_count == 1
    assert (parsed.entries[0].pl_congress, parsed.entries[0].pl_num) == (None, None)


def test_a_sec_cell_overrunning_with_digits_is_re_split():
    """`101, 102, 103, 104, 105` overruns a 22-character column and leaves `5 3` in
    the Stat. cell, which is digits and spaces and so passes the cell's own shape
    test. The column boundary having cut a number in half is the signal, and 29 of
    the 31 files carry no statviewer link to catch it any other way."""
    page = (
        "<html><body><pre>\n U. S. Code\n"
        "Title Section      Description      Pub. L.  Sec.                  138 Stat.\n"
        "-------------      -----------      -------------                  ---------\n"
        "18    3551         nt               118-35   101, 102, 103, 104, 105 3\n"
        "</pre></body></html>"
    )
    parsed = parse_classification_file(page, filename="tbl118pl_2nd.htm")
    row = parsed.entries[0]
    assert row.pl_section_raw == "101, 102, 103, 104, 105"
    assert row.stat_pages == (3,)


def test_a_line_that_is_not_a_row_is_counted_and_reported():
    page = (
        "<html><body><pre>\n U. S. Code\n"
        "Title Section      Description      Pub. L.  Sec.                  138 Stat.\n"
        "-------------      -----------      -------------                  ---------\n"
        "18    3551         nt               118-35   101(3)                   3\n"
        "  * See the note at the end of this table.\n"
        "</pre></body></html>"
    )
    with pytest.warns(UserWarning, match="does not start with a title number"):
        parsed = parse_classification_file(page, filename="tbl118pl_2nd.htm")
    assert parsed.row_count == 1
    assert parsed.skipped_lines == ("  * See the note at the end of this table.",)


# --- hazard 3: anchors inside the fixed-width text --------------------------------


def test_statviewer_links_are_harvested_before_the_tags_go(modern):
    """The href carries the volume and the page; the visible text carries only the
    page, and the row would still need the volume from somewhere."""
    row = _row(modern, "18    3551         nt               118-35")
    assert row.stat_volume == 138
    assert row.stat_pages == (3,)
    assert "<a" not in row.raw_line
    assert row.raw_line.endswith("3")


def test_openplaw_anchors_are_stripped_and_the_row_realigns(older, oldest):
    """The 104th and 110th wrap the Pub. L. cell in `<a href='#' onclick="return
    openPLaw('110', '1');">110-1</a>`, which carries nothing the visible text does
    not. Stripping it restores the fixed-width layout."""
    row = older.entries[0]
    assert row.raw_line == (
        "16    460nn-1      nt new           110-1    1                        3"
    )
    assert (row.pl_congress, row.pl_num) == (110, 1)
    assert oldest.entries[0].pl_congress == 104
    assert all("openPLaw" not in entry.raw_line for entry in oldest.entries)


# --- hazard 4: multi-value cells --------------------------------------------------


def test_multiple_stat_pages_in_one_cell(modern):
    row = _row(modern, "tr fr 42/254c-15")
    assert row.stat_pages == (1544, 1545)
    assert row.stat_page_labels == ("1544", "1545")


def test_a_stat_range_gives_its_endpoints(oldest):
    row = _row(oldest, "104-6    401-407")
    assert row.pl_section_raw == "401-407"
    assert row.stat_pages == (89, 92)


def test_a_hyphenated_stat_page_is_a_page_and_not_a_range(oldest):
    """110 Stat. 3009-587 is one page of the 1997 omnibus appropriations act. Only
    the direction tells it apart from `4264-4267`, which is a range."""
    row = _row(oldest, "8     1229          tr to 1224")
    assert row.stat_page_labels == ("3009-587",)
    assert row.stat_pages == ()
    assert parse_stat_pages("4264-4267") == (("4264-4267",), (4264, 4267))
    assert parse_stat_pages("1544, 1545") == (("1544", "1545"), (1544, 1545))


def test_a_stat_page_numbered_with_a_letter_is_a_page(oldest):
    """113 Stat. 1501A-594 is one page: the appropriations volumes number their
    divisions with a letter. 3,323 rows across the 105th–107th cite one, and a
    Stat. cell of digits and hyphens alone read every one of them as an overrun."""
    page = (
        "<html><body><pre>\n U. S. Code\n"
        "Title Section      Description      Pub. L.  Sec.                  113 Stat.\n"
        "-------------      -----------      -------------                  ---------\n"
        "47    336          nt new           106-113  1000(a)(9)               1501A-594\n"
        "</pre></body></html>"
    )
    row = parse_classification_file(page, filename="tbl106pl_1st.htm").entries[0]

    assert row.stat_page_labels == ("1501A-594",)
    assert row.stat_pages == ()
    assert row.pl_section_raw == "1000(a)(9)"


def test_a_corrected_row_is_a_row():
    """OLRC marks a row it has since corrected with an asterisk in front of the
    title number — "`*` denotes an item that was corrected as of October 6, 2005",
    says `tbl108pl_1st.htm`'s footnote. 29 rows across three files carry one, and
    before this they were not recognised as rows at all. The marker is column 1 as
    printed and no parsed field."""
    row = parse_classification_file(
        _page(_line("*16", "3503", "nt", "108-7", "155", "246")),
        filename="tbl108pl_1st.htm",
    ).entries[0]

    assert (row.title_raw, row.title_num) == ("*16", "16")
    assert row.usc_identifier == "/us/usc/t16/s3503"
    assert (row.pl_congress, row.pl_num, row.pl_section_raw) == (108, 7, "155")
    assert row.stat_pages == (246,)
    assert row.raw_line.startswith("*16")


@pytest.mark.parametrize(
    ("marker", "keeps_width"),
    [("*", True), ("*", False), ("**", False)],
    ids=["padding-absorbs-it", "one-right", "two-right"],
)
def test_a_corrected_row_realigns_however_far_the_marker_pushed_it(marker, keeps_width):
    """The Title column is six characters wide and holds at most four, so the
    marker sometimes fits in the padding and sometimes pushes every later column
    right: `*16   3503` keeps them, `*42    7619` moves them one and `**15    683`
    two. All three shapes are in the files."""
    # Inside the Title cell the marker eats the padding and every later column
    # stays put; in front of the line it pushes them all right.
    line = (
        _line(marker + "16", "3503", "nt", "108-7", "155", "246")
        if keeps_width
        else marker + _line("16", "3503", "nt", "108-7", "155", "246")
    )

    parsed = parse_classification_file(_page(line), filename="tbl108pl_1st.htm")

    assert parsed.skipped_lines == ()
    assert parsed.warnings == ()
    row = parsed.entries[0]
    assert (row.section_raw, row.pl_num, row.pl_section_raw) == ("3503", 7, "155")
    assert row.stat_pages == (246,)


def test_a_linked_stat_page_butted_against_the_designator_is_split_off():
    """`4001(b)(2)(A), (B), (D)(iii)1967` has no whitespace to cut at, and the
    anchor around the page says where the cell begins — evidence from the document
    rather than a guess. Roughly a hundred rows are this shape."""
    page = (
        "<html><body><pre>\n U. S. Code\n"
        "Title Section      Description      Pub. L.  Sec.                  129 Stat.\n"
        "-------------      -----------      -------------                  ---------\n"
        "20    7221                          114-95   4001(b)(2)(A), (B), (D)(iii)"
        '<a href="/statviewer.htm?volume=129&page=1967">1967</a>\n'
        "</pre></body></html>"
    )
    row = parse_classification_file(page, filename="tbl114pl_1st.htm").entries[0]

    assert row.pl_section_raw == "4001(b)(2)(A), (B), (D)(iii)"
    assert row.stat_pages == (1967,)
    assert row.stat_volume == 129


def test_a_multi_value_section_of_law_cell_is_kept_verbatim(older):
    """`2, 3` and `2(6), (7)` are the act's own designators, not a shape we impose."""
    assert _row(older, "5A    105          Ethics Act       110-24").pl_section_raw == "2, 3"


def test_a_non_breaking_space_costs_one_column():
    """`&#160;` is one glyph on screen and must be one character here, or every
    offset after it is wrong."""
    page = (
        "<html><body><pre>\n U. S. Code\n"
        "Title Section      Description      Pub. L.  Sec.                  138 Stat.\n"
        "-------------      -----------      -------------                  ---------\n"
        "18&#160;&#160;&#160;&#160;3551&#160;        nt               118-35   101(3)"
        "                   3\n"
        "</pre></body></html>"
    )
    parsed = parse_classification_file(page, filename="tbl118pl_2nd.htm")
    assert parsed.entries[0].section_norm == "3551"
    assert parsed.entries[0].pl_num == 35


def test_a_quoted_new_section_is_peeled_off_the_sec_cell(modern):
    """`202 "1948"` — section 202 of the law adds section 1948 to the underlying
    act. Two different section numbers in one cell."""
    row = _row(modern, '202 "1948"')
    assert row.pl_section_raw == "202"
    assert row.new_section_quote == "1948"
    assert row.usc_identifier == "/us/usc/t42/s1396w–8"


# --- hazard 5 and the identifier-derivation rules ---------------------------------


def test_appendix_rows_derive_no_identifier(older, oldest):
    """`5A / 101` cannot produce `/us/usc/t5a/pl/92/463/s1`, which is the shape an
    appendix provision's identifier really has (ADR-0065). Null by rule."""
    appendix = [entry for entry in older.entries if entry.is_appendix]
    assert appendix, "the 110th slice carries the 5A and 50A rows"
    assert {entry.title_num for entry in appendix} == {"5a", "50a"}
    assert all(entry.usc_identifier is None for entry in appendix)
    assert all(entry.usc_identifier is None for entry in oldest.entries if entry.is_appendix)
    assert derive_usc_identifier("5a", "101", is_appendix=True) is None


def test_a_range_or_a_list_derives_no_identifier():
    """A section number, or nothing. `254c-15` and `2680-3` are single sections and
    do derive — the shape decides, not the hyphen."""
    assert derive_usc_identifier("42", "1231 to 1234", is_appendix=False) is None
    assert derive_usc_identifier("42", "1231, 1232", is_appendix=False) is None
    assert derive_usc_identifier("42", "subchapter ii", is_appendix=False) is None
    assert derive_usc_identifier("42", "254c-15", is_appendix=False) == "/us/usc/t42/s254c–15"
    assert derive_usc_identifier("22", "2680-3", is_appendix=False) == "/us/usc/t22/s2680–3"


def test_a_note_row_derives_the_parent_sections_identifier(modern):
    """`18 / 3551 / nt` is a note *to* § 3551 and belongs on that section's page.
    `is_note` says which it is."""
    row = modern.entries[0]
    assert (row.is_note, row.usc_identifier) == (True, "/us/usc/t18/s3551")


def test_a_prec_row_derives_the_parent_sections_identifier(modern):
    """`prec` means the new material precedes the named section."""
    row = _row(modern, '5501         prec new         118-159  1649(a) "CHAPTER 551"')
    assert row.action == "prec new"
    assert row.is_note is False
    assert row.usc_identifier == "/us/usc/t10/s5501"


def test_section_numbers_normalize_the_en_dash():
    """`section_norm` folds every dash to the hyphen, which is the spelling typed
    input arrives in (CLAUDE.md gotcha 17)."""
    assert normalize_section("45A–1") == "45a-1"
    assert normalize_section("45a‑1") == "45a-1"


def test_the_derived_identifier_is_spelled_with_an_en_dash():
    """The corpus writes `/us/usc/t16/s45a–1` with U+2013 — all 5,697 of its
    hyphenated section identifiers do — so an identifier built with the table's own
    hyphen joins nothing."""
    identifier = derive_usc_identifier("16", normalize_section("45A–1"), is_appendix=False)
    assert identifier == "/us/usc/t16/s45a–1"
    assert "-" not in identifier
    assert derive_usc_identifier("16", "45a-1", is_appendix=False) == identifier


# --- the description column is an open set ----------------------------------------


@pytest.mark.parametrize(
    "description,expected",
    [
        ("", (False, None, None, None)),
        ("nt", (True, None, None, None)),
        ("nts", (True, None, None, None)),
        ("note", (True, None, None, None)),
        ("new", (False, "new", None, None)),
        ("nt new", (True, "new", None, None)),
        ("nt [tbl]", (True, "[tbl]", None, None)),
        ("gen amd", (False, "gen amd", None, None)),
        ("nt prec ed chg", (True, "prec ed chg", None, None)),
        ("nt prec repealed", (True, "prec repealed", None, None)),
        ("tr to 42/290ee-10", (False, "tr to", "42/290ee-10", None)),
        ("to 36/300113", (False, "tr to", "36/300113", None)),
        ("fr 36/300111", (False, "tr fr", "36/300111", None)),
        ("tr fr 1228", (False, "tr fr", "1228", None)),
        ("Ethics Act nt new", (True, "new", None, "Ethics Act")),
        ("nt new IG Act", (True, "new", None, "IG Act")),
        ("R Plan 2, 1968", (False, None, None, "R Plan 2, 1968")),
        ("App R new", (False, "new", None, "App R")),
    ],
)
def test_description_vocabulary(description, expected):
    """Every one of these is in the three downloaded files. The column is an open
    set — an unrecognised word becomes the act name rather than a failure."""
    assert parse_description(description) == expected


def test_the_older_bare_transfer_normalizes_to_the_modern_spelling(older, modern):
    """The 118th writes `tr to 42/290ee-10`; the 110th and 104th write `to
    36/300113`. One action either way."""
    assert _row(older, "to 36/300113").action == "tr to"
    assert _row(modern, "tr to 42/290ee-10118-84").action == "tr to"


def test_an_amended_section_has_an_empty_description(modern):
    row = _row(modern, "42    1396n                         118-42   204(a)-(c)(1)(A)")
    assert (row.description_raw, row.is_note, row.action) == ("", False, None)


# --- hazard 6: change detection ---------------------------------------------------


def test_the_content_hash_is_of_the_extracted_pre_text(modern):
    """Not of the response body: these pages embed a per-request `jsessionid`, so no
    two downloads are byte-identical and a body hash detects nothing."""
    again = _parse("tbl118pl_2nd_slice.htm", "tbl118pl_2nd.htm")
    assert modern.content_hash == again.content_hash
    assert len(modern.content_hash) == 64


def test_the_covered_text_can_be_overridden_by_the_index_pages_wording():
    """The file says "Public Laws 118-35 through 118-274" and the index says
    "…118-35 to 118-274". A poll compares the index's wording, so that is what the
    registry row stores."""
    page = (FIXTURES / "tbl118pl_2nd_slice.htm").read_text()
    from_file = parse_classification_file(page, filename="tbl118pl_2nd.htm")
    from_index = parse_classification_file(
        page,
        filename="tbl118pl_2nd.htm",
        covered_laws_text="Public Laws 118-35 to 118-274",
    )
    assert from_file.covered_laws_text == "Public Laws 118-35 through 118-274"
    assert from_index.covered_laws_text == "Public Laws 118-35 to 118-274"
    assert from_file.covered_ranges == from_index.covered_ranges == ("35-274",)


# --- the report -------------------------------------------------------------------


def test_the_report_says_what_the_parse_found(modern, older):
    report = modern.report()
    assert report.rows_parsed == modern.row_count == 84
    assert (report.skipped_lines, report.warnings) == (0, ())
    assert report.pl_span == ("118-35", "118-273")
    assert report.rows_outside_covered_ranges == 0
    assert report.rows_without_pl == 0
    assert report.rows_without_identifier == 0
    assert "18" in report.distinct_titles

    # The 110th slice's 22 appendix rows are the only ones without an identifier.
    older_report = older.report()
    assert older_report.rows_without_identifier == sum(
        1 for entry in older.entries if entry.is_appendix
    )


def test_the_report_round_trips_through_json(modern):
    from ingest.classification import ClassificationParseReport

    report = modern.report()
    assert ClassificationParseReport.from_json(report.as_json()) == report


def test_a_parsed_file_round_trips_through_json(modern, oldest):
    for parsed in (modern, oldest):
        assert ParsedClassificationFile.from_json(parsed.as_json()) == parsed


def test_the_pl_label_is_derived_and_not_stored(modern):
    assert modern.entries[0].pl_label == "118-35"
    assert ClassificationEntry.from_json(modern.entries[0].as_json()) == modern.entries[0]


# --- the ECCT ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def ecct():
    return parse_ecct(
        (FIXTURES / "ecct.html").read_text(), filename="ecct.html", congress=119, session=2
    )


def test_the_ecct_is_read_out_of_a_malformed_table(ecct):
    """A `<div id="boxheads">` opens inside the `<table>` and its `</div>` closes
    before `</table>`. An HTML parser is entitled to reparent the whole thing."""
    assert ecct.row_count == 1
    row = ecct.entries[0]
    assert (row.former_raw, row.new_raw) == ("42:294t nt", "42:294u new")
    assert (row.former_title_num, row.former_section_norm, row.former_is_note) == (
        "42",
        "294t",
        True,
    )
    assert (row.new_title_num, row.new_section_norm, row.new_is_note) == ("42", "294u", False)


def test_the_ecct_keeps_both_citations_verbatim_and_parses_their_laws(ecct):
    row = ecct.entries[0]
    assert row.provision_affected == "Pub. L. 117-105, § 3, Mar. 18, 2022, 136 Stat. 1118"
    assert row.provision_prompting == (
        "Pub. L. 119-75, Div. J, title V, § 6508(b), Feb. 3, 2026, 140 Stat. 695"
    )
    assert (row.affected_pl_congress, row.affected_pl_num) == (117, 105)
    assert (row.prompting_pl_congress, row.prompting_pl_num) == (119, 75)


def test_an_ecct_with_no_data_rows_is_valid():
    """Sessions go by without an editorial reclassification. Zero rows is an answer."""
    page = (
        "<html><body><table>"
        "<tr><th>Former Classification</th><th>New Classification</th>"
        "<th>Provision Affected</th><th>Provision Prompting Change</th></tr>"
        "</table></body></html>"
    )
    parsed = parse_ecct(page)
    assert parsed.row_count == 0
    assert parsed.entries == ()


def test_an_ecct_row_whose_cells_do_not_close_is_warned_about():
    """The cells are matched by regex on a document the source writes malformed, so a
    row whose `<td>`s never close yields nothing. It carries text, so it is a row
    being lost rather than an empty `<tr>`."""
    page = (
        "<html><body><table>"
        "<tr><th>Former Classification</th><th>New Classification</th>"
        "<th>Provision Affected</th><th>Provision Prompting Change</th></tr>"
        "<tr><td>42:294t nt<td>42:294u new<td>Pub. L. 119-1<td>Pub. L. 119-1</tr>"
        "</table></body></html>"
    )
    with pytest.warns(UserWarning, match="text but no parseable cells"):
        parsed = parse_ecct(page)
    assert parsed.row_count == 0


def test_an_ecct_with_no_header_cells_is_a_parse_error():
    """The four columns are read by position; without the headers there is nothing
    saying they are still the four columns."""
    with pytest.raises(ClassificationParseError, match="no header cells"):
        parse_ecct("<html><body><p>Down for maintenance.</p></body></html>")


def test_ecct_entries_round_trip_through_json(ecct):
    from ingest.classification import EcctEntry, ParsedEcctFile

    assert ParsedEcctFile.from_json(ecct.as_json()) == ecct
    assert EcctEntry.from_json(ecct.entries[0].as_json()) == ecct.entries[0]
