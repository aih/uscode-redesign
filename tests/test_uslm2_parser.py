"""`Uslm2Parser` — the Day 1 scope: detection plus basic section extraction.

Runs against `samples/uslm2/USLM2/usc01.xml` (253 KB, ~15 ms). The heavier 2.x
samples (usc16 for cross-schema parity, usc49 for tables and `renumbered` status)
are exercised in `test_uslm_full_corpus.py` behind `@pytest.mark.slow`.

These tests pin what the stub *does* handle, so Day 7's parity work has a floor to
build on. TOC, tables and the indent model are explicitly out of scope here.
"""

from lxml import etree

from ingest import Uslm2Parser, parse_meta

USLM2 = "http://schemas.gpo.gov/xml/uslm"


def records(path):
    return list(Uslm2Parser().iter_sections(path))


def test_extracts_sections_in_document_order(uslm2_usc01):
    sections = records(uslm2_usc01)

    assert len(sections) == 39
    assert [s.seq for s in sections] == list(range(39))
    assert sections[0].identifier == "/us/usc/t1/s1"
    assert sections[-1].identifier == "/us/usc/t1/s213"


def test_quoted_sections_are_excluded_here_too(uslm2_usc01):
    tree = etree.parse(str(uslm2_usc01))
    all_sections = tree.findall(f".//{{{USLM2}}}section")
    quoted = [
        element
        for element in all_sections
        if any(a.tag == f"{{{USLM2}}}quotedContent" for a in element.iterancestors())
    ]
    assert quoted

    assert len(all_sections) - len(quoted) == len(records(uslm2_usc01))


def test_section_fields_match_the_uslm1_shape(uslm2_usc01):
    """Records must be indistinguishable in shape from 1.x records — that is the
    whole point of the parser layer."""
    section = records(uslm2_usc01)[0]

    assert section.identifier == "/us/usc/t1/s1"
    assert section.guid == "ide95c894b-167e-11ee-ba21-fbcfe3ed3956"
    assert section.num == "§ 1."
    assert section.num_value == "1"
    assert section.heading == "Words denoting number, gender, and so forth"
    assert section.status is None
    assert section.schema_version == "uslm-2.0.12"
    assert section.source_credit.startswith("(July 30, 1947, ch. 388, 61 Stat. 633;")
    assert section.notes[0].topic == "editorialNote"
    assert section.ancestors == (
        ("title", "/us/usc/t1"),
        ("chapter", "/us/usc/t1/ch1"),
    )


def test_subsection_guids_are_indexed(uslm2_usc01):
    section = next(s for s in records(uslm2_usc01) if s.identifier == "/us/usc/t1/s7")
    guid_map = {ref.guid: ref.identifier for ref in section.guid_refs}

    assert guid_map["ide95ed278-167e-11ee-ba21-fbcfe3ed3956"] == "/us/usc/t1/s7/a"
    assert section.guid in guid_map


def test_xml_fragment_supports_request_time_provision_extraction(uslm2_usc01):
    section = next(s for s in records(uslm2_usc01) if s.identifier == "/us/usc/t1/s7")
    fragment = etree.fromstring(section.xml.encode("utf-8"))

    target = fragment.xpath("//*[@identifier='/us/usc/t1/s7/a']")
    assert len(target) == 1


def test_meta_uses_the_2_x_field_names(uslm2_usc01):
    """2.x drops `<property role="is-positive-law">` and renames
    dcterms:created/dc:creator to processedDate/processedBy."""
    meta = parse_meta(uslm2_usc01)

    assert meta.identifier == "/us/usc/t1"
    assert meta.doc_number == "1"
    assert meta.doc_title == "Title 1"
    assert meta.schema_version == "uslm-2.0.12"
    assert meta.uslm_version == "2"
    assert meta.doc_publication_name == "Online"
    assert meta.release_label is None  # samples are not release-point publications
    assert meta.is_positive_law is None
    assert meta.created == "2023-06-29T09:14:42"
    assert meta.converter.startswith("USCConverter 4.8.0")
    assert meta.extra["dc:publisher"] == "OLRC"
