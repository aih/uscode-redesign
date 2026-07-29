# uscode-redesign

A conceptual redesign of [uscode.house.gov](https://uscode.house.gov) focused on **retrieval and display of US Code provisions by version** — any provision, at any release point, via a clean URL scheme that mirrors the USLM `@identifier`:

```
GET /us/usc/t16/s45f/c/5?release=119-102
GET /us/usc/t16/s45f/c/5?date=07/12/2026
GET /us/usc/?id=id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd   # guid = provision + release point
```

Those are **citation URLs**, and they answer with a 307 to whichever surface the caller can read:
the reader at `/app/us/usc/…` for a browser, the API at `/api/v1/us/usc/…` for everything else
([ADR-0010](docs/adr/0010-reader-and-api-separated-behind-a-redirecting-citation-url.md)). One
citation, one address, two surfaces that can be cached and deployed apart.

Built on FastAPI + Postgres (v1), designed to swap to [XCiteDB](https://xcitedb.com) behind a repository interface (v2). Handles both USLM 1.x (current OLRC downloads) and USLM 2.x (OLRC's announced migration; samples in `samples/uslm2/`). Reader features: section-level display with provision anchoring, prev/next navigation, per-section version timelines, and user watchlists for the provisions a researcher actually works with.

## Documents

| File | Purpose |
|---|---|
| [PLAN.md](PLAN.md) | Research findings, architecture, schema, API design, day-1/week-1 milestones, agent orchestration plan |
| [GETTING-STARTED.md](GETTING-STARTED.md) | Step-by-step guide to executing the plan with Claude Code, from zero |
| [BUILDLOG.md](BUILDLOG.md) | Session-by-session record of how this site was actually built |
| `docs/adr/` | Architecture Decision Records — the "why" behind each consequential choice |
| `data/manifests/` | Provenance manifests: source URL + sha256 + counts for every ingested release point |

## How this site is being built — and how to verify it

This site is being built with AI agents (Claude Code), deliberately in the open. For readers reconstructing the process (blog series forthcoming) and for users skeptical of AI-built software, the repo is designed so that **every claim is checkable**:

- **Process**: `BUILDLOG.md` records each session (model, prompts, decisions, commits); `docs/adr/` records each design decision and its rationale; the git history preserves `Co-Authored-By` trailers showing which commits were AI-assisted.
- **Data integrity**: every release point ingested has a manifest with the uscode.house.gov source URL and zip sha256 — re-download and compare; per-title section counts are verified against the source XML by `make verify`, and the reports are committed to `docs/verification/`.
- **Behavior**: the test suite is the specification. `make test` (Python) and `make test-web` (the reader) run it; nothing is merged without both passing. `make shots` re-takes the screenshots in `docs/screenshots/` at 375px and 1280px, and fails if a page scrolls sideways at either width.

The data source is the official [OLRC XML downloads](https://uscode.house.gov/download/download.shtml) (USLM). Release-point download tooling builds on [dreamproit/loadusc-xcitedb](https://github.com/dreamproit/loadusc-xcitedb).

## Status

**The reader and the API are live locally, and now separate** (BUILDLOG 006–007, 014). The reader
is an Astro 5 + TypeScript app styled with [USWDS](https://designsystem.digital.gov/) at
`/app`, server-rendered with no JavaScript bundle; the API is machine-only at `/api/v1`; and a
citation URL redirects to whichever one the caller can read. 271 Python tests and 42 frontend
tests, both re-run by CI on every push.

**The whole corpus is downloaded and loaded** (BUILDLOG 023). The resumable backfill
([ADR-0012](docs/adr/0012-resumable-backfill-driven-by-titles-affected.md)) fetched **3,153 of
3,197 planned title-releases** — 9.7 GB — with the other 44 recorded as unavailable and
individually accounted for; all of it is mirrored to S3
([ADR-0013](docs/adr/0013-s3-mirror-of-record-disposable-downloader.md)). The ledger-driven bulk
load ([ADR-0014](docs/adr/0014-bulk-load-resume-state-lives-in-the-database.md)) then loaded every
one of them, with no failures:

| | |
|---|---|
| Title-releases loaded | **3,153** (58 titles × 381 release points, as published) |
| Sections | 65,938 distinct; **5,466,652** (section, release) pairs |
| Stored texts | **489,738** `section_versions` |
| **Dedupe ratio** | **91.0%** — the same text is stored once however many release points publish it ([ADR-0007](docs/adr/0007-content-dedupe-on-guid-stripped-content-key.md)) |
| Guid index | **96,185,732** rows — one per (provision, release), subsections included |
| Database on disk | 27 GB |

Every number above is reproduced by `make verify-deep`, which re-parses the source XML for an
independent recount rather than trusting the loader's own bookkeeping, and writes
[`docs/verification/database.json`](docs/verification/database.json). It reports six title-releases
where the source publishes two or more elements under one `@identifier`; they are explained, not
averaged away, in [ADR-0021](docs/adr/0021-repeated-identifiers-serve-every-occurrence.md) — the
reader shows every occurrence with a note rather than silently picking one.

```bash
docker compose up -d db
make dev-data          # seed the release-point inventory; load Title 16 at both release points
make dev-all           # the whole site on :8000 — Caddy in front of the reader and the API
                       # (`make dev` runs the API alone; `make dev-web` the reader alone)

open "http://localhost:8000/us/usc/t16/s45f/c/5?date=07/12/2026"      # §45f, (c)(5) highlighted
curl -L "http://localhost:8000/us/usc/t16/s45f/c/5?date=07/12/2026"   # the same URL, as JSON
curl "http://localhost:8000/api/v1/us/usc/t16/s45f/c/5?date=07/12/2026"   # or address the API
```

The first two commands paste the *same* citation and arrive in different places: a citation has one
URL, and `Accept:` decides which surface serves it
([ADR-0009](docs/adr/0009-one-url-per-provision-negotiated-by-accept.md), as amended by
[ADR-0010](docs/adr/0010-reader-and-api-separated-behind-a-redirecting-citation-url.md)). `curl`
needs `-L` because it now follows a redirect — or skip it and call `/api/v1` directly.

Next: deploy ([ADR-0020](docs/adr/0020-deploy-one-ec2-box-compose-caddy.md), `docs/deploy.md`) and
Day 7 hardening — USLM 2.x parser parity, an accessibility pass, and the public "how it was built"
page. See BUILDLOG.md for what has been verified and how to re-check it.
