# The reader as a progressive web application — spec and agent plan

**Status:** plan, 2026-09-02. Nothing in this document is built. It says what installing the
reader on a phone requires, how each requirement meets the site as it is, what the offline copy
may and may not promise, which ratchets the work trips, and how to split it across agents.

**Asked:** plan in detail converting the site into a progressive web application that can be
launched from a mobile device, with a multi-agent implementation plan and an assessment of which
agents can run on Opus and which need Fable-level coding.

---

## 1. What "installable" requires, against what exists

Installation on a phone means the browser offers "Add to Home Screen" (iOS, Safari 16.4+) or an
install prompt (Android, Chrome) and the result opens without browser chrome. The requirements,
and where the site stands on each (file:line at `93ba5fa`):

| Requirement | State | Gap |
|---|---|---|
| Served over HTTPS | `uscode.linkedlegislation.org`, Let's Encrypt (ADR-0020) | none |
| A web app manifest linked from every page | none; `frontend/src/layouts/Base.astro:118-160` carries no `<link rel="manifest">` | write it, serve it under `/app/`, link it |
| Icons: 192 and 512 px PNG, one `maskable`; iOS `apple-touch-icon` 180 px | only `static/favicon.svg`, root-absolute and served by FastAPI (`main.py:204-217`) | render PNGs from the SVG, reproducibly |
| `name`, `short_name`, `start_url`, `scope`, `display`, `theme_color`, `background_color`, `id` | none | in the manifest |
| `<meta name="theme-color">` | absent; the brand primary is `#31509d` (`site.scss:116`) | add, and keep it in step with the theme toggle |
| A service worker with a `fetch` handler | none; `deploy/Caddyfile`'s CSP already carries `worker-src 'self' blob:` for ReDoc | write it, serve it at `/app/sw.js`, register it |
| A same-origin script to register it | every island is `<script is:inline>`; `script-src 'self' 'unsafe-inline'` | one external file under `public/`, so it costs no inline bytes and needs no `'unsafe-inline'` |
| An offline response for a navigation the network cannot answer | none; a network failure is the browser's error page | a fixed `/app/offline` page, precached |
| Viewport and safe areas for a notch in standalone display | `width=device-width, initial-scale=1` (`Base.astro:121`); no `viewport-fit`, no `env(safe-area-inset-*)` anywhere | add both, on the sticky bar and the footer |

iOS shows no prompt: the reader uses Share → Add to Home Screen, which reads the manifest for the
name, icon and display mode since 16.4 and the `apple-touch-icon` link for the icon before. Android
Chrome shows its prompt when the manifest meets the criteria above and a service worker is
registered. Neither platform is affected by `robots.txt`'s `Disallow: /` or the crawler 403
(ADR-0037, ADR-0073): an installed app is the same browser with the same user agent.

## 2. The contract for the offline copy

The reader's whole point is *which* text: a provision at a release point. An installed reader that
shows a section without saying which release point it is from, or shows a superseded release point
as if it were current, is worse than one that shows nothing. The service worker's rules follow
from ADR-0018, which already sorts every response into three classes by its `Cache-Control`:

| Origin says | Meaning | Service worker does |
|---|---|---|
| `public, max-age=31536000, immutable` — a pinned release point, or a hashed `/app/_astro/*` asset | can never change | **cache-first**: serve the copy, fetch nothing |
| `public, max-age=300` — an unpinned or `?date=` page, a TOC, the front page, a versions page | the answer moves when a release point loads | **network-first**: fetch; on failure serve the copy **only if one exists and only with the offline banner** (§2.1) |
| `private, no-store` — `/app/provisions`, login, settings, a 429 | per-user or an error | **network-only**, never stored |
| `/app/preview/*`, `/api/v1/*` (the two islands that fetch), `/app/goto` | live lookups | **network-only** |

The worker reads the header off the response it is about to store, so the rule is ADR-0018's and
lives in one more place — Python (`params.py:162`), TypeScript (`lib/cache.ts:23`) and the worker
— with the same test shape each time. A response with no `Cache-Control` (the `public/` files the
Node adapter serves bare, `serve-static.js:80-82`) is treated as `max-age=300`.

### 2.1 The banner

A page served from the cache while the network is unreachable must say so, without JavaScript,
before anything else on the screen. The worker rewrites the cached HTML as it serves it — one
string replacement, `<html` → `<html data-offline-copy="2026-09-01T06:41Z" data-offline-release="119-102not101"` — and a rule in `site.scss` draws a banner from the attribute: *Offline
copy, saved 1 September 2026, release point 119-102not101. The site may have changed since.* The
release point is read from the page's own `X-Release-Point` header at store time. No script runs,
so the banner is there on the first paint and in the accessibility tree, and it is not there on a
page the network answered.

### 2.2 Saving a section on purpose

The worker never pre-fetches statute: the corpus is 25 M reader pages behind `?release=` and the
reader chooses what to keep. Each section page gets a **Save for offline** control beside the copy
control (ADR-0033), an island that asks the worker to store the page at its **served-from release
point** — `?release=119-102not101`, the label `ReleaseContext` already prints — rather than at the
unpinned URL the reader arrived on. A saved copy is therefore a pinned page, `immutable` under
ADR-0018, and can never be stale: it is the text at that release point forever, and the banner says
which. The saved list is the Cache Storage's own key list, read by `/app/offline` and by the
control's own state (saved / not saved), with a remove action. Nothing about it is per-account, so
it works with accounts off (ADR-0034).

### 2.3 What is not promised

- **No offline search, no offline hover previews, no offline version history** beyond the saved
  pages themselves: those are live lookups and stay network-only. A saved section's cross-reference
  links work offline only where the target is also saved; the preview card renders its existing
  "Preview unavailable" state (ADR-0041).
- **No background sync, no push.** Nothing on the site changes on a schedule a reader would want
  to be woken for, and a push subscription is a per-user record the site does not keep.
- **No pre-caching of the front page's title list or any TOC.** They are `max-age=300` pages; a
  reader who opened them while online has them under the network-first rule, with the banner.

## 3. Design

### 3.1 The manifest — `frontend/public/manifest.webmanifest`, served at `/app/manifest.webmanifest`

```json
{
  "id": "/app/",
  "name": "United States Code",
  "short_name": "US Code",
  "description": "Any provision of the US Code, at any release point.",
  "start_url": "/app/",
  "scope": "/app/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#31509d",
  "lang": "en-US",
  "icons": [
    { "src": "/app/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/app/icons/icon-512.png", "sizes": "512x512", "type": "image/png" },
    { "src": "/app/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
```

`scope` is `/app/` because everything the reader serves is under `base: "/app"`
(`astro.config.mjs:57`); the API and the citation redirector at `/us/usc/…` are outside the app,
and a citation link opened from a saved page leaves standalone display for the browser, which is
the right behaviour for a URL the app does not own. `display: standalone` on iOS means no back
button: the reader's own chrome — breadcrumb (ADR-0043), section bar, `u` / `[` / `]` — is the
navigation, and the dead-end pages already say where else to go (ADR-0065). `background_color` is
the light `--page`; the splash is drawn before the theme bootstrap runs.

`Base.astro` gains `<link rel="manifest" href="/app/manifest.webmanifest">`,
`<link rel="apple-touch-icon" href="/app/icons/apple-touch-icon.png">`, and two
`<meta name="theme-color">` — one per theme, selected by the `data-theme` the bootstrap stamps,
which needs the toggle to update the meta's `content` (three lines in `ThemeToggle.astro:61`).
`viewport` gains `viewport-fit=cover`.

### 3.2 Icons — `scripts/icons.mjs`, `docs/verification/icons.json`

Four PNGs rendered from `static/favicon.svg` by the pre-installed Chromium through Playwright
(`page.setContent` with the SVG at the target size, `page.screenshot`), the maskable one on a
`#31509d` field with the glyph inside the safe zone (80% of the canvas). The script writes the
files to `frontend/public/icons/` and the artifact records each file's size and sha256, the
pattern `scripts/fonts.py` set (ADR-0052): reproducible, and a test asserts the files on disk match
the artifact.

### 3.3 The service worker — `frontend/scripts/build-sw.mjs` → `dist/client/sw.js`

Not a page under `src/pages/`: a `.ts` endpoint would be server-rendered per fetch, pass through
the middleware, and count as a reader route for the guide ratchet (`guide.test.ts:104-127` walks
`.ts` files too). Not a hand-written `public/sw.js` either: the precache list is the hashed
`/app/_astro/*` asset names, known only after `astro build`. A post-build step reads
`dist/client/_astro/`, `dist/client/fonts/` and `dist/client/uswds/`, and writes `sw.js` from a
template with the list and a build id (the `__COMMIT_HASH__` the config already computes,
`astro.config.mjs:15-27`). `package.json`'s `build` becomes `astro build && node
scripts/build-sw.mjs`; `frontend/Dockerfile:27` runs the same command. The worker is served by the
Node adapter from `dist/client/` as any static file, at `/app/sw.js`, whose default scope is
`/app/` — no `Service-Worker-Allowed` header needed.

The worker:

- **install:** precache the app shell — every `/app/_astro/*` file, the six fonts (125,720 bytes,
  `docs/verification/fonts.json`), the 16 USWDS icons, `/app/offline`, the manifest and the icons.
  Measured, the shell is under 400 KB; the artifact records it and a test bounds it.
- **activate:** delete caches from other build ids, `clients.claim()`.
- **fetch:** the three rules of §2, chosen by the *stored* response's `Cache-Control`, with
  navigation preload on so a network-first page does not wait for the worker to boot. `POST` and
  anything with a `Cookie`-varying response are ignored.
- **message:** `save` / `forget` / `list` from the Save-for-offline island, against a named
  `saved-pages` cache that survives activation.
- **update:** `skipWaiting()` on install. Pages are network-first and assets are hashed, so a new
  worker can take over at once with no skew: a new page references new asset names, which miss
  the old precache and fetch from the network.

Registration is `frontend/public/register-sw.js`, loaded from `Base.astro` with `defer`, five lines
guarded on `'serviceWorker' in navigator` and `location.pathname.startsWith('/app')`. An external
same-origin script is covered by `script-src 'self'` without `'unsafe-inline'` and, being in
`public/`, adds nothing to any route's inline budget (`docs/js-budgets.json`, where the 18,500-byte
routes have 200 bytes of headroom by construction).

### 3.4 `/app/offline` — `frontend/src/pages/offline.astro`

A fixed page with no data (ADR-0053's property): what offline means on this site, the saved
sections listed from the worker by a small island (or "nothing saved yet"), and the one search box
the chrome already has, which says it needs the network. It is what a navigation gets when the
network fails and no copy exists. As a new reader route it wants: a guide chapter's
`covers.routes`, a `docs/a11y/routes.json` entry, a `docs/js-budgets.json` key, a
`docs/ia-map.md` row, and a `scripts/screenshots.mjs` entry.

### 3.5 Save for offline — `frontend/src/components/SaveOffline.astro`

An island on the section page, next to `CopyColumn`: one button, state read from the worker on
mount (`saved` when the pinned URL is in `saved-pages`), `Save` stores the page at its served-from
release point, `Remove` deletes it. It fetches the pinned URL itself and hands the response to the
worker so the copy is the pinned page even when the reader is on the unpinned URL. Absent when
`navigator.serviceWorker` is undefined, so a browser without workers sees no dead control. Its
measured size raises `/app/us/usc`'s budget alone (44,000 today).

### 3.6 Safe areas and standalone chrome

`viewport-fit=cover` lets the page under the notch; `padding-left/right: env(safe-area-inset-*)`
on `.sectionbar`, `.navbar`, the footer and the offline banner keeps text out of it, and
`padding-bottom: env(safe-area-inset-bottom)` on the footer clears the home indicator. `--sticky-h`
is unchanged: the insets are horizontal except at the bottom. `docs/verification/mobilebar.json`
(`make mobilebar`) is the number to re-check, at 320 and 375.

### 3.7 CSP, Caddy, deployment

The Caddyfile's CSP needs `manifest-src 'self'` added for clarity (today `default-src 'self'`
covers it) and nothing else: `worker-src 'self'` is present, `img-src 'self' data:` covers the
icons, `connect-src 'self'` covers the worker's fetches. `/app/sw.js`, `/app/manifest.webmanifest`
and `/app/icons/*` reach the frontend through the existing `/app*` handler. No `Cache-Control` is
set on `public/` files today; the worker script is capped at 24 hours by the platform regardless,
and the manifest is re-read on update checks. Nothing in `deploy/` changes: the image build runs
the new build step, the box pulls the image.

## 4. Ratchets the work trips, and what each costs

| Ratchet | Trips on | Answer |
|---|---|---|
| Guide routes (`guide.test.ts:179-196`) | `/app/offline` | chapter 11, or a section of chapter 02 with `covers.routes` |
| Guide ADRs (`guide.test.ts:198-212`) | ADR-0078 | the same chapter's `covers.adrs` |
| JS budgets (`jsbudget.test.ts:137-153`) | `offline.astro`; `SaveOffline` on `/app/us/usc`; the theme-color lines in `ThemeToggle` (on every route) | new key; raise `/app/us/usc` by the island's size; the toggle's ~120 bytes fit the 200-byte headroom on every 18,500 route, measured before merge |
| a11y matrix (`docs/a11y/routes.json`, 343 scans) | `/app/offline`; the banner as an interactive state on a section page | one route entry; one `states` id with a setup that fakes the attribute |
| `make shots` overflow (WCAG 1.4.10) | `/app/offline`; the banner at 320 px | `PAGES` entry; the banner wraps |
| Sticky geometry (`sticky.spec.ts`) | the banner if it were sticky | it is in flow above the header, not pinned |
| Fonts test (`fonts.test.ts`) | nothing — no new `<link>` to an external host | — |
| Footer hrefs (`chrome.spec.ts:369-396`, eleven exact) | a footer link to `/app/offline` | add it to the Site group and the list, or reach the page from the banner and the Save control only |
| Contrast (`scripts/contrast.py`, 20 pairs) | the banner's colours | two new token pairs in `color-pairs.json`, both themes |
| Theme spec (`theme.spec.ts:91,176`) | the head bootstrap if edited | it is not edited; the meta update is in the toggle |

The guide's scenario vocabulary (`frontend/scripts/remark-scenario.mjs`, `tests/e2e/guide.spec.ts`)
has no way to take the browser offline. A step `offline: true` mapping to Playwright's
`context.setOffline(true)` is the addition that lets chapter 11's claims be executable, and the
demo video can then show a saved section opening with the banner.

## 5. Tests and verification

- **Vitest:** the manifest parses, its icon paths exist under `public/icons/` with the sizes the
  PNG headers say, `start_url` and `scope` begin with `/app/`; `docs/verification/icons.json`
  matches the files; the worker template's rule table matches `lib/cache.ts`'s three constants.
- **Playwright, a new `pwa.spec.ts`:** the worker registers and reaches `activated`; the precache
  holds every `/app/_astro/*` the page references; a pinned section is served from the cache with
  the network blocked (`context.route` aborting everything); an unpinned page is fetched from the
  network when it can be and served with the banner when it cannot; `no-store` pages are never in
  any cache; `/app/offline` renders offline; Save stores the pinned URL and Remove drops it.
- **Artifacts:** `docs/verification/pwa.json` — manifest fields, icon hashes, precache count and
  bytes, the worker's byte size — the ratchet a later change to the shell has to update on purpose.
- **Live:** `deploy/watchdog.sh` is unchanged; a smoke line in `docs/deploy-status.md` fetches
  `/app/manifest.webmanifest` and `/app/sw.js` through the proxy and checks their content types.

## 6. Phases and the agent plan

Six agents, four phases, two worktrees at a time. The main session holds the plan, merges in
order and runs the full suites between merges.

| Phase | Agent | Produces | Depends on | Model | Why this model |
|---|---|---|---|---|---|
| P1 | **manifest-and-icons** | manifest, `scripts/icons.mjs`, `icons.json`, the four PNGs, `Base.astro` head lines, `ThemeToggle` meta update, `viewport-fit`, safe-area CSS, `mobilebar.json` re-measured | nothing | Opus 5 | well-specified; every file it touches has a test or an artifact that says when it is right |
| P1 | **guide-and-harness** | chapter 11 skeleton with `covers`, the `offline:` scenario step in `remark-scenario.mjs` and `guide.spec.ts`, `pwa.spec.ts` skeleton, `routes.json` / `js-budgets.json` / `screenshots.mjs` / `ia-map.md` entries for `/app/offline` | nothing (a stub `offline.astro` so the ratchets pass) | Opus 5 | mechanical against known ratchets; the prose follows Documentation duty 7 |
| P2 | **service-worker** | `build-sw.mjs`, the worker template, `register-sw.js`, `offline.astro` in full, the banner CSS and its two token pairs, `pwa.json`, the Dockerfile/`package.json` build line | P1 merged (icon paths, the offline page's chrome) | **Fable 5.1** | the worker encodes the never-stale contract across three response classes, navigation preload, cache naming across deploys, base-path and scope, and CSP — a wrong rule here is a silently superseded statute on a phone, the failure class ADR-0018 exists to prevent, and it cannot be caught by the existing suites until `pwa.spec.ts` exists |
| P3 | **save-offline** | `SaveOffline.astro`, its messages to the worker, the saved list on `/app/offline`, the `/app/us/usc` budget | P2 merged | Opus 5 | an island in the established pattern (ADR-0033's copy control), against a worker whose message API P2 fixed |
| P4 | **tests-and-adr** | `pwa.spec.ts` in full, the Vitest tests, chapter 11's scenarios, the demo scene, ADR-0078, `docs/deploy-status.md`'s smoke line, BUILDLOG | P3 merged | Opus 5 | the assertions are enumerated above; the writing is descriptive |
| Review | **reviewer** | a fresh-context read of P2's diff against §2 before P3 starts; a second read of the whole branch before the PR | — | **Fable 5.1** | the review has to reason about race and ordering: a navigation preload racing the worker, a page stored under one build id and served under another, a `Vary: Cookie` response the rule table must never store |

P1's two agents run in parallel worktrees; P2 starts when both are merged; P3 and P4 are
sequential. Each phase is one PR with `make test`, `make test-web`, `make test-e2e` and
`make test-a11y` green, as every session here has run them.

### 6.1 Opus or Fable

Four of the six agents can be Opus 5: their work is bounded by files that already have tests,
artifacts and a documented pattern to copy, and the failure of a wrong line is loud (a budget, a
ratchet, a screenshot diff). Two want Fable 5.1, and for the same reason: the worker's fetch
handler and its review are the places where a wrong line is *quiet*. A cached page served past
its release point looks exactly like a correct one, which is the property ADR-0018 was written
about, and the suites that would catch it are the ones P2 is writing. The judgement is about the
failure mode, not the size of the diff — P2 is perhaps 300 lines.

### 6.2 Effort

P1 half a session each; P2 one session plus the review; P3 half; P4 one. Five sessions, four
PRs, one ADR, one guide chapter.

## 7. What is deliberately left out

- **Web Push and Background Sync** — no per-user state to notify about while accounts are off.
- **Pre-caching statute** beyond what the reader saves — the corpus is too large and the contract
  in §2 forbids storing what is not pinned.
- **A `display_override` to `minimal-ui`** — unsupported on iOS, which is where the missing back
  button is.
- **Periodic update checks in the page** — the platform's 24-hour worker check and the hashed
  assets are enough at this deploy cadence.
- **Nonces for the inline islands** — ADR-0030's recorded cost, unchanged; the registration script
  is external precisely so it does not add to it.
