# uscode-redesign

A conceptual redesign of [uscode.house.gov](https://uscode.house.gov) built around one idea: **every provision of the US Code has an address, at every point in time it has existed.** The address mirrors the USLM `@identifier`, which is to say it is the citation you already know.

```
GET /us/usc/t16/s45f/c/5?release=119-102not101
GET /us/usc/t16/s45f/c/5?date=07/12/2026
GET /us/usc/?id=id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd   # a guid pins provision *and* release point
```

Those are **citation URLs**, and each answers with a 307 to whichever surface the caller can read:
the reader at `/app/us/usc/…` for a browser, the API at `/api/v1/us/usc/…` for everything else
([ADR-0010](docs/adr/0010-reader-and-api-separated-behind-a-redirecting-citation-url.md)). One
citation, one address, two surfaces that cache and deploy independently.

FastAPI and Postgres today, designed from the start to swap to [XCiteDB](https://xcitedb.com) behind
a repository interface tomorrow. Both USLM schemas are parsed: 1.x, which is what OLRC publishes
now, and 2.x, its announced migration (samples in `samples/uslm2/`).

The reader is where the versioning shows. A section arrives with the cited provision highlighted in
place, above a timeline of every release point where its text actually changed and a redline between
any two of them. One box in the header takes either a citation or a phrase, and cross references
preview on hover rather than costing you your place. Accounts and watchlists are built and tested
but switched off, and the site says so where the controls would be
([ADR-0034](docs/adr/0034-features-built-and-switched-off-say-so.md)).

## Documents

| File | Purpose |
|---|---|
| [PLAN.md](PLAN.md) | Research findings, architecture, schema, API design, milestones, agent orchestration plan |
| [GETTING-STARTED.md](GETTING-STARTED.md) | Step-by-step guide to executing the plan with Claude Code, from zero |
| [BUILDLOG.md](BUILDLOG.md) | Session-by-session record of how this site was actually built |
| `docs/adr/` | Architecture Decision Records — the "why" behind each consequential choice |
| `docs/verification/` | Reports from `make verify` and friends: counts, load tests, measurements |
| `data/manifests/` | Provenance manifests: source URL + sha256 + counts for every ingested release point |

## How this site is being built — and how to verify it

This site is being built with AI agents (Claude Code), deliberately in the open. For readers
reconstructing the process (blog series forthcoming) and for anyone skeptical of AI-built software,
the repo is arranged so that **every claim is checkable**:

- **Process** — `BUILDLOG.md` records each session: model, what was asked, what was decided, what
  was verified. `docs/adr/` records each design decision and its reasoning, including the ones that
  went the other way. The git history preserves `Co-Authored-By` trailers, so which commits were
  AI-assisted is a matter of record rather than of memory.
- **Data integrity** — every ingested release point carries a manifest with its uscode.house.gov
  source URL and the sha256 of the zip, so anyone can re-download and compare. `make verify-deep`
  re-parses the source XML for an independent recount instead of trusting the loader's own
  bookkeeping, and its reports are committed to `docs/verification/`.
- **Behavior** — the test suite is the specification. Three suites run it and all three are
  required: `make test` for Python, `make test-web` for the reader's logic, and `make test-e2e` for
  what only a browser can answer — sticky geometry, hover timing, the top layer. `make shots`
  re-takes the screenshots in `docs/screenshots/` at 375px and 1280px and fails outright if a page
  scrolls sideways at either width.

The data source is the official [OLRC XML downloads](https://uscode.house.gov/download/download.shtml)
(USLM). Release-point download tooling builds on
[dreamproit/loadusc-xcitedb](https://github.com/dreamproit/loadusc-xcitedb).

## Status

**The reader and the API are live locally, and separate** (BUILDLOG 006–007, 014). The reader is an
Astro 5 + TypeScript app styled with [USWDS](https://designsystem.digital.gov/) at `/app`, server-rendered:
no framework reaches the browser, only a few small inline islands for the handful of things that
genuinely need one. The API is machine-only at `/api/v1`, and a citation URL redirects to whichever
of them the caller can read. **474 Python tests, 185 frontend tests and 74 browser tests**, all three
required by CI on every push.

**The whole corpus is downloaded and loaded** (BUILDLOG 023). The resumable backfill
([ADR-0012](docs/adr/0012-resumable-backfill-driven-by-titles-affected.md)) fetched **3,153 of
3,197 planned title-releases** — 9.7 GB — with the other 44 recorded as unavailable and
individually accounted for; all of it is mirrored to S3
([ADR-0013](docs/adr/0013-s3-mirror-of-record-disposable-downloader.md)). The ledger-driven bulk
load ([ADR-0014](docs/adr/0014-bulk-load-resume-state-lives-in-the-database.md)) then loaded every
one of them, with no failures:

| | |
|---|---|
| Title-releases loaded | **3,153**, spanning 58 titles and 381 release points |
| Sections | 65,938 distinct; **5,466,652** (section, release) pairs |
| Stored texts | **489,738** `section_versions` |
| **Dedupe ratio** | **91.0%** — the same text is stored once however many release points publish it ([ADR-0007](docs/adr/0007-dedupe-on-guid-stripped-content.md)) |
| Guid index | **96,185,732** rows — one per (provision, release), subsections included |
| Database on disk | 27 GB |

Every number above is reproduced by `make verify-deep`, which re-parses the source XML for an
independent recount rather than trusting the loader's own bookkeeping, and writes
[`docs/verification/database.json`](docs/verification/database.json). It reports six title-releases
where the source publishes two or more elements under one `@identifier`; those are explained rather
than averaged away, in [ADR-0021](docs/adr/0021-repeated-identifiers-serve-every-occurrence.md) —
the reader shows every occurrence with a note instead of silently picking one.

**Keyword search runs on OpenSearch** ([ADR-0028](docs/adr/0028-keyword-search-opensearch-current-by-default.md)),
strict by default: the words you typed, all of them, with the loosening operators documented at
`/app/search/syntax` ([ADR-0031](docs/adr/0031-search-is-strict-unless-asked.md)). One
caveat worth knowing before you judge the results — the index here holds a smoke slice rather than
the full corpus until you build it with `python -m ingest.reindex_search --recreate`.

```bash
cp .env.example .env    # docker compose refuses to start without SEARCH_PASSWORD
docker compose up -d db
make dev-data           # seed the release-point inventory; load Title 16 at both release points
make dev-all            # the whole site on :8000 — Caddy in front of the reader and the API
                        # (`make dev` runs the API alone; `make dev-web` the reader alone)

open "http://localhost:8000/us/usc/t16/s45f/c/5?date=07/12/2026"      # §45f, (c)(5) highlighted
curl -L "http://localhost:8000/us/usc/t16/s45f/c/5?date=07/12/2026"   # the same URL, as JSON
curl "http://localhost:8000/api/v1/us/usc/t16/s45f/c/5?date=07/12/2026"   # or address the API
```

The first two commands paste the *same* citation and arrive in different places, because a citation
has one URL and `Accept:` decides which surface serves it
([ADR-0009](docs/adr/0009-one-url-per-provision-negotiated-by-accept.md), as amended by
[ADR-0010](docs/adr/0010-reader-and-api-separated-behind-a-redirecting-citation-url.md)). `curl`
needs `-L` because it now follows a redirect — or skip it and call `/api/v1` directly.

Next: deploy ([ADR-0020](docs/adr/0020-deploy-one-ec2-box-compose-caddy.md), `docs/deploy.md`),
which is waiting on an AWS identity and a domain name rather than on code, and then Day 7
hardening — USLM 2.x parser parity, an accessibility pass, and the public "how it was built" page.
BUILDLOG.md is the place to find what has been verified and how to re-check it.
