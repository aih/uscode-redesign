# uscode-redesign

A conceptual redesign of [uscode.house.gov](https://uscode.house.gov). Every provision of the US
Code has an address, at every point in time it has existed, and that address mirrors the USLM
`@identifier`. It is live at
[uscode.linkedlegislation.org](https://uscode.linkedlegislation.org/app/).

```
GET /us/usc/t16/s45f/c/5?release=119-102not101
GET /us/usc/t16/s45f/c/5?date=07/12/2026
GET /us/usc/?id=id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd   # a guid pins provision *and* release point
```

Those are **citation URLs**, and each answers with a 307 to whichever surface the caller can read:
the reader at `/app/us/usc/…` for a browser, the API at `/api/v1/us/usc/…` for everything else
([ADR-0010](docs/adr/0010-reader-and-api-separated-behind-a-redirecting-citation-url.md)). The two
surfaces cache and deploy independently.

FastAPI and Postgres today, designed from the start to swap to [XCiteDB](https://xcitedb.com) behind
a repository interface tomorrow. Both USLM schemas are parsed: 1.x, which is what OLRC publishes
now, and 2.x, its announced migration (samples in `samples/uslm2/`). The 2.x parser reads sections,
headings, status and structure; it has no table or indent handling yet.

The reader is where the versioning shows. A section arrives with the cited provision highlighted in
place, above a timeline of every release point where its text actually changed and a redline between
any two of them. One box in the header takes either a citation or a phrase, and cross references
preview on hover. Accounts and watchlists are built and tested but switched off, and the site says
so where the controls would be
([ADR-0034](docs/adr/0034-features-built-and-switched-off-say-so.md)).

The reading surface is built from a documented set of parts, rendered on one page at
[`/app/design`](https://uscode.linkedlegislation.org/app/design)
([ADR-0053](docs/adr/0053-a-living-style-guide-at-app-design.md)): two self-hosted faces —
Spectral for statutory text, Archivo for everything written about it — over USWDS tokens
([ADR-0052](docs/adr/0052-a-brand-layer-over-uswds-expressed-only-as-tokens.md)), a subsection
ladder and two reading densities measured against
[`docs/verification/ladder.json`](docs/verification/ladder.json) and
[`measure.json`](docs/verification/measure.json)
([ADR-0054](docs/adr/0054-typography-for-statutory-text.md)), one navigation chrome on every page
that is a place in the Code
([ADR-0043](docs/adr/0043-one-navigation-chrome-on-every-page-that-is-a-place-in-the-code.md)), a
release switcher in the sticky bar
([ADR-0056](docs/adr/0056-the-release-switcher-returns-to-the-sticky-bar.md)), and one keyboard map
the dialog, the design page and the binding island all read from
([ADR-0055](docs/adr/0055-navigation-inside-a-section-and-a-keyboard-map.md)). The API reference is
served from this origin at `/app/docs`, `/docs` and `/redoc`
([ADR-0032](docs/adr/0032-serve-the-api-docs-assets-ourselves.md)), and the demo video is at
`/app/demo`.

All of that is written up in a **user guide at `/app/guide`**, and the guide is executable
([ADR-0038](docs/adr/0038-the-user-guide-is-executable.md)): every behavioural claim in it carries a
scenario block that is simultaneously the walkthrough a reader follows, a Playwright test that runs
on every push, and a captioned scene of the demo video `make demo-video` records. A claim that stops
being true fails the build.

## The corpus as a dataset

The parsed corpus is published on Hugging Face at
[dreamproit/uscode](https://huggingface.co/datasets/dreamproit/uscode)
([ADR-0069](docs/adr/0069-publish-the-corpus-as-a-hugging-face-dataset.md)): a `current` config —
one row per section at its newest release point, 65,938 rows — and a `versions` config — one row
per distinct text with the release points it was in force, 489,738 rows. Each row carries plain
text, verbatim USLM XML, citation, hierarchy and release metadata; `content_hash` joins the two
configs.

```python
from datasets import load_dataset
sections = load_dataset("dreamproit/uscode", "current", split="train")
```

`make hf-export` regenerates the shards from the loaded corpus (a no-op until OLRC publishes a new
release point) and `make hf-upload` pushes them; `docs/verification/hf-dataset.json` records what
was last published.

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

This site is being built with AI agents (Claude Code), deliberately in the open. A blog series
reconstructing the process is forthcoming. What is checkable, and where:

- **Process** — `BUILDLOG.md` records each session: model, what was asked, what was decided, what
  was verified. `docs/adr/` records each design decision and its reasoning, including the ones that
  went the other way. The git history preserves `Co-Authored-By` trailers, which record the commits
  that were AI-assisted.
- **Data integrity** — every ingested release point carries a manifest with its uscode.house.gov
  source URL and the sha256 of the zip, so anyone can re-download and compare. `make verify-deep`
  recounts every title-release from the source XML, and its reports are committed to
  `docs/verification/`.
- **Behavior** — three suites run on every push and all three are required: `make test` for Python,
  `make test-web` for the reader's logic and the guide ratchet, and `make test-e2e` for what only a
  browser can answer — sticky geometry, hover timing, the top layer.
- **Accessibility** — `make test-a11y` runs axe-core over the route matrix in
  `docs/a11y/routes.json` at three widths, in both themes, under forced colours and in nine
  interactive states, and fails on any violation not listed in `docs/a11y/known-violations.json`
  ([ADR-0039](docs/adr/0039-accessibility-is-a-ratchet-in-the-browser-suite.md)). The measured
  baseline is [`docs/verification/a11y.json`](docs/verification/a11y.json).
- **Layout** — `make shots` re-takes the screenshots in `docs/screenshots/` and fails if a page
  scrolls sideways at 320px or at 1280px zoomed to 200% (WCAG 1.4.10 and 1.4.4). `make measure`
  counts the characters per rendered line of statutory text in both reading densities and exits
  non-zero when a median leaves 62–70.

The data source is the official [OLRC XML downloads](https://uscode.house.gov/download/download.shtml)
(USLM). Release-point download tooling builds on
[dreamproit/loadusc-xcitedb](https://github.com/dreamproit/loadusc-xcitedb).

## Status

**The site is deployed** at [uscode.linkedlegislation.org](https://uscode.linkedlegislation.org/app/)
— one EC2 box running Compose behind Caddy, images built by Actions on arm64 and pushed to ECR,
deploys by SSM
([ADR-0020](docs/adr/0020-deploy-one-ec2-box-compose-caddy.md),
[ADR-0035](docs/adr/0035-images-from-ecr-deploys-from-actions.md)). It polls uscode.house.gov daily
and records every check, successful or not
([ADR-0036](docs/adr/0036-record-every-check-of-the-source.md)); `GET /api/v1/status` and
`/app/releases` say when it last looked. Live state and outstanding items are in
[`docs/deploy-status.md`](docs/deploy-status.md).

**The reader and the API are separate** (BUILDLOG 006–007, 014). The reader is an
Astro 5 + TypeScript app styled with [USWDS](https://designsystem.digital.gov/) at `/app`, server-rendered:
no framework reaches the browser, only a few small inline islands for the handful of things that
genuinely need one. The API is machine-only at `/api/v1`, and a citation URL redirects to whichever
of them the caller can read. **545 Python tests, 299 frontend tests and 449 browser tests** — 268 of
the browser tests the accessibility scan — all three required by CI on every push.

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
where the source publishes two or more elements under one `@identifier`.
[ADR-0021](docs/adr/0021-repeated-identifiers-serve-every-occurrence.md) explains them: the reader
shows every occurrence with a note.

**Keyword search runs on OpenSearch** ([ADR-0028](docs/adr/0028-keyword-search-opensearch-current-by-default.md)),
strict by default: the words you typed, all of them, with the loosening operators documented at
`/app/search/syntax` ([ADR-0031](docs/adr/0031-search-is-strict-unless-asked.md)). Ranking is scored
against 37 drafter queries and 529 graded documents in
[`docs/verification/search-relevance.json`](docs/verification/search-relevance.json)
([ADR-0049](docs/adr/0049-search-relevance-measured-and-scoped.md)). The deployed index is complete
— 489,578 documents. **A fresh local checkout holds a smoke slice** until you build it with
`python -m ingest.reindex_search --recreate`.

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

The first two commands paste the *same* citation and arrive in different places: a citation has one
URL, and `Accept:` decides which surface serves it
([ADR-0009](docs/adr/0009-one-url-per-provision-negotiated-by-accept.md), as amended by
[ADR-0010](docs/adr/0010-reader-and-api-separated-behind-a-redirecting-citation-url.md)). `curl`
needs `-L` to follow the redirect — or skip it and call `/api/v1` directly.

Next: USLM 2.x parser parity — tables and indentation — and Day 7 hardening. BUILDLOG.md is the
place to find what has been verified and how to re-check it.
