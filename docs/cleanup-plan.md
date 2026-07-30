# Cleanup plan: security, usability, and documentation debt

*Written 2026-07-30 (Opus 5) from a read-only review of the repository at commit
`3804422`, on branch `feature/search-versioned`. Every finding below was confirmed
in code — file and line references are given so each can be re-checked
independently rather than taken on trust. Scope was agreed with the user: one
comprehensive plan, phased; merge the search branch first; rework the search page
fully; clean up ADRs by index and back-pointers rather than retro-normalizing all
28 files.*

## Context

Twelve sessions of work have landed. The corpus is complete and independently
recounted, three test suites are green (verified this session: 401 Python, 78
frontend), and the architecture rules in `tests/test_architecture.py` are holding.
What has not kept pace is everything *around* the features: Session 12's search
was bolted on without the care the rest of the reader got, several security debts
recorded in ADRs were never paid, and the documentation now contradicts itself in
about a dozen places.

Two things make this urgent rather than cosmetic:

1. **Deploy is the declared next step** (ADR-0020, `docs/deploy.md`), and the
   deployed shape is currently broken and unsafe: `docker-compose.prod.yml` has
   **no OpenSearch service at all** and sets neither `SEARCH_URL` nor
   `SEARCH_PASSWORD`, so production would fall back to `https://localhost:9200`
   with a password committed to the repo. Three endpoints the ADRs each flagged as
   "must be rate-limited before the URL is advertised" still have no limit.
2. **A live authentication bypass was found during this review** that is not in any
   ADR: the per-IP login throttle is defeatable with one header.

Scope confirmed with the user: one comprehensive plan, phased; merge the search
branch to main first; rework the search page fully; ADR cleanup by index and
back-pointers rather than retro-normalizing all 28 files.

---

## Phase 0 — Merge, so this stops being a one-copy risk

`feature/search-versioned` is 12 commits of finished work with no remote
counterpart. Everything in Phase 2's search findings exists only there.

1. Commit the pending `frontend/package-lock.json`.
2. Decide `docs/ui-improvements-plan-unapproved.md` (see Phase 3 D8) and `.agents/`
   (a symlink into `.venv`; add to `.gitignore`).
3. Merge `feature/search-versioned` → `main`, push.
4. Branch `cleanup/hardening-and-hygiene` off `main`. All phases below land there.
5. Delete the three dead branches: `feature/ui-refresh-title-order` (Session 10 is
   merged), `feature/keyword-search` (superseded by `feature/search-versioned`, and
   still checked out in a worktree — release it first), and
   `origin/add-claude-github-actions-1785264278064`.

---

## Phase 1 — Security

Ordered by severity. S1–S4 are deploy blockers.

### S1. The per-IP login throttle is spoofable (HIGH, new — not in any ADR)

`docker-compose.yml:73` and `docker-compose.prod.yml:71` start uvicorn with
`--forwarded-allow-ips "*"`. In that mode uvicorn's proxy-headers middleware
returns **`x_forwarded_for_hosts[0]` — the leftmost, entirely client-supplied
value** (`.venv/.../uvicorn/middleware/proxy_headers.py:176-177`); the
reverse-scan that picks the real client only runs when trust is *not* `*`. Caddy
appends the true address, so a caller who sends their own `X-Forwarded-For` wins.

`api/auth.py:85-95` documents the exact opposite assumption. The consequence is
that `MAX_FAILURES_PER_IP = 50` (`api/auth.py:64`) is bypassed by rotating one
header — defeating precisely the credential-stuffing case it was written for — and
that `login_attempts.ip` (`db/models.py:233+`, unbounded `String`) becomes an
attacker-controlled write primitive.

**Fix**, in `deploy/Caddyfile`, inside both `handle` blocks:

```
reverse_proxy api:8001 {
    header_up X-Forwarded-For {remote_host}
}
```

Caddy *overwrites* rather than appends, so the header uvicorn reads is the real
peer regardless of the trust setting. This is the correct layer: the compose
network CIDR is dynamic, so narrowing `--forwarded-allow-ips` to a literal range is
fragile. Additionally truncate the stored value at the storage boundary in
`storage/postgres_accounts.py:record_login_failure` (45 chars covers IPv6+port) so
no migration is needed. Rewrite the `api/auth.py:85-95` comment to describe what is
actually true. Regression test: `tests/test_auth.py`, asserting that a forged
`X-Forwarded-For` does not open a fresh throttle bucket.

### S2. No rate limiting on any expensive unauthenticated route (HIGH)

Four ADRs (0016, 0020, 0024, 0026, 0028), `docs/deploy.md`, and
`docs/verification/loadtest.json` each name this; nothing implements it. The
concrete levers:

- `POST /api/v1/auth/signup` (`api/auth.py:215`) — unthrottled argon2id at
  defaults: **64 MiB and 4 threads per request**, plus a durable `users` row.
- `GET /api/v1/sections/{id}/diff` (`api/routes.py:305`) — `Diff_Timeout = 0`
  (`api/diff.py:39`) deliberately removes diff-match-patch's only runtime bound.
  Measured at ~0.45 rps, failing entirely past ~10 concurrent.
- `GET /api/v1/search` (`api/search.py:59`) — `offset` is bounded below (`ge=0`)
  but not above, so deep paging past OpenSearch's `max_result_window` both throws
  and pressures the heap.
- `GET /api/v1/labels` (`api/routes.py:244`) — `identifier: list[str]` with no
  `max_length`, fanning into one `IN (...)`.

Amplifier: every handler under `api/` is a sync `def`, so all share Starlette's
40-slot threadpool. Saturating it stalls `/health` and every read route, which
turns "expensive endpoint" into "full outage".

**Fix.** Add a `rate_limit(...)` dependency factory to **`params.py`** — the module
that already owns the shared HTTP concerns (`public_cache`, `no_store`,
`cookies_are_secure`) and is imported by every router. An in-process token bucket
keyed on `request.client.host`, trustworthy once S1 lands, returning 429 with
`Retry-After` — reusing the shape `api/auth.py:244-248` already established, so the
error surface stays uniform. Apply to signup, diff, search, labels, and the
citation parser. Bound the inputs at the same time: `le=1000` on search `offset`,
`max_length=100` on the labels list.

Per-process state is honest for ADR-0020's single box; record that as the stated
cost, alongside the note that a second instance would need shared state.

The two Astro SSR routes need their own answer, because they run on Node's single
event loop rather than a threadpool: `/app/preview` (fans out per hovered citation,
ADR-0024) and `/app/diff` (`documentDiff` synchronous, `diff/[...identifier].astro:73`).
Add `frontend/src/middleware.ts` — the file does not exist yet — with the same
bucket, applied to those two paths only.

New **ADR-0029: request identity and rate limits** covering S1 and S2 together.
They are one subject: you cannot limit by client until you can identify the client.

### S3. Open redirect and a `javascript:` sink on the auth forms (MEDIUM-HIGH)

`frontend/src/pages/login.astro:17` reads `?next` with no validation, carries it in
`data-next` (`:23`), and `:71` does `window.location.assign(form.dataset.next || …)`.
`signup.astro:13,19,69` is identical. So `/app/login?next=https://evil.example/`
is a phishing redirect off the trusted origin at the exact moment of credential
entry, and `?next=javascript:…` executes in the page's own origin.

**Fix.** Add `safeNext(value)` to `frontend/src/lib/url.ts` — accept only paths
beginning `/app/`, reject `//`, reject anything containing `:` before the first
`/`, fall back to `provisionsHref()` (which exists at `url.ts:80` and currently has
zero callers because both pages hardcode the string instead). Apply in both pages
and cover it in `frontend/tests/url.test.ts`.

### S4. OpenSearch: committed credential, disabled TLS verification, and absent from production (HIGH)

`storage/search.py:16` hardcodes `SEARCH_PASSWORD` as a default, and `:24-27`
sends admin credentials with `verify_certs=False, ssl_assert_hostname=False`. The
same literal appears three times in `docker-compose.yml` (`:33`, `:42`, `:59`).
**`docker-compose.prod.yml` has no `opensearch` service and sets neither variable**,
so a deploy today points at `https://localhost:9200` with the repo's password —
search is simply broken in production, which is worth catching before deploy for
its own sake.

**Fix.** Drop the default (raise if `SEARCH_PASSWORD` is unset when search is
enabled); add `SEARCH_VERIFY_CERTS`, defaulting to verifying and set to `false`
only for the dev stack's self-signed cert; move the dev password into `.env` /
`.env.example`; add the `opensearch` service plus both variables to
`docker-compose.prod.yml`, with a volume under `${DATA_ROOT}` and no published
port. While here, make `get_search_client()` a module-level singleton —
`api/search.py:125` builds a fresh client on **every request**.

### S5. Internal detail leaked in errors (MEDIUM)

`api/search.py:129` returns `f"Search failed: {e}"` — the raw opensearch-py
exception, carrying internal hostnames, ports and index names.
`frontend/src/pages/search.astro:26` assigns `e.message` and renders it at `:50`,
so a Node fetch failure prints `connect ECONNREFUSED api:8001` to the reader. Log
the exception, return and render a fixed sentence. (Checked and clean: FastAPI
`debug` is nowhere set, `main.py`'s handler covers `HTTPException` only and
unhandled errors fall to Starlette's bare 500, and `frontend/Dockerfile:16` sets
`NODE_ENV=production`, so there is no dev overlay in the deployed image.)

### S6. No CSP and no framing protection (MEDIUM)

`deploy/Caddyfile:48-56` sets HSTS, `X-Content-Type-Options` and `Referrer-Policy`
only. There is no `Content-Security-Policy` and no `X-Frame-Options` /
`frame-ancestors` anywhere in the repo — the whole site is frameable, and there is
no backstop under the four `set:html` sinks.

**Fix.** Add `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `object-src
'none'`, `base-uri 'self'`, `form-action 'self'`, and `includeSubDomains` on HSTS.
Note honestly in the ADR that `script-src` must carry `'unsafe-inline'` for now:
every island is `<script is:inline>` (ADR-0022's deliberate no-framework choice),
and nonces would require the Astro middleware being added in S2 — a reasonable
follow-up, not this pass. New **ADR-0030: browser security headers**.

### S7. `login_attempts` grows without bound (MEDIUM)

`purge_login_failures` exists (`storage/postgres_accounts.py:116`) and its only
caller in the repo is `tests/test_auth.py:32`. Rows clear only on a *successful*
login for that exact email; failures against never-registered addresses — the
common case under attack — are never removed. ADR-0019 names this.

**Fix.** Add a `python -m ingest purge-auth` subcommand and a cron line in
`docs/deploy.md` §6 beside the nightly `pg_dump` that ADR-0020 already
established. No new in-process machinery.

### S8. XSS sink under the search snippets (LOW, latent)

`search.astro:80` renders OpenSearch highlight fragments with `set:html`, and
OpenSearch does not escape field content — only the `<em>` wrappers are added.
Not currently exploitable, because `strip_xml_tags` (`ingest/search_sync.py:36-41`)
removes markup before indexing and entities are never decoded, so no raw `<`
reaches the index. It is one ingest change from being live and has no CSP behind
it. Escape at the boundary and mark the `<em>` wrappers explicitly. Rolled into
the Phase 2 search rework.

**Confirmed clean, for the record** (so a later pass does not re-litigate them):
no SQL injection anywhere — every query is SQLAlchemy Core/ORM, no `text()`, no
f-string SQL; **no XPath injection** — `storage/postgres.py:357` uses lxml's
parameterized binding, `root.xpath("//*[@identifier=$wanted]", wanted=identifier)`;
no header injection in the `Location:` construction (`citation.py:32-36`), the
en-dash hazard of gotcha 17 notwithstanding; session tokens are
`secrets.token_urlsafe(32)` stored as `sha256`; CSRF is verified against the
server-side session on all 8 state-changing routes with `compare_digest`; watchlist
ownership is enforced with 404-not-403; no CORS middleware; `uslm.ts` escapes every
text node and attribute; no dependency is outdated or known-vulnerable; CI uses no
secrets.

---

## Phase 2 — Usability

### U1. Rework `frontend/src/pages/search.astro` (the weakest page in the app)

Every item below is confirmed in that one 98-line file:

- **Dark mode is unreadable.** `:75` `color: #555` is ≈2.2:1 against
  `--page: #16150f`; `:80` sets `background-color: #f0f0f0` with no `color`, so
  text inherits `--ink: #e8e6e1` — near-white on near-white. Replace the hardcoded
  literals with `var(--muted)` / `var(--panel)` / `var(--link)`. This is the only
  page in the codebase that hardcodes colors instead of using the ADR-0027 tokens.
- **Wrong API base.** `:16` defaults to `http://api:8001`; every other caller
  defaults to `http://localhost:8000` (`lib/api.ts:25`, `astro.config.mjs:23`). Under
  `npm run dev` search alone silently fails. Route through **`lib/api.ts`**, whose
  own docstring claims to be the only place this app calls `/api/v1` — a rule
  `releases.astro:23` and `us/usc/index.astro:22` also break.
- **Heading order skips h2** (`:40` h1 → `:70` h3). WCAG 1.3.1.
- **No zero-results state** — "Found 0 results" plus an empty `<ul>`, with no
  suggestion to try the citation box, which is exactly where that reader belongs.
- **`?release=` has no UI.** `:8` reads the param and `:44` round-trips it, but
  nothing lets a reader choose one, so ADR-0028's headline feature — search the law
  as of a release point — is unreachable from the interface. `?date=` is never
  passed at all. Reuse the existing `ReleasePicker.astro` pattern.
- **`SearchResponse` / `SearchResultItem` / `SearchSnippet` are missing from
  `lib/types.ts`**, which is why `:68` and `:79` are `any`.
- Page size hardcoded to 20 in three places (`:17`, `:89`, `:91`) against an API
  `limit` that is a parameter. Pagination `:87` is a `flex` row with no wrap.
- Imports the layout as `Layout` where all 12 other pages use `Base`.
- **No link to `/app/search` in `SiteHeader.astro:27-39` or `SiteFooter.astro:17-25`** —
  it is reachable only by submitting the header form.
- **Zero test coverage** — no Vitest, no e2e, for the newest page. Add both.

### U2. `<date>` renders as a block (one line, largest surface)

`INLINE_TAGS` at `frontend/src/lib/uslm.ts:97-105` holds only
`i, b, sub, sup, span, inline, a`. `date` is in none of the four tag maps, so it
falls through to the `<div>` fallback at `:165` and breaks dates mid-sentence
throughout every notes block in the corpus. Add `date: "span"`, and add the test
in `frontend/tests/uslm.test.ts` whose absence is why this survived.

### U3. Pages that 500 instead of showing an error

- `releases.astro:23-27` does a bare `fetch` then `await response.json()`; a
  non-200 becomes `.map is not a function`.
- `index.astro:7` calls `fetchTitles()` unguarded.

Route both through `lib/api.ts` and the existing `ErrorPage.astro`, which
`us/usc/[...identifier].astro:64-73` and `goto.astro:81-113` already use well.

### U4. Focus and announcement after client-side mutation

`WatchButton.astro:116,136` call `showOnly(...)`, hiding the focused button and
revealing a different one — focus falls to `<body>`. Its `statusEl` (`:43`) has no
`role="status"`, so the failure message at `:72-75` is never announced.
`RemoveWatchItem.astro:37` does a full `window.location.reload()`. Move focus to
the newly revealed control, add the live region, and replace the reload with an
in-place removal.

Also: `signup.astro:33` uses `usa-hint`, which `site.scss:33-53` never
`@forward`s — the "At least 8 characters" hint renders unstyled. And neither auth
form disables its submit button in flight (`login.astro:57-78`), so a double-click
double-posts.

### U5. Extract the three duplications

- The **compare-two-versions form** is duplicated verbatim, ~29 lines each, in
  `versions/[...identifier].astro:107-135` and `diff/[...identifier].astro:136-165`
  — same classes, same `id="from"`/`id="to"`. Extract `DiffPicker.astro`.
- **`csrfToken()`** is byte-identical in `WatchButton.astro:61-64` and
  `RemoveWatchItem.astro:25-28`.
- The **auth form and its fetch handler** differ between `login.astro` and
  `signup.astro` only in endpoint, one `minlength`, and hint text.

### U6. `/app` is spelled out in seven places outside `url.ts`

`lib/url.ts:2` states architecture rule 5. Violations: `CitePreview.astro:132`,
`goto.astro:120` (where `gotoHref()` already exists at `url.ts:86`),
`diff/[...identifier].astro:136`, `versions/[...identifier].astro:107`,
`login.astro:17,71`, `signup.astro:13,69`, `provisions.astro:35`.

One of these is an actual bug, not just style: **`CitePreview.astro:132` builds
`/app/preview${identifier}` without the percent-encoding** that `url.ts:41-43`
applies for gotcha 17's en dash — so hovering a citation in any of the 5,697
sections whose number contains U+2013 requests a malformed URL. Add `previewHref()`
and `diffHref()` to `url.ts`, use `provisionsHref()` and `gotoHref()`, and make
`titleSortKey` (`url.ts:121`) module-private.

### U7. HEAD is 405 on every `/api/v1` route

Confirmed at the framework level: Starlette auto-adds HEAD
(`starlette/routing.py:233-234`), but FastAPI's `APIRoute` bypasses that —
`fastapi/routing.py:1032-1034` sets `route.methods` from the given methods only,
and dispatch 405s at `:1513-1514`. `citation.py:39,51` gets this right with
`api_route(..., methods=["GET", "HEAD"])`; the machine surface does not. ADR-0018
flags it as needing a fix before a CDN or uptime monitor goes in front — which
Phase 1's deploy work makes imminent.

### U8. Dead code

`fetchDiff` (`lib/api.ts:156`, whose own docstring admits "the page it was written
for stopped calling it") and `fetchToc` (`:92`) have zero callers. `web/` contains
nothing but four `.pyc` files from the Jinja reader retired in BUILDLOG 014 —
`tests/test_architecture.py:82` still forbids importing it, so the ghost is
enforced while the corpse is unburied. `main.py:61-62` has a module-level import
sitting after five `include_router` calls, marking exactly where search was bolted
on; move it to the import block.

---

## Phase 3 — Documentation and repo hygiene

### D1. ADR index and template

`docs/adr/` has 28 files, no `README.md`, no template. Add
`docs/adr/README.md` — number, title, status, and the supersession chains — and
`docs/adr/0000-template.md`. Do **not** retro-normalize the four existing header
formats; the history is the walkthrough.

### D2. Back-pointers, which are currently one-directional

Annotate the amended ADRs, which today only ever point forward from the amender:
**0009** (mechanism replaced by 0010; it still describes the retired Jinja reader),
**0016** (reader half replaced by 0026), **0006** (caveat closed by 0008), **0017**
(amended by 0019). Mark **0002/0004** as carrying an unmet promise — both say
`Uslm2Parser` reaches parity "by Day 7", which has not happened. Add the
smoke-slice caveat to **0028**: it describes an index maintained over the corpus,
while the live index holds ~4,000 documents. That caveat exists only in CLAUDE.md.

### D3. README is stale by three sessions and has a broken link

`README.md:59` links to `docs/adr/0007-content-dedupe-on-guid-stripped-content-key.md`,
which does not exist (the file is `0007-dedupe-on-guid-stripped-content.md`) — the
only broken relative link in the repo. `README.md:41-43` claims "271 Python tests
and 42 frontend tests"; the true figures, re-run this session, are **401 / 78 / 44**.
The Status section stops at BUILDLOG 023 and never mentions Sessions 10, 11 or 12.

### D4. Documents that contradict each other

- **PLAN §6 and §8** still propose "Fly.io or Render … or a Hetzner/DO VPS … with
  Cloudflare in front"; ADR-0020 chose EC2 + Caddy and excludes a CDN. Days 2–6
  carry no completion marks although only Day 7 remains.
- **`docs/remote-ops.md` §7** still frames `pg_dump` as "Session 8's call to
  record"; ADR-0020 §7 and `docs/deploy.md` §6 answered it.
- **CLAUDE.md contradicts itself on `make verify`** — the Commands block says
  "(TBD — stub, exits 1)" while the status paragraph says it is real.
- **PLAN §2/§5 and ADR-0009** still describe `web/` as a live layer.

### D5. `make verify` cannot be a gate, by construction

`ingest/verify.py:112-113` defines `sound` as `not count_mismatches and not
source_mismatches`, and `ingest/__main__.py:475` exits 1 unless sound. The
committed `docs/verification/database.json` has **`"sound": false`** — driven
entirely by the six count mismatches that **ADR-0021 explicitly accepted** as the
source publishing several elements under one `@identifier`. So a perfectly loaded
corpus reports failure, which means the project's own verification gate is
permanently red and a real regression would be indistinguishable from the expected
six. Classify ADR-0021 mismatches as accepted, and fold `incomplete_loads` into
soundness where it belongs.

### D6. Missing and stray artifacts

- **`docs/verification/downloads.json` does not exist** although ADR-0012,
  CLAUDE.md, GETTING-STARTED.md and `docs/remote-ops.md` §5 all promise it and two
  code paths produce it. Run `python -m ingest verify-downloads` and commit it —
  documentation duty 5 says verification artifacts are committed.
- **`docs/ui-improvements-plan-unapproved.md`** is untracked, one `git clean` from
  gone. Its theme-toggle item was superseded by ADR-0027 the same day, and its
  "18rem sticky stack" figure conflicts with ADR-0027's measurement. Two items are
  still live and worth keeping: the smart-sticky-header (see U9) and the
  monolithic-SCSS refactor. Fold those two into a tracked `docs/backlog.md` and
  delete the file.
- `make shots` covers home/TOC/section/demo only — nothing for search, the citation
  box, the hover preview, or dark mode, which are the newest features.

### D7. Repo hygiene

- **`.gitignore` unanchored directory patterns.** The `/lib/` fix from BUILDLOG 019
  is correctly in place (`:17-20`, verified with `git check-ignore`), but the same
  class of bug is still latent elsewhere: **`parts/` (`:22`) is the sharpest — that
  is a US Code domain word** — plus `build/`, `downloads/`, `var/`, `target/`
  (USLM 2.x uses `<target>`), `cover/`, `instance/`, `env/`. Anchor them all.
- ~1.8 MB of untracked logs in the repo root (`mirror-session9.log` alone is
  987 KB); `web/__pycache__/`; a stale `frontend/dist/` built before search existed.
- Add `.agents/` to `.gitignore` — it is a symlink into `.venv`.

### U9 (deferred, recorded not done)

`--sticky-h: 18rem` between 40em and 64em (`site.scss:106`) permanently occupies
~37% of a landscape tablet viewport, and `scroll-margin-top` reserves 296px above
every anchor jump. Below 40em the mitigation is real and well-engineered
(`site.scss:319-331`). This is the largest remaining layout cost and the subject of
the surviving half of the unapproved UI plan — worth its own session, not this one.

---

## Phase 4 — The gates that would have caught all of this

Nothing in CI would have caught the search page's `any`s, its wrong API base, or
its contrast failures.

- **ruff**: `.ruff_cache/` exists on disk but ruff is in neither
  `[dependency-groups].dev` nor `[tool.ruff]` — someone lints ad hoc with unpinned
  defaults. Add both, plus `make lint`.
- **Type checking**: `@astrojs/check` and `typescript` are installed but
  `astro check` / `tsc --noEmit` appears in no npm script and no CI step. Add
  `npm run check` and `make typecheck`.
- **CI**: add lint and typecheck jobs. Set `DISABLE_SEARCH_SYNC=1` on `make ci-data`
  — `tests/conftest.py:16` sets it for pytest only, so the CI data load currently
  attempts an OpenSearch connection with no cluster present, swallowed as a warning
  after a connect timeout on every load.
- **`make test-all`** (`Makefile:70-72`) omits `test-e2e` although all three suites
  are documented as required.
- **`frontend/package.json`** ships `typescript`, `sass` and `vitest` in
  `dependencies`, so they land in the production image. Move to `devDependencies`.

---

## Verification

Per phase, not just at the end:

| What | How |
|---|---|
| S1 spoofing closed | New test in `tests/test_auth.py`: a forged `X-Forwarded-For` reuses the same throttle bucket. Then `make dev-all` + `curl -H 'X-Forwarded-For: 1.2.3.4'` against `/api/v1/auth/login`. |
| S2 limits | New `tests/test_rate_limit.py`; then re-run `make loadtest` and confirm `/diff` now sheds load with 429 + `Retry-After` instead of collapsing. Regenerate `docs/verification/loadtest.json` — it is stale for `/app/diff` anyway since ADR-0026 moved that work off the API. |
| S3 open redirect | `frontend/tests/url.test.ts` cases for `//evil`, `https://evil`, `javascript:`, and a valid `/app/...`. |
| S4 prod search | `docker compose -f docker-compose.prod.yml config` resolves; bring the stack up and hit `/api/v1/search?q=conservation`. Confirm no credential remains in tracked files (`git grep Usc0deSearch`). |
| S6 headers | `curl -I` against `make dev-all` for CSP, `X-Frame-Options`, HSTS. |
| U1 search | New Vitest + a Playwright spec in `frontend/tests/e2e/`; `make shots` at 375/1280 in both themes to confirm contrast. |
| U2 `<date>` | Failing-first test in `frontend/tests/uslm.test.ts`. |
| U7 HEAD | `curl -I` each `/api/v1` route family; assert 200 in `tests/test_api.py`. |
| D5 verify gate | `make verify` exits 0 on the current corpus; a deliberately corrupted row still exits 1. |
| Everything | `make test` (401+), `make test-web` (78+), `make test-e2e` (44+), `make lint`, `make typecheck` — all green, all in CI. |

**Documentation duties** (CLAUDE.md, non-negotiable): ADR-0029 (request identity
and rate limits) and ADR-0030 (browser security headers) written as the work lands;
one BUILDLOG entry for the session; CLAUDE.md's status paragraph and open-debts
list updated to reflect what these phases close and what they deliberately leave
(U9, `Uslm2Parser` parity, email verification and password reset, `<ref>` links in
the reader redline).

## Out of scope

Day 7's `Uslm2Parser` table/indent parity — confirmed still absent
(`ingest/uslm2.py` is 84 lines, and the gap is end-to-end: `list`/`listItem`/
`listContent` appear in none of `uslm.ts`'s tag maps either, so a 2.x list renders
as nested `<div>`s). Email verification and password reset, decided as accepted
debt in ADR-0019. The actual deploy, which this work unblocks but does not perform.
