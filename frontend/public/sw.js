/*
 * The reader's service worker (ADR-0080). Hand-rolled, no build step, no
 * dependency — served from `frontend/public/` at `/app/sw.js`, which gives it
 * default scope `/app/` with no `Service-Worker-Allowed` header (ADR-0079's
 * serving facts). Registered by `Base.astro` on `load` with
 * `updateViaCache: "none"`, so this file is fetched from the network on every
 * update check.
 *
 * Strategies, per docs/pwa-spec.md § Service worker and offline:
 *
 *   navigations under /app/      network-first (preload response first);
 *                                store ok, non-redirected responses in
 *                                usc-pages-v1, LRU-bounded at 40; on failure
 *                                serve the cached copy, else the offline page
 *   /app/_astro/                 cache-first in usc-assets-v1 — build-hashed,
 *                                never a new byte under one URL
 *   /app/fonts/ /app/uswds/      cache-first with a background revalidation:
 *   /app/icons/                  stable names whose bytes change in place
 *                                when scripts/fonts.py, scripts/icons.py or
 *                                a USWDS vendoring bump regenerates them
 *   everything else              untouched: /app/preview/, /app/healthz,
 *                                non-GET, cross-origin, non-/app
 *
 * usc-assets-v1 is bounded at ASSET_LIMIT: every deploy mints a new set of
 * build-hashed _astro names, and without a trim the superseded ones accumulate
 * for the life of the registration. The offline page is exempt — losing it
 * loses the fallback.
 *
 * A response is stored only when it is `ok` and not `redirected`: the reader's
 * canonical-redirect middleware 307s a URL with an empty `?release=`, and only
 * the final response is a page worth serving under the URL that was asked for.
 *
 * No corpus-generation coupling, deliberately: network-first means a cached
 * page is served only while the network is down, so staleness is bounded to
 * offline periods, and every section page states its release point and whether
 * it is the newest (ADR-0044).
 */

const PAGES = "usc-pages-v1";
const ASSETS = "usc-assets-v1";
/* Anything not in this list is deleted at activate, so bumping a cache's
 * version suffix retires its predecessor on the next update. */
const KNOWN_CACHES = [PAGES, ASSETS];

const OFFLINE_URL = "/app/offline";
/* The offline page is fetched only at `install`, so an edit to
 * `offline.astro` reaches already-registered clients only when this file
 * itself byte-changes. Bump this when the page changes. */
const OFFLINE_REV = 2;
const PAGE_LIMIT = 40;
const ASSET_LIMIT = 120;
const ASSET_PREFIXES = ["/app/_astro/", "/app/fonts/", "/app/uswds/", "/app/icons/"];
/* The one prefix whose filenames carry the build hash. */
const HASHED_PREFIX = "/app/_astro/";
/* Pass-through even though they are under /app: the hover preview is one
 * fetch per citation and useless stale, and the healthcheck exists to answer
 * whether the *site* is up, which a cache would answer wrongly. */
const BYPASS_PREFIXES = ["/app/preview/", "/app/healthz"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      /* The offline page is self-contained — no build-hashed subresources —
       * so caching the one document suffices. It lives in the assets cache,
       * not the pages cache, so the LRU trim can never evict it and it never
       * appears in its own recently-read list. `cache: "reload"` bypasses the
       * HTTP cache: an install must pick up the current page, not a copy. */
      const response = await fetch(OFFLINE_URL, { cache: "reload" });
      /* A failed precache fails the install, and the registration retries on
       * the next load — better than an offline fallback that is a 500. */
      if (!response.ok) throw new Error(`precache ${OFFLINE_URL}: ${response.status}`);
      const cache = await caches.open(ASSETS);
      await cache.put(OFFLINE_URL, response);
      /* Immediate takeover is safe because this worker precaches no shell —
       * it is a thin pass-through, so a fixed worker takes effect on the next
       * load instead of waiting for every tab to close. */
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      /* Without preload, a network-first worker taxes every navigation with
       * worker startup before the request even leaves; with it, the browser
       * starts the fetch in parallel and hands the response over below. */
      if (self.registration.navigationPreload) {
        await self.registration.navigationPreload.enable();
      }
      const names = await caches.keys();
      await Promise.all(
        names.filter((name) => !KNOWN_CACHES.includes(name)).map((name) => caches.delete(name)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (!url.pathname.startsWith("/app/")) return;
  if (BYPASS_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))) return;

  if (ASSET_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))) {
    /* A direct navigation to an asset URL still has a preload fetch in
     * flight; consume it in the background so the browser does not log a
     * cancelled preload. */
    if (request.mode === "navigate" && event.preloadResponse) {
      event.waitUntil(event.preloadResponse.catch(() => {}));
    }
    event.respondWith(assetFirst(event));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(pageFirst(event, url));
  }
  /* Anything else — the page's own fetches, API-shaped calls — passes
   * through untouched. */
});

/** Whether a response may be stored at all. Never `no-store` — the per-user
 * pages (`/app/login`, `/app/provisions`, …) carry it, and ADR-0018 is the
 * policy this worker must not contradict. */
function storable(response) {
  return (
    response.ok &&
    !response.redirected &&
    !(response.headers.get("Cache-Control") || "").includes("no-store")
  );
}

/** Network-first for a navigation, with the recently-read cache behind it. */
async function pageFirst(event, url) {
  try {
    /* The preload response is the same network fetch, already in flight. */
    const response = (await event.preloadResponse) || (await fetch(event.request));
    if (storable(response) && url.pathname !== OFFLINE_URL) {
      /* The store rides in `waitUntil`, off the response path: the reader
       * gets first byte without waiting on the download completing or the
       * cache write, and a failed write — quota, most likely — costs the
       * cache entry rather than the page. */
      event.waitUntil(storePage(event.request, response.clone()).catch(() => {}));
    }
    return response;
  } catch (error) {
    const cache = await caches.open(PAGES);
    const cached = await cache.match(event.request);
    if (cached) return cached;
    const offline = await (await caches.open(ASSETS)).match(OFFLINE_URL);
    if (offline) return offline;
    throw error;
  }
}

/** Delete-then-put moves a revisited page to the back of the queue, so the
 * trim removes the least recently *fetched* rather than the first ever seen. */
async function storePage(request, response) {
  const cache = await caches.open(PAGES);
  await cache.delete(request);
  await cache.put(request, response);
  await trim(cache, PAGE_LIMIT);
}

/** Cache-first for the static files. */
async function assetFirst(event) {
  const request = event.request;
  const cache = await caches.open(ASSETS);
  const cached = await cache.match(request);
  if (cached) {
    /* Everything outside /app/_astro/ keeps its URL when its bytes change —
     * scripts/fonts.py, scripts/icons.py and a USWDS bump all regenerate in
     * place — so the cached copy is served and refreshed behind it.
     * `no-cache` sends the conditional request to the server rather than the
     * HTTP cache; these files carry ETag/Last-Modified, so an unchanged one
     * costs a 304. */
    if (!new URL(request.url).pathname.startsWith(HASHED_PREFIX)) {
      event.waitUntil(
        fetch(request, { cache: "no-cache" })
          .then((response) => (storable(response) ? storeAsset(cache, request, response) : undefined))
          .catch(() => {}),
      );
    }
    return cached;
  }
  const response = await fetch(request);
  if (storable(response)) {
    /* Off the response path for the same reason as above: a failed write
     * must not reject `respondWith` and fail an asset the network answered. */
    event.waitUntil(storeAsset(cache, request, response.clone()).catch(() => {}));
  }
  return response;
}

/** Store an asset and keep the cache bounded. The offline page is exempt from
 * the trim; everything else evicts oldest-stored first, which after a deploy
 * is mostly the superseded build-hashed files. */
async function storeAsset(cache, request, response) {
  await cache.put(request, response);
  const keys = await cache.keys();
  const evictable = keys.filter((key) => new URL(key.url).pathname !== OFFLINE_URL);
  for (const key of evictable.slice(0, Math.max(0, evictable.length - ASSET_LIMIT))) {
    await cache.delete(key);
  }
}

/** Drop the oldest entries until the cache holds at most `limit`. */
async function trim(cache, limit) {
  const keys = await cache.keys();
  for (const key of keys.slice(0, Math.max(0, keys.length - limit))) {
    await cache.delete(key);
  }
}
