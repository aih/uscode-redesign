# ADR-0051 — The search index rebuilds itself when its mapping changes

- **Status:** Accepted
- **Date:** 2026-08-05
- **Context:** Session 29, after B4
- **Amends:** [ADR-0049](0049-search-relevance-measured-and-scoped.md)'s consequence "the mapping
  changed, so the index must be rebuilt", which was a line in a runbook

## Context

ADR-0028 recorded that the index mapping is not additive: OpenSearch will not add a field type to a
live index, so a mapping change needs `--recreate`. ADR-0049 changed the mapping and inherited that
sentence as an instruction to somebody.

The reason that is not good enough is the shape of the failure. A field the new code queries and
the old index does not have is **absent, not broken**. `title:16` becomes a filter on a field that
does not exist, which matches nothing — and "no results" is what a title with nothing in it looks
like too. Nothing raises, nothing is logged, no alert fires, the deploy is green, and every scoped
search quietly returns an empty page. `/app/search/syntax` describing operators that silently do
nothing is precisely what ADR-0038 exists to prevent, arrived at from the deployment side instead
of the documentation side.

The obvious automation — run `--recreate` on every deploy — is worse than the problem. It deletes
the live index and rebuilds 66,000 documents while the site is up, so search answers 503 for the
length of the rebuild, on every deploy, whether or not anything changed.

## Decision

### The mapping carries a fingerprint, and the deploy asks

`mapping_fingerprint()` is a short sha256 of the mapping as declared, canonicalised so a field
moved in the source is not a change. It is stamped into the index's `_meta` at creation.
`stale_aliases()` compares what the code declares against what each live index was built from, and
`python -m ingest.reindex_search --if-changed` rebuilds only those. On a deploy that changes no
mapping it is two requests.

An index with no fingerprint at all counts as stale. That is every index built before this existed,
including the deployed one, so the first run migrates rather than needing to be told to.

### The index names become aliases, and a rebuild builds beside the live one

`uscode_sections` and `uscode_structure` are now aliases pointing at a physical index named for the
mapping it was built from — `uscode_sections_b8be98476068`. A rebuild creates the next generation
under its own name, fills it while every reader is still being served by the current one, and moves
the alias in a single `update_aliases` call. A search issued during a rebuild reads the old index
throughout and the new one afterwards; there is no moment in between.

Reads and incremental writes go through the alias and did not change. Only the rebuild names a
physical index, through the `index=` parameter added to `sync_sections` and `sync_structure_nodes`.

### Nothing is promoted until everything is built

Both indices are filled first and both aliases moved afterwards, so a failure in the second does not
leave the first live against a half-migrated pair.

### A failed rebuild is not a failed deploy

The step is `|| echo` in `deploy/deploy-on-box.sh`. This is safe rather than lax, and it is safe
*because* of the order above: a failure part-way leaves the alias where it was, so the site keeps
the index it already had. Stale search on a deployed site beats rolling back everything else on the
release because a reindex timed out.

## Consequences

- **One gap, once.** An index and an alias cannot share a name, so on a box where `uscode_sections`
  is still a concrete index it has to be deleted before the alias can take the name — a gap of one
  round trip, on that migration only. Every rebuild after it is gapless. Asserted in
  `tests/test_search_mapping.py::test_a_concrete_index_of_the_alias_name_is_replaced`.
- **Deploys that change the mapping get longer** by a full current-text rebuild — 66k documents.
  Deploys that do not are unaffected.
- **The box rebuilds current text only.** `--all-versions` is 490k documents and has been OOM-killed
  on this box twice (`docs/deploy-status.md`), so `?release=` search reaches back only as far as
  whatever `--all-versions` pass last succeeded. The same limit ADR-0028 already recorded, now with
  a deploy that will not quietly make it worse.
- **A rebuild concurrent with a corpus load is still unguarded.** `update-corpus.sh` and a deploy
  can in principle overlap, and an incremental load during a rebuild writes through the alias to the
  outgoing index, so those writes are lost when it is promoted away. The corpus poll is daily and a
  deploy is minutes; the fix is a lock, and it is not here.
- **Two generations exist on disk** between build and promote, so the cluster needs room for both.
  At 66k current-text documents that is under a gigabyte.
- **Disk left behind by a failed rebuild is not collected.** The half-built index keeps its name and
  the next run of `--if-changed` reuses it, since `create_index` is create-if-absent and the
  documents are overwritten by `_id`. `--recreate` deletes every `<alias>_*` index and starts over.
