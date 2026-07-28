"""The TOC pass: hierarchy read off structural elements, not off `<toc>` (ADR-0006).

The fixture's `<toc>` bodies are truncated to 5 items while its chapter/subchapter
headings are intact, so a parser that secretly read `<toc>` would fail these.
"""

import pytest

from ingest.parser import parser_for
from ingest.records import StructureRecord


@pytest.fixture(scope="module")
def nodes(slice_path) -> list[StructureRecord]:
    return list(parser_for(slice_path).iter_structure(slice_path))


def test_yields_the_title_root_first(nodes):
    root = nodes[0]
    assert (root.identifier, root.level, root.depth) == ("/us/usc/t16", "title", 0)
    assert root.heading == "CONSERVATION"
    assert root.parent_identifier is None


def test_captures_chapter_num_and_heading(nodes):
    chapter = next(n for n in nodes if n.identifier == "/us/usc/t16/ch1")
    assert chapter.level == "chapter"
    assert chapter.num == "CHAPTER 1—"
    assert chapter.num_value == "1"
    assert chapter.heading.startswith("NATIONAL PARKS, MILITARY PARKS")
    assert chapter.parent_identifier == "/us/usc/t16"
    assert chapter.depth == 1


def test_subchapters_are_children_of_the_chapter_in_document_order(nodes):
    subchapters = [n for n in nodes if n.level == "subchapter"]
    assert all(n.parent_identifier == "/us/usc/t16/ch1" for n in subchapters)
    assert [n.seq for n in subchapters] == list(range(len(subchapters)))
    assert [n.num_value for n in subchapters[:3]] == ["I", "II", "III"]


def test_yields_parents_before_children(nodes):
    """Pre-order, so the tree can be inserted parent-first — `end` events alone
    would arrive innermost-first."""
    seen: set[str] = set()
    for node in nodes:
        assert node.parent_identifier is None or node.parent_identifier in seen
        seen.add(node.identifier)


def test_status_is_captured_on_a_subchapter(nodes):
    """Title 16's only `reserved` is on a subchapter, not a section (gotcha 13) —
    if structure nodes dropped `@status` it would be unreachable."""
    reserved = [n for n in nodes if n.status == "reserved"]
    assert [n.identifier for n in reserved] == ["/us/usc/t16/ch1/schXCVII"]


def test_every_node_carries_a_guid(nodes):
    """Structure guids go into `guid_map` too, so `?id=` resolves a chapter."""
    assert all(node.guid and node.guid.startswith("id") for node in nodes)


def test_no_sections_or_quoted_content_leak_in(nodes):
    assert {n.level for n in nodes} == {"title", "chapter", "subchapter"}
    assert all(n.identifier.count("/s") == 0 or "/sch" in n.identifier for n in nodes)
