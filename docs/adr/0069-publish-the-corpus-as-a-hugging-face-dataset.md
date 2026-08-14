# ADR-0069 — Publish the corpus as a Hugging Face dataset

**Status:** accepted (2026-08-14)

**Task:** a public `dreamproit/uscode` dataset on the Hugging Face Hub, with a card, built from
this corpus and refreshed when OLRC publishes, modeled on
[dreamproit/bill_summary_us](https://huggingface.co/datasets/dreamproit/bill_summary_us).

**Related:** [ADR-0003](0003-identifier-vs-guid-vs-temporalid.md) (identifier semantics the schema
carries), [ADR-0007](0007-dedupe-section-content.md) (`content_hash` is the join key between the two
configs), [ADR-0008](0008-per-release-facts-on-the-map.md) (why release ranges come from the map),
[ADR-0021](0021-render-every-occurrence.md) (the 160 duplicate-identifier pairs, flagged),
[ADR-0036](0036-poll-daily-record-every-check.md) (the poll an update rides behind),
[ADR-0040](0040-inline-block-partition-measured.md) (the measured partition the text extraction
follows), [ADR-0066](0066-compare-from-the-section-header.md) (why `first_release_id` is not a
release range).

## Context

The corpus is fully loaded: 65,938 sections, 489,738 deduped section versions, 381 release points,
58 titles. AI pipelines that want the US Code as data get it today by scraping or by re-parsing
OLRC's XML themselves. A parquet dataset on the Hub with `load_dataset` access removes both, and the
versioned axis — which text was in force at which release point — is what this corpus has that
existing US Code datasets do not.

## Decisions

### 1. Two configs, one repo

`current` (one row per section at its newest release point, ~66k rows) and `versions` (one row per
distinct text with its release range and list, ~490k rows), both single `train` splits.
`content_hash` — the ADR-0007 dedupe key in hex — joins them. A `current`-only dataset would drop
the versioned axis; a `versions`-only dataset would make the common case (the Code as it stands) a
filter every consumer writes.

### 2. Export from Postgres, not from the XML files

The corpus in Postgres is already parsed, already deduped, and already carries structure, status and
placement; the export is one streaming SQL pass per config
(`ingest/hf_export.py`, on `reindex_search`'s `yield_per` pattern). Re-parsing the 9.7 GB zip corpus
would re-do all of that to produce the same rows. The cost is a loaded database as a prerequisite,
which the dev box and the deployed box both satisfy.

### 3. Datatrove: evaluated and declined

[datatrove](https://github.com/huggingface/datatrove) was reviewed for the pipeline. It processes
documents shaped `(text, id, metadata)` through distributed executors with per-task checkpointing —
built for multi-terabyte unstructured web text (FineWeb, CommonCrawl). This export is a few GB of
structured, multi-column rows produced by one database cursor; the streaming, dedupe and resume
machinery it would add already exist in the ingest layer, and its document model has no place for a
30-column schema. Plain `pyarrow.parquet.ParquetWriter` writes the shards; the `datasets` library is
also not a dependency, for the same reason.

### 4. Plain text is extracted in the parser layer

The dataset's `text` column is the first Python-side USLM→text rendering
(`search_sync.strip_xml_tags` is a regex fallback; the real renderer is TypeScript).
`tests/test_architecture.py` allows USLM element names only in the three parser files, so the
extraction lives there: `ElementNames` gains `toc`, `text_blocks`, `text_run_on` and `text_spaced`
vocabularies, and `StreamingSectionParser` gains `plain_text()` / `notes_text()` driven by them.
Both schema generations get extraction from their own vocabulary, and the allowlist is unchanged.
The block/inline partition follows ADR-0040's measured artifact; `quotedContent` is kept in body
text and classified per occurrence by the same running-prose test. An unheaded designator runs into
its text (`(1) assure the preservation…`, the printed form); a headed provision breaks after its
heading line, which the printed Code does not — recorded on the card as a limitation.

### 5. Release ranges come from the map, never `first_release_id`

`first_release`/`last_release`/`releases`/`text_since` are aggregated from `section_release_map`
ordered by `release_points.seq`. ADR-0066 records why: an incremental load can attach an earlier
release to a version without lowering `first_release_id`, so that column is a storage fact, not a
history.

### 6. One-time setup and recurring update are separate commands

`hf-upload --init` creates the repo (`exist_ok=True`) and uploads the card; it pushes no data.
`hf-export` no-ops when the corpus fingerprint (newest loaded release + table counts) matches
`data/hf/manifest.json`, and refuses nothing else; `hf-upload` pushes the shards in one commit named
for the release point, refuses a `--limit` export, and writes
`docs/verification/hf-dataset.json`. Authentication is `huggingface_hub`'s own resolution (the
`hf auth login` token or `HF_TOKEN`); no command takes a token argument. The dependencies live in a
`dataset` group so the API image carries neither pyarrow nor huggingface_hub, and the CLI imports
them lazily with an install hint.

### 7. License and identity choices

CC0 1.0 — the Code is a US Government work. Appendix and act-form identifiers get `citation: null`
rather than a synthesized `5 U.S.C. App.` form the corpus itself cannot resolve (ADR-0065's
finding). Section numbers keep their en dashes. The four identifiers that embed a literal `§ `
(a converter artifact: `/us/usc/t2/s § 112g`) keep it in `identifier` and lose it in `citation` and
`num_value`.

## Costs

- The full export is a long job (streaming 10 GB of XML with an lxml parse per fragment); it runs
  from `make hf-export`, never in tests. The CI integration test exports the fixture corpus in full
  and asserts exact counts; against a larger corpus it exports 300 rows and asserts shape.
- `versions` re-exports wholesale on every new release point. A new release point touches most
  version rows' `releases` list anyway, and the hub skips unchanged shards by hash at upload.
- The `update-corpus.sh` hook is designed (run export+upload inside the existing `LOADED>0` gate,
  skip without a token) but not wired: the api image would need the `dataset` group first, and until
  then the export runs from the dev box.
- `ancestors` reflects `structure_nodes`' unversioned newest view for rows of every age, said on the
  card.
