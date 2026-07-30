# ADR-0022 — Keyword search on OpenSearch, indexed by version, current by default

- **Status:** Accepted
- **Date:** 2026-07-30
- **Context:** Session 10 (search)
- **Supersedes:** the draft filed as `0018-keyword-and-vector-search.md`, which
  collided with ADR-0018 (caching). Renumbered rather than filed as "18a": a
  suffix reads as an amendment to the decision it hangs off, and search amends
  nothing about cache policy.

## Context

The site can retrieve any provision at any release point, but only if you already
know its citation. Nothing answers "which sections mention wild horses". That
needs an index over the text.

We considered Postgres full-text search (`tsvector`), which would add no
infrastructure. It was rejected for ranking control and because the same index
has to carry dense vectors later for retrieval-augmented answering; `pgvector` is
another extension to operate and a less direct path than a search engine that
does both.

The hard part is not the engine, it is **what a document is**. The corpus is
5,466,652 (section, release) pairs, deduped by ADR-0007 into 489,738
`section_versions` and 65,938 distinct sections. Three different things could be
"a document", and the choice decides what a search result means.

## Decision

### The index unit is the deduped section *version*

One document per `section_versions` row, `_id` = `{identifier}@{first_release_id}`.

Not the (section, release) pair: that is 5.4M documents, 91% of them
byte-identical republications of text that did not change.

Not the section: that would throw away every superseded version and make
point-in-time search impossible, in a project whose entire subject is that the
law has versions.

### The default search returns only the text in force

Every document carries `is_current`, and a search with no release parameter
filters on it. Without that filter a query for "conservation" returns §3831 once
per amendment — the same provision several times over, ranked against itself.
That is not a result list.

`?release=` / `?date=` swap the filter for `first_release_seq <= seq` plus a
`collapse` on `identifier`, which yields the newest text at or before that
release: the same "answer from the newest release at or before the one asked
for" rule the Repository already applies (gotcha 10). Release labels resolve
through `Repository.resolve_release`, not through SQL in the handler, so
`119-102` disambiguates to `119-102not101` here exactly as on a section page.

### Ordering is the inventory's `seq`, never a row id

The first draft filtered on `release_id`, a Postgres primary key. Release ids are
insertion order, and release labels do not sort lexically (gotcha 4), so neither
orders release points. `first_release_seq` carries `release_points.seq` — the
global ordering taken from the inventory page — which is comparable, stable
across a reload, and the same key every other temporal query in the project uses.

### The index is maintained incrementally, not rebuilt

`ingest.load.load_release` updates the index as it loads:

- a **new** version is indexed, `is_current=True`;
- the section's **previous** versions are retired to `is_current=False`;
- a version that **deduped** — the release republished the text unchanged —
  writes nothing at all.

That last case is 91% of the corpus, so a release point costs an index write per
section it actually changed, not per section in the title. Writes happen *after*
the database transaction commits: indexing text whose transaction then rolled
back would advertise a section the database does not have.

Current-ness is decided against the newest **completed** load of that title, not
against wall-clock order, so loading an old release point after a newer one does
not relabel superseded text as in force. This is the same `seq` gate
`structure_nodes` already uses, and for the same reason — an earlier load once
silently relabelled a `reserved` subchapter `repealed`.

`python -m ingest.reindex_search` is the rebuild path, needed after a mapping
change or over a corpus loaded before search existed. It defaults to
current-only (66k documents, what the default query reads); `--all-versions`
adds the superseded ones (490k) so `?release=` can reach back.

### Search is not required for ingest

`DISABLE_SEARCH_SYNC=1`, and every failure is logged and swallowed. A load that
cannot reach OpenSearch is a successful load with a stale index, never a failed
load — `make dev-data`, CI, and the ingest tests all run without a cluster.

## Consequences

- Fuzzy matching, highlighting and ranking come free, and the `embedding`
  (`knn_vector`, 768-d) field is declared now so dense retrieval needs no
  remapping later.
- A new stateful container in `docker-compose.yml`, and the local memory
  footprint that comes with a JVM.
- **The mapping is not additive.** Changing it needs `--recreate`; OpenSearch
  will not add a field type to a live index.
- `?release=` only reaches as far back as what has been indexed. With the default
  current-only build, a point-in-time search answers from current text alone
  until `--all-versions` has run. The response reports the release it searched,
  so this is visible rather than silent.
- **Not solved here:** a section the source publishes twice under one identifier
  at one release (ADR-0021) has two versions sharing a `_id`, so the index keeps
  one of them. Six title-releases are affected.
- The endpoint is unauthenticated and unthrottled, like `/diff` (ADR-0016). Both
  need rate limiting before the URL is advertised.
