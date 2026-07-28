# ADR-0014: Bulk-load resume state lives in the database, not a second ledger

**Status:** Accepted — 2026-07-28 (Session 8)
**Context:** ADR-0012 (download ledger); ADR-0007 (content dedupe); ADR-0008
(per-release facts on the release map); PLAN §11.5 (`make verify`). Implements
`ingest/load_all.py` and `ingest/verify.py`.

## The question

The download side keeps its own ledger (ADR-0012) because the filesystem cannot
express "the server says this file does not exist". The load side has no such
gap — Postgres already knows what was loaded. Adding a second JSON ledger for
loads would create two states that can disagree, and the disagreement would be
silent.

## Decision

**`title_versions.sections_loaded` is the resume marker.** It is NULL until a
load finishes and is stamped with the section count in the same commit that ends
the load. `load-all` skips a `(release, title)` only when it is non-NULL.

The subtlety this exists for: the `title_versions` *row* is created before any
section is read, and `load_release` commits as it goes (guid batches). So row
presence proves nothing — an interrupted load leaves a row with partial sections.
Only the completion count, written last, means "finished". A crash therefore
leaves NULL, and the pair is redone from the top, which is safe because
`load_release` is idempotent by construction: content-hash dedupe (ADR-0007) plus
upserts on the release map mean a redo costs time, never duplicate rows.

The same column does double duty as the verification datum, which is why it is a
count rather than a boolean.

**Order is inventory `seq`, oldest release point first.** The baseline sweep
(ADR-0012) must land before the deltas that assume it, and `first_release_id`
must end up on the earliest release carrying a given text (ADR-0008) — loading
newest-first would attribute every text to whenever we happened to start.

**Bounded disk and memory.** Each title's zip is extracted to a temporary
directory and deleted after loading, so the corpus never doubles (the XML is
several times the ~9 GB of zips). One session per title, closed after, so a
5,000-section identity map does not survive into the next title.

**Failures are isolated.** One title that will not parse must not end a run of
3,000 — it is recorded and the walk continues, the same stance the downloader
takes toward one file that will not fetch.

## Two vocabularies for a title number, and the bug that proved it

`Title.num` is the **URL** form, taken from `<docNumber>`: `1`, `16` — what
`/us/usc/t1/...` resolves against. The ledger and every OLRC filename use the
**file-naming** form: `01`, `16`, `05a` (gotcha 7). Both are correct in their own
layer, and neither can be changed without breaking the other.

Comparing them raw meant resume never recognized a loaded single-digit title, so
`load-all` would have reloaded titles 1–9 on every run, forever, while reporting
success. Conversion is now explicit at the one boundary where the two meet.

A related defect surfaced the same way: ledger paths written as relative *but
including* the corpus prefix (`data/releases/{label}/{file}`) slipped past
ADR-0013's absolute-path normalization and re-resolved to
`data/releases/data/releases/…`, hiding 449 of 538 downloaded files from the
planner. Paths now normalize to the `{label}/{filename}` contract however they
were recorded.

Both bugs share a shape worth naming: **a string that means different things in
two layers, compared without conversion, failing silently in the safe-looking
direction** — extra work rather than an error.

## `make verify`, at two depths

- **Shallow** (default, seconds): for every completed `(title, release)`, does
  `section_release_map` hold exactly `sections_loaded` rows?
- **Deep** (`--deep`, hours): re-parse the source XML and recount independently.

The distinction matters. Shallow compares the loader's work against the loader's
own bookkeeping, so it cannot catch a parser that missed the same sections at
load time and again now. Only deep re-derives from source, which is what makes
the committed artifact evidence rather than an assertion (documentation duty 5).

The gap between raw section-shaped elements and stored sections is ADR-0005's and
is reported per title, not treated as an error. `ingest/verify.py` names no USLM
elements — which elements are excluded is the parser's business (architecture
rule 2); verification only sees `raw - stored`.

## Consequences

- `make verify` stops being a stub; `make verify-deep` and `make load-all` join it.
- Reports go to `docs/verification/database.json`, committed.
- The headline metric is the dedupe ratio — `section_versions` against
  one-row-per-(section, release) — which is what ADR-0007 predicted and this is
  the first run large enough to measure honestly.
- Two `title_versions` rows loaded before this column existed read as incomplete
  and will be redone once; harmless, and correct given the marker's meaning.
- API tests that asserted the database held *exactly* Title 16 now assert Title
  16's entry, so a bulk-loaded database still passes `make test`.
