"""`Uslm1Parser` against `tests/fixtures/usc16_slice.xml`.

The slice is Title 16 chapter 1 (subchapters I-VI through § 45f, plus subchapter
XIII for quoted sections and subchapter XCVII for the reserved status), extracted
verbatim by `scripts/extract_fixture.py`. Full-file counts live in
`test_uslm_full_corpus.py` behind `@pytest.mark.slow`.
"""

from lxml import etree

from ingest import Uslm1Parser, iter_sections, parse_meta

USLM = "http://xml.house.gov/schemas/uslm/1.0"
NS = {"u": USLM}

# Known-good assertion carried in CLAUDE.md.
S45F = "/us/usc/t16/s45f"
S45F_GUID = "id0b32dfeb-810c-11f1-b7ce-bdea3d14cbdd"
S45F_C5 = "/us/usc/t16/s45f/c/5"
S45F_C5_GUID = "id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd"


def records(path):
    return list(Uslm1Parser().iter_sections(path))


def test_emits_every_real_section_in_document_order(slice_path):
    sections = records(slice_path)

    assert len(sections) == 158
    assert [s.seq for s in sections] == list(range(158))
    assert sections[0].identifier == "/us/usc/t16/s1"
    assert sections[-1].identifier == "/us/usc/t16/s119a"


def test_quoted_sections_are_not_code_sections(slice_path):
    """`<section>` also appears inside `<quotedContent>` — text quoted from an
    amending act. Those elements carry no `@identifier` and must not be emitted."""
    tree = etree.parse(str(slice_path))
    all_section_elements = tree.findall(f".//{{{USLM}}}section")
    quoted = [
        element
        for element in all_section_elements
        if any(a.tag == f"{{{USLM}}}quotedContent" for a in element.iterancestors())
    ]
    assert len(quoted) == 9, "fixture must exercise the quoted-section rule"

    sections = records(slice_path)
    assert len(all_section_elements) - len(quoted) == len(sections)
    assert all(s.identifier for s in sections)


def test_quoted_text_stays_inside_its_enclosing_section(slice_path):
    """Skipping a quoted section must not remove it from the parent's XML."""
    by_id = {s.identifier: s for s in records(slice_path)}
    host = by_id["/us/usc/t16/s119"]
    fragment = etree.fromstring(host.xml.encode("utf-8"))
    assert fragment.findall(f".//{{{USLM}}}quotedContent//{{{USLM}}}section")


def test_status_values_are_carried(slice_path):
    sections = records(slice_path)
    counts = {}
    for section in sections:
        counts[section.status] = counts.get(section.status, 0) + 1

    assert counts["repealed"] == 111
    assert counts["omitted"] == 2
    assert counts["transferred"] == 7


def test_reserved_status_on_a_subchapter_is_not_a_section(slice_path):
    """Title 16's single `reserved` sits on `<subchapter>`, not `<section>` — so a
    section-level status tally will never account for it."""
    tree = etree.parse(str(slice_path))
    reserved = tree.xpath("//*[@status='reserved']")
    assert [etree.QName(e).localname for e in reserved] == ["subchapter"]
    assert all(s.status != "reserved" for s in records(slice_path))


def test_repealed_sections_keep_their_place_in_reading_order(slice_path):
    """Gotcha 9: prev/next must not skip them."""
    sections = records(slice_path)
    by_id = {s.identifier: s.seq for s in sections}
    assert by_id["/us/usc/t16/s4"] + 1 == by_id["/us/usc/t16/s5"]  # s5 is omitted
    assert by_id["/us/usc/t16/s5"] + 1 == by_id["/us/usc/t16/s6"]


def test_section_fields(slice_path):
    section = next(s for s in records(slice_path) if s.identifier == S45F)

    assert section.guid == S45F_GUID
    assert section.num == "§ 45f."
    assert section.num_value == "45f"
    assert section.heading == "Mineral King Valley addition authorized"
    assert section.status is None
    assert section.schema_version == "uslm-1.0.15"
    assert section.source_credit.startswith("(Pub. L. 95–625, title III, § 314,")
    assert section.ancestors == (
        ("title", "/us/usc/t16"),
        ("chapter", "/us/usc/t16/ch1"),
        ("subchapter", "/us/usc/t16/ch1/schVI"),
    )


def test_temporal_id_is_absent_in_uslm_1_0_15(slice_path):
    """The 1.0.15 converter emits no @temporalId at all — display-only field, so
    its absence is recorded, not worked around."""
    assert all(s.temporal_id is None for s in records(slice_path))


def test_notes_are_captured_with_their_topics(slice_path):
    repealed = next(s for s in records(slice_path) if s.identifier == "/us/usc/t16/s1")

    assert repealed.status == "repealed"
    assert repealed.heading.startswith("Repealed. Pub. L. 113–287")
    assert [note.topic for note in repealed.notes][:2] == [
        "removalDescription",
        "statutoryNotes",
    ]
    assert repealed.notes[0].xml.startswith("<note")


def test_guid_refs_index_every_id_in_the_section(slice_path):
    section = next(s for s in records(slice_path) if s.identifier == S45F)
    fragment = etree.fromstring(section.xml.encode("utf-8"))

    ids_in_xml = [e.get("id") for e in fragment.iter() if e.get("id")]
    assert [ref.guid for ref in section.guid_refs] == ids_in_xml
    assert (section.guid_refs[0].guid, section.guid_refs[0].identifier) == (
        S45F_GUID,
        S45F,
    )


def test_known_good_guid_maps_to_its_provision(slice_path):
    """CLAUDE.md's standing assertion: id0b32dff7-… <-> /us/usc/t16/s45f/c/5."""
    section = next(s for s in records(slice_path) if s.identifier == S45F)
    guid_map = {ref.guid: ref.identifier for ref in section.guid_refs}

    assert guid_map[S45F_C5_GUID] == S45F_C5


def test_guids_without_an_identifier_resolve_to_the_nearest_provision(slice_path):
    """`<p>` and friends carry @id but no @identifier; `?id=` must still land
    somewhere retrievable."""
    section = next(s for s in records(slice_path) if s.identifier == "/us/usc/t16/s1")
    fragment = etree.fromstring(section.xml.encode("utf-8"))
    bare = {
        e.get("id")
        for e in fragment.iter()
        if e.get("id") and not e.get("identifier")
    }
    assert bare

    guid_map = {ref.guid: ref.identifier for ref in section.guid_refs}
    assert all(guid_map[guid].startswith("/us/usc/t16/s1") for guid in bare)


def test_guids_are_unique_across_the_document(slice_path):
    refs = [ref.guid for section in records(slice_path) for ref in section.guid_refs]
    assert len(refs) == len(set(refs))


def test_xml_is_a_verbatim_reparseable_fragment(slice_path):
    """ADR-0001: sub-section provisions are XPathed out of this at request time."""
    section = next(s for s in records(slice_path) if s.identifier == S45F)
    fragment = etree.fromstring(section.xml.encode("utf-8"))

    assert etree.QName(fragment).localname == "section"
    target = fragment.xpath(f"//*[@identifier='{S45F_C5}']", namespaces=NS)
    assert len(target) == 1
    assert target[0].get("id") == S45F_C5_GUID
    assert "Mineral King" in "".join(fragment.itertext())


def test_meta(slice_path):
    meta = parse_meta(slice_path)

    assert meta.identifier == "/us/usc/t16"
    assert meta.doc_number == "16"
    assert meta.doc_title == "Title 16"
    assert meta.schema_version == "uslm-1.0.15"
    assert meta.uslm_version == "1"
    assert meta.doc_publication_name == "Online@119-102not101"
    assert meta.release_label == "119-102not101"
    assert meta.is_positive_law is False
    assert meta.converter == "USCConverter 1.7.2"


def test_count_section_elements_includes_quoted_sections(slice_path):
    """PLAN §11.4 provenance manifests want both numbers side by side; the gap
    between them is exactly ADR-0005's quoted-content exclusion."""
    real = len(records(slice_path))
    tree = etree.parse(str(slice_path))
    quoted = [
        e
        for e in tree.findall(f".//{{{USLM}}}section")
        if any(a.tag == f"{{{USLM}}}quotedContent" for a in e.iterancestors())
    ]

    assert Uslm1Parser().count_section_elements(slice_path) == real + len(quoted)


def test_accepts_an_open_stream_as_well_as_a_path(slice_path):
    with open(slice_path, "rb") as handle:
        streamed = list(iter_sections(handle))

    assert [s.identifier for s in streamed] == [
        s.identifier for s in records(slice_path)
    ]
