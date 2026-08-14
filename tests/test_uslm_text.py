"""Plain-text extraction (`plain_text` / `notes_text`, ADR-0069) against
`tests/fixtures/usc16_slice.xml` and inline fragments of both schemas.

The stored `SectionRecord.xml` fragments are what the extractor is fed in
production (the HF export reads them back out of `section_versions.xml`), so
these tests run it on exactly that: a record's `xml`, re-parsed through
`parser_for_fragment`.
"""

from functools import lru_cache

import pytest

from ingest.parser import iter_sections, parser_for_fragment
from ingest.uslm1 import Uslm1Parser
from ingest.uslm2 import Uslm2Parser


@lru_cache(maxsize=1)
def records(path):
    return {record.identifier: record for record in iter_sections(str(path))}


def text_of(record) -> str:
    return parser_for_fragment(record.xml).plain_text(record.xml)


def test_fragment_parser_is_chosen_by_the_fragment_itself(slice_path):
    record = records(slice_path)["/us/usc/t16/s45f"]
    assert isinstance(parser_for_fragment(record.xml), Uslm1Parser)


def test_section_num_and_heading_share_the_first_line(slice_path):
    text = text_of(records(slice_path)["/us/usc/t16/s45f"])
    assert text.split("\n")[0] == "§ 45f. Mineral King Valley addition authorized"


def test_headed_subsection_breaks_after_its_heading(slice_path):
    lines = text_of(records(slice_path)["/us/usc/t16/s45f"]).split("\n")
    assert "(a) Statement of purpose" in lines
    assert "It is the purpose of this section to—" in lines


def test_unheaded_designator_runs_into_its_text(slice_path):
    lines = text_of(records(slice_path)["/us/usc/t16/s45f"]).split("\n")
    assert any(
        line.startswith("(1) assure the preservation") for line in lines
    ), "printed-Code form: bare designator on the same line as its text"
    assert "(1)" not in lines, "no designator left alone on a line"


def test_notes_and_source_credit_stay_out_of_the_body(slice_path):
    record = records(slice_path)["/us/usc/t16/s45f"]
    text = text_of(record)
    assert record.source_credit not in text
    assert "References in Text" not in text
    assert "Editorial Notes" not in text


def test_whitespace_is_collapsed_and_no_line_is_blank(slice_path):
    text = text_of(records(slice_path)["/us/usc/t16/s45f"])
    for line in text.split("\n"):
        assert line == " ".join(line.split())
        assert line != ""


def test_notes_text_carries_topics_without_duplicating_headings(slice_path):
    record = records(slice_path)["/us/usc/t16/s45f"]
    notes = parser_for_fragment(record.xml).notes_text(record.xml)
    topics = {note.topic for note in notes}
    assert {"referencesInText", "codification", "amendments"} <= topics
    references = next(n for n in notes if n.topic == "referencesInText")
    assert references.heading == "References in Text"
    assert not references.text.startswith("References in Text")
    assert "referred to in text" in references.text


def test_note_count_matches_the_record(slice_path):
    record = records(slice_path)["/us/usc/t16/s45f"]
    notes = parser_for_fragment(record.xml).notes_text(record.xml)
    assert len(notes) == len(record.notes)


USLM1_NS = "http://xml.house.gov/schemas/uslm/1.0"
USLM2_NS = "http://schemas.gpo.gov/xml/uslm"


def _fragment(namespace: str, body: str) -> str:
    return f'<section xmlns="{namespace}" identifier="/us/usc/t0/s1">{body}</section>'


def test_block_quoted_content_gets_its_own_lines():
    xml = _fragment(
        USLM1_NS,
        "<num value='1'>§ 1.</num><heading>Test</heading>"
        "<subsection identifier='/us/usc/t0/s1/a'><num value='a'>(a)</num>"
        "<content>The following is inserted:"
        "<quotedContent><section><num value='9'>§ 9.</num>"
        "<heading>Inserted heading</heading>"
        "<content>Inserted body text.</content></section></quotedContent>"
        "</content></subsection>",
    )
    lines = parser_for_fragment(xml).plain_text(xml).split("\n")
    assert "(a) The following is inserted:" in lines
    assert "§ 9. Inserted heading" in lines, "a quoted section is body text"


def test_inline_quoted_content_stays_in_its_sentence():
    xml = _fragment(
        USLM1_NS,
        "<num value='1'>§ 1.</num>"
        "<subsection identifier='/us/usc/t0/s1/a'><num value='a'>(a)</num>"
        "<content>is amended by striking <quotedContent>five years"
        "</quotedContent> and inserting <quotedContent>ten years"
        "</quotedContent>.</content></subsection>",
    )
    lines = parser_for_fragment(xml).plain_text(xml).split("\n")
    assert (
        "(a) is amended by striking five years and inserting ten years." in lines
    ), "quotedContent beside running text must not break the sentence"


def test_toc_is_excluded():
    xml = _fragment(
        USLM1_NS,
        "<num value='1'>§ 1.</num><heading>Test</heading>"
        "<toc><tocItem>1. A table of contents row</tocItem></toc>"
        "<content>Real body.</content>",
    )
    text = parser_for_fragment(xml).plain_text(xml)
    assert "table of contents row" not in text
    assert "Real body." in text


def test_uslm2_fragment_extracts_with_its_own_vocabulary():
    xml = _fragment(
        USLM2_NS,
        "<num value='1'>§ 1.</num><heading>Short title</heading>"
        "<subsection identifier='/us/usc/t0/s1/a'><num value='a'>(a)</num>"
        "<heading>In general</heading><content>Body under 2.x.</content>"
        "</subsection>",
    )
    parser = parser_for_fragment(xml)
    assert isinstance(parser, Uslm2Parser)
    lines = parser.plain_text(xml).split("\n")
    assert lines[0] == "§ 1. Short title"
    assert "(a) In general" in lines
    assert "Body under 2.x." in lines


def test_uslm2_table_rows_break_lines():
    xml = _fragment(
        USLM2_NS,
        "<num value='1'>§ 1.</num>"
        "<content><layout><header><column>State</column></header>"
        "<row><column>Alabama</column><column>1819</column></row>"
        "<row><column>Alaska</column><column>1959</column></row>"
        "</layout></content>",
    )
    lines = parser_for_fragment(xml).plain_text(xml).split("\n")
    assert "Alabama 1819" in lines
    assert "Alaska 1959" in lines


def test_every_slice_section_extracts_without_error(slice_path):
    for record in records(slice_path).values():
        text = parser_for_fragment(record.xml).plain_text(record.xml)
        if record.status is None:
            assert text, f"empty text for {record.identifier}"


def test_bad_fragment_raises():
    with pytest.raises(Exception):
        parser_for_fragment("<not-xml")
