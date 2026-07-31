# CLAUDE.md — uscode-redesign

Versioned US Code retrieval site: any provision, at any release point (RP), via a URL scheme
mirroring the USLM `@identifier`. FastAPI + Postgres v1, XCiteDB later behind a repository
interface. Full context in [PLAN.md](PLAN.md); decisions in `docs/adr/`.

**Status:** Sessions 1–8 built; **`feature/reader-overhaul` merged into main (BUILDLOG 016) — the reader/API separation is LIVE, `frontend/` exists, and Jinja is gone.** The release-point inventory is seeded (382 RPs with real `currency_date` and a true global `seq`); **the whole corpus is loaded (BUILDLOG 023) — 3,153 title-releases across 58 titles and 381 release points, 65,938 distinct sections, 5,466,652 (section, release) pairs stored as 489,738 `section_versions`, 91.0% deduped, 96,185,732 `guid_map` rows, 27 GB on disk** (ADR-0007's dedupe working at full scale); `structure_nodes` holds the hierarchy from a streaming TOC pass (ADR-0006); `storage/` has the `Repository` protocol + Postgres implementation, plus a second, narrower `AccountsRepository`/`PostgresAccounts` pair for users/sessions/watchlists (ADR-0017 — not bolted onto `Repository`, which stays version-resolution-only); `api/` serves PLAN §4's routes — identifier lookup with `?release`/`?date`/`?format`, `?id=` guid lookup, TOC, neighbors, versions, releases, a diff between two release points (`/api/v1/sections/{id}/diff?from=&to=`, ADR-0016), the batched `/api/v1/labels`, and since Day 5 (BUILDLOG 020) `/api/v1/auth/{signup,login,logout,me}` (argon2 hashing, HttpOnly session cookie + double-submit CSRF cookie, ADR-0017) and `/api/v1/watchlist{,s}` CRUD; and `frontend/` is the reader — **Astro 5 + TypeScript + USWDS** at `/app/us/usc/…` (ADR-0011, ADR-0015), server-rendered with no JS bundle except one keyboard-nav island (Day 4), with provision highlighting, breadcrumbs, prev/next top and bottom, a release picker, status badges, citation hover text from one batched `/api/v1/labels` call, heading depth that tracks USLM nesting (`h2`–`h6`, not flat), notes/`sourceCredit` as no-JS `<details>` (open on desktop, closed on mobile), a version-timeline page per section (`/app/versions/…`) linked prominently by the title, a diff view (`/app/diff/…?from=&to=`) that redlines the **reading text** (`lib/diffdoc.ts` over `uslm.readingBlocks`, ADR-0026) while the API keeps serving the source-level XML redline it links to (`/api/v1/sections/{id}/diff`, `api/diff.py`, `diff-match-patch`, `Diff_Timeout=0` — ADR-0016), and since Day 5 two more small islands — a Watch button on section pages and login/signup forms (`fetch`-driven JSON, ADR-0017) — plus a pure-SSR `/app/provisions` ("My Provisions") that forwards the browser's session cookie to its own server-side API calls; **since Day 6 (BUILDLOG 022) every response carries a cache policy (ADR-0018) — `immutable` only when the release point was pinned *and resolved to itself*, `max-age=300` + ETag revalidation otherwise, `no-store` + `Vary: Cookie` on everything per-user, and `If-None-Match` short-circuits to 304**; the Jinja reader retired in BUILDLOG 014; and `ingest/backfill.py` is the resumable bulk downloader (ADR-0012) — `python -m ingest backfill`, driven by `titlesAffected` (3,197 files, not 22,156), with a ledger at `data/releases/ledger.json` and hash-dedupe verification; and the corpus mirrors to S3 (ADR-0013) — `python -m ingest mirror push/pull`, a disposable EC2 box runs the backfill unattended and powers itself off (`docs/remote-ops.md`), sized by measurement at **~9 GB / 40–50 h**, not the old 40–80 GB guess. **The backfill is COMPLETE** (BUILDLOG 022): the ledger is 3,153 `ok` / 44 `unavailable` / 0 pending, 9.7 GB on disk. `make test` = **474** Python tests; `make test-web` = **185** frontend tests; `make test-e2e` = **74** Playwright tests (**all three are required** — reader coverage lives in Vitest since Jinja retired; BUILDLOG 019 found and fixed the reason `test-web` had silently been testing nothing — `frontend/src/lib/` was never in git at all, an unanchored `lib/` line in the root `.gitignore` swallowing it every time, fixed to `/lib/`), and **CI runs all three on every push** (`.github/workflows/ci.yml`, Postgres service container, offline fixtures via `make ci-data`, `USC_REQUIRE_INTEGRATION=1` so a misconfigured job can't go green having run nothing) — the standing "test counts are the sessions' own claims" gap is closed. **Session 10 (BUILDLOG 024, ADR-0022/0023/0024/0025) is done — the UI refresh:** titles list in the Code's own order (`1, 2, … 5, 5a, 6, … 50, 50a, 51, 52, 54`) with the ordering documented on `Repository.list_titles` (ADR-0025); a **citation box in the header** (plain GET form, no JS) over a pure `citeparse.py` and `GET /api/v1/citation`, landing on `/app/goto` — 84 accepted forms, DB-free, from `11 usc 523(a)(1)(B)(ii)` to `11/523` to `section 523 of title 11` to raw identifier paths (ADR-0023); a **scrollable hover preview** of any cited provision (`/app/preview/…`, an Astro *endpoint* rendered by the same `lib/uslm.ts` so no USLM renderer reaches the browser; `popover` + CSS anchor positioning; WCAG 2.1 SC 1.4.13's three clauses as three named mechanisms; touch navigates — ADR-0024); and a **sticky reading chrome** (`.topbar` + a new `SectionBar` that absorbed `NavStrip`) — whole on desktop, one 44px row below 40em, with `--sticky-h` driving `scroll-margin-top` so a deep-linked provision never lands behind the bar. **Appica was evaluated and rejected on measurement** (one npm version ever, published 2026-07-09; last repo push 61 minutes after creation; 1,124 weekly downloads vs Base UI's 7.65M; React 19 + Tailwind 4 required) — but the deciding reason is local: `lib/uslm.ts` renders to an **HTML string**, so a React card cannot wrap a `<ref>` without rewriting the sole presentation layer (ADR-0022). The refresh added **one ~3 KB island**. Four live bugs fell out of building it: **OLRC writes section numbers with an EN DASH** (`/us/usc/t16/s45a–1`) — 5,697 of 65,938 sections contain one and *none* contains a plain hyphen, so every typed hyphen matched nothing, and a raw en dash in a `Location:` header **throws** (a header is a ByteString), which had been 500ing the `?id=` guid lookup for those sections since Session 7; every section page drew **all three Watch buttons at once** because USWDS's `.usa-button{display:inline-block}` beats the UA `[hidden]{display:none}`; citation hover text read **`§ § 688.`**; and `make shots` had silently stopped working since Day 5 (`networkidle` never settles once an island polls). **Session 11 (BUILDLOG 025, ADR-0026/0027) is done:** the site is **light by default at every OS setting**, with dark a header toggle stamped on `<html data-theme>` before first paint and remembered in `localStorage` — never a cookie, because a cookie would put `Vary: Cookie` on the whole cached reader (ADR-0027); the reader's **diff shows what the section says, not the XML it is stored as** — reading-text lines aligned, then word-diffed, so an untouched section reports *"identical at both release points"* instead of hundreds of regenerated guids (ADR-0026); and `/app/releases` **names the titles a release point changed** (each linked at that release, ones this database lacks marked) instead of counting them twice. **Session 12 (BUILDLOG 026, ADR-0028) is done — keyword search:** OpenSearch behind `storage/search.py`, `/api/v1/search` and a reader page at `/app/search`, with the search box in the header's `.navtools` row (**merged with the citation box in Session 13** — one control, `SiteSearch`). The index unit is the deduped section *version*, and **the default search returns only the text in force** (`is_current`); `?release=`/`?date=` swap that for `first_release_seq <= seq` plus a `collapse` on `identifier` — the newest text at or before the release asked for, gotcha 10's rule — with labels resolved through `Repository.resolve_release`. Ordering is the inventory's `seq`, never a row id. `ingest/search_sync.py` keeps the index in step **incrementally**: a new version is indexed current, its predecessors are retired with a partial update, and text republished unchanged writes nothing (91% of the corpus), after the transaction commits and gated on the title's newest *completed* load. `DISABLE_SEARCH_SYNC=1` means ingest never requires a cluster. **Session 13 (BUILDLOG 027, ADR-0029/0030) is done — the security debt, then the chrome:** every expensive unauthenticated route is now rate-limited (ADR-0029) — token buckets in `params.py` for `/api/v1` and in a new `frontend/src/middleware.ts` for `/app/preview` and `/app/diff`, which the API cannot attribute because the reader's server-side calls all arrive from one container address; budgets are therefore split by *who calls the route*, and inputs are bounded too (100 identifiers on `/labels`, `offset<=1000` and 1–500 chars on `/search`). Request identity comes first, because a limiter keyed on a caller-chosen value is not a limiter: `deploy/Caddyfile` overwrites `X-Forwarded-For` with `{remote_host}` in both handle blocks. **The S1 finding's stated mechanism was wrong and the correction is recorded** — Caddy preserves an inbound `X-Forwarded-For` only from a *trusted proxy*, and the global block trusts `private_ranges`, so the forgery worked from a private peer and not from the public internet: the dev stack was exposed and ADR-0020's EC2 shape was not, but a CDN or load balancer in front (which ADR-0018 anticipates) would be (`docs/verification/xff.md`, measured in a container). ADR-0030 adds `frame-ancestors 'none'`/`X-Frame-Options: DENY` and a CSP that *describes* a site with no CDN, font or analytics — with `script-src 'unsafe-inline'` stated plainly as the cost of eight `<script is:inline>` islands, nonces named as the follow-up now that the middleware exists. `safeNext()` closed an **open redirect and a `javascript:` sink on both auth forms**. OpenSearch stopped being configured by accident: **no default password** (`SearchNotConfigured` instead of a literal published in this repo), TLS verified unless `SEARCH_VERIFY_CERTS=false`, and the service finally present in `docker-compose.prod.yml` — so `docker compose` now **requires `SEARCH_PASSWORD` in `.env`** (copy it from `.env.example`). And four reader changes: **one search box instead of two** (`SiteSearch`; `/app/goto` is now a router — citation → provision, `cites …` → a marked keyword search, anything else → a plain one, with `citeparse` still the only thing deciding what a citation *is*), the header box given **its own row from 64em up** — 467px, up from 116px, because sharing the navbar's row inside USWDS's 1024px container only ever left it a remainder — and from a sliver to **234/426/686px** at 375/640/900 below that. That row costs `--sticky-h`, measured rather than estimated and corrected in both bands (`19rem` at ≥64em, `22rem` at 40–64em; the latter had already been short of the worst case before this session), with the e2e anchor-jump assertions as the check; the **footer laid out horizontally** (4 stacked rows → 1); the **verbatim-XML redline rendered in the page** as syntax-coloured HTML (`lib/xmlredline.ts`, opt-in behind `?source=1`, computed locally rather than from the API so it neither doubles the work nor spends ADR-0029's tightest budget); and an empty redline now **says which of three things it found** — byte-identical, guid-only, or beyond guids — and names the guids, which differ per release even when the deduped fragment is shared. **Session 14 (BUILDLOG 028, ADR-0031) is done — a search that means it, and chrome that stays on the site:** the keyword search is **strict by default** — the old `fuzziness: "AUTO"` spent two character edits on every term of six letters or more, so `compare` returned `compact` and `company`, each *exactly* two edits away (and not stemming: no analyzer is configured anywhere, so both text fields use the `standard` analyzer). `simple_query_string` with `default_operator: and` replaces it, with `~n`, `*`, `"…"`, `+`, `-`, `|` and `( )` as opt-ins documented at **`/app/search/syntax`**, linked from the zero-results panel where someone who mistyped actually lands. The flags are **named rather than `ALL`** so `tests/test_search_syntax.py` can check the guide against them — the only link between the Python suite and the frontend one — and `WHITESPACE` is in that list because leaving it out (it looks like a flag no search box needs) stops the parser splitting on spaces at all, so `water -pollution` silently parses to `water AND pollution`: valid query, opposite meaning, no error, visible only through `_validate/query?explain=true`. Also: **one search box, not two** (the search and go-to pages rendered a second copy in the body while the sticky header one sat empty — the header box is prefilled through `Base`'s `searchValue` and the `variant` prop is gone); the **API reference renders inside the site** at `/app/docs`, server-rendered from `/openapi.json` because the CSP names no CDN and ADR-0030's `X-Frame-Options: DENY` blocks framing `/docs` even same-origin (FastAPI's `/docs`/`/redoc` stay mounted and linked — Swagger UI can send a request); **sign-in moved from a button inside statutory text to the navbar** (`AuthNav`, an island for the same `Vary: Cookie` reason as the theme toggle; the Watch button now shows a logged-out reader nothing); and **cross references and search results open in a new tab**, with the choice stored per account in a new `user_settings` table but *applied* client-side, because a page in a shared cache cannot carry one reader's preference — new-tab is what scripting-off gets, and breadcrumbs/prev-next/TOC stay same-tab because those are the reading rather than a departure from it. The diff-XML item needed no work: Session 13 had already moved it in-page. **Session 15 (BUILDLOG 032, ADR-0032/0033/0034) is done — the chrome a public site needs:** **`/docs` and `/redoc` had been answering 200 with a blank body since Session 13** — FastAPI loads Swagger UI and ReDoc from `cdn.jsdelivr.net`, its favicon from `fastapi.tiangolo.com` and ReDoc's typefaces from Google, and ADR-0030's `default-src 'self'` refuses all six; nothing on the server said so and `curl` returned perfect markup. Both bundles are **vendored under `static/apidocs/`** with a URL and a sha256 per file (`scripts/vendor_apidocs.py --check`, run from `tests/test_apidocs.py`, which asserts that **no `src`/`href` in either page names another origin** and that every same-origin asset each page names answers 200) — ADR-0032, which also adds the one CSP directive this earned, `worker-src 'self' blob:`: ReDoc builds its search index in a Blob worker, so without it `/redoc` rendered in full and searched nothing (measured 0 hits, then 8). An **SVG favicon** (`static/favicon.svg`, served at the root by the API because `/favicon.svg` is not under `/app`) drawn for 16px — the first version was a blank tab, because an SVG comment must not contain a double hyphen and the comment in it held an em dash, a parse error nothing reports. **Accounts and bulk downloads are built-and-off and say so** (ADR-0034): one constant each in `frontend/src/lib/features.ts`, one copy of the wording, and an ordinary **enabled** `<button>` with a `popover` — not `disabled` (which hides the explanation from keyboard and screen-reader users) and not `aria-disabled` (a falsehood about a control that does have an action, which Playwright caught by refusing to click it). `/app/login`, `/app/signup`, `/app/settings` and `/app/provisions` render that explanation rather than 404ing, and `AuthNav`/`WatchButton` are no longer rendered at all, saving two `/auth/me` requests per page view — **this is a UI switch, not a security control: the auth routes are still live for anyone calling them directly**. An **About page** carries the disclaimer that was eight-point grey type below the fold, linked from the navbar and the footer. The **search guide now documents both halves of the one box** — `lib/citationforms.ts` lists 14 accepted citation shapes and the identifier each resolves to plus two documented limits, and `tests/test_citation_forms.py` runs every example through `citeparse.parse_citation`, limits included. A **copy control beside every provision** (ADR-0033) with four modes — text / citation / citation + text / link — a toggle above them and Shift/Alt/Ctrl as a per-click override; link mode writes a `text/html` flavour so it pastes as a real hyperlink labelled with the citation; **every citation and URL is computed server-side** by `lib/cite.ts` (the inverse of `citeparse.py`, unit-tested both ways) so the island holds only DOM work and the clipboard. And two CSS faults, both other people's defaults: USWDS ships **`[type="search"]` unscoped** with `border-right: none` and `float: left`, so the header box's right edge vanished into the Go button (measured `1px 0 1px 1px` before touching it); and the footer's links were underlined while the navbar's were not, now consistent. **`--sticky-h` re-measured at eight widths** after the nav grew by two items: 386px against a 352px token in the 40–64em band, corrected to 25rem. **A cacheable 401 was found and fixed** — `/api/v1/settings` was missing from `params.PRIVATE_PREFIXES`, and every settings test passed anyway because they all checked a 200. `docs/citation-index-plan.md` plans the reverse citation lookup `cites` will become, grounded in a measurement (55,659 `<ref>` in Title 16, of which **only 21.3% point into the USC**) and correcting a first draft that wrongly claimed ingest already extracts cross references. All three suites were run against the recreated compose stack at the end of Session 13 — **413 / 119 / 45** (now **474 / 185 / 74** after Session 15) — and the live stack was checked for the new headers (CSP, `X-Frame-Options: DENY`, HSTS with `includeSubDomains`) and for the diff limiter shedding with 429 + `Retry-After` after a burst of five. **Next: (1) deploy (ADR-0020, `docs/deploy.md`) — needs an IAM identity that can create EC2/IAM and a domain name; (2) Day 7 hardening.** The mirror push is finished (3,153 zips + 381 manifests + ledger, 9.70 GB, verified against the local corpus) and Session 9's `load-all` + `verify-deep` are done. Day 4 (BUILDLOG 019) is done: keyboard nav, notes/`sourceCredit` toggles, version timeline, diffs, and the heading-outline fix all landed. **Day 5 (BUILDLOG 020, ADR-0017) is done:** email+password auth (argon2, server-side sessions keyed by `sha256(token)` so logout actually revokes, double-submit CSRF), watchlist CRUD (`storage/accounts.py`/`storage/postgres_accounts.py`, a second storage module — `Repository` stays version-resolution-only), a Watch button island, a pure-SSR "My Provisions" page (`/app/provisions`) with one-click open at pinned-or-current release, and status badges that are a live `Repository.labels()` lookup rather than a copy of status at add time. **Day 6 (BUILDLOG 022, ADR-0018/0019/0020) is done:** the caching policy above, CI, the breadcrumb debt (a section now carries its own `ancestors`, so the reader's fan-out is three calls not four), login throttling (5/email and 50/IP per 15 min, 429 + `Retry-After`, a delay never a lockout) with the unknown-email timing oracle closed by a dummy-hash verify, `USC_COOKIE_SECURE` so the `Secure` flag is configuration rather than inference through a proxy, a load test (`make loadtest`), and the deploy design + runbook. Open debts: **the rate limiters are per-process state**, honest for ADR-0020's single box and wrong for a second instance (ADR-0029's recorded cost); **the CSP carries `script-src 'unsafe-inline'`** until the islands get nonces through the new Astro middleware (ADR-0030's recorded cost); **no email verification and no password reset — accounts are throwaway until email exists, decided and recorded in ADR-0019** rather than left as a gap; **the site is not deployed** (needs the mirror push finished, an IAM identity that can create EC2/IAM, and a domain); **appendix titles are unreachable by citation** — `5 U.S.C. App. 3` parses to `/us/usc/t5a/s3` and OLRC publishes nothing there (0 of 461 appendix sections use the flat form; they are `/us/usc/t5a/pl/92/463/s1` or `/us/usc/t50a/act/1917-05-18/ch15/s212`), so the API explains rather than 404s; the preview endpoint is unauthenticated and fans out per hovered citation — **now rate-limited in `frontend/src/middleware.ts` (ADR-0029)**, still unauthenticated; **USLM `<date>` renders as a block**, so dates break mid-sentence throughout the notes — one entry in `uslm.ts`'s inline set, left out of a scoped refresh; **the reader's redline drops `<ref>` links and cannot see a whitespace-only change** (ADR-0026's named costs); **the search index holds a 4,000-document smoke slice, not the corpus** — a full build was deferred; `python -m ingest.reindex_search --recreate` builds the 66k current-text index the default query reads and `--all-versions` the 490k superseded ones `?release=` needs, and until then a point-in-time search answers from current text alone (the response names the release it searched, so this is visible); the search endpoint is unauthenticated — **now throttled and input-bounded (ADR-0029)**; **a section the source publishes twice under one identifier at one release (ADR-0021) shares an OpenSearch `_id`**, so the index keeps one of the two; the diff endpoint is CPU-bound — ~0.45 rps at any concurrency, failing entirely past ~10 concurrent — and is **now rate-limited (ADR-0029, the tightest budget in the project)**, so it sheds with 429 + `Retry-After` rather than collapsing; `docs/verification/loadtest.json` predates that and has not been regenerated; **~half the API diff's cost is `@id` churn rather than legal change** — diffing the guid-stripped text is 2,220 ms → 1,172 ms and 51 → 20 ops; the *reader* no longer pays it (ADR-0026 moved the reader to a text redline), the endpoint still does, and `docs/verification/loadtest.json` is stale for `/app/diff` as a result; **accounts and bulk downloads are switched off in the reader but their API routes are untouched** — ADR-0034 is a UI decision, so `POST /api/v1/auth/signup` still works for a direct caller; **the copy column adds ~100 tab stops to a long section** and its copied text drops notes and `sourceCredit` (ADR-0033's named costs); **2.4 MB of vendored Swagger UI / ReDoc is committed**, so a security fix in either arrives only when someone bumps `static/apidocs/MANIFEST.json` (ADR-0032's named cost); **HEAD is 405 on every `/api/v1` route** (FastAPI registers GET alone), which matters once a CDN or uptime monitor is in front; `purge_login_failures` exists but nothing calls it on a schedule; **the general `/api/v1/watchlists` multi-list CRUD has no frontend UI** (only the default-list convenience endpoints the reader uses are wired to a page); a deduped fragment carries the guids of the release its text first appeared at (ADR-0007's recorded cost); `structure_nodes` is unversioned — one row per node, holding **the newest loaded release's view**; `first_release_id`/`last_release_id` bound its life, and both those and the descriptive fields are gated on `seq`, so load order doesn't decide the answer (an older load silently relabelled a `reserved` subchapter `repealed` before that gate existed). Per-release structural history is still owed; **the source sometimes publishes several elements under one `@identifier` at one release point — the reader shows every occurrence with a note rather than picking one (ADR-0021), and `sections_loaded` therefore exceeds `section_release_map` on six title-releases**; `Uslm2Parser` has no table/indent handling (Day 7); `make verify` is real (ADR-0014) and `--deep` has now been run over the whole corpus — **3,153 of 3,153 title-versions independently recounted from source, 0 source mismatches, 0 incomplete loads** (`docs/verification/database.json`); the six count mismatches it reports are the source publishing several elements under one `@identifier` (ADR-0021), left reported rather than smoothed away. **Test speed rule:** default `make test` never parses the 32 MB usc16.xml — unit tests use `tests/fixtures/usc16_slice.xml` (regenerate with `make fixtures`); full-sample tests are `@pytest.mark.slow`, run by `make test-slow`. API integration tests need a loaded database (`make dev-data`) and skip without one.

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

# python -m ingest inventory [--from-file PATH] [--no-seed]
#   Fetches uscode.house.gov/download/priorreleasepoints.htm, writes data/uscreleasepoints.json
#   ({name, date, titlesAffected, url} per RP, loadusc-xcitedb's shape), and seeds release_points
#   with real currency dates, titles_affected, and a global seq from page order.
#
# python -m ingest fetch --release <label> --title <num>
#   Downloads and unpacks one title's zip into data/releases/{label}/ (~1 req/sec, cached on disk).
#   Raises on failure — the interactive single-title path. The bulk path records and continues.
#
# python -m ingest backfill [--title N]... [--release LABEL]... [--limit N] [--plan-only]
#                           [--retry-unavailable] [--no-baseline]
#   The full corpus, resumably (ADR-0012). Plans from data/uscreleasepoints.json driven by
#   titlesAffected — 3,197 downloads, not 382×58=22,156 — with the oldest RP fetched in full
#   as the baseline a delta needs. Re-run to resume: outcomes live in data/releases/ledger.json
#   (ok / unavailable / failed), and a zip on disk with no ledger entry is re-hashed and
#   adopted, so a lost ledger costs a hashing pass rather than a re-download. Hours long and
#   interruptible; Ctrl-C saves the ledger.
#
# python -m ingest mirror {push,pull} [--bucket B] [--title N]... [--release L]...
#   S3 mirror of the corpus (ADR-0013; bucket from $USC_MIRROR_BUCKET; ops guide
#   docs/remote-ops.md). push uploads zips+inventory+manifests then the ledger LAST, so the
#   mirror never advertises files it lacks; pull fetches (a slice of) the mirror and
#   re-hashes it against the ledger — transport is aws s3 sync, trust is ours. One writer
#   rule: the ledger's writer is wherever the backfill runs; everyone else pulls.
#
# python -m ingest load-all [--title N]... [--release L]... [--limit N] [--plan-only]
#   Bulk load of the downloaded corpus (ADR-0014), ledger-driven, in inventory seq order so
#   the baseline lands before the deltas. Resume state is the DATABASE, not a second ledger:
#   `title_versions.sections_loaded` is stamped last, so a crash mid-title leaves NULL and the
#   pair is redone (load_release is idempotent). Each zip is extracted to a temp dir and
#   deleted, so the corpus never doubles on disk. `make load-all`.
#
# python -m ingest.reindex_search [--recreate] [--all-versions] [--limit N] [--skip-sections]
#   Rebuild the search indices from Postgres (ADR-0028). Normal loading keeps them in step
#   incrementally, so this is the "start over" path: after a mapping change (which needs
#   --recreate — OpenSearch will not add a field type to a live index) or over a corpus
#   loaded before search existed. Defaults to the text in force: one document per section,
#   66k of them, which is what the default query reads. --all-versions adds every superseded
#   version (490k) so `?release=` can reach back — much longer, and it buys the default
#   query nothing. Both passes stream; ingest never requires a cluster (DISABLE_SEARCH_SYNC=1).
#
# uv run python scripts/vendor_apidocs.py [--check] [--update]
#   Swagger UI and ReDoc, vendored into static/apidocs/ (ADR-0032). The site's CSP names no
#   CDN, so FastAPI's stock docs pages loaded six blocked assets and rendered blank. --check
#   recomputes each sha256 against static/apidocs/MANIFEST.json and is what
#   tests/test_apidocs.py runs; bare re-downloads the pinned versions; --update accepts new
#   hashes after a version bump. static/favicon.svg lives beside them and is served at the
#   root by main.py, because /favicon.svg is not under /app.
#
# python -m ingest verify [--deep]      (`make verify` / `make verify-deep`)
#   Shallow: recorded `sections_loaded` vs the rows `section_release_map` actually holds —
#   seconds. --deep re-parses every source file for an INDEPENDENT recount, which is the only
#   version that can catch a parser confirming its own bookkeeping. Writes
#   docs/verification/database.json. Headline metric: the dedupe ratio.
#
# python -m ingest verify-downloads [--deep]
#   Hash-dedupe over the downloaded corpus → docs/verification/downloads.json. Same title at
#   two RPs with identical bytes is reported (OLRC republished it unchanged; also the u1
#   substitution signature); two *different* titles sharing a zip fails the report, because
#   that means URL construction collapsed two addresses. --deep re-hashes from disk.
#
# python -m ingest load <xmlfile> --release <label> [--currency-date YYYY-MM-DD] [--source-url URL]
#                                                   [--source-zip PATH]
#   Parses one USLM title file into Postgres: content-hash dedupe (over the guid-stripped
#   content_key — ADR-0007), guid_map upsert, structure_nodes from the TOC pass, per-release
#   seq_in_title/parent_identifier, and a data/manifests/{release}.json provenance manifest.
#   --currency-date is only needed for a release the inventory doesn't list.
#   Example: uv run python -m ingest load samples/uslm1/usc16.xml --release 119-102not101
```

Stack: Python 3.12 + uv, FastAPI, SQLAlchemy, Alembic, lxml, Postgres 16 via docker-compose
(`db` service; `api` service builds from `Dockerfile`, UV_PROJECT_ENVIRONMENT=/opt/venv so the
dev bind mount doesn't shadow the container venv). `db/config.py` reads `DATABASE_URL` (see
`.env.example`); Alembic's `env.py` pulls the same setting and `target_metadata` from
`db.models.Base` — no separate URL to keep in sync. Node 20+ is required: the Astro
frontend (ADR-0011) landed in Session 7 and `make test-web` runs under it.

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

## Model assignment (PLAN §7)

| Workstream | Agent / mode | Model |
|---|---|---|
| Architecture decisions, schema review, resolver design | Plan mode / `Plan` subagent | **Opus 5** |
| USLM parser + ingest pipeline | Main session | **Opus 5** |
| Repo scaffold, docker-compose, Alembic, CI | Main or worktree agent | **Sonnet 5** |
| FastAPI routes + repository impl | Worktree agent | **Sonnet 5** |
| Frontend reader UI | Worktree agent | **Sonnet 5** |
| Auth + watchlist | Worktree agent | **Sonnet 5** |
| Bulk download/backfill scripts | One session writes, then runs unattended | **Sonnet 5** (no LLM at runtime) |
| Test writing, fixture generation | `general-purpose` subagent per module | **Sonnet 5** |
| Verification, PR diff review | Separate reviewer session (fresh context) | **Opus 5**; **Haiku 4.5** for lint/link/doc sweeps |
| Exploration ("where is X handled?") | `Explore` subagent | **Haiku 4.5 / Sonnet 5** |
| Build-log & ADR upkeep | End of every session, same session | any |

Rhythm per module: plan (Opus) → approve → implement in a worktree → tests pass → fresh-context
reviewer reads the diff → merge. Merge order: schema → ingest → API → web → auth.

## External source etiquette

uscode.house.gov needs no credentials, but be polite: sequential downloads, ~1 req/sec, cache
everything, descriptive User-Agent. Reuse [dreamproit/loadusc-xcitedb](https://github.com/dreamproit/loadusc-xcitedb)
for the RP inventory/downloader and [dreamproit/versions](https://github.com/dreamproit/versions)
for the temporal diff approach — don't rediscover solved problems.
