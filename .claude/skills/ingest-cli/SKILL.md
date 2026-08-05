---
name: ingest-cli
description: The `python -m ingest` command-line reference for this project — inventory, fetch, backfill, mirror push/pull, load-all, load, reindex_search, verify, verify-downloads — plus scripts/vendor_apidocs.py. Use when running, resuming, or debugging any corpus download, load, search-index, or verification job.
---

# `python -m ingest` — command reference

Moved out of `CLAUDE.md` so it loads only when ingest work is actually happening.
The `make` targets stay in `CLAUDE.md`; this file covers the module CLI beneath them.

## python -m ingest inventory [--from-file PATH] [--no-seed]
  Fetches uscode.house.gov/download/priorreleasepoints.htm, writes data/uscreleasepoints.json
  ({name, date, titlesAffected, url} per RP, loadusc-xcitedb's shape), and seeds release_points
  with real currency dates, titles_affected, and a global seq from page order.

  Records a `source_checks` row when it actually fetches (not for `--from-file`, and not for
  `--no-seed`, which is told to leave the database alone) — see `check` below and ADR-0036.

## python -m ingest check [--url U] [--out PATH]
  The daily poll (ADR-0036). One request to the release-points page; writes a `source_checks`
  row whatever happens — including when the fetch fails, which is the case the table exists
  for — seeds any new release points, and signals through its **exit code**: 0 nothing new,
  10 new release points published, 1 the check itself failed. `deploy/update-corpus.sh` runs
  the full download-and-load chain only on 10. Pass `--out` somewhere disposable when the
  canonical `data/uscreleasepoints.json` must survive: `mirror pull` overwrites it, and a
  backfill planned from the stale copy would miss the release point just found.

## python -m ingest fetch --release <label> --title <num>
  Downloads and unpacks one title's zip into data/releases/{label}/ (~1 req/sec, cached on disk).
  Raises on failure — the interactive single-title path. The bulk path records and continues.

## python -m ingest backfill [--title N]... [--release LABEL]... [--limit N] [--plan-only]
                          [--retry-unavailable] [--no-baseline]
  The full corpus, resumably (ADR-0012). Plans from data/uscreleasepoints.json driven by
  titlesAffected — 3,197 downloads, not 382×58=22,156 — with the oldest RP fetched in full
  as the baseline a delta needs. Re-run to resume: outcomes live in data/releases/ledger.json
  (ok / unavailable / failed), and a zip on disk with no ledger entry is re-hashed and
  adopted, so a lost ledger costs a hashing pass rather than a re-download. Hours long and
  interruptible; Ctrl-C saves the ledger.

## python -m ingest mirror {push,pull} [--bucket B] [--title N]... [--release L]...
  S3 mirror of the corpus (ADR-0013; bucket from $USC_MIRROR_BUCKET; ops guide
  docs/remote-ops.md). push uploads zips+inventory+manifests then the ledger LAST, so the
  mirror never advertises files it lacks; pull fetches (a slice of) the mirror and
  re-hashes it against the ledger — transport is aws s3 sync, trust is ours. One writer
  rule: the ledger's writer is wherever the backfill runs; everyone else pulls.

## python -m ingest load-all [--title N]... [--release L]... [--limit N] [--plan-only]
  Bulk load of the downloaded corpus (ADR-0014), ledger-driven, in inventory seq order so
  the baseline lands before the deltas. Resume state is the DATABASE, not a second ledger:
  `title_versions.sections_loaded` is stamped last, so a crash mid-title leaves NULL and the
  pair is redone (load_release is idempotent). Each zip is extracted to a temp dir and
  deleted, so the corpus never doubles on disk. `make load-all`.

## python -m ingest.reindex_search [--if-changed | --recreate] [--all-versions] [--limit N] [--skip-sections]
  Rebuild the search indices from Postgres (ADR-0028). Normal loading keeps them in step
  incrementally, so this is the "start over" path: after a mapping change (OpenSearch will
  not add a field type to a live index) or over a corpus loaded before search existed.
  Defaults to the text in force: one document per section, 66k of them, which is what the
  default query reads. --all-versions adds every superseded version (490k) so `?release=`
  can reach back — much longer, and it buys the default query nothing. Both passes stream;
  ingest never requires a cluster (DISABLE_SEARCH_SYNC=1).

  --if-changed is the deploy's path (ADR-0051) and the one to reach for by hand. It
  compares the mapping the code declares against the fingerprint stamped in the live
  index's _meta and exits doing nothing when they agree. When they differ it builds the new
  generation under a name of its own (uscode_sections_<fingerprint>) and moves the alias in
  one call at the end, so search stays up throughout and a failure leaves the old index
  live. `ingest.search_sync.stale_aliases(client)` answers "does this need rebuilding" on
  its own.

  --recreate is the destructive one: it deletes every index for both aliases, including any
  half-built generation a failed --if-changed left behind, and rebuilds in place. Search
  answers 503 while it runs. Use it to reclaim disk or to start genuinely clean.

## uv run python scripts/vendor_apidocs.py [--check] [--update]
  Swagger UI and ReDoc, vendored into static/apidocs/ (ADR-0032). The site's CSP names no
  CDN, so FastAPI's stock docs pages loaded six blocked assets and rendered blank. --check
  recomputes each sha256 against static/apidocs/MANIFEST.json and is what
  tests/test_apidocs.py runs; bare re-downloads the pinned versions; --update accepts new
  hashes after a version bump. static/favicon.svg lives beside them and is served at the
  root by main.py, because /favicon.svg is not under /app.

## python -m ingest verify [--deep]      (`make verify` / `make verify-deep`)
  Shallow: recorded `sections_loaded` vs the rows `section_release_map` actually holds —
  seconds. --deep re-parses every source file for an INDEPENDENT recount, which is the only
  version that can catch a parser confirming its own bookkeeping. Writes
  docs/verification/database.json. Headline metric: the dedupe ratio.

## python -m ingest verify-downloads [--deep]
  Hash-dedupe over the downloaded corpus → docs/verification/downloads.json. Same title at
  two RPs with identical bytes is reported (OLRC republished it unchanged; also the u1
  substitution signature); two *different* titles sharing a zip fails the report, because
  that means URL construction collapsed two addresses. --deep re-hashes from disk.

## python -m ingest load <xmlfile> --release <label> [--currency-date YYYY-MM-DD] [--source-url URL]
                                                  [--source-zip PATH]
  Parses one USLM title file into Postgres: content-hash dedupe (over the guid-stripped
  content_key — ADR-0007), guid_map upsert, structure_nodes from the TOC pass, per-release
  seq_in_title/parent_identifier, and a data/manifests/{release}.json provenance manifest.
  --currency-date is only needed for a release the inventory doesn't list.
  Example: uv run python -m ingest load samples/uslm1/usc16.xml --release 119-102not101
