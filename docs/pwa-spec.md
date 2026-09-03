# Progressive web app — implementation spec for aih/uscode-redesign

**Status:** spec written 2026-09-02, from a three-agent research session (session 95, BUILDLOG):
a survey of the frontend serving surface, a UX/chrome inventory, and an external practice brief
on 2026 installability. Phase P1 is implemented (ADR-0079, branch `c5-pwa-p1`, merged), so is
P2 (ADR-0080, branch `c5-pwa-p2`, merged), and so is P4 (ADR-0081, branch `c5-pwa-p4`).
Implementing sessions update this line and the [§ Status](#status) table as waves land.

The reader becomes installable as a desktop and mobile app — a web app manifest, app icons, a
service worker with an offline fallback, and behavior adjustments for a standalone window — while
the site keeps working unchanged in a browser. The app experience stays what the site already is:
searching, reading, and navigating the Code, with almost no new chrome (one install row in the
More menu is the whole addition). Everything ships under `/app`, so Caddy, FastAPI, and the API
surface are untouched.

Scope, from the user's request (2026-09-02):

- Installable as either a desktop app or a mobile app; simple, uncluttered, focused on
  searching, reading and navigating the legal content.
- The site continues to work well as it is; installation is an additional possibility, not a
  migration.

## What was found

Facts from the research session that shape the design. Repo citations are to the working tree at
`06caaf5`; external claims carry their source.

**Serving surface.**

1. `frontend/astro.config.mjs` sets `base: "/app"`, `output: "server"`, Node standalone adapter
   (lines 46-49). Everything in `frontend/public/` is served at `/app/<path>` by the adapter
   (`@astrojs/node` `serve-static.js:64-68`) — so a worker script at `frontend/public/sw.js`
   surfaces at `/app/sw.js` and gets default scope `/app/` with no `Service-Worker-Allowed`
   header. Only `/app/_astro/*` gets `Cache-Control: immutable` from the adapter; other public
   assets get ETag/Last-Modified defaults, which is enough for worker-script freshness.
2. `deploy/Caddyfile` routes `handle /app*` to the frontend (lines 148-156); everything else to
   FastAPI. A root-level `/manifest.webmanifest` or `/sw.js` would reach FastAPI and 404 — both
   files must live under `/app`. Caddy needs no change.
3. The CSP (`deploy/Caddyfile:230`) already permits everything required: `worker-src 'self'
   blob:` governs service-worker registration, `manifest-src` falls back to
   `default-src 'self'`, `connect-src 'self'` covers the worker's same-origin fetches.
4. There is no PWA infrastructure today: no manifest, no worker, no `theme-color` meta, no
   `apple-touch-icon`, no icon of any kind in `frontend/public/` (the favicon is FastAPI's, at
   `static/favicon.svg`, because `/favicon.svg` is not under `/app` — `main.py:220-233`).
5. All client JS is `<script is:inline>` — zero framework islands, zero client bundle — and
   every byte is ratcheted by `frontend/tests/jsbudget.test.ts` against `docs/js-budgets.json`.
   The 18,250-byte floor is `Base.astro`'s component graph, so anything added to `Base.astro`
   raises all 23 route budgets.
6. `Base.astro:176-193` stamps `data-theme`/`data-density` pre-paint from
   `localStorage["usc-theme"]`/`["usc-density"]`; `Base.astro:195-241` toggles
   `target="_blank"` on `a[data-newtab]` from `localStorage["usc-linktarget"]`.
7. The reader's HTML responses carry ADR-0018 cache headers but not `X-Corpus-Generation`
   (only `/api/v1` responses carry it; `frontend/src/lib/generation.ts` holds it server-side).
8. The guide ratchet (`frontend/tests/guide.test.ts`) fails on any new page file under
   `frontend/src/pages/` not claimed by a chapter's `covers.routes` (escape hatch:
   `UNDOCUMENTED_ROUTES`, which already holds `/app/404`, `/app/429`, `/app/healthz`,
   `/app/preview`) and on any new ADR claimed by no chapter and absent from
   `INFRASTRUCTURE_ADRS`. Files in `frontend/public/` are not walked.

**UX in a standalone window.**

9. `lib/uslm.ts:517-528` stamps `target="_blank" … data-newtab` on every cross reference, and
   `SearchResult.astro:45` on every search result. In an installed app each opens a browser tab
   outside the app. The escape hatch exists (`usc-linktarget === "same"`,
   `Base.astro:223-239`) but the only UI setting it is hidden while accounts are off
   (`settings.astro:42`).
10. `/app/search` and `/app/goto`'s failure render pass no `crumbs` to `Base` — no breadcrumb,
    no back link — which matters where there is no browser back button. `/app/versions`,
    `/app/diff`, 404 and 429 all carry explicit trails (ADR-0065).
11. The command palette is keyboard-only (`KeyboardNav.astro:236-240` is the sole opener) and
    is the only surface naming `/app/settings`. Not addressed here; recorded in § Non-goals.
12. The theme is chosen pre-paint from localStorage; nothing tells the OS, so an installed
    window's title bar cannot match a dark reader without a `theme-color` meta the page updates.
13. The failure-copy pattern to reuse is ADR-0041's: never nothing — the preview card renders
    "Preview unavailable" plus the citation rather than silently declining.

**External practice (September 2026).**

14. Chromium requires HTTPS plus a valid manifest — `name`/`short_name`, 192 and 512 px icons,
    `start_url`, `display` other than `browser`; a service worker is no longer an install
    requirement (Chrome 108/112, developer.chrome.com/blog/update-install-criteria).
15. iOS installs only via Share → Add to Home Screen; no prompt API. Manifest icons are honored
    since iOS 15.4 but an `apple-touch-icon` overrides them; `background_color` and `shortcuts`
    are ignored; `minimal-ui` falls back to `browser`, so `display` must be `standalone`. Since
    iOS 26 every Home Screen site opens as a web app by default; a manifest still controls
    name, icon and mode (webkit.org/blog/16993). Home Screen apps are exempt from the 7-day
    script-storage eviction that applies in tab Safari (webkit.org/tracking-prevention).
16. For a subpath app: `scope: "/app/"` with the trailing slash (`"/app"` also matches
    `/apple…`), `start_url` inside scope, an explicit `id` so the entry page can move without
    orphaning installs. One PWA per origin at a subpath is a supported shape.
17. In-page `<meta name="theme-color">` updates an installed Chromium window's title bar live,
    and is the only mechanism that can follow a runtime theme toggle — the manifest's
    `theme_color` is static and there is no shipped manifest dark-mode member (w3c/manifest
    #975 is still open).
18. For SSR HTML the recommended worker is network-first with navigation preload enabled —
    without preload, a network-first worker taxes every navigation with worker startup. Cache
    only `GET`, same-origin, `response.ok`, non-`redirected` responses. Workbox is in
    maintenance; `@vite-pwa/astro` supports Astro 5 SSR but its value is precache-manifest
    generation, which an SSR reader barely uses. A hand-rolled worker of ~120 lines is the
    least machinery and fits this codebase's zero-dependency client.
19. `beforeinstallprompt` is Chromium-only: stash the event, reveal an affordance, call
    `prompt()` on click. On iOS the pattern is a dismissible instruction (Share → Add to Home
    Screen) shown only when not already standalone. `@media (display-mode: standalone)` and
    `navigator.standalone` detect the installed state.

## Design

### Manifest and identity (Phase P1)

`frontend/public/manifest.webmanifest`, served at `/app/manifest.webmanifest`:

```json
{
  "id": "/app/",
  "name": "United States Code",
  "short_name": "US Code",
  "description": "Any provision of the US Code, at any release point.",
  "start_url": "/app/",
  "scope": "/app/",
  "display": "standalone",
  "launch_handler": { "client_mode": "navigate-existing" },
  "theme_color": "<light chrome background token>",
  "background_color": "<light --page token>",
  "categories": ["reference", "books", "government"],
  "icons": [ "…192/512 any + 192/512 maskable, under /app/icons/…" ],
  "shortcuts": [
    { "name": "Search", "url": "/app/search" },
    { "name": "Release points", "url": "/app/releases" },
    { "name": "User guide", "url": "/app/guide" }
  ]
}
```

- The two colours are the values the token block in `site.scss` declares for the light theme —
  read them out of the token block / `frontend/src/data/color-pairs.json`, never retyped from
  memory. `background_color` is the splash background only and stays the light value (finding
  17: the manifest cannot follow the theme; the meta can).
- `display_override` is omitted: `standalone` is the intended mode everywhere
  (window-controls-overlay declined — § Non-goals).
- No `prefer_related_applications`, no `screenshots` (declined for now — § Non-goals), no
  `scope_extensions` (same-origin subpath needs none).

**Icons.** `scripts/icons.py` (run as `uv run --with cairosvg python scripts/icons.py`, the
`scripts/fonts.py` pattern — cairosvg is deliberately not a project dependency) renders
`static/favicon.svg`'s mark into `frontend/public/icons/`:

- `icon-192.png`, `icon-512.png` — `purpose: any`, transparent-safe.
- `icon-maskable-192.png`, `icon-maskable-512.png` — separate entries, mark within the inner
  80% safe zone on a full-bleed background (never one icon with `"any maskable"` — finding 14's
  sources warn the combined purpose crops the `any` rendering).
- `apple-touch-icon-180.png` — opaque background (iOS composites no alpha).

The script writes `docs/verification/icons.json` (file, pixel size, bytes, sha256) so the
committed binaries are reproducible from the committed SVG.

**Head, in `Base.astro`:**

- `<link rel="manifest" href="/app/manifest.webmanifest">` on every page (the install surface
  only appears on pages carrying the link).
- `<link rel="apple-touch-icon" href="/app/icons/apple-touch-icon-180.png">`.
- One `<meta name="theme-color">` whose `content` the existing pre-paint bootstrap sets from
  the resolved theme, and which `ThemeToggle` updates on toggle — the two values (light and
  dark chrome background) inlined next to the bootstrap, sourced from the token block.
- `viewport-fit=cover` added to the viewport meta, paired with `env(safe-area-inset-*)`
  padding on the sticky chrome and footer in `site.scss` (the two must land together: `cover`
  without the padding puts the topbar under a notch in landscape standalone).

**A Vitest ratchet for the manifest** — `frontend/tests/pwa.test.ts`: the manifest parses; `id`,
`scope` (trailing slash), `start_url`-inside-scope, `display: standalone` hold; every declared
icon exists on disk at its declared pixel size (read the PNG header); the theme-color values in
`Base.astro` match the token block. This is the same shape as `fonts.test.ts` asserting the
`@font-face` contract.

### Standalone behavior (Phase P1)

- **Links stay in the app.** The link-target script in `Base.astro` treats
  `matchMedia("(display-mode: standalone)").matches || navigator.standalone` as
  `usc-linktarget === "same"`: in an installed window, cross references and search results
  navigate in place (finding 9). In a browser tab nothing changes.
- **Every page carries a trail.** `/app/search` and `/app/goto` pass `crumbs` to `Base` (Home ›
  Search), closing the only no-trail gap (finding 10). This helps the browser site too.

### Service worker and offline (Phase P2)

`frontend/public/sw.js`, hand-rolled, no build step, no dependency (finding 18). Registered
from `Base.astro` on `load`: `navigator.serviceWorker.register("/app/sw.js",
{ updateViaCache: "none" })`.

**Strategies:**

| request | strategy | cache |
|---|---|---|
| navigations under `/app/` | network-first, navigation preload enabled; on success, store; on failure, match the URL, else serve the offline page | `usc-pages-v1`, LRU-bounded at 40 entries |
| `/app/_astro/` | cache-first — the names carry the build hash | `usc-assets-v1`, bounded at 120 entries |
| `/app/fonts/`, `/app/uswds/`, `/app/icons/` | cache-first with a background revalidation — stable names whose bytes regenerate in place | `usc-assets-v1` |
| everything else (`/app/preview/`, `/app/healthz`, non-GET, cross-origin, non-`/app`) | pass through untouched | — |

- Store only `GET` + `response.ok` + `response.redirected === false` (the canonical-redirect
  middleware means a URL with empty `?release=` 307s; only final responses are cacheable —
  finding 18).
- `self.skipWaiting()` + `clients.claim()`: the worker is a thin pass-through with no precached
  shell, so immediate activation is safe and worker fixes take effect on the next load.
- Versioned cache names; `activate` deletes any cache not in the current set.
- **No corpus-generation coupling, deliberately.** Network-first means a cached page is served
  only when the network is down, so staleness is bounded to offline periods, and every section
  page states its release point and whether it is the newest (`ReleaseContext`, ADR-0044). The
  reader's HTML does not carry `X-Corpus-Generation` today (finding 7); wiring it through so
  the worker could stamp cache entries is recorded as a possible refinement, not built.

**The offline page** — `frontend/src/pages/offline.astro`, precached at worker install:

- Self-contained: does not use `Base`, inlines its own minimal styling (both themes, via a copy
  of the theme bootstrap) and uses system fonts, so caching the one HTML document suffices —
  no build-hashed subresources to enumerate from a static worker script.
- Says the site is unreachable, lists the cached recently-read sections as links (a small
  inline script enumerating `usc-pages-v1`), and offers a retry. ADR-0041's rule: never
  nothing (finding 13).
- Joins `UNDOCUMENTED_ROUTES` in `guide.test.ts` (the 404/429 class: a page reached only on
  failure); Phase P4 documents offline behavior in the guide's install section.

**Browser tests** — `frontend/tests/e2e/pwa.spec.ts`: manifest and `sw.js` served with correct
content types; registration reaches `ready`; with `context.setOffline(true)`, a previously
visited section renders from cache and an unvisited URL renders the offline page. Playwright
contexts are ephemeral, so a worker registered in one spec does not leak into another — but the
spec should still unregister in teardown as hygiene.

### Install surface and documentation (Phase P4)

- **One install row** in the More menu's HELP group: hidden by default; a small `InstallApp`
  island reveals it as a button when `beforeinstallprompt` fires (stash → `prompt()` on click,
  hide on `appinstalled`), or as a link to the guide's install instructions on iOS Safari when
  not standalone; never shown when already `display-mode: standalone` (finding 19).
- **Guide**: the "Install as an app" section in chapter 02 (which owns the chrome) grows from
  P1's stub to the full treatment — what installing does, Chromium/macOS/iOS instructions,
  what works offline and what does not, with a scenario answerable from the fixture corpus
  (e.g. the manifest link and apple-touch-icon present on a section page).
- `docs/a11y/routes.json` gains `/app/offline` (it renders normally online); `docs/ia-map.md`
  gains the row; `CLAUDE.md`'s status section gains the PWA paragraph.

### ADRs

Three, written by the phases that land them. ADR-0077 (ECCT probe) and ADR-0078 (Redis cache)
are claimed on open branches — take the next free numbers at implementation time; expected:

- **ADR-A (≈0079), Phase P1** — the reader is installable: manifest under `/app`, generated
  icons, live theme-color, standalone same-tab links, safe-area insets. Records the declined
  alternatives: `window-controls-overlay`, manifest `screenshots`, `@vite-pwa/astro`.
- **ADR-B (≈0080), Phase P2** — offline is network-first with a recently-read cache: the
  strategy table, `skipWaiting`, the self-contained offline page, and the declined
  generation coupling with its reasoning.
- **ADR-C (≈0081), Phase P4** — the install affordance: one hidden-by-default row, the
  per-platform reveal rules, and why there is no banner.

### Costs and risks, named

1. **Every route's JS budget rises twice** (P1: theme-color + standalone link check, ~300
   bytes; P2: registration, ~250 bytes) and P4 raises it again for the install island —
   `docs/js-budgets.json` is edited in three phases, and P4 re-measures after P2 merges.
2. **The manifest's colours are static.** An installed dark reader gets a light splash;
   the title bar follows the meta and is correct after first paint (finding 17).
3. **iOS behavior is unverifiable in CI** — Add to Home Screen has no emulation. The deploy
   check is a manual pass on a device against the deployed box, recorded in
   `docs/deploy-status.md` when done.
4. **A cached section served offline can be stale.** Bounded by network-first to offline
   periods and visible on the page itself (release point + newest-or-not).
5. **Out-of-scope URLs** — bare `/us/usc/…` citations, `/docs`, `/redoc`, external links —
   show Chromium's out-of-scope bar or an iOS in-app sheet inside the installed app. Reader
   hrefs already stay on `/app` (`lib/url.ts`), so this arises only when leaving the reader,
   which is correct.
6. **Committed PNG icons** are five more binaries in the repo, regenerable from
   `static/favicon.svg` via `scripts/icons.py` and pinned by `docs/verification/icons.json`.
7. **The worker is a new global behavior in e2e runs.** Playwright context isolation contains
   it; the a11y scan and `make shots` use their own contexts and are unaffected.

### Non-goals

Named so a future session builds them deliberately or not at all:

- Push notifications and the Badging API (watchlist notifications would want iOS 18.4's
  declarative web push; accounts are off — ADR-0034).
- Full-offline browsing (precaching titles), background sync, periodic sync.
- `window-controls-overlay`, `tabbed` display, file/protocol handlers.
- Manifest `screenshots` (the richer install UI) — add later from `make shots` output if
  wanted.
- A touch path to the command palette, and exposing the link-target preference while accounts
  are off (findings 9 and 11 record the state; the standalone override removes the standalone
  harm).
- A continue-reading surface on `/app/` (the front page is the `start_url` as it stands; its
  hardcoded demo date and `make dev-data` empty-state copy are pre-existing).
- TWA/store packaging.

## Phases

Each phase is one worktree agent session on the model-assignment rhythm (PLAN §7): read this
spec, implement, tests green, guide/ADR duties in-session, BUILDLOG entry, small commits. Every
prompt below is self-contained for an agent starting cold in the repo.

### P1 — identity and standalone behavior (frontend only)

**Prompt:**

> Read `docs/pwa-spec.md` (§ Design: Manifest and identity, Standalone behavior; § What was
> found items 1-6, 9-10, 12, 14-17) and ADR-0030, ADR-0042, ADR-0046, ADR-0052. Implement
> Phase P1: `scripts/icons.py` (`uv run --with cairosvg`, the `scripts/fonts.py` pattern)
> rendering `static/favicon.svg` into `frontend/public/icons/` — 192/512 `any`, 192/512
> maskable (mark in the inner 80% on a full-bleed background; separate entries, never
> `"any maskable"`), 180 apple-touch opaque — writing `docs/verification/icons.json`;
> `frontend/public/manifest.webmanifest` exactly per the spec's § Manifest (colours read from
> `site.scss`'s token block, never retyped); in `Base.astro`: the manifest link,
> apple-touch-icon link, one `theme-color` meta set by the pre-paint bootstrap and updated by
> `ThemeToggle` on toggle, and `viewport-fit=cover` paired with `env(safe-area-inset-*)`
> padding on `.topbar`, `.sectionbar` and the footer in `site.scss`; the standalone same-tab
> override in `Base.astro`'s link-target script
> (`matchMedia("(display-mode: standalone)").matches || navigator.standalone` behaves as
> `usc-linktarget === "same"`); `crumbs` on `/app/search` and `/app/goto`. Write ADR-A (the
> spec's § ADRs — check `docs/adr/` and open branches for the next free number; 0077/0078 are
> claimed) and claim it in guide chapter 02's `covers.adrs` with a two-sentence "Install as an
> app" stub section (Phase P4 expands it). Add `frontend/tests/pwa.test.ts` (manifest parses;
> `id`/`scope`-with-trailing-slash/`start_url`-in-scope/`display` hold; every declared icon
> exists at its declared pixel size via the PNG header; theme-color values match the token
> block). Raise `docs/js-budgets.json` per its own headroom rule. `make test-web` green; run
> `make test-e2e`, `make test-a11y` and `make shots` against `make dev-all` (sticky geometry
> must not move — `sticky.spec.ts` is the referee for the safe-area padding). Update this
> spec's Status table; BUILDLOG entry. Do NOT touch Python, `deploy/`, `frontend/public/sw.js`
> (does not exist yet), or `SiteHeader.astro`.

**May touch:** `frontend/public/icons/`, `frontend/public/manifest.webmanifest`,
`frontend/src/layouts/Base.astro`, `frontend/src/components/ThemeToggle.astro`,
`frontend/src/styles/site.scss`, `frontend/src/pages/search.astro`,
`frontend/src/pages/goto.astro`, `frontend/src/pages/guide/02-reading.md`,
`frontend/tests/pwa.test.ts`, `scripts/icons.py`, `docs/verification/icons.json`,
`docs/js-budgets.json`, `docs/adr/`, `docs/pwa-spec.md`, `BUILDLOG.md`.

### P2 — service worker and offline (depends on P1 merged)

**Prompt:**

> Read `docs/pwa-spec.md` (§ Design: Service worker and offline; § What was found items 1-3,
> 5, 7, 13, 18) and ADR-0018, ADR-0041, ADR-0046. Implement Phase P2:
> `frontend/public/sw.js`, hand-rolled — install precaches `/app/offline`; navigation preload
> enabled in `activate`; fetch handles only `GET`: navigations under `/app/` network-first
> (preload response first), storing only `ok` non-`redirected` responses in `usc-pages-v1`
> (LRU 40), falling back to the cache then the offline page; `/app/_astro/`, `/app/fonts/`,
> `/app/uswds/`, `/app/icons/` cache-first in `usc-assets-v1`; `/app/preview/`,
> `/app/healthz`, non-GET and non-`/app` pass through; `skipWaiting` + `clients.claim`;
> versioned cache names cleaned in `activate`. Registration in `Base.astro` on `load` with
> `updateViaCache: "none"`. `frontend/src/pages/offline.astro` self-contained per the spec
> (no `Base`, inline both-theme styling via a copy of the theme bootstrap, system fonts, the
> cached-pages list from `usc-pages-v1`, a retry link); add it to `UNDOCUMENTED_ROUTES` in
> `frontend/tests/guide.test.ts`. Write ADR-B (spec § ADRs; next free number) and add it to
> `INFRASTRUCTURE_ADRS` (Phase P4 moves it into chapter 02's covers). Add
> `frontend/tests/e2e/pwa.spec.ts` per the spec's § Browser tests (unregister in teardown).
> Raise `docs/js-budgets.json` (all routes + a new `/app/offline` key). `make test-web`
> green; `make test-e2e` against `make dev-all`. Update this spec's Status table; BUILDLOG
> entry. Do NOT touch Python, `deploy/`, `SiteHeader.astro`, the guide chapters, or
> `docs/a11y/routes.json`.

**May touch:** `frontend/public/sw.js`, `frontend/src/pages/offline.astro`,
`frontend/src/layouts/Base.astro` (registration script only),
`frontend/tests/guide.test.ts`, `frontend/tests/e2e/pwa.spec.ts`, `docs/js-budgets.json`,
`docs/adr/`, `docs/pwa-spec.md`, `BUILDLOG.md`.

### P4 — install surface and documentation (depends on P1 merged; merges after P2)

**Prompt:**

> Read `docs/pwa-spec.md` (§ Design: Install surface and documentation; § What was found
> items 8, 11, 15, 19) and ADR-0058, ADR-0061, ADR-0064, and the merged ADR-A and ADR-B.
> Implement Phase P4: an `InstallApp` island rendering one hidden-by-default row in the More
> menu's HELP group (`SiteHeader.astro`) — revealed as a button by `beforeinstallprompt`
> (stash → `prompt()` on click, hide on `appinstalled`), or as a link to the guide's install
> section on iOS Safari when not standalone; never rendered visible under
> `display-mode: standalone`. Expand guide chapter 02's "Install as an app" stub to the full
> section (installing on Chromium/macOS/iOS, what works offline, ADR-A/ADR-B claimed in
> `covers.adrs` — move ADR-B out of `INFRASTRUCTURE_ADRS`), with a scenario answerable from
> the CI fixture corpus (the manifest link and apple-touch-icon on a section page). Add
> `/app/offline` to `docs/a11y/routes.json` and `docs/ia-map.md`. Write ADR-C (spec § ADRs;
> next free number), claimed in chapter 02. Rebase on P2's merge and re-measure
> `docs/js-budgets.json` before finishing. Add the PWA paragraph to `CLAUDE.md`'s status
> section and the manual iOS device check as an owed item in `docs/deploy-status.md`.
> `make test-web` green; `make test-e2e` and `make test-a11y` against `make dev-all`. Update
> this spec's Status table; BUILDLOG entry. Do NOT touch Python, `deploy/` (the
> `deploy-status.md` note aside), `Base.astro`, or `sw.js`.

**May touch:** `frontend/src/components/InstallApp.astro`,
`frontend/src/components/SiteHeader.astro`, `frontend/src/styles/site.scss`,
`frontend/src/pages/guide/02-reading.md`, `frontend/tests/guide.test.ts`,
`docs/a11y/routes.json`, `docs/ia-map.md`, `docs/js-budgets.json`, `docs/adr/`, `CLAUDE.md`,
`docs/deploy-status.md`, `docs/pwa-spec.md`, `BUILDLOG.md`.

## Wave plan

| wave | phases | parallel? | notes |
|---|---|---|---|
| 1 | P1 | alone | owns `Base.astro`, `site.scss` and the manifest; everything later builds on it |
| 2 | P2 ∥ P4 | yes — disjoint files (P2: worker + offline page + `Base` registration; P4: `SiteHeader` + guide + a11y map) | both branch from main after P1 merges; **P2 merges first** — P4 rebases and re-measures `docs/js-budgets.json` (both phases raise it) and moves ADR-B out of `INFRASTRUCTURE_ADRS` |

Worktree agents per phase; each merges via PR with a fresh-context review of the diff before
the next wave starts. File-boundary lists above are the non-interference contract. The one
shared file in wave 2 is `docs/js-budgets.json` (and `guide.test.ts`'s two lists), resolved by
the stated merge order. After wave 2, deploy and run the manual device pass (cost 3).

## Status

| phase | state | branch/PR | notes |
|---|---|---|---|
| P1 identity + standalone | implemented | `c5-pwa-p1` | ADR-0079; manifest + icons + theme-color meta + safe-area insets + standalone same-tab links + Home › Search trails; `tests/pwa.test.ts` |
| P2 worker + offline | implemented | `c5-pwa-p2` | ADR-0080; `sw.js` (network-first + preload, LRU-40 pages, cache-first assets), registration in `Base.astro`, self-contained `/app/offline`, `tests/e2e/pwa.spec.ts` |
| P4 install surface + docs | implemented | `c5-pwa-p4` | ADR-0081; `InstallApp` row in More › Help, chapter 02's full install section + scenario, `/app/offline` in the a11y matrix and the IA map, the device pass owed in `docs/deploy-status.md` |
| deploy + device check | not started | — | manual iOS/macOS install pass against the deployed box; record in `docs/deploy-status.md` (the checklist is written there) |
