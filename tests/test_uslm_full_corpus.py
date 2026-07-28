"""Full-sample integration tests — `@pytest.mark.slow`, excluded from `make test`.

Run with `make test-slow` (or `uv run pytest -m slow`). These are the counts that
prove the parser sees the whole corpus the way the source XML actually is; the
numbers below were derived from the samples and are recorded in CLAUDE.md.
"""

import subprocess
import sys
from collections import Counter

import pytest
from lxml import etree

from ingest import (
    UslmVersion,
    detect_uslm_version,
    iter_sections,
    iter_structure,
    parse_meta,
)

from .conftest import REPO_ROOT, USLM1_USC16, USLM2_USC16, USLM2_USC49, require

pytestmark = pytest.mark.slow

USLM1 = "http://xml.house.gov/schemas/uslm/1.0"

# Title 16 @ 119-102not101, USLM 1.0.15.
T16_SECTION_ELEMENTS = 5393  # every <section> in the file, quoted text included
T16_QUOTED_SECTIONS = 298  # <section> inside <quotedContent> — not code sections
T16_SECTIONS = 5095  # what the parser emits
T16_STATUS = {"repealed": 522, "omitted": 102, "transferred": 19}
T16_RESERVED_SUBCHAPTERS = 1  # the file's one status="reserved", not on a section

T16_STRUCTURE = {"title": 1, "chapter": 153, "subchapter": 345, "part": 57, "subpart": 13}

S45F_C5 = "/us/usc/t16/s45f/c/5"
S45F_C5_GUID = "id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd"


@pytest.fixture(scope="module")
def usc16_sections():
    return list(iter_sections(require(USLM1_USC16)))


def test_title_16_section_counts(usc16_sections):
    assert len(usc16_sections) == T16_SECTIONS
    assert [s.seq for s in usc16_sections] == list(range(T16_SECTIONS))
    assert len({s.identifier for s in usc16_sections}) == T16_SECTIONS


def test_title_16_status_counts(usc16_sections):
    counts = Counter(s.status for s in usc16_sections if s.status)

    assert dict(counts) == T16_STATUS


def test_title_16_raw_element_counts_explain_the_emitted_total():
    """CLAUDE.md's headline figure (5,393 sections; 523 repealed) counts raw
    `<section>` elements. 298 of them are quoted text from amending acts and one of
    those is marked repealed, so the parser emits 5,095 sections and 522 repealed.
    The document's single `reserved` is on a `<subchapter>`."""
    tree = etree.parse(str(require(USLM1_USC16)))
    elements = tree.findall(f".//{{{USLM1}}}section")
    quoted = [
        element
        for element in elements
        if any(a.tag == f"{{{USLM1}}}quotedContent" for a in element.iterancestors())
    ]
    reserved = tree.xpath("//*[@status='reserved']")

    assert len(elements) == T16_SECTION_ELEMENTS
    assert len(quoted) == T16_QUOTED_SECTIONS
    assert len(elements) - len(quoted) == T16_SECTIONS
    assert Counter(e.get("status") for e in elements if e.get("status"))["repealed"] == 523
    assert [etree.QName(e).localname for e in reserved] == [
        "subchapter"
    ] * T16_RESERVED_SUBCHAPTERS


def test_known_good_guid_maps_to_its_provision(usc16_sections):
    guid_map = {
        ref.guid: ref.identifier
        for section in usc16_sections
        for ref in section.guid_refs
    }

    assert guid_map[S45F_C5_GUID] == S45F_C5


def test_every_guid_in_the_file_is_indexed_exactly_once(usc16_sections):
    """`guid_map` is global (PLAN.md §3) — a guid appearing twice would corrupt it."""
    guids = [ref.guid for s in usc16_sections for ref in s.guid_refs]

    assert len(guids) == len(set(guids))
    assert len(guids) > 60_000


def test_title_16_structure_counts():
    """Every structural element in the file carries an `@identifier` and none sit
    inside `<toc>`, `<notes>` or `<quotedContent>` — verified against the raw tree
    below, so the TOC pass's totals are the document's totals, not a subset."""
    nodes = list(iter_structure(require(USLM1_USC16)))
    tree = etree.parse(str(require(USLM1_USC16)))
    raw = [
        element
        for level in T16_STRUCTURE
        for element in tree.findall(f".//{{{USLM1}}}{level}")
    ]

    assert dict(Counter(n.level for n in nodes)) == T16_STRUCTURE
    assert len(nodes) == len(raw) == sum(T16_STRUCTURE.values())
    assert all(element.get("identifier") for element in raw)


def test_title_16_structure_is_one_tree_in_pre_order():
    nodes = list(iter_structure(require(USLM1_USC16)))
    seen: set[str] = set()

    for node in nodes:
        assert node.parent_identifier is None or node.parent_identifier in seen
        seen.add(node.identifier)

    assert [n.identifier for n in nodes if n.parent_identifier is None] == ["/us/usc/t16"]
    assert len(seen) == len(nodes)


def test_uslm2_structure_uses_the_same_element_vocabulary():
    """ADR-0006's premise: structural markup barely moved between 1.x and 2.x, so
    one TOC pass serves both. Title 49 also exercises `subtitle`, which Title 16
    has no instance of."""
    nodes = list(iter_structure(require(USLM2_USC49)))

    assert dict(Counter(n.level for n in nodes)) == {
        "title": 1,
        "subtitle": 10,
        "chapter": 114,
        "subchapter": 58,
        "part": 16,
        "subpart": 4,
    }
    assert nodes[0].identifier == "/us/usc/t49"
    assert nodes[0].heading == "TRANSPORTATION"


def test_meta_of_the_current_release_point():
    meta = parse_meta(require(USLM1_USC16))

    assert meta.schema_version == "uslm-1.0.15"
    assert meta.release_label == "119-102not101"
    assert meta.is_positive_law is False


def test_parsing_32_mb_stays_memory_bounded():
    """Gotcha 6: Title 42 is multiples of this file. If the streaming prune ever
    regressed to holding the tree, peak RSS would grow with file size.

    Measured in a clean subprocess: `ru_maxrss` is a high-water mark, so anything
    an earlier test allocated in this process would mask a regression.
    """
    result = subprocess.run(
        [sys.executable, "-c", _PEAK_RSS_PROBE, str(require(USLM1_USC16))],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    count, peak_bytes = (int(value) for value in result.stdout.split())

    assert count == T16_SECTIONS
    assert peak_bytes < 150 * 1024 * 1024, (
        f"peak RSS {peak_bytes / 1e6:.0f} MB for a 32 MB file — streaming regressed"
    )


_PEAK_RSS_PROBE = """
import resource, sys
from ingest import iter_sections
count = sum(1 for _ in iter_sections(sys.argv[1]))
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
# ru_maxrss is bytes on macOS, kilobytes on Linux.
print(count, peak if sys.platform == "darwin" else peak * 1024)
"""


@pytest.mark.parametrize(
    "path,expected_sections,expected_status",
    [
        (USLM2_USC16, 5028, {"repealed": 520, "omitted": 102, "transferred": 19}),
        (USLM2_USC49, 1350, {"repealed": 43, "renumbered": 9}),
    ],
)
def test_uslm2_samples_parse(path, expected_sections, expected_status):
    """Title 49 carries `renumbered`, a status Title 16 never shows — which is why
    `status` is a free string and never an enum."""
    sections = list(iter_sections(require(path)))

    assert detect_uslm_version(require(path)) is UslmVersion.V2
    assert len(sections) == expected_sections
    assert dict(Counter(s.status for s in sections if s.status)) == expected_status


def test_cross_schema_parity_for_one_section():
    """Same provision, two schemas: identity and text carry over, the guid does not
    (it pins a release point — ADR-0003), and neither vintage is the other's."""
    one = next(s for s in iter_sections(require(USLM1_USC16)) if s.identifier.endswith("/s45f"))
    two = next(s for s in iter_sections(require(USLM2_USC16)) if s.identifier.endswith("/s45f"))

    assert one.identifier == two.identifier == "/us/usc/t16/s45f"
    assert one.num_value == two.num_value == "45f"
    assert one.heading == two.heading == "Mineral King Valley addition authorized"
    assert one.guid != two.guid
    assert (one.schema_version, two.schema_version) == ("uslm-1.0.15", "uslm-2.0.12")
