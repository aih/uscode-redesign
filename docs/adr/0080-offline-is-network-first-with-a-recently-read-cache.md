# ADR-0080 — Offline is network-first with a recently-read cache

- **Status:** Accepted
- **Date:** 2026-09-02
- **Context:** `docs/pwa-spec.md` Phase P2 (research findings cited by number
  below); ADR-0079 (the install identity this builds on), ADR-0018 (the HTTP
  cache policy the worker must not contradict), ADR-0041 (a failure surface
  is never nothing), ADR-0046 (the JS byte budget). Session 97.

## Context

ADR-0079 made the reader installable with no offline behaviour: an installed
app with no network showed the browser's own error page. The spec's brief for
this phase is a service worker that keeps the site exactly what it is online
and degrades honestly offline — recently read pages stay readable, everything
else says so.

The serving facts are ADR-0079's: `frontend/public/` surfaces at
`/app/<path>` (finding 1), so a worker at `frontend/public/sw.js` gets
default scope `/app/` with no header; the CSP's `worker-src 'self'` already
permits registration (finding 3). For SSR HTML the recommended strategy is
network-first with navigation preload — without preload, a network-first
worker taxes every navigation with worker startup (finding 18). Workbox is in
maintenance and `@vite-pwa/astro`'s value is precache-manifest generation,
which a server-rendered reader with no client bundle barely uses; ADR-0079
already declined both.

## Decision

1. **The worker is hand-rolled** — `frontend/public/sw.js`, ~150 lines, no
   build step, no dependency, matching the zero-client-bundle frontend
   (ADR-0022, ADR-0046). The strategies:

   | request | strategy | cache |
   |---|---|---|
   | navigations under `/app/` | network-first, preload response first; store on success; on failure the cached copy, else the offline page | `usc-pages-v1`, LRU-bounded at 40 |
   | `/app/_astro/` | cache-first | `usc-assets-v1` |
   | `/app/fonts/`, `/app/uswds/`, `/app/icons/` | cache-first with a background revalidation | `usc-assets-v1` |
   | `/app/preview/`, `/app/healthz`, non-GET, cross-origin, non-`/app` | pass through untouched | — |

   The preview is one fetch per citation and useless stale; the healthcheck
   exists to answer whether the site is up, which a cache would answer
   wrongly. Only `/app/_astro/` names carry the build hash; the fonts, icons
   and USWDS files keep their URLs when `scripts/fonts.py`,
   `scripts/icons.py` or a vendoring bump regenerates their bytes, so a
   cached copy of those is served and revalidated behind it
   (`fetch(request, { cache: "no-cache" })` — the conditional request goes to
   the server, and an unchanged file costs a 304). Plain cache-first there
   would keep the old bytes for the life of the registration.
   `usc-assets-v1` is bounded at 120 entries, evicting oldest-stored first
   and never the offline page: every deploy mints a new set of build-hashed
   names, and without a trim the superseded ones accumulate until origin
   quota pressure starts failing the pages cache's own writes.

2. **Only `ok`, non-`redirected`, non-`no-store` responses are stored.** The
   reader's canonical-redirect middleware 307s a URL with an empty
   `?release=` (finding 18's trap), and only the final response is a page
   worth serving under the URL that was asked for; the per-user pages —
   `/app/login`, `/app/signup`, `/app/provisions`, `/app/settings` — carry
   `Cache-Control: no-store` (`lib/cache.ts`), and ADR-0018 is the policy
   this worker must not contradict. The store is LRU by fetch order:
   delete-then-put moves a revisited page to the back, and a trim drops the
   front past 40 entries. The write rides in `event.waitUntil`, off the
   response path — the reader gets first byte without waiting on the cache
   write, and a failed write (quota, most likely) costs the cache entry
   rather than the page.

3. **`skipWaiting()` + `clients.claim()`.** The worker precaches no shell —
   it is a thin pass-through — so immediate activation risks nothing and a
   worker fix takes effect on the next load instead of waiting for every tab
   to close. Cache names are versioned and `activate` deletes any cache not
   in the current set, so bumping a suffix retires its predecessor.

4. **Registration is in `Base.astro`, on `load`, with
   `updateViaCache: "none"`** — the worker script itself is always checked
   against the network, so a stale HTTP-cached copy cannot pin an old worker.
   Registration failure is swallowed: everything the worker does is an
   enhancement.

5. **The offline page is self-contained.** `frontend/src/pages/offline.astro`
   uses no `Base`, inlines its styling for both themes (a hand-copied set of
   the token values, plus a copy of the theme bootstrap — including the
   `theme-color` meta and its dark correction, so a dark reader's standalone
   window does not paint the manifest's light title bar over a dark page) and
   system fonts — so precaching the one HTML
   document at install suffices, with no build-hashed subresources to
   enumerate from a static worker script. It says the site is unreachable,
   lists the pages `usc-pages-v1` holds as links, and offers a retry
   (ADR-0041's rule, finding 13). It is served under whatever URL failed, so
   the retry is an empty `href` — the current URL. It lives in
   `usc-assets-v1`, not the pages cache, so the LRU trim can never evict it
   and it never appears in its own list. The route joins
   `UNDOCUMENTED_ROUTES` (the 404/429 class — a page reached on failure);
   Phase P4 documents offline behaviour in the guide.

## Declined

- **Corpus-generation coupling.** The reader's HTML does not carry
  `X-Corpus-Generation` (finding 7), and wiring it through so the worker
  could stamp cache entries buys little: network-first means a cached page is
  served only while the network is down, so staleness is bounded to offline
  periods, and every section page states its release point and whether it is
  the newest (ADR-0044). Recorded as a possible refinement, not built.
- **Precaching a shell or any statute.** Full-offline browsing is the spec's
  named non-goal; the offline surface is what was actually read.

## Consequences

- **Every route's JS budget rises once more** for the registration script in
  `Base.astro`'s graph — 285 bytes with its comment, 19,518 → 19,803 on the
  Base-only routes — and `/app/offline` gets a budget of its own (1,600
  measured: the theme bootstrap copy and the cached-pages list). Ceilings
  re-measured per `docs/js-budgets.json`'s headroom rule.
- **A cached section served offline can be stale**, bounded to offline
  periods and visible on the page itself (release point plus newest-or-not).
- **The worker holds copies ADR-0018 never promised.** The HTTP policy gives
  unpinned pages a 5-minute window; `usc-pages-v1` keeps them until evicted.
  That is the offline feature itself, and it is read only when the network
  has failed — online, every navigation goes to the network first.
- **The worker is a new global behaviour in e2e runs.** Playwright context
  isolation contains it; `tests/e2e/pwa.spec.ts` still unregisters and
  clears its caches in teardown as hygiene.
- **`/app/offline` visited online renders normally** — the worker refuses to
  store it in the pages cache, and the install-time copy in `usc-assets-v1`
  is refreshed on every worker update (`cache: "reload"`).
- **An edited offline page reaches an already-registered client only when
  `sw.js` itself byte-changes** — the precache runs in `install`, which
  fires only for a worker the browser considers new. `OFFLINE_REV` in
  `sw.js` exists to be bumped alongside such an edit.
