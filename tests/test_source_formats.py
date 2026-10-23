"""The registry of source formats (ADR-0094): every markup OLRC has served for a
page this project reads, each with a committed capture its signature is tested
against."""

from __future__ import annotations

import pytest

from ingest import classification as classification_mod
from ingest import inventory as inventory_mod
from ingest import source_formats
from ingest.classification import (
    ClassificationParseError,
    ClassificationTableUnavailable,
)
from ingest.inventory import InventoryParseError
from ingest.source_formats import REGISTRY, UnrecognisedSourceFormat
from tests.conftest import FIXTURES, REPO_ROOT


def test_format_ids_are_unique_and_name_their_page():
    ids = [source_format.id for source_format in REGISTRY]
    assert len(ids) == len(set(ids))
    for source_format in REGISTRY:
        assert source_format.page in source_formats.PAGE_KINDS
        assert source_format.id.startswith(source_format.page + "/")


def test_every_page_kind_has_a_format_served_now():
    for page in source_formats.PAGE_KINDS:
        assert any(not source_format.retired for source_format in source_formats.formats_for(page))


def test_a_retired_format_was_seen_no_later_than_it_was_retired():
    for source_format in REGISTRY:
        if source_format.last_seen is not None:
            assert source_format.first_seen <= source_format.last_seen


@pytest.mark.parametrize("source_format", REGISTRY, ids=lambda f: f.id)
def test_each_capture_matches_its_own_format_and_no_other(source_format):
    html = (FIXTURES / source_format.fixture).read_text()
    assert source_formats.matching(source_format.page, html) == (source_format,)


@pytest.mark.parametrize("page", source_formats.PAGE_KINDS)
def test_an_unknown_page_names_the_formats_tried(page):
    with pytest.raises(UnrecognisedSourceFormat) as raised:
        source_formats.detect(page, "<html><body>the page moved</body></html>", url="x.html")
    for source_format in source_formats.formats_for(page):
        assert source_format.id in str(raised.value)


def test_every_prior_page_format_has_a_parser():
    prior = {f.id for f in source_formats.formats_for(source_formats.PRIOR_RELEASE_POINTS)}
    assert set(inventory_mod._PRIOR_PARSERS) == prior


@pytest.mark.parametrize(
    "source_format",
    [f for f in REGISTRY if f.page != source_formats.CLASSIFICATION_TABLE],
    ids=lambda f: f.id,
)
def test_every_capture_parses(source_format):
    """Detection decides the parser; each capture then yields something."""
    html = (FIXTURES / source_format.fixture).read_text()
    if source_format.page == source_formats.PRIOR_RELEASE_POINTS:
        assert inventory_mod.parse_inventory(html)
    elif source_format.page == source_formats.CURRENT_RELEASE_POINT:
        assert inventory_mod.parse_current_release_point(html).titles_affected
    elif source_format.page == source_formats.CLASSIFICATION_INDEX:
        assert classification_mod.parse_tables_index(html)
    else:
        assert classification_mod.parse_ecct(html).row_count >= 0


TABLE_FILENAMES = {
    "classification-table/pre-text": "tbl118pl_2nd.htm",
    "classification-table/viewer-empty": "tbl118pl_2nd.html",
    "classification-table/viewer-records": "tbl118pl_2nd.html",
}


@pytest.mark.parametrize(
    "source_format", source_formats.formats_for(source_formats.CLASSIFICATION_TABLE), ids=lambda f: f.id
)
def test_every_table_capture_is_read_by_its_format(source_format):
    html = (FIXTURES / source_format.fixture).read_text()
    filename = TABLE_FILENAMES[source_format.id]
    if source_format.id == "classification-table/viewer-empty":
        with pytest.raises(ClassificationTableUnavailable):
            classification_mod.parse_classification_file(html, filename=filename)
        return
    parsed = classification_mod.parse_classification_file(html, filename=filename)
    assert parsed.source_format == source_format.id
    assert parsed.row_count > 0


def test_the_parse_errors_keep_their_module_types():
    page = "<html><body>the page moved</body></html>"
    with pytest.raises(InventoryParseError):
        inventory_mod.parse_inventory(page)
    with pytest.raises(ClassificationParseError):
        classification_mod.parse_tables_index(page)


def test_the_format_history_documents_every_format():
    """`docs/source-formats.md` is the registry as prose; a format added to one
    and not the other fails here."""
    history = (REPO_ROOT / "docs" / "source-formats.md").read_text()
    for source_format in REGISTRY:
        assert f"`{source_format.id}`" in history, source_format.id
        assert f"`{source_format.fixture}`" in history, source_format.fixture
