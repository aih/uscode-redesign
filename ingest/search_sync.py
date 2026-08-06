"""Keeping OpenSearch in step with Postgres (ADR-0028).

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

import copy
import hashlib
import json
import logging
import os
from typing import Any, Iterable
import re
from opensearchpy import helpers
from storage.postgres import title_sort_key
from storage.search import (
    SECTIONS_INDEX,
    STRUCTURE_INDEX,
    SearchNotConfigured,
    get_search_client,
)

logger = logging.getLogger(__name__)


def _disabled() -> bool:
    """Ingest must not require a search cluster: `make dev-data`, CI, and the
    ingest tests all load without one. A load that cannot reach OpenSearch is a
    successful load with a stale index, never a failed load."""
    return os.environ.get("DISABLE_SEARCH_SYNC") == "1"


_warned_unconfigured = False


def _client():
    """The search client, or None if this environment has no cluster configured.

    Every call below already treats a *failing* cluster as a warning rather than
    an error, per this module's contract. An *unconfigured* one has to be
    treated the same way, and it did not used to need saying: `storage.search`
    defaulted the password, so the client always constructed and the failure
    surfaced later as a connection error inside the try. Now that the default is
    gone (it was a committed credential — ADR-0029) construction itself can
    raise, and it raises outside those try blocks. Without this, forgetting
    SEARCH_PASSWORD would turn a stale index into a failed corpus load.
    """
    global _warned_unconfigured
    try:
        return get_search_client()
    except SearchNotConfigured as exc:
        if not _warned_unconfigured:
            logger.warning(
                "search indexing is skipped: %s "
                "(set DISABLE_SEARCH_SYNC=1 to make this deliberate)",
                exc,
            )
            _warned_unconfigured = True
        return None


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


_TITLE_IN_IDENTIFIER = re.compile(r"^/us/usc/t([0-9]+[a-zA-Z]?)(?:/|$)")
_CHAPTER_IN_IDENTIFIER = re.compile(r"/ch([^/]+)")


def title_num_of(identifier: str | None) -> str | None:
    """`/us/usc/t16/s45f` → `16`, `/us/usc/t5a/pl/92/463/s1` → `5a`.

    Read off the identifier rather than joined from `titles`, so it is available
    to every caller — including `retire_versions`, which has only the key.
    Appendix titles are their own titles (gotcha 7), so `5a` stays `5a`.
    """
    if not identifier:
        return None
    match = _TITLE_IN_IDENTIFIER.match(identifier)
    return match.group(1) if match else None


def chapter_num_of(parent_identifier: str | None) -> str | None:
    """`/us/usc/t16/ch1/schVI` → `1`.

    A section's identifier does not carry its chapter, so this reads the parent
    subdivision recorded on `section_release_map` (ADR-0008 — placement is the
    release point's, not the deduped text's). A section directly under the title
    has no chapter and gets None.
    """
    if not parent_identifier:
        return None
    match = _CHAPTER_IN_IDENTIFIER.search(parent_identifier)
    return match.group(1) if match else None


def citation_sort_key(identifier: str | None, seq_in_title: int | None) -> str | None:
    """A single sortable string putting the corpus in citation order.

    Two parts. The title comes from `title_sort_key`, the same `'5a'` → `(5, 'a')`
    split the front page sorts by (gotcha 16), zero-padded to four digits so the
    comparison stays correct as a string. The position within the title is
    `section_release_map.seq_in_title` — document order as published, which is
    what prev/next already walks — rather than the section number, because
    section numbers are not orderable text: `45a–1` carries an en dash (gotcha
    17) and `2000e-2` sorts nowhere near `2000`.

    A title with no suffix pads with `0`, which sorts before `a`, so title 5
    precedes title 5a as the Code prints them.

    Structure nodes have no `seq_in_title`. They all take position `000000`,
    which puts every chapter and subchapter heading of a title ahead of every
    section of it, rather than each one immediately before the sections it
    contains. Giving them a true position means deriving one from the first
    section beneath each node, and that is a join this pass does not do. The
    user guide records it, under "Ordering the results" in chapter 05; nothing
    on the results page itself does.
    """
    title = title_num_of(identifier)
    if title is None:
        return None
    number, suffix = title_sort_key(title)
    return f"{number:04d}{suffix or '0'}|{(seq_in_title or 0):06d}"


SECTIONS_MAPPING: dict[str, Any] = {
    "mappings": {
        "properties": {
            "identifier": {"type": "keyword"},
            # `num` is a keyword so it can be filtered and aggregated, with a
            # text subfield so `45f` is findable as a word. Without the subfield
            # a search for a section number matched only where the number also
            # appeared in prose.
            "num": {"type": "keyword", "fields": {"text": {"type": "text"}}},
            # No index-time `boost` here. It was 2.0, and OpenSearch multiplies
            # it into the query-time weight rather than replacing it, so
            # `heading^2` in the handler was really weighting headings 4×.
            # Weighting is the scoring model's business (ADR-0049), stated in
            # one place, and measured.
            "heading": {"type": "text"},
            "xml_text": {"type": "text"},
            "status": {"type": "keyword"},
            "version_id": {"type": "integer"},
            # Title and chapter, so a search can be scoped to one (`title:16`,
            # `chapter:1`) and faceted by title. `title_num` is read off the
            # identifier; `chapter` comes from the parent subdivision recorded
            # on `section_release_map`.
            "title_num": {"type": "keyword"},
            "chapter": {"type": "keyword"},
            # Citation order as one sortable string — `?sort=citation`.
            "sort_key": {"type": "keyword"},
            # The source published more than one element under this identifier
            # at this release point (ADR-0021), so this document is one of two
            # that share an `_id` and the index kept one. Flagged rather than
            # smoothed over: it is the one case where a result is knowingly
            # incomplete.
            "id_collision": {"type": "boolean"},
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
            "heading": {"type": "text"},
            "status": {"type": "keyword"},
            "title_num": {"type": "keyword"},
            "chapter": {"type": "keyword"},
            "sort_key": {"type": "keyword"},
            # structure_nodes is unversioned — one row holding the newest loaded
            # release's view (CLAUDE.md). Carrying the field anyway keeps the
            # default `is_current` filter from silently excluding this index.
            "is_current": {"type": "boolean"},
            "first_release_seq": {"type": "integer"},
        }
    }
}


INDEX_MAPPINGS: dict[str, dict[str, Any]] = {
    SECTIONS_INDEX: SECTIONS_MAPPING,
    STRUCTURE_INDEX: STRUCTURE_MAPPING,
}
"""What each index name means. `SECTIONS_INDEX` and `STRUCTURE_INDEX` are
*aliases* pointing at a physical index named for the mapping it was built from —
see `mapping_fingerprint`."""


def mapping_fingerprint(mapping: dict[str, Any]) -> str:
    """A short, stable hash of a mapping.

    This is what makes "the deployed index is out of date" a question a script
    can answer. The mapping is not additive (ADR-0028): OpenSearch will not add
    a field type to a live index, so a mapping change that nobody rebuilds for
    leaves the new fields **absent rather than broken** — `title:16` returns no
    results, which reads exactly like a title with nothing in it.

    Computed over the mapping as declared, before `_meta` is attached, so
    stamping the fingerprint into the index does not change the fingerprint.
    """
    canonical = json.dumps(mapping, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def physical_index(alias: str, fingerprint: str | None = None) -> str:
    """`uscode_sections` → `uscode_sections_a1b2c3d4e5f6`.

    The name carries the mapping it was built from, so two generations can exist
    at once — which is what lets a rebuild finish before anything starts reading
    from it.
    """
    if fingerprint is None:
        fingerprint = mapping_fingerprint(INDEX_MAPPINGS[alias])
    return f"{alias}_{fingerprint}"


def _body_with_meta(alias: str) -> dict[str, Any]:
    body = copy.deepcopy(INDEX_MAPPINGS[alias])
    body.setdefault("mappings", {})["_meta"] = {
        "fingerprint": mapping_fingerprint(INDEX_MAPPINGS[alias]),
        "alias": alias,
    }
    return body


def indexed_fingerprint(client, alias: str) -> str | None:
    """The mapping fingerprint of whatever `alias` currently resolves to.

    None when the alias resolves to nothing, or to an index built before
    fingerprints existed — both of which mean "rebuild".
    """
    try:
        mappings = client.indices.get_mapping(index=alias)
    except Exception:
        return None
    for body in mappings.values():
        meta = body.get("mappings", {}).get("_meta") or {}
        return meta.get("fingerprint")
    return None


def stale_aliases(client) -> list[str]:
    """Which indices were built from a mapping this code no longer declares."""
    return [
        alias
        for alias in INDEX_MAPPINGS
        if indexed_fingerprint(client, alias) != mapping_fingerprint(INDEX_MAPPINGS[alias])
    ]


def create_index(client, alias: str) -> str:
    """Create a fresh physical index for `alias`'s current mapping, and return
    its name. Does not point the alias at it — see `promote`."""
    name = physical_index(alias)
    if not client.indices.exists(index=name):
        client.indices.create(index=name, body=_body_with_meta(alias))
    return name


def promote(client, alias: str, physical: str) -> None:
    """Point `alias` at `physical`, and delete whatever it pointed at before.

    The alias move is one `update_aliases` call, so readers never see the name
    resolve to nothing: a search issued during a rebuild reads the old index
    until this returns and the new one after, and there is no moment in between.

    The exception is the first run against a box where `uscode_sections` is a
    *concrete index* rather than an alias, which is every deployment built before
    this existed. An index and an alias cannot share a name, so the old index has
    to be deleted before the alias can take it — a gap of one round trip, once,
    and only on that migration.
    """
    old = []
    if client.indices.exists_alias(name=alias):
        old = [name for name in client.indices.get_alias(name=alias) if name != physical]
    elif client.indices.exists(index=alias):
        logger.info("replacing the concrete index %s with an alias", alias)
        client.indices.delete(index=alias)

    actions = [{"remove": {"index": name, "alias": alias}} for name in old]
    actions.append({"add": {"index": physical, "alias": alias}})
    client.indices.update_aliases(body={"actions": actions})

    for name in old:
        try:
            client.indices.delete(index=name)
        except Exception as exc:
            # The alias already points at the new index, so the site is correct
            # either way; this only leaves disk in use.
            logger.warning("could not delete the superseded index %s: %s", name, exc)


def create_indices():
    """Create the indices if they are missing. Called on every load.

    Deliberately not a rebuild: a load must not decide to spend twenty minutes
    reindexing because the mapping moved. `python -m ingest.reindex_search
    --if-changed` is what does that, and the deploy runs it.
    """
    if _disabled():
        return

    client = _client()
    if client is None:
        return
    try:
        for alias in INDEX_MAPPINGS:
            if client.indices.exists(index=alias) or client.indices.exists_alias(name=alias):
                continue
            promote(client, alias, create_index(client, alias))
    except Exception as e:
        logger.warning(f"Could not create OpenSearch indices: {e}")


def recreate_indices():
    """Drop and rebuild both indices, in place. Used by `--recreate`.

    This is the destructive path: the alias resolves to nothing while the
    rebuild runs, so search answers 503 until it finishes. `--if-changed` builds
    beside the live index instead and is what a deploy should use.
    """
    if _disabled():
        return
    client = _client()
    if client is None:
        return
    for alias in INDEX_MAPPINGS:
        for name in _every_index_for(client, alias):
            try:
                client.indices.delete(index=name)
            except Exception as e:
                logger.warning(f"Could not delete index {name}: {e}")
    create_indices()


def _every_index_for(client, alias: str) -> list[str]:
    """The alias's target, plus any physical index named after it — including
    one a previous rebuild left behind."""
    names = set()
    try:
        if client.indices.exists_alias(name=alias):
            names.update(client.indices.get_alias(name=alias))
        elif client.indices.exists(index=alias):
            names.add(alias)
        names.update(client.indices.get(index=f"{alias}_*", ignore_unavailable=True))
    except Exception as e:
        logger.warning(f"Could not list indices for {alias}: {e}")
    return sorted(names)


def sync_sections(versions: list[dict[str, Any]], index: str | None = None):
    """Bulk index a list of section versions.

    `index` writes into a named physical index instead of through the alias,
    which is what a rebuild does: it fills the new generation while every reader
    is still being served by the old one.

    Each dict needs `identifier`, `first_release_id`, `first_release_seq` and
    `is_current`; `first_release_label`, `num`, `heading`, `xml`, `status`,
    `version_id`, `parent_identifier`, `seq_in_title` and `id_collision` are
    optional.

    `title_num`, `chapter` and `sort_key` are derived here rather than asked of
    every caller: `load.py` and `reindex_search.py` both index sections, and a
    field computed twice is a field that eventually disagrees with itself.
    """
    if _disabled():
        return

    client = _client()
    if client is None:
        return
    actions = []
    for v in versions:
        first_release_id = v["first_release_id"]
        identifier = v["identifier"]
        actions.append({
            "_index": index or SECTIONS_INDEX,
            "_id": doc_id(identifier, first_release_id),
            "_source": {
                "identifier": identifier,
                "num": v.get("num"),
                "heading": v.get("heading"),
                "xml_text": strip_xml_tags(v.get("xml")),
                "status": v.get("status"),
                "version_id": v.get("version_id"),
                "title_num": title_num_of(identifier),
                "chapter": chapter_num_of(v.get("parent_identifier")),
                "sort_key": citation_sort_key(identifier, v.get("seq_in_title")),
                "id_collision": bool(v.get("id_collision", False)),
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

    client = _client()
    if client is None:
        return
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


def sync_structure_nodes(nodes: list[dict[str, Any]], index: str | None = None):
    """Bulk index structure nodes. `index` writes into a named physical index
    rather than through the alias — see `sync_sections`."""
    if _disabled():
        return

    client = _client()
    if client is None:
        return
    actions = []
    for n in nodes:
        identifier = n["identifier"]
        actions.append({
            "_index": index or STRUCTURE_INDEX,
            "_id": identifier,
            "_source": {
                "identifier": identifier,
                "level": n.get("level"),
                "num_value": n.get("num_value"),
                "heading": n.get("heading"),
                "status": n.get("status"),
                "title_num": title_num_of(identifier),
                # A chapter's own identifier carries its number, so this reads
                # the node rather than a parent — `/us/usc/t16/ch1/schVI` is in
                # chapter 1 as much as its sections are.
                "chapter": chapter_num_of(identifier),
                # No `seq_in_title` on a structure node, so it takes position 0
                # and sorts ahead of the sections beneath it.
                "sort_key": citation_sort_key(identifier, None),
                "is_current": True,
                "first_release_seq": n.get("first_release_seq"),
            }
        })
    if actions:
        try:
            helpers.bulk(client, actions)
        except Exception as e:
            logger.warning(f"Failed to bulk index structure nodes: {e}")
