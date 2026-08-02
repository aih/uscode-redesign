# CLAUDE.md — uscode-redesign

Versioned US Code retrieval site: any provision, at any release point (RP), via a URL scheme
mirroring the USLM `@identifier`. FastAPI + Postgres v1, XCiteDB later behind a repository
interface. Full context in [PLAN.md](PLAN.md); decisions in `docs/adr/`.

**Status:** The reader/API separation is live (`frontend/` exists, Jinja is gone). The release-point
inventory is seeded (382 RPs with real `currency_date` and a true global `seq`) and **the whole corpus
is loaded — 3,153 title-releases across 58 titles and 381 release points, 65,938 distinct sections,
5,466,652 (section, release) pairs stored as 489,738 `section_versions`, 91.0% deduped, 96,185,732
`guid_map` rows, 27 GB on disk** (ADR-0007's dedupe working at full scale); `structure_nodes` holds the
hierarchy from a streaming TOC pass (ADR-0006). The backfill is **COMPLETE** — the ledger is 3,153 `ok`
/ 44 `unavailable` / 0 pending, 9.7 GB on disk — and the S3 mirror (ADR-0013) holds all of it, verified
against the local corpus.

`storage/` has the `Repository` protocol + Postgres implementation, plus a second, narrower
`AccountsRepository`/`PostgresAccounts` pair for users/sessions/watchlists (ADR-0017 — not bolted onto
`Repository`, which stays version-resolution-only), and `storage/search.py` over OpenSearch (ADR-0028).
`api/` serves PLAN §4's routes — identifier lookup with `?release`/`?date`/`?format`, `?id=` guid lookup,
TOC, neighbors, versions, releases, a diff between two release points (ADR-0016), the batched
`/api/v1/labels` (100 identifiers max, the bound the route enforces), `/api/v1/search`,
`/api/v1/citation`, and auth + watchlist CRUD (ADR-0017). `frontend/` is the reader — **Astro 5 +
TypeScript + USWDS** at `/app/us/usc/…` (ADR-0011, ADR-0015), server-rendered with a handful of small
islands: sticky reading chrome, a version timeline, a reading-text redline (ADR-0026), keyword search,
hover previews (ADR-0024), one search-and-citation box (ADR-0023), a theme toggle (ADR-0027), and a copy
control (ADR-0033). Every response carries a cache policy (ADR-0018); every expensive unauthenticated
route is rate-limited (ADR-0029); CSP and frame headers are ADR-0030; accounts and bulk downloads are
built-and-off in the UI, a UI switch and not a security control (ADR-0034).

`make test` = **475** Python tests; `make test-web` = **194** frontend tests; `make test-e2e` = **82**
Playwright tests (**all three are required** — reader coverage lives in Vitest since Jinja retired), and
**CI runs all three on every push** (`.github/workflows/ci.yml`, Postgres service container, offline
fixtures via `make ci-data`, `USC_REQUIRE_INTEGRATION=1` so a misconfigured job can't go green having run
nothing).

**Session history lives in [BUILDLOG.md](BUILDLOG.md)** — one entry per session, and in `docs/adr/`
(34 ADRs). Read the entry you need rather than assuming; this file deliberately no longer restates them.

**Deployed** to one EC2 box at `uscode.linkedlegislation.org` (ADR-0020 + ADR-0035): images built by
Actions on arm64 and pushed to ECR, deploys by SSM, corpus seeded by `pg_restore` from the mirror,
weekly corpus update scheduled. **Live state and what is still owed are in
[docs/deploy-status.md](docs/deploy-status.md)** — read that before touching the deployment.

**Next: (1) finish the deployment's open items (`docs/deploy-status.md`); (2) Day 7 hardening.**

Open debts: **the rate limiters are per-process state**, honest for ADR-0020's single box and wrong for a second instance (ADR-0029's recorded cost); **the CSP carries `script-src 'unsafe-inline'`** until the islands get nonces through the new Astro middleware (ADR-0030's recorded cost); **no email verification and no password reset — accounts are throwaway until email exists, decided and recorded in ADR-0019** rather than left as a gap; **the search index on the deployed box is not built yet** and `docs/verification/loadtest.json` has never been regenerated against the deployed site (`docs/deploy-status.md`); **appendix titles are unreachable by citation** — `5 U.S.C. App. 3` parses to `/us/usc/t5a/s3` and OLRC publishes nothing there (0 of 461 appendix sections use the flat form; they are `/us/usc/t5a/pl/92/463/s1` or `/us/usc/t50a/act/1917-05-18/ch15/s212`), so the API explains rather than 404s; the preview endpoint is unauthenticated and fans out per hovered citation — **now rate-limited in `frontend/src/middleware.ts` (ADR-0029)**, still unauthenticated; **USLM `<date>` renders as a block**, so dates break mid-sentence throughout the notes — one entry in `uslm.ts`'s inline set, left out of a scoped refresh; **the reader's redline drops `<ref>` links and cannot see a whitespace-only change** (ADR-0026's named costs); **the search index holds a 4,000-document smoke slice, not the corpus** — a full build was deferred; `python -m ingest.reindex_search --recreate` builds the 66k current-text index the default query reads and `--all-versions` the 490k superseded ones `?release=` needs, and until then a point-in-time search answers from current text alone (the response names the release it searched, so this is visible); the search endpoint is unauthenticated — **now throttled and input-bounded (ADR-0029)**; **a section the source publishes twice under one identifier at one release (ADR-0021) shares an OpenSearch `_id`**, so the index keeps one of the two; the diff endpoint is CPU-bound — ~0.45 rps at any concurrency, failing entirely past ~10 concurrent — and is **now rate-limited (ADR-0029, the tightest budget in the project)**, so it sheds with 429 + `Retry-After` rather than collapsing; `docs/verification/loadtest.json` predates that and has not been regenerated; **~half the API diff's cost is `@id` churn rather than legal change** — diffing the guid-stripped text is 2,220 ms → 1,172 ms and 51 → 20 ops; the *reader* no longer pays it (ADR-0026 moved the reader to a text redline), the endpoint still does, and `docs/verification/loadtest.json` is stale for `/app/diff` as a result; **accounts and bulk downloads are switched off in the reader but their API routes are untouched** — ADR-0034 is a UI decision, so `POST /api/v1/auth/signup` still works for a direct caller; **the copy column adds ~100 tab stops to a long section** and its copied text drops notes and `sourceCredit` (ADR-0033's named costs); **link mode has no plain-text fallback** — if the `ClipboardItem` write throws (older Firefox, plain HTTP on a non-localhost host) the reader is told "Could not copy" and gets nothing, where the bare URL would still be useful (BUILDLOG 034, raised and left unchanged); **the labels batching has no end-to-end test** because CI's fixture corpus tops out at 75 cross references (16 U.S.C. § 1801) against a bound of 100, so an e2e assertion would pass with or without the fix — real cover needs a denser fixture title in `make ci-data` (BUILDLOG 034); **2.4 MB of vendored Swagger UI / ReDoc is committed**, so a security fix in either arrives only when someone bumps `static/apidocs/MANIFEST.json` (ADR-0032's named cost); **HEAD is 405 on every `/api/v1` route** (FastAPI registers GET alone), which matters once a CDN or uptime monitor is in front; `purge_login_failures` is now on a weekly cron on the deployed box but nothing calls it in dev; **the general `/api/v1/watchlists` multi-list CRUD has no frontend UI** (only the default-list convenience endpoints the reader uses are wired to a page); a deduped fragment carries the guids of the release its text first appeared at (ADR-0007's recorded cost); `structure_nodes` is unversioned — one row per node, holding **the newest loaded release's view**; `first_release_id`/`last_release_id` bound its life, and both those and the descriptive fields are gated on `seq`, so load order doesn't decide the answer (an older load silently relabelled a `reserved` subchapter `repealed` before that gate existed). Per-release structural history is still owed; **the source sometimes publishes several elements under one `@identifier` at one release point — the reader shows every occurrence with a note rather than picking one (ADR-0021), and `sections_loaded` therefore exceeds `section_release_map` on six title-releases**; `Uslm2Parser` has no table/indent handling (Day 7); `make verify` is real (ADR-0014) and `--deep` has now been run over the whole corpus — **3,153 of 3,153 title-versions independently recounted from source, 0 source mismatches, 0 incomplete loads** (`docs/verification/database.json`); the six count mismatches it reports are the source publishing several elements under one `@identifier` (ADR-0021), left reported rather than smoothed away. **Test speed rule:** default `make test` never parses the 32 MB usc16.xml — unit tests use `tests/fixtures/usc16_slice.xml` (regenerate with `make fixtures`); full-sample tests are `@pytest.mark.slow`, run by `make test-slow`. API integration tests need a loaded database (`make dev-data`) and skip without one.

## Architecture rules (PLAN §2)

1. **API and UI talk only to the `Repository` interface** (`storage/repository.py`) —
   `resolve_release(...)`, `get_section(identifier, release)`, `get_toc(...)`, `resolve_id(...)`,
   `neighbors(...)`, `versions(...)`, `list_releases(...)`. Postgres is implementation v1
   (`storage/postgres.py`, the only SQL in the project); XCiteDB becomes a second implementation
   with no API/UI changes. **No raw SQL in API handlers**, and nothing version-resolution-related
   outside the Repository. `api/` holds no database session either — `storage.get_repository` is
   the FastAPI dependency. `tests/test_architecture.py` enforces all of this; ingest is
   deliberately on the other side of the boundary and writes `db/` models directly.
2. **The ingest layer is schema-plural.** A `UslmParser` protocol with `Uslm1Parser` and
   `Uslm2Parser`, selected by `detect_uslm_version(file)` — **the root namespace URI decides**
   (`xml.house.gov/schemas/uslm/1.0` → 1.x, `schemas.gpo.gov/xml/uslm` → 2.x); `xsi:schemaLocation`
   only labels the point version (ADR-0004). Both emit the same normalized `SectionRecord`
   (identifier, guid, temporalId, num, heading, status, seq, raw XML fragment, source credit,
   notes, guid_refs, ancestors). **Never hard-code USLM element paths outside a parser
   implementation** — `StreamingSectionParser` shares the traversal but knows no element names of
   its own; each parser supplies an `ElementNames` vocabulary. Downstream layers are
   schema-agnostic; `schema_version` rides along so original XML is always returnable verbatim.
3. **Sections are the storage atom** (ADR-0001). Sub-section provisions (`/c/5`) are extracted from
   the section XML at request time via lxml XPath on `@identifier`, returning the whole section with
   the target anchored/highlighted — the reader always keeps context.
4. **Layout:** `ingest/` (fetch RPs, parse USLM, split into sections) → `storage/` (Postgres +
   repository interface) ← `api/` (FastAPI resolver, auth, watchlist) ← `frontend/` (the Astro
   reader, over HTTP only). Top-level `main.py` composes the app, `params.py` holds what the
   surfaces share, `citation.py` is the redirector.
5. **Reader and API separated; the citation URL redirects (ADR-0010, amends ADR-0009 — done,
   BUILDLOG 014).** Reader at `/app/us/usc/…` (always HTML, no negotiation), API at
   `/api/v1/us/usc/…` (JSON default, `?format=xml` verbatim; no Jinja imports under `api/`), and
   the bare citation URL `/us/usc/…` a thin redirector — 307 to `/app` for HTML-winning `Accept:`,
   307 to `/api/v1` otherwise, `?format=` wins, `Vary: Accept`, query string copied through
   verbatim. The app is assembled in top-level **`main.py`** (`uvicorn main:app`), the only module
   that imports both surfaces; the HTTP helpers they share — `?release`/`?date`/`?format`, release
   resolution, `Accept:` parsing — live in top-level **`params.py`**, and the redirector in
   **`citation.py`**. `tests/test_architecture.py` enforces it: **no Python module imports a
   template engine**, which is the strongest form of the rule and true since the Jinja reader
   retired. The reader is Astro 5 + TypeScript + USWDS in `frontend/` (ADR-0011, accepted),
   consuming `/api/v1` over HTTP and nothing else; one Caddy (`deploy/Caddyfile`) owns :8000 and
   routes `/app/*` to it, everything else to FastAPI on :8001 (ADR-0015). Every reader href goes
   through `frontend/src/lib/url.ts` — `/app` is spelled out once. Presentation — the sole place
   outside the parsers allowed to know USLM element names — is `frontend/src/lib/uslm.ts`.

## Identifier semantics (PLAN §1, ADR-0003) — the thing most likely to be gotten wrong

| Attribute | Meaning | Use for |
|---|---|---|
| `@identifier` | Logical path `/us/usc/t16/s45f/c/5`. **Cross-release identity.** Stable across RPs *unless renumbered*. | Primary key for the URL scheme; joining a provision to itself over time |
| `@id` (guid) | `id0b32dff7-810c-11f1-…`. **Pins (provision, release point)** — regenerated at every RP *by design*, and that pair is globally unique. | Global `guid_map` index; `?id=` lookup needs no release param; stable "this exact text at this exact time" citation |
| `@temporalId` | `s1201_a_1_A`. **Not guaranteed unique.** | Display only — never a key |
| `@status` | `repealed` / `omitted` / `transferred` / `reserved` | Must stay retrievable and badged in UI |

A guid is never a cross-release identity — that is `@identifier`'s job, and only its job.

## Gotchas (PLAN §9) — encoded here because each one has already bitten someone

1. **Guids regenerate per RP by design.** Version pin, never cross-release identity. **This
   defeats naive content dedupe** — an untouched section's raw XML differs at every RP, so
   hashing it collapses nothing (measured: 0 of 5,095 Title 16 sections identical between
   119-99 and 119-102not101; 5,093 identical once `@id` was stripped). Hash
   `SectionRecord.content_key`, never `.xml` (ADR-0007).
2. **Dual schemas** — no USLM 1.x paths outside `Uslm1Parser` (see architecture rule 2).
3. **Renumbering/transfers break `@identifier` continuity.** Track `status="transferred"`; consider a
   redirects table. An identifier can vanish at an RP *without* being repealed.
4. **RP labels do not sort lexically.** Parse into (congress, law_num, excluded_laws[], update_num)
   plus a global `seq` taken from the inventory page's order. Skip labels compound
   (`277not255not268`), and 17 of the 385 published RPs carry a `u1` update suffix (`118-22u1`) —
   `118-22` is a *different* release point with different files.
5. **"not" laws vs `?date`.** At RP `119-102not101` the text is *not* fully current through
   07/12/2026. The UI must surface the exception, not just the date.
6. **Title 42 is huge** (multiples of Title 16). Parsers must stream — `iterparse` + element
   clearing, never whole trees. Batch DB writes.
7. **Appendix titles** (`05a`, `11a`, `18a`, `28a`, `50a`) are separate files with looser structure —
   treat as distinct titles.
8. **Early RPs (2013–2015)** came from an older USLM 1.0 converter; expect attribute drift. Validate
   ingest counts per title per RP.
9. **Repealed/omitted sections keep their place in reading order** — present in prev/next, badged.
10. **Every RP republishes all titles** but few changed — dedupe by content hash or storage explodes
    (~300 RPs × ~1 GB). `titlesAffected` from the RP inventory drives ingest; hashing verifies.
    The flip side is a *retrieval* rule: a request for an RP that was never ingested is answerable
    from the newest ingested RP at or before it, because the title didn't change in between. The
    Repository does that and reports it as `served_from` — answer, but never silently.
11. **XCiteDB is the near future,** not "someday" — respect rule 1 strictly.
12. **`<section>` inside `<quotedContent>` is not a section** — it is statutory text quoted by an
    amending act, carries no `@identifier`/`@id`, and must never be stored or counted (ADR-0005).
    Counting `<section>` elements naively inflates Title 16 by 298. Related: skipping such an
    element must not *remove* it — it is part of the enclosing section's verbatim XML.
13. **`@status` is not section-only and not a closed set.** Title 16's one `reserved` is on a
    `<subchapter>`; USLM 2.x Title 49 uses `renumbered`. Never model status as an enum.
14. **USLM 1.0.15 emits no `@temporalId` at all** — zero in a 32 MB title. Display-only field;
    do not build anything that assumes it is present. It also emits no `<dc:title>`, so a title's
    real name (`CONSERVATION`) comes from the root structural element, not `<meta>`.
15. **Facts that can change while the text does not** — reading order, parent chapter — belong on
    `section_release_map`, never on the content-deduped `section_versions` row (ADR-0008).
16. **A title number is a string; never `ORDER BY` one.** `5a` is a title and `5` is a different
    one, so `Title.num` cannot be an integer — and sorting it as text gives
    `1, 10, 11, 11a, 12, … 2, 20`, which is what the front page listed for eight sessions. Sort
    through `storage.postgres.title_sort_key` (`'5a'` → `(5, 'a')`), which is also the documented
    contract on `Repository.list_titles` (ADR-0025). Do **not** reach for `_padded()` instead: that
    is OLRC's file-naming form (`05`, `18a`) for matching `titles_affected`, and it is still a
    string comparison — one that merely happens to work below title 100.

17. **OLRC writes section numbers with an EN DASH, not a hyphen.** `/us/usc/t16/s45a–1` is
    U+2013, and **5,697 of the corpus's 65,938 sections contain one while not a single section
    contains `-`**. No keyboard has that key, so anything matching user input against an
    identifier must try both (`citeparse.ParsedCitation.section_variants`). Worse, a raw en dash
    in an HTTP header **throws** — a header value is a ByteString — so every URL built for a
    redirect must be percent-encoded (`frontend/src/lib/url.ts`). Both failures were live.

## Fixtures

- `samples/uslm1/usc16.xml` — USLM 1.0.15, 32 MB. Primary parser fixture.
- `samples/uslm2/USLM2/` — USLM 2.x: `usc16.xml` (cross-schema parity), `usc49.xml` (heaviest
  table/layout markup), `usc01.xml` (253 K, fast iteration). Trimmed from OLRC's full 57-title,
  594 MB [sample zip](https://uscode.house.gov/currency/uscinuslmv2samples.zip) — re-download it if
  another title is needed.
- `tests/fixtures/usc16_slice.xml` — 878 KB verbatim slice of usc16.xml (ch.1 subchapters I–VI
  through §45f, plus schXIII for quoted sections and schXCVII for `reserved`). Every unit test runs
  against this. Regenerate with `make fixtures` (`scripts/extract_fixture.py`).
- Known-good assertion: `id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd` ↔ `/us/usc/t16/s45f/c/5`.
- Title 16 @ 119-102not101 — **two counts, don't conflate them (ADR-0005):**
  - raw `<section>` elements: **5,393**; 523 repealed / 102 omitted / 19 transferred.
  - real code sections the parser emits: **5,095**; 522 repealed / 102 omitted / 19 transferred.
  - The 298-element gap is `<section>` inside `<quotedContent>` — statutory text quoted by amending
    acts, with no `@identifier` and no `@id`. One of them is marked repealed, hence 523 vs 522.
  - The file's **single `reserved` is on a `<subchapter>`** (`/us/usc/t16/ch1/schXCVII`), not a
    section. Section status counts total 643, never 644.
- **Never commit `data/`** — the RP zips (measured ~9 GB via `titlesAffected`; 40–80 GB only if
  every title were fetched at every RP) are gitignored; the corpus of record is the S3 mirror
  (ADR-0013).

## Commands

```
make dev        # the API alone: /api/v1, the citation redirector at /us/usc, /docs
make dev-web    # the reader alone on :4321 (Astro), against API_BASE_URL
make dev-all    # the whole site on :8000 — Caddy in front of both, as deployed
make dev-data   # seed release_points from the RP inventory, then load Title 16 at 119-99
                # (downloaded, ~5 MB) and 119-102not101 (from samples/) — what the API
                # integration tests need; they skip without it
make ci-data    # the same two release points with NO network: inventory from
                # tests/fixtures/releasepoints.json, 119-99 from a committed zip. What CI
                # uses — never fetch from uscode.house.gov on every push (ADR-0013).
make loadtest   # hey against the top routes → docs/verification/loadtest.json; needs
                # `make dev-all` running and `brew install hey`
make test       # uv run pytest (-m 'not slow') — the specification; nothing merges without it green
make test-web   # vitest: the USLM renderer + reading-text extraction, the reference rules,
                # the document redline, url/cache/preview helpers
make test-e2e   # playwright: what only a browser can answer — the theme toggle (light default,
                # persistence, no sticky-height cost), the hover preview's three WCAG
                # 1.4.13 clauses, sticky geometry, scroll-margin-top, the citation box end to
                # end. Needs `make dev-all` running.
make shots      # headless screenshots at 375px and 1280px → docs/screenshots/
make test-slow  # full-sample parser integration tests (~4 s): counts vs samples/, memory bound
make test-all   # both
make fixtures   # regenerate tests/fixtures/usc16_slice.xml from samples/uslm1/usc16.xml
make verify     # (TBD — stub, exits 1) full-corpus counts vs source XML → docs/verification/, PLAN §11.5, Day 7
docker compose up --build   # full containerized stack (db + api) instead of `make dev`'s local API
```

The `python -m ingest …` CLI reference (inventory, fetch, backfill, mirror, load-all, load,
reindex_search, verify, verify-downloads) and `scripts/vendor_apidocs.py` are in the **`ingest-cli`
skill** (`.claude/skills/ingest-cli/SKILL.md`) — loaded on demand rather than every session.

Stack: see `pyproject.toml`, `package.json` and `docker-compose.yml`. What they don't say: the `api`
service builds from `Dockerfile` with UV_PROJECT_ENVIRONMENT=/opt/venv so the dev bind mount doesn't
shadow the container venv; `db/config.py` reads `DATABASE_URL` (see `.env.example`) and Alembic's
`env.py` pulls the same setting and `target_metadata` from `db.models.Base`, so there is no separate URL
to keep in sync. Node 20+ is required — the Astro frontend (ADR-0011) landed in Session 7 and
`make test-web` runs under it.

## Documentation duties (PLAN §11) — non-negotiable, this project is built in the open

1. **Every session ends by updating `BUILDLOG.md`** — one entry per session, in the format at the top
   of that file: date, tool/model, what was asked, what was decided (link ADRs), commits produced,
   what was verified and how to re-check it. Write it while context is hot, before the session ends.
2. **`docs/adr/`** — one short ADR per consequential decision. Skeptics audit reasoning, not results.
3. **Commit discipline** — small commits, imperative messages, preserve `Co-Authored-By` trailers.
   The git history is the walkthrough.
4. **Provenance manifests** — every ingest writes `data/manifests/{release}.json`: source URL,
   download timestamp, zip sha256, per-title section/element counts. Anyone can re-download and
   confirm.
5. **Verification artifacts committed** to `docs/verification/`, regenerated by `make verify` —
   reliability claims must be reproducible commands, not assertions.

## Model assignment

The per-workstream agent/model table is **PLAN §7** — read it there. Rhythm per module: plan (Opus) →
approve → implement in a worktree → tests pass → fresh-context reviewer reads the diff → merge. Merge
order: schema → ingest → API → web → auth.

## External source etiquette

uscode.house.gov needs no credentials, but be polite: sequential downloads, ~1 req/sec, cache
everything, descriptive User-Agent. Reuse [dreamproit/loadusc-xcitedb](https://github.com/dreamproit/loadusc-xcitedb)
for the RP inventory/downloader and [dreamproit/versions](https://github.com/dreamproit/versions)
for the temporal diff approach — don't rediscover solved problems.
