"""Keeping OpenSearch in step with Postgres (ADR-0022).

The index unit is a *section version* — the deduped text (ADR-0007), not the
(section, release) pair. 5.4M pairs collapse to 490k versions, and a section's
text is one document however many release points republish it unchanged.

Versioning rule: exactly one version per section carries `is_current`, and the
default search filters on it. Without that filter a query for "conservation"
returns the same section once per version, which is not a useful result list and
is not what a reader means by "search the US Code".

`first_release_seq` is the release the text first appeared at, on the inventory's
global ordering (`release_points.seq`) rather than a database id, so it is
comparable across releases and survives a reload. It is immutable for the life of
the document, which is what makes incremental sync cheap: a release republishing
a section unchanged touches nothing at all.
"""

import logging
import os
from typing import Any, Iterable
import re
from opensearchpy import helpers
from storage.search import SECTIONS_INDEX, STRUCTURE_INDEX, get_search_client

logger = logging.getLogger(__name__)


def _disabled() -> bool:
    """Ingest must not require a search cluster: `make dev-data`, CI, and the
    ingest tests all load without one. A load that cannot reach OpenSearch is a
    successful load with a stale index, never a failed load."""
    return os.environ.get("DISABLE_SEARCH_SYNC") == "1"


def strip_xml_tags(xml_str: str) -> str:
    """A simple fallback regex to strip xml tags for text indexing."""
    if not xml_str:
        return ""
    text = re.sub(r'<[^>]+>', ' ', xml_str)
    return re.sub(r'\s+', ' ', text).strip()


def doc_id(identifier: str, first_release_id: int) -> str:
    """One document per (section, text). `first_release_id` is the version's own
    identity under ADR-0007 dedupe, so this is stable across reindexes — a
    re-run overwrites rather than duplicating."""
    return f"{identifier}@{first_release_id}"


SECTIONS_MAPPING: dict[str, Any] = {
    "mappings": {
        "properties": {
            "identifier": {"type": "keyword"},
            "num": {"type": "keyword"},
            "heading": {"type": "text", "boost": 2.0},
            "xml_text": {"type": "text"},
            "status": {"type": "keyword"},
            "version_id": {"type": "integer"},
            # The release this text first appeared at, as an inventory seq —
            # `release_id` (a row id) was neither ordered nor stable.
            "first_release_id": {"type": "integer"},
            "first_release_seq": {"type": "integer"},
            "first_release_label": {"type": "keyword"},
            "is_current": {"type": "boolean"},
            "embedding": {
                "type": "knn_vector",
                "dimension": 768,
                "method": {
                    "name": "hnsw",
                    "space_type": "l2",
                    "engine": "nmslib"
                }
            }
        }
    },
    "settings": {
        "index": {
            "knn": True
        }
    }
}

STRUCTURE_MAPPING: dict[str, Any] = {
    "mappings": {
        "properties": {
            "identifier": {"type": "keyword"},
            "level": {"type": "keyword"},
            "num_value": {"type": "keyword"},
            "heading": {"type": "text", "boost": 2.0},
            # structure_nodes is unversioned — one row holding the newest loaded
            # release's view (CLAUDE.md). Carrying the field anyway keeps the
            # default `is_current` filter from silently excluding this index.
            "is_current": {"type": "boolean"},
            "first_release_seq": {"type": "integer"},
        }
    }
}


def create_indices():
    """Create OpenSearch indices if they do not exist."""
    if _disabled():
        return

    client = get_search_client()
    try:
        if not client.indices.exists(index=SECTIONS_INDEX):
            client.indices.create(index=SECTIONS_INDEX, body=SECTIONS_MAPPING)
        if not client.indices.exists(index=STRUCTURE_INDEX):
            client.indices.create(index=STRUCTURE_INDEX, body=STRUCTURE_MAPPING)
    except Exception as e:
        logger.warning(f"Could not create OpenSearch indices: {e}")


def recreate_indices():
    """Drop and rebuild both indices. Mapping changes need this — OpenSearch will
    not add a field type to a live index, and a `create_indices` that only ever
    creates-if-absent would leave the old mapping in place forever."""
    if _disabled():
        return
    client = get_search_client()
    for index in (SECTIONS_INDEX, STRUCTURE_INDEX):
        try:
            if client.indices.exists(index=index):
                client.indices.delete(index=index)
        except Exception as e:
            logger.warning(f"Could not delete index {index}: {e}")
    create_indices()


def sync_sections(versions: list[dict[str, Any]]):
    """Bulk index a list of section versions.

    Each dict needs `identifier`, `first_release_id`, `first_release_seq` and
    `is_current`; `first_release_label`, `num`, `heading`, `xml`, `status`,
    `version_id` are optional.
    """
    if _disabled():
        return

    client = get_search_client()
    actions = []
    for v in versions:
        first_release_id = v["first_release_id"]
        actions.append({
            "_index": SECTIONS_INDEX,
            "_id": doc_id(v["identifier"], first_release_id),
            "_source": {
                "identifier": v["identifier"],
                "num": v.get("num"),
                "heading": v.get("heading"),
                "xml_text": strip_xml_tags(v.get("xml")),
                "status": v.get("status"),
                "version_id": v.get("version_id"),
                "first_release_id": first_release_id,
                "first_release_seq": v["first_release_seq"],
                "first_release_label": v.get("first_release_label"),
                "is_current": v["is_current"],
            }
        })
    if actions:
        try:
            helpers.bulk(client, actions)
        except Exception as e:
            logger.warning(f"Failed to bulk index sections: {e}")


def retire_versions(keys: Iterable[tuple[str, int]]):
    """Clear `is_current` on superseded versions.

    `keys` is (identifier, first_release_id) pairs. This is the whole cost of an
    incremental update: a release point that changes 300 sections retires 300
    documents, regardless of how many sections the title has. Uses a partial
    update so the indexed text is not resent.
    """
    if _disabled():
        return

    client = get_search_client()
    actions = [
        {
            "_op_type": "update",
            "_index": SECTIONS_INDEX,
            "_id": doc_id(identifier, first_release_id),
            "doc": {"is_current": False},
        }
        for identifier, first_release_id in keys
    ]
    if actions:
        try:
            # A superseded version may not be indexed yet (search came after the
            # corpus was loaded), and missing documents are not an error here.
            helpers.bulk(client, actions, raise_on_error=False)
        except Exception as e:
            logger.warning(f"Failed to retire section versions: {e}")


def sync_structure_nodes(nodes: list[dict[str, Any]]):
    """Bulk index structure nodes."""
    if _disabled():
        return

    client = get_search_client()
    actions = []
    for n in nodes:
        actions.append({
            "_index": STRUCTURE_INDEX,
            "_id": n["identifier"],
            "_source": {
                "identifier": n["identifier"],
                "level": n.get("level"),
                "num_value": n.get("num_value"),
                "heading": n.get("heading"),
                "is_current": True,
                "first_release_seq": n.get("first_release_seq"),
            }
        })
    if actions:
        try:
            helpers.bulk(client, actions)
        except Exception as e:
            logger.warning(f"Failed to bulk index structure nodes: {e}")
