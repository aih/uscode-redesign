"""What ingest writes to the index, and what it deliberately does not (ADR-0028).

These bind the module-level functions before `conftest.mock_search_sync` patches
the module attributes, so the real implementations are under test. The OpenSearch
client is mocked; nothing here needs a cluster.
"""

import pytest
from unittest.mock import MagicMock, patch

from ingest.search_sync import (
    doc_id,
    retire_versions,
    strip_xml_tags,
    sync_sections,
    sync_structure_nodes,
)


@pytest.fixture
def enabled(monkeypatch):
    """Ingest disables sync by default (conftest sets DISABLE_SEARCH_SYNC=1) so
    loads never need a cluster. These tests are about what it writes when it is
    switched on."""
    monkeypatch.delenv("DISABLE_SEARCH_SYNC", raising=False)


@pytest.fixture
def bulk(enabled):
    with patch("ingest.search_sync.get_search_client", return_value=MagicMock()), \
         patch("ingest.search_sync.helpers") as helpers:
        yield helpers.bulk


def _actions(bulk):
    return bulk.call_args.args[1]


VERSION = {
    "identifier": "/us/usc/t16/s45f",
    "num": "§ 45f.",
    "heading": "Wolf Trap National Park",
    "xml": "<section><content>Wolf Trap</content></section>",
    "status": None,
    "version_id": 7,
    "first_release_id": 12,
    "first_release_seq": 379,
    "first_release_label": "119-99",
    "is_current": True,
}


def test_the_document_id_is_the_version_not_the_release(bulk):
    """`_id` keys on the release the text *first appeared* at, which is the
    version's identity under ADR-0007 dedupe. Keying on the requesting release
    would write a new document for every republication of unchanged text."""
    assert doc_id("/us/usc/t16/s45f", 12) == "/us/usc/t16/s45f@12"

    sync_sections([VERSION])
    action = _actions(bulk)[0]
    assert action["_id"] == "/us/usc/t16/s45f@12"
    assert action["_index"] == "uscode_sections"


def test_a_section_is_indexed_with_its_release_ordering_and_currency(bulk):
    sync_sections([VERSION])
    source = _actions(bulk)[0]["_source"]

    assert source["identifier"] == "/us/usc/t16/s45f"
    assert source["is_current"] is True
    # The inventory's global seq, not the row id: labels do not sort (gotcha 4)
    # and ids are insertion order.
    assert source["first_release_seq"] == 379
    assert source["first_release_label"] == "119-99"
    assert source["xml_text"] == "Wolf Trap"


def test_retiring_a_version_sends_a_partial_update_not_the_text(bulk):
    """Superseding a version must not resend its body — the whole point of the
    incremental path is that an amendment costs one small write per section."""
    retire_versions([("/us/usc/t16/s45f", 12), ("/us/usc/t16/s1", 3)])

    actions = _actions(bulk)
    assert [a["_id"] for a in actions] == ["/us/usc/t16/s45f@12", "/us/usc/t16/s1@3"]
    assert all(a["_op_type"] == "update" for a in actions)
    assert all(a["doc"] == {"is_current": False} for a in actions)
    assert all("xml_text" not in a.get("doc", {}) for a in actions)


def test_retiring_tolerates_documents_that_were_never_indexed(bulk):
    """Search arrived after the corpus was loaded, so a superseded version may
    have no document at all. That is not an error."""
    retire_versions([("/us/usc/t16/s45f", 12)])
    assert bulk.call_args.kwargs["raise_on_error"] is False


def test_nothing_is_written_for_an_empty_batch(bulk):
    sync_sections([])
    retire_versions([])
    sync_structure_nodes([])
    bulk.assert_not_called()


def test_structure_nodes_carry_is_current_so_the_default_filter_keeps_them(bulk):
    """structure_nodes is unversioned; without the field the `is_current` filter
    would quietly drop every chapter and subchapter from results."""
    sync_structure_nodes([
        {"identifier": "/us/usc/t16/ch1", "level": "chapter", "num_value": "1", "heading": "PARKS"}
    ])
    source = _actions(bulk)[0]["_source"]
    assert source["is_current"] is True
    assert _actions(bulk)[0]["_id"] == "/us/usc/t16/ch1"


def test_sync_is_a_no_op_when_disabled(monkeypatch):
    """A load that cannot reach OpenSearch is a successful load with a stale
    index — ingest must not require a cluster."""
    monkeypatch.setenv("DISABLE_SEARCH_SYNC", "1")
    with patch("ingest.search_sync.get_search_client") as factory:
        sync_sections([VERSION])
        retire_versions([("/us/usc/t16/s45f", 12)])
        sync_structure_nodes([{"identifier": "/us/usc/t16/ch1"}])
    factory.assert_not_called()


@pytest.mark.parametrize(
    "xml, expected",
    [
        ("<a>one</a><b>two</b>", "one two"),
        ("", ""),
        (None, ""),
    ],
)
def test_strip_xml_tags(xml, expected):
    assert strip_xml_tags(xml) == expected
