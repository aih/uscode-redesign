# uscode-redesign

A conceptual redesign of [uscode.house.gov](https://uscode.house.gov) focused on **retrieval and display of US Code provisions by version** — any provision, at any release point, via a clean URL scheme that mirrors the USLM `@identifier`:

```
GET /us/usc/t16/s45f/c/5?release=119-102
GET /us/usc/t16/s45f/c/5?date=07/12/2026
GET /us/usc/?id=id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd   # guid = provision + release point
```

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
- **Behavior**: the test suite is the specification. `make test` runs it; nothing is merged without it passing.

The data source is the official [OLRC XML downloads](https://uscode.house.gov/download/download.shtml) (USLM). Release-point download tooling builds on [dreamproit/loadusc-xcitedb](https://github.com/dreamproit/loadusc-xcitedb).

## Status

**Day 1 is done: the reader and the API are both live locally** (BUILDLOG 006–007). Title 16 is
loaded at two release points — 119-99 (06/12/2026) and 119-102not101 (07/12/2026) — out of the
382 the release-point inventory knows about, with the full hierarchy, a working resolver, and
162 tests.

```bash
docker compose up -d db
make dev-data          # seed the release-point inventory; load Title 16 at both release points
make dev               # the reader at http://localhost:8000/ , the API docs at /docs

open "http://localhost:8000/us/usc/t16/s45f/c/5?date=07/12/2026"   # §45f, (c)(5) highlighted
curl "http://localhost:8000/us/usc/t16/s45f/c/5?date=07/12/2026"   # the same URL, as JSON
```

The two commands hit the same address on purpose: a citation has one URL, and `Accept:` decides
whether a person or a program is reading it ([ADR-0009](docs/adr/0009-one-url-per-provision-negotiated-by-accept.md)).

Next: the bulk backfill of all titles and release points (PLAN Day 2), then reader polish —
keyboard navigation, version timelines and diffs (Day 4). See BUILDLOG.md for what has been
verified and how to re-check it.
