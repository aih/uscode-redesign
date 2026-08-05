"""Detecting that the deployed search index was built from an older mapping.

The deploy runs `python -m ingest.reindex_search --if-changed`, and what that
decides rests entirely on the fingerprint. It has to be wrong in the safe
direction: a fingerprint that fails to change when the mapping does leaves a
deployed index missing fields nobody will notice are missing, because the
mapping is not additive (ADR-0028) and an absent field returns *no results*
rather than an error.

No cluster here. `stale_aliases` and `promote` talk to one, so they are driven
against a fake that records what was asked of it — the point being the sequence
of calls, which is the part that has to be right on a box where
`uscode_sections` is still a concrete index.
"""

import copy

import pytest

from ingest import search_sync
from storage.search import SECTIONS_INDEX, STRUCTURE_INDEX


class TestFingerprint:
    def test_it_is_stable_across_runs(self):
        assert search_sync.mapping_fingerprint(
            search_sync.SECTIONS_MAPPING
        ) == search_sync.mapping_fingerprint(search_sync.SECTIONS_MAPPING)

    def test_key_order_does_not_change_it(self):
        # Canonical JSON, so a field moved in the source is not a rebuild.
        reordered = {
            "settings": copy.deepcopy(search_sync.SECTIONS_MAPPING["settings"]),
            "mappings": copy.deepcopy(search_sync.SECTIONS_MAPPING["mappings"]),
        }
        assert search_sync.mapping_fingerprint(reordered) == search_sync.mapping_fingerprint(
            search_sync.SECTIONS_MAPPING
        )

    def test_a_new_field_changes_it(self):
        changed = copy.deepcopy(search_sync.SECTIONS_MAPPING)
        changed["mappings"]["properties"]["something_new"] = {"type": "keyword"}
        assert search_sync.mapping_fingerprint(changed) != search_sync.mapping_fingerprint(
            search_sync.SECTIONS_MAPPING
        )

    def test_a_changed_field_type_changes_it(self):
        """The case that actually bites: `num` gaining a text subfield is not a
        new field, and an index built before it will silently match nothing on
        `num.text`."""
        changed = copy.deepcopy(search_sync.SECTIONS_MAPPING)
        changed["mappings"]["properties"]["num"] = {"type": "keyword"}
        assert search_sync.mapping_fingerprint(changed) != search_sync.mapping_fingerprint(
            search_sync.SECTIONS_MAPPING
        )

    def test_the_two_indices_do_not_share_a_fingerprint(self):
        assert search_sync.mapping_fingerprint(
            search_sync.SECTIONS_MAPPING
        ) != search_sync.mapping_fingerprint(search_sync.STRUCTURE_MAPPING)

    def test_the_physical_name_carries_it(self):
        name = search_sync.physical_index(SECTIONS_INDEX)
        assert name.startswith(f"{SECTIONS_INDEX}_")
        assert name.endswith(search_sync.mapping_fingerprint(search_sync.SECTIONS_MAPPING))

    def test_the_stamped_fingerprint_is_of_the_mapping_without_it(self):
        """Otherwise it is circular: stamping `_meta` into the body would change
        the thing being fingerprinted, and no index would ever match."""
        body = search_sync._body_with_meta(SECTIONS_INDEX)
        assert body["mappings"]["_meta"]["fingerprint"] == search_sync.mapping_fingerprint(
            search_sync.SECTIONS_MAPPING
        )


class FakeIndices:
    """Just enough of `client.indices` to drive the swap."""

    def __init__(self, concrete=(), aliases=None, meta=None):
        self.concrete = set(concrete)
        self.aliases = dict(aliases or {})  # alias -> {index: {}}
        self.meta = dict(meta or {})  # index -> fingerprint
        self.calls: list[tuple] = []

    def exists(self, index):
        return index in self.concrete

    def exists_alias(self, name):
        return name in self.aliases

    def get_alias(self, name):
        return self.aliases[name]

    def get_mapping(self, index):
        target = index
        if index in self.aliases:
            target = next(iter(self.aliases[index]))
        if target not in self.concrete:
            raise KeyError(index)
        fingerprint = self.meta.get(target)
        meta = {"_meta": {"fingerprint": fingerprint}} if fingerprint else {}
        return {target: {"mappings": meta}}

    def create(self, index, body):
        self.calls.append(("create", index))
        self.concrete.add(index)
        self.meta[index] = body["mappings"]["_meta"]["fingerprint"]

    def delete(self, index):
        self.calls.append(("delete", index))
        self.concrete.discard(index)
        self.meta.pop(index, None)

    def update_aliases(self, body):
        self.calls.append(("update_aliases", tuple(sorted(map(str, body["actions"])))))
        for action in body["actions"]:
            if "remove" in action:
                self.aliases.get(action["remove"]["alias"], {}).pop(
                    action["remove"]["index"], None
                )
            else:
                add = action["add"]
                self.aliases.setdefault(add["alias"], {})[add["index"]] = {}

    def refresh(self, index):
        self.calls.append(("refresh", index))


class FakeClient:
    def __init__(self, indices):
        self.indices = indices


def _current(alias):
    return search_sync.mapping_fingerprint(search_sync.INDEX_MAPPINGS[alias])


class TestDriftDetection:
    def test_an_empty_cluster_is_stale(self):
        client = FakeClient(FakeIndices())
        assert search_sync.stale_aliases(client) == [SECTIONS_INDEX, STRUCTURE_INDEX]

    def test_a_concrete_index_with_no_fingerprint_is_stale(self):
        """Every deployment built before this existed. It must rebuild, not be
        mistaken for current because the name is there."""
        client = FakeClient(FakeIndices(concrete=[SECTIONS_INDEX, STRUCTURE_INDEX]))
        assert search_sync.stale_aliases(client) == [SECTIONS_INDEX, STRUCTURE_INDEX]

    def test_an_index_built_from_this_mapping_is_not_stale(self):
        physical = {alias: search_sync.physical_index(alias) for alias in search_sync.INDEX_MAPPINGS}
        client = FakeClient(
            FakeIndices(
                concrete=physical.values(),
                aliases={alias: {name: {}} for alias, name in physical.items()},
                meta={name: _current(alias) for alias, name in physical.items()},
            )
        )
        assert search_sync.stale_aliases(client) == []

    def test_an_index_built_from_an_older_mapping_is_stale(self):
        physical = f"{SECTIONS_INDEX}_oldfingerprint"
        client = FakeClient(
            FakeIndices(
                concrete=[physical],
                aliases={SECTIONS_INDEX: {physical: {}}},
                meta={physical: "oldfingerprint"},
            )
        )
        assert SECTIONS_INDEX in search_sync.stale_aliases(client)


class TestPromote:
    def test_it_moves_the_alias_and_drops_the_old_index(self):
        old, new = f"{SECTIONS_INDEX}_old", f"{SECTIONS_INDEX}_new"
        indices = FakeIndices(concrete=[old, new], aliases={SECTIONS_INDEX: {old: {}}})
        search_sync.promote(FakeClient(indices), SECTIONS_INDEX, new)

        assert indices.aliases[SECTIONS_INDEX] == {new: {}}
        assert old not in indices.concrete
        # The alias moved in one call, so the name never resolves to nothing.
        assert sum(1 for call in indices.calls if call[0] == "update_aliases") == 1

    def test_the_old_index_is_deleted_after_the_alias_moves(self):
        """Order matters: deleting first would leave the alias pointing at a
        missing index for the length of a round trip."""
        old, new = f"{SECTIONS_INDEX}_old", f"{SECTIONS_INDEX}_new"
        indices = FakeIndices(concrete=[old, new], aliases={SECTIONS_INDEX: {old: {}}})
        search_sync.promote(FakeClient(indices), SECTIONS_INDEX, new)

        kinds = [call[0] for call in indices.calls]
        assert kinds.index("update_aliases") < kinds.index("delete")

    def test_a_concrete_index_of_the_alias_name_is_replaced(self):
        """The first run on a box built before aliases existed. An index and an
        alias cannot share a name, so the index has to go first — the one gap in
        this design, once, on that migration."""
        new = f"{SECTIONS_INDEX}_new"
        indices = FakeIndices(concrete=[SECTIONS_INDEX, new])
        search_sync.promote(FakeClient(indices), SECTIONS_INDEX, new)

        assert indices.aliases[SECTIONS_INDEX] == {new: {}}
        assert SECTIONS_INDEX not in indices.concrete
        kinds = [call[0] for call in indices.calls]
        assert kinds.index("delete") < kinds.index("update_aliases")

    def test_promoting_what_is_already_live_deletes_nothing(self):
        live = f"{SECTIONS_INDEX}_live"
        indices = FakeIndices(concrete=[live], aliases={SECTIONS_INDEX: {live: {}}})
        search_sync.promote(FakeClient(indices), SECTIONS_INDEX, live)

        assert indices.aliases[SECTIONS_INDEX] == {live: {}}
        assert live in indices.concrete
        assert not [call for call in indices.calls if call[0] == "delete"]

    def test_a_failed_delete_does_not_undo_the_promotion(self):
        """The alias is already right; a leftover index costs disk and nothing
        else, so it must not turn a successful rebuild into a failure."""
        old, new = f"{SECTIONS_INDEX}_old", f"{SECTIONS_INDEX}_new"

        class Stubborn(FakeIndices):
            def delete(self, index):
                raise RuntimeError("no")

        indices = Stubborn(concrete=[old, new], aliases={SECTIONS_INDEX: {old: {}}})
        search_sync.promote(FakeClient(indices), SECTIONS_INDEX, new)
        assert indices.aliases[SECTIONS_INDEX] == {new: {}}


class TestWriteTarget:
    @pytest.mark.parametrize(
        "sync,payload,default",
        [
            (
                search_sync.sync_sections,
                [{"identifier": "/us/usc/t16/s1", "first_release_id": 1,
                  "first_release_seq": 1, "is_current": True}],
                SECTIONS_INDEX,
            ),
            (
                search_sync.sync_structure_nodes,
                [{"identifier": "/us/usc/t16/ch1"}],
                STRUCTURE_INDEX,
            ),
        ],
    )
    def test_an_explicit_index_beats_the_alias(self, sync, payload, default, monkeypatch):
        """What lets a rebuild fill the new generation while every reader is
        still served by the old one."""
        sent: list[dict] = []
        # The suite runs with DISABLE_SEARCH_SYNC=1 so nothing needs a cluster,
        # and with it set these functions return before building an action.
        monkeypatch.setattr(search_sync, "_disabled", lambda: False)
        monkeypatch.setattr(search_sync, "_client", lambda: object())
        monkeypatch.setattr(
            search_sync.helpers, "bulk", lambda client, actions, **kw: sent.extend(actions)
        )

        sync(payload, index="somewhere_else")
        assert sent[0]["_index"] == "somewhere_else"

        sent.clear()
        sync(payload)
        assert sent[0]["_index"] == default
