# US Code Redesign — Research Findings & Agent Build Plan

Goal: a working, demonstrable site in 1 day; a robust site in 1 week covering all release points, with retrieval of any provision at any version, reader navigation, and user watchlists.

> **Progress: Day 1 is complete — items 1–6 ✅** (BUILDLOG 002–007). Detection rule in [ADR-0004](docs/adr/0004-uslm-version-detection-by-namespace.md); section boundaries and corrected Title 16 counts in [ADR-0005](docs/adr/0005-what-counts-as-a-section.md); hierarchy from structural elements in [ADR-0006](docs/adr/0006-toc-from-structural-elements.md); the dedupe correction in [ADR-0007](docs/adr/0007-dedupe-on-guid-stripped-content.md); per-release facts in [ADR-0008](docs/adr/0008-per-release-facts-live-on-the-release-map.md); one URL for reader and API in [ADR-0009](docs/adr/0009-one-url-per-provision-negotiated-by-accept.md).
>
> The release-point inventory is seeded (382 RPs, real currency dates, global `seq`), Title 16 is loaded at **two** release points (119-99 and 119-102not101), `structure_nodes` holds its 569-node hierarchy, the API serves §4's routes over the `Repository` in `storage/`, and `web/` is the reader — server-rendered Jinja at the same identifier URLs. `make test` is 162 tests. *(Day-1 snapshot: `web/` and the shared-URL scheme were both superseded in Session 7 — see the Day 2–3 note below.)* §10's demo works in a browser: browse the Title 16 TOC → §45f → (c)(5) highlighted → flip the release picker → prev/next.
>
> **Two findings worth carrying forward.** (1) Loading a *real* second release point showed the content-hash dedupe collapsing nothing — guids regenerate at every RP by design (§9.1), so an untouched section's raw XML differs at every one of them: 0 of 5,095 Title 16 sections had identical raw XML between the two RPs, 5,093 were identical once `@id` was stripped, 2 had really been amended. Hashing is now over guid-stripped content ([ADR-0007](docs/adr/0007-dedupe-on-guid-stripped-content.md)); §9.1 and §9.10 were both already written down, and what was missing was the observation that the first defeats the second. (2) Building the reader showed that **every browser had been getting raw XML at the demo URL**: `Accept:` was substring-matched, and Chrome asks for `application/xml;q=0.9`. `?format=html` had covered for it in every test. Content negotiation now reads q-values ([ADR-0009](docs/adr/0009-one-url-per-provision-negotiated-by-accept.md)) — and a hand-written `Accept:` header in a test is not the header a browser sends.
>
> **Progress (Day 2–3):** Sessions 1–8 built ✅ — prior art (`docs/prior-art.md`), the resumable backfill tool (ADR-0012, BUILDLOG 010), the S3 mirror + disposable EC2 box (ADR-0013, docs/remote-ops.md), and the ledger-driven bulk load + a real `make verify` (ADR-0014). **Session 7 is done and merged into main (BUILDLOG 014, 016): the surfaces are separated per ADR-0010 — reader at `/app/us/usc/…`, API at `/api/v1/…`, the bare citation URL a 307 redirector — and the `/app` reader is Astro 5 + TypeScript + USWDS per ADR-0011, behind one Caddy origin (ADR-0015), with the Jinja reader retired.** `make test` is 209 Python tests and `make test-web` 27 frontend tests; reader coverage lives in Vitest now, so **CI must run both suites**. In flight on main: the local backfill (~1,742/3,197 ledger entries, 5.1 GB) and the bulk load, running concurrently; hand off to EC2 per remote-ops §2–3 or let the local run finish. Next: finish the backfill + load, then full-corpus `make verify-deep` (the dedupe ratio is the headline number), then Day 4 polish (keyboard nav, notes toggles, version timeline, diffs) on the Astro layout. Still open: `Uslm2Parser` table/indent parity (Day 7).
>
> **Progress (2026-08-06).** Everything in the paragraph above is done and its figures are superseded. The backfill is complete (3,153 `ok` / 44 `unavailable`, 9.7 GB, mirrored to S3) and so is the load — 3,153 title-releases across 58 titles and 381 loaded release points, 65,938 sections, 489,738 `section_versions`, 91.0% deduped, 27 GB on disk. `make verify --deep` has recounted all 3,153 from source with 0 mismatches. The suites are **545 Python / 299 frontend / 449 browser tests**, all three required by CI. Days 4–6 shipped (version timeline, redlines, search, accounts-built-and-off, deploy) and the site is live at `uscode.linkedlegislation.org`. Still open: `Uslm2Parser` table/indent parity, and Day 7 hardening. **The current picture is [CLAUDE.md](CLAUDE.md) and [BUILDLOG.md](BUILDLOG.md); the sections below are the plan as written, with dated notes where a decision was later taken another way.**

---

## 1. Research findings (verified against usc16.xml and uscode.house.gov, 2026-07-27)

**Schema versions — the site must handle both USLM 1.x and USLM 2.x.** Current USC release-point downloads are **USLM 1.0** (`USLM-1.0.15.xsd`, namespace `http://xml.house.gov/schemas/uslm/1.0`). OLRC has announced the move to USLM 2.x and publishes **sample USC titles in USLM 2.x** at `https://uscode.house.gov/currency/uscinuslmv2samples.zip` (samples will be committed to this repo under `samples/uslm2/`). Per OLRC's migration note, the main 1.x→2.x differences for the USC are: (1) tables of contents, (2) tables, (3) the indent model; USLM 2.0.17 also adds MathML 3 and new elements. The parser detects the schema version per file from the **root namespace URI** — `http://xml.house.gov/schemas/uslm/1.0` (1.x) vs `http://schemas.gpo.gov/xml/uslm` (2.x), locked in on Day 1 against the repo samples ([ADR-0004](docs/adr/0004-uslm-version-detection-by-namespace.md)) — and normalizes both into one internal model.

**Identifiers (from the USLM User Guide + observed data):**
- `@identifier` — logical, human-meaningful path (`/us/usc/t16/s45f/c/5`). Stable across releases *unless the provision is renumbered*. This is the primary key for the URL scheme.
- `@id` — GUID (`id0b32dff7-810c-11f1-...`). GUIDs are **intentionally regenerated at each release point**: a GUID identifies the pair *(provision, release point)*, and that pair is unique. This makes `@id` a first-class, globally unique index — `?id=` lookup needs no release parameter because the GUID itself pins the version. **Design consequence: maintain a global `guid → (identifier, release)` index covering every element id in every ingested file.**
- `@temporalId` — human-readable path-like name (`s1201_a_1_A`), not guaranteed unique; useful for display, not for keys.
- `@status` — in Title 16, counting raw elements: 523 `repealed`, 102 `omitted`, 19 `transferred`, 1 `reserved`. **Corrected on Day 1 against the parser ([ADR-0005](docs/adr/0005-what-counts-as-a-section.md)):** among *real code sections* it is 522/102/19, and the single `reserved` is on a `<subchapter>`, not a section. Must be surfaced in UI and kept retrievable.

**Structure observed in Title 16:** 5,393 `<section>` elements — but **298 of those are inside `<quotedContent>`** (text quoted by amending acts; no `@identifier`, no `@id`), so the code has **5,095 real sections**. Also 153 chapters, 345 subchapters, 8,906 subsections, 15,810 paragraphs, 4,026 clauses; 32 MB XML. Sections carry `<num>`, `<heading>`, nested provisions, `<sourceCredit>` (refs to Pub. L. + dates), and `<note>` blocks (881 in t16). Big levels: title → chapter → subchapter → part → subpart → section.

**Release points:**
- Current RP: **119-102 (07/12/2026), except 119-101** → label `119-102not101`; `docPublicationName` = `Online@119-102not101`.
- Download URL scheme (confirmed): `https://uscode.house.gov/download/releasepoints/us/pl/{congress}/{law}{notX...}/xml_usc{NN}[a]@{congress}-{law}{notX...}.zip` (e.g. `.../us/pl/119/102not101/xml_usc16@119-102not101.zip`; `xml_uscAll@...zip` for all titles; `05a`, `11a`, `18a`, `28a`, `50a` are appendices).
- Prior release points page lists **382 RPs back to the 113th Congress** (2013-07-18 through 2026-07-12) — counted, not estimated, by parsing the page on 2026-07-27; the earlier "~324" was an estimate. Skip labels can compound (`277not255not268`), and 17 carry a `u1` update suffix (`118-22u1`) that makes them distinct release points from the same public law. RP labels are *not* lexically sortable — parse into (congress, law_num, excluded_laws[], update_num) and take the global sequence from the page's own newest-first order.
- Every RP republishes **all** titles, but only some titles changed — so full-corpus ingest must **dedupe by content hash** or storage explodes (~300 RPs × ~1 GB/RP uncompressed).

**Date semantics.** An RP is named for the latest incorporated law; the site shows its date (e.g. 07/12/2026 for 119-102). `?date=` resolves to the latest RP whose currency date ≤ query date. Caveat to display: "not" laws mean the code text at that RP may not reflect every law enacted by that date.

**Existing tooling to reuse: [dreamproit/loadusc-xcitedb](https://github.com/dreamproit/loadusc-xcitedb).** This repo already implements: (1) `downloadusc.py` — downloads *all* release points and emits `uscreleasepoints.json`, an inventory of `{name, date, titlesAffected, url}` per RP; (2) `loaduscxcite.py` — loads titles into XCiteDB; (3) `updateusc.sh` — nightly cron update. Three consequences for this plan:
- The **RP inventory JSON is the seed for the `release_points` table** — it supplies the currency `date` (powers `?date=` resolution) and `titlesAffected` (tells ingest which titles actually changed per RP, so hash-dedupe becomes a verification step instead of the discovery mechanism).
- The **Day 2–3 bulk downloader should port/modernize `downloadusc.py`** (it's Python 3.7-era) rather than be written from scratch.
- The **XCiteDB future is closer than "later"**: the Repository interface's second implementation can wrap the existing loader; the nightly-cron pattern becomes the site's auto-update job for new RPs.

**Prior art: [dreamproit/versions](https://github.com/dreamproit/versions)** — an older working site that uses this data + XCiteDB to display the US Code and **generate diffs between temporal versions**. It predates FastAPI and lacks the new site's feature set, but it is proven code: mine it for (a) the diff algorithm and rendering approach (feeds Day 4's version-timeline/diff feature directly), (b) display/navigation decisions that worked or didn't, and (c) XCiteDB query patterns for the eventual Repository v2. Study it before designing the resolver and the diff UI — don't rediscover solved problems.

---

## 2. Architecture (modular, storage-swappable)

```
 ┌────────────┐   ┌─────────────┐   ┌──────────────┐   ┌───────────┐
 │  ingest/    │→ │  storage/    │← │  api/ FastAPI │← │  web/      │
 │  fetch RPs, │   │  Postgres +  │   │  resolver +   │   │  reader UI │
 │  parse USLM │   │  repository  │   │  auth +       │   │  watchlist │
 │  split into │   │  interface   │   │  watchlist    │   │            │
 │  sections   │   │  (swap to    │   └──────────────┘   └───────────┘
 └────────────┘   │  xcitedb     │
                   │  later)      │
                   └─────────────┘
```

*Superseded in Session 7 (2026-07-30):* `web/` is empty. The reader is `frontend/` — Astro 5 +
TypeScript + USWDS at `/app` ([ADR-0011](docs/adr/0011-astro-uswds-frontend-at-app.md)) — and it
reaches `api/` over HTTP rather than sharing a process
([ADR-0010](docs/adr/0010-reader-and-api-separated-behind-a-redirecting-citation-url.md),
[ADR-0015](docs/adr/0015-one-origin-two-services-renderer-in-the-frontend.md)). Top-level `main.py`
composes the app, `params.py` holds what the surfaces share, and `citation.py` is the redirector.

Hard rule: **API and UI talk only to a `Repository` interface** (get_section(identifier, release), get_toc(...), resolve_id(...), neighbors(...)). The Postgres implementation is v1; xcitedb becomes a second implementation later with no API/UI changes.

Second hard rule: **the ingest layer is schema-plural.** A `UslmParser` protocol with `Uslm1Parser` and `Uslm2Parser` implementations, chosen by a `detect_uslm_version(file)` sniffer, both emitting the same normalized `SectionRecord` (identifier, guid, temporalId, num, heading, status, seq, raw XML fragment, source credit, notes). Everything downstream — storage, API, UI — is schema-agnostic; `schema_version` is carried as metadata so the original XML can always be returned verbatim. Fixtures for both parsers: `usc16.xml` (1.x) and `samples/uslm2/` (2.x).

Sections are the storage atom (per your spec). Sub-section provisions (`/c/5`) are extracted from the section XML at request time — server-side via lxml XPath on `@identifier`, returning the full section with the target provision anchored/highlighted, so the reader always has context.

---

## 3. Postgres schema (core tables)

```sql
release_points(id, congress int, law_num int, excluded_laws int[],
               update_num int null,        -- the `u1` re-issue suffix: 118-22 vs 118-22u1
               label text unique,          -- '119-102not101'
               titles_affected text[],     -- from the RP inventory; drives ingest
               currency_date date, seq int unique)  -- global ordering

titles(id, num text unique, name text, is_positive_law bool)   -- '16', '05a'

title_versions(id, title_id, release_id, source_zip_sha256,
               schema_version text,          -- 'uslm-1.0.15' | 'uslm-2.x'
               downloaded_at, unchanged_from_release_id nullable)
               -- records per-RP title currency; null = new content

sections(id, title_id, identifier text,      -- '/us/usc/t16/s45f'
         unique(title_id, identifier))       -- identity across time

-- Hierarchy above the section, for TOC nodes and breadcrumbs (added Day 1 item 3a;
-- not in the original schema, and nothing else stores a chapter's name):
structure_nodes(id, title_id, identifier text,   -- '/us/usc/t16/ch1/schVI'
         level text,                         -- 'chapter'|'subchapter'|'part'|'subpart'
         num text, num_value text, heading text,
         status text nullable,               -- t16's one 'reserved' is on a subchapter
         parent_id nullable, seq int,        -- document order among siblings
         depth int,
         first_release_id, last_release_id,  -- first filters TOCs; last is informational
         unique(title_id, identifier))
-- Unversioned, as planned: headings rarely change, what changes is which nodes exist.
-- Filled by a TOC pass over *structural elements*, never <toc> (ADR-0006).

section_versions(id, section_id,
         first_release_id,                   -- RP where this content first appeared
         content_hash bytea,                 -- sha256 of the *guid-stripped* XML (ADR-0007);
                                             -- hashing raw XML dedupes nothing — guids
                                             -- regenerate at every RP
         xml xml/text, html_cache text nullable,
         num text, heading text, status text nullable,
         source_credit text, unique(section_id, content_hash, first_release_id))

-- Resolve (section, RP) → version. Also carries the facts that are true of a section
-- *at* an RP rather than of its text (ADR-0008): a section keeps its words while its
-- neighbours are repealed, and a transferred section changes chapter without changing.
section_release_map(section_version_id, release_id,
         seq_in_title int,                   -- document order → prev/next
         parent_identifier text nullable)    -- immediate structure node → TOC listing
guid_map(guid text primary key,              -- globally unique by design:
         release_id, identifier text)        -- guid ≡ (provision, release point)

-- Indexes beyond PKs/uniques (migrated in aef3da4cc2e9, BUILDLOG 005; guid_map
-- alone will hold tens of millions of rows at full corpus):
--   guid_map(release_id, identifier)         -- reverse lookup: provision @ RP → guid
--   section_release_map(release_id)          -- "everything at this RP" scans
--   section_versions(section_id, first_release_id)  -- version-timeline queries
users(id, email, password_hash/oauth, created_at)
watchlists(id, user_id, name)
watchlist_items(id, watchlist_id, identifier text, title_id, note text,
                pinned_release_id nullable, created_at)
```

Resolution of `GET /us/usc/t16/s45f/c/5?date=2026-07-12` (implemented in `storage/postgres.py`):
1. `?date` → latest `release_points` with `currency_date <= date` (or `?release=119-102` → label match; bare `119-102` matches `119-102not101` with a disambiguation note).
2. Longest-prefix match: strip provision path down to the section identifier (`/us/usc/t16/s45f`), keeping remainder `/c/5`.
3. `section_release_map` → section_version for that RP.
4. XPath the fragment by `@identifier` for anchor/extract; return per `?format=` (html | xml | json).

**Step 2.5, which fell out of the data:** the requested RP may be one we never ingested. Since every RP republishes all titles and few change any, the text at an un-ingested RP *is* the text at the newest ingested RP at or before it — so resolution finds that RP (`served_from`) via `title_versions` and answers, rather than 404ing. Responses carry three release points: `release` (asked for), `served_from`, and `content_first_seen` (whose bytes are stored, since identical content is deduped across RPs). Answer, but never silently.

`GET /us/usc/?id=idXXXX` → `guid_map`. No release parameter needed: the GUID pins both provision and release point. This is also the stable citation form for "this exact text at this exact point in time."

Prev/next: `seq_in_title` within the resolved RP, skipping nothing (repealed sections stay in reading order, flagged).

---

## 4. API surface (FastAPI, versioned OpenAPI)

| Route | Purpose |
|---|---|
| `GET /us/usc/t{T}/s{S}[/provision-path]` | Provision by identifier; `?release=`, `?date=`, `?format=` |
| `GET /us/usc/?id={guid}` | Lookup by XML @id — guid encodes provision + release point |
| `GET /us/usc/t{T}` , `/t{T}/ch{C}` | TOC nodes at a version |
| `GET /api/v1/sections/{...}/neighbors` | prev/next section |
| `GET /api/v1/sections/{...}/versions` | list of RPs where the section changed (diff timeline) |
| `GET /api/v1/releases` | all RPs with dates and changed-title flags |
| `POST /api/v1/auth/*` | signup/login (email+password or GitHub/Google OAuth) |
| `GET/POST/DELETE /api/v1/watchlist*` | watchlist CRUD; items open directly to reader |

Content negotiation: `Accept: application/xml` returns raw USLM fragment; HTML rendering reuses OLRC's CSS conventions (`usctitle.css` classes are already in the XML `@class`/`@style`) so display fidelity is nearly free.

*Amended, 2026-08-06.* What shipped differs from the table above in four ways.

1. **Every route is under `/api/v1`**, including the identifier and guid lookups, which the first
   two rows write without the prefix. The bare `/us/usc/…` form is the citation redirector, not the
   API ([ADR-0010](docs/adr/0010-reader-and-api-separated-behind-a-redirecting-citation-url.md)).
2. **The API serves no HTML at all**, so the OLRC-CSS sentence above describes nothing that exists.
   Rendering is `frontend/src/lib/uslm.ts`, the one place outside the parsers allowed to know USLM
   element names. `?format=xml` still returns the stored fragment verbatim.
3. **There is no OAuth.** Accounts are email and password only
   ([ADR-0017](docs/adr/0017-auth-sessions-argon2-csrf-double-submit.md)), and the whole feature is
   switched off in the reader ([ADR-0034](docs/adr/0034-features-built-and-switched-off-say-so.md)).
4. **Six routes the table does not list** shipped: `GET /api/v1/search`
   ([ADR-0028](docs/adr/0028-keyword-search-opensearch-current-by-default.md)),
   `GET /api/v1/citation` ([ADR-0023](docs/adr/0023-citations-parse-server-side-to-an-identifier.md)),
   `GET /api/v1/labels`, `GET /api/v1/status`
   ([ADR-0036](docs/adr/0036-record-every-check-of-the-source.md)),
   `GET /api/v1/sections/{identifier}/diff`
   ([ADR-0016](docs/adr/0016-diff-computes-server-side-presents-in-the-frontend.md)), and
   `GET`/`PUT /api/v1/settings`. The live surface is `/docs`, `/redoc` and `/app/docs`.

---

## 5. Day 1 — demonstrable MVP (Title 16, 2 release points)

| # | Deliverable | Notes |
|---|---|---|
| 1 | ✅ Repo scaffold: `ingest/ api/ web/ db/ docker-compose.yml` (Postgres 16 + API) | uv + FastAPI + SQLAlchemy + Alembic |
| 2 | ✅ USLM parser layer: `detect_uslm_version` + `Uslm1Parser` (full) + `Uslm2Parser` (stub passing detection + basic section extraction on repo samples) | **Fixture strategy for speed:** first, script-extract a small fixture (`tests/fixtures/usc16_slice.xml`: title/meta wrapper + ch.1 through §45f + one each of repealed/omitted/transferred sections) and write unit tests against it — subsecond test runs. The full 32 MB usc16.xml runs as a `@pytest.mark.slow` integration test asserting the known-good counts (5,095 real sections of 5,393 `<section>` elements; 522/102/19 by section status; s45f/c/5 guid mapping — [ADR-0005](docs/adr/0005-what-counts-as-a-section.md) corrected the 5,393/523/102/19/1 figures this row used to carry). Never let the default `make test` path parse 32 MB. |
| 3 | ✅ Title 16 at **two** release points, 119-99 and 119-102not101, with dedupe that actually dedupes | The prior RP was chosen via `titlesAffected` as this row insisted: 119-99 is the newest earlier RP that changed Title 16, and 119-100 sits between them changing only title 47 — which made it the test case for serving an un-ingested RP. Downloading it also exposed that the BUILDLOG 005 dedupe collapsed nothing, because it had only ever been tested by re-loading one file ([ADR-0007](docs/adr/0007-dedupe-on-guid-stripped-content.md)): 0 of 5,095 sections had identical raw XML across the two RPs, 5,093 were identical once guids were stripped, 2 were genuinely amended. |
| 3a | ✅ Hierarchy storage + TOC pass — `structure_nodes`, filled from structural elements ([ADR-0006](docs/adr/0006-toc-from-structural-elements.md)) | 569 nodes for Title 16 (1/153/345/57/13 title/chapter/subchapter/part/subpart), and the same pass yields 203 for USLM 2.x Title 49 including the `subtitle` level Title 16 never uses — which is the evidence for reading structure instead of `<toc>`. The streaming caveat held: frames open at `start` and close at `end`, so peak RSS on the 32 MB file is 35 MB. |
| 4 | ✅ Resolver + routes (identifier, ?id, ?release, ?date, ?format) | `storage/repository.py` is the protocol, `storage/postgres.py` the only SQL, `storage/session.py` the FastAPI dependency — so `api/` holds no session and imports no models, enforced by `tests/test_architecture.py`. OpenAPI live at `/docs`. 35 integration tests against the two loaded RPs. |
| 5 | ✅ Minimal reader: TOC → section page, provision anchor highlight, prev/next, release picker, status badges | Server-rendered Jinja in `web/`, one stylesheet, no build step — and at **the same `/us/usc/…` URLs as the API**, chosen by `Accept:`/`?format=` ([ADR-0009](docs/adr/0009-one-url-per-provision-negotiated-by-accept.md)), because a citation should not have one address for people and another for programs. That decision exposed the bug this row would otherwise have shipped over: `Accept:` was substring-matched, so browsers got raw USLM and `?format=html` hid it. The reader also carries the two things a date alone would hide — the `not`-law caveat and the served-from release point. *(Superseded in Session 7: the Jinja reader was retired for the Astro app at `/app`, and the shared URL became a redirector — [ADR-0010](docs/adr/0010-reader-and-api-separated-behind-a-redirecting-citation-url.md), [ADR-0011](docs/adr/0011-astro-uswds-frontend-at-app.md).)* |
| 6 | ✅ Demo: `/us/usc/t16/s45f/c/5?date=07/12/2026` end-to-end | Returns §45f with (c)(5) extracted and anchored, the `except 119-101` caveat, and an ETag. Add `&format=html` to read it. |

## 6. Week 1 — day-by-day

- **Day 2:** All 54+ titles (incl. appendices) at current RP. Bulk downloader: port `downloadusc.py` from loadusc-xcitedb (modern Python, checksum cache, polite rate limiting). **The inventory half moves earlier** — loading `uscreleasepoints.json` into `release_points` is now a Day 1 prerequisite (item 3), because both the second release point and `?date=` resolution depend on real currency dates and a true global `seq`; what remains here is the bulk, resumable download. HTML rendering polish; citation-style search box ("16 USC 45f(c)(5)" → identifier).
- **Day 3:** Backfill prior RPs (~324, back to 2013 — *the real count is 382 published, per §1; 381 loaded*). Downloader runs as a resumable queue (bandwidth-bound; measured ~9 GB of zips under `titlesAffected` — start it Day 2 night; corpus of record on the S3 mirror, ADR-0013 / docs/remote-ops.md). Ingest driven by `titlesAffected` per RP, hash-dedupe as verification; build `guid_map` per RP.
- **Days 2–3, parallel track — reader interface overhaul (Session 7, worktree, independent of the backfill):** the Session-5 reader is the demo minimum and its review (BUILDLOG 008) found five things to fix before polish makes sense: **(1) mobile-first restyle** — base styles authored for ~360 px with `min-width` media queries upward; indents become a CSS-variable step (small on phones, 1.6rem wide) instead of fixed 1.6–6.4rem margins; ≥16px form controls (iOS zoom), ≥44px tap targets. **(2) A real site navbar** above everything: brand + Titles + Release points + API docs (Watchlist joins Day 5), no JS; breadcrumbs + release picker move to a contextual bar *below* it. **(3) The section title fixed**: `§ 45f. Mineral King Valley addition authorized` as one reading-face line (num inline, not a gray eyebrow), badge after. **(4) Navigation top *and* bottom**: compact prev/next + up-a-level strip under the title bar, full neighbors block and a site footer at the bottom. **(5) `<ref>` handling** — internal `/us/usc/` refs carry the page's `?release=` and get hover text (`title=` with the cited section's num + heading, batched in one repository query per page); `/us/pl/` and `/us/stat/` refs currently render as broken relative links and must link out (govinfo link service `/link/plaw/{congress}/public/{law}`, statviewer/`/link/statute/{vol}/{page}`) or degrade to spans — never a local 404.
- **Day 4:** Reader UX on top of the overhaul: keyboard nav, notes/sourceCredit toggles, version timeline per section ("changed at these RPs"), diffs between two versions — port/adapt the diff approach from dreamproit/versions rather than writing one from scratch.
- **Day 5:** Auth + watchlists (provision, section, or whole-chapter items; optional pinned release). "My provisions" home page. Email is out of scope for v1 (no notifications yet — but schema supports it).
- **Day 6:** Performance & deploy: HTTP caching (immutable per (identifier, RP) → cache-forever ETags), CDN in front, deploy API+DB (Fly.io/Render/VPS), smoke tests.
- **Day 7:** Hardening: `Uslm2Parser` to full parity (TOC/tables/indent-model differences, validated against samples/uslm2/ — so the day OLRC flips to 2.x, ingest keeps working); full-corpus verification job (counts per title per RP vs source), accessibility pass, README + API docs, load test, backlog for xcitedb port.

---

## 7. Agent orchestration plan

**Recommended interface: Claude Code (CLI or VS Code extension) on your machine, one git repo, using plan mode + subagents + git worktrees for parallel workstreams.** Cowork is right for docs/research (like this plan); Claude Code is better for a multi-module build because it gives you plan-mode review before edits, parallel worktree agents, hooks/tests on every change, and cheap re-runs. Optionally add the Claude GitHub Action so PRs get automatic review.

Setup once: `CLAUDE.md` at repo root recording the conventions above (repository interface rule, identifier semantics, dedupe rule, test commands). Every agent session inherits it — this is what keeps a multi-agent build coherent.

| Workstream | Agent / mode | Model | Rationale |
|---|---|---|---|
| Architecture decisions, schema review, resolver design | Plan-mode session (or `Plan` subagent) | **Opus 5** | Highest-stakes decisions; errors here are expensive |
| USLM parser + ingest pipeline | Main Claude Code session | **Opus 5** | USLM edge cases (appendices, status, notes, big-title streaming) are the hardest code |
| Repo scaffold, docker-compose, Alembic, CI | Main session or worktree agent | **Sonnet 5** | Well-trodden patterns; fast and cheap |
| FastAPI routes + repository impl | Worktree agent | **Sonnet 5** | Straightforward once resolver is specified |
| Frontend reader UI | Worktree agent | **Sonnet 5** | Iterative UI work; Sonnet iterates fastest |
| Auth + watchlist | Worktree agent | **Sonnet 5** | Standard CRUD + auth patterns |
| Bulk download/backfill scripts | One session writes; then runs unattended | **Sonnet 5** (code), no LLM at runtime | Long-running jobs are plain Python, not agent loops |
| Test writing, fixture generation | `general-purpose` subagent per module | **Sonnet 5** | Parallel to feature work |
| Verification: cross-check counts vs source XML, API contract tests, review PR diffs | Separate reviewer session / GitHub Action | **Opus 5** for review, **Haiku 4.5** for mechanical checks (lint, link checks, doc sweeps) | Independent verification catches what the author-agent misses |
| Exploration ("where is X handled?") | `Explore` subagent | **Haiku 4.5 / Sonnet 5** | Keeps main context clean |
| Build-log & ADR upkeep (see §11) | End of every session, same session | any | Documentation debt compounds; write it while context is hot |

Working rhythm per module: Plan mode (Opus) → approve plan → implement (assigned model) in a worktree → tests pass → reviewer session (fresh context, Opus) reads the diff → merge. Merge order: schema → ingest → API → web → auth (each unblocks the next; UI can start against fixture JSON in parallel).

---

## 8. Accounts & setup you need

**Claude access.** Heavy multi-agent use for a week means Opus + parallel sessions. Starting point here is Claude Pro + $100 API credits; see GETTING-STARTED.md §2 for the exact upgrade path. Summary:
- **Upgrade Pro → Max** for the build week (Max 5x $100/mo minimum; **Max 20x $200/mo recommended** for Days 2–4 parallel work). Pro alone gives Claude Code with Sonnet only — no Opus — and its limits won't survive Day 1.
- The **$100 API credits** are best spent on headless/CI agents (GitHub Action PR review, scheduled verification runs) and as overflow if subscription limits hit mid-day.

**Development.**
- GitHub repo (you have one initialized here already) + optionally the Claude Code GitHub App for PR review.
- Local: Docker Desktop, Python 3.12 + uv, Node 20+ (Astro frontend, ADR-0011), `lxml`, Postgres 16 via compose.
- Disk: ~100 GB free for the RP zip archive, or an S3/Backblaze B2 bucket (~$5/mo) as the zip cache. *(Measured: the zips are 9.7 GB and the database 27 GB.)*

**Hosting (Day 6).**
- Simple: **Fly.io or Render** (FastAPI + managed Postgres). Postgres with all RPs deduped is likely 10–40 GB — check managed-tier pricing, or
- Cheaper for storage-heavy DB: a **Hetzner/DO VPS** (~$20–40/mo) running compose, with Cloudflare (free) in front for caching immutable section responses.
- Domain (~$12/yr) + Cloudflare DNS, optional.

*Superseded, 2026-08-01.* None of these was taken. The site runs on **one EC2 box** with Compose
behind Caddy, images built by Actions on arm64 and pushed to ECR and deploys carried by SSM
([ADR-0020](docs/adr/0020-deploy-one-ec2-box-compose-caddy.md),
[ADR-0035](docs/adr/0035-images-from-ecr-deploys-from-actions.md)); DNS is Route 53 and the
certificate is Caddy's. There is **no CDN in front of the spine**
([ADR-0047](docs/adr/0047-no-shared-cache-in-front-of-the-spine.md)), so the "Cloudflare in front
for caching immutable section responses" line above describes an arrangement that was considered
and declined. Live state is [docs/deploy-status.md](docs/deploy-status.md).

**No credentials needed** for uscode.house.gov — downloads are public. Be polite: sequential downloads, ~1 req/sec, cache everything, set a descriptive User-Agent.

---

## 9. Risks & gotchas (encode these in CLAUDE.md)

*Renumbered 2026-08-06.* This list used to run 1, 1a, 2, 3 …, which put every entry after the first
one place behind the same entry in CLAUDE.md's gotcha list — and `api/routes.py` cites those by
number ("gotcha 4", "gotcha 9"). The numbering below is CLAUDE.md's, and entry 10 — cited as
"§9.10" by `ingest/load.py`, ADR-0007 and ADR-0012, and stated in §1's release-points bullet but
never in this list — is written out here so those references land on it.

1. **`@id` GUIDs are regenerated at each RP by design** — a GUID means (provision, release point). Treat it as a globally unique version pin, and never as a cross-release identity (that's `@identifier`'s job).
2. **Dual schemas** — never hard-code USLM 1.x element paths outside `Uslm1Parser`; all schema knowledge lives in the parser implementations.
3. **Renumbering/transfers** break `@identifier` continuity — track `status="transferred"` and consider a redirects table; a section identifier may disappear at an RP without being repealed.
4. **RP labels don't sort** — always use parsed (congress, law, exclusions, update) + `seq`; handle compound `notXnotY` and the `u1` re-issue suffix.
5. **"not" laws vs `?date`** — at RP `119-102not101` the text is *not* fully current through 07/12/2026; the UI must show the exception, not just the date.
6. **Title 42 is huge** (multiples of Title 16) — parser must stream (`iterparse` + element clearing), never load whole trees; DB writes batched.
7. **Appendix titles** (`05a` etc.) have their own files and sometimes looser structure — treat as distinct titles.
8. **Early RPs (2013–2015)** use older USLM 1.0 converter output — expect attribute drift; validate ingest counts per title per RP.
9. **Repealed/omitted sections** still occupy reading order — keep them in prev/next with badges.
10. **Every RP republishes all titles**, but few of them changed — full-corpus ingest must dedupe by content hash or storage explodes (~300 RPs × ~1 GB/RP uncompressed). `titlesAffected` from the RP inventory drives ingest; hashing verifies. *(Written out 2026-08-06 from §1; it was always cited as §9.10 and never printed here.)*
11. **xcitedb future** — everything version-resolution-related stays behind the Repository interface; no raw SQL in API handlers. The existing loader (dreamproit/loadusc-xcitedb) is the starting point for the XCiteDB Repository implementation and the nightly auto-update job.

## 10. Demo definition of done

Day 1: open the site → browse Title 16 TOC → open §45f → highlight (c)(5) via URL → flip release picker between two RPs → prev/next works. **Done (BUILDLOG 006–007)** — `docker compose up -d --build`, then `http://localhost:8000/us/usc/t16/s45f/c/5?date=07/12/2026`.
Day 7: any citation, any of ~324 RPs (*382 published, 381 loaded — §1*), by `?release` or `?date`; log in; watch `/us/usc/t16/s45f/c/5`; reopen it from watchlist in one click; section version timeline visible; both USLM 1.x and 2.x files ingest cleanly.

## 11. Documentation & provenance (for the blog series and for AI-skeptical users)

Every working session leaves a paper trail in the repo, so the build can be reconstructed step by step and independently verified:

1. **`BUILDLOG.md`** — one entry per session: date, model used, what was asked, what was decided, commits produced, what was verified and how. Written at the end of each Claude Code session ("Update BUILDLOG.md for this session" is the last prompt, every time).
2. **`docs/adr/`** — Architecture Decision Records: one short file per consequential decision (why Postgres first, why sections are the storage atom, why a dual-parser layer, GUID semantics). Skeptics can audit reasoning, not just results.
3. **Commit discipline** — small commits, imperative messages, `Co-Authored-By: Claude <model>` trailers preserved. The git history *is* the walkthrough.
4. **Data provenance manifests** — every ingest writes `data/manifests/{release}.json`: source URL, download timestamp, zip sha256, per-title section/element counts. Anyone can re-download from uscode.house.gov and confirm hashes and counts match — the strongest answer to "did the AI make this up?" is a mechanical check against the official source.
5. **Verification artifacts committed** — test outputs and the Day-7 full-corpus count report live in `docs/verification/`, regenerated by `make verify`, so reliability claims are reproducible commands, not assertions.
6. **README** — carries the project story, links to all of the above, and a standing "How this site was built" section that grows as the build progresses.
