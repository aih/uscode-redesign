/**
 * Rate limits for the reader's two expensive server-rendered routes (ADR-0029).
 *
 * `params.py` limits `/api/v1`. This file exists because the reader cannot be
 * covered by that limit at all, for two independent reasons:
 *
 *  1. **The work happens here, not there.** `/app/diff` renders its redline in
 *     this process (`lib/diffdoc.ts`; ADR-0026 moved the reader off the API's
 *     source-level diff), so there is no API call for a limiter to see.
 *  2. **The API cannot tell readers apart.** Every server-side call this app
 *     makes arrives at FastAPI from the frontend container's one address, so
 *     `/api/v1`'s buckets are sized for a server. The browser's own address is
 *     visible *here* and nowhere else.
 *
 * The amplifier is worse on this side than on the API's. FastAPI's sync handlers
 * at least have a 40-slot threadpool; Node has one event loop, and both routes
 * below occupy it synchronously — `documentDiff` over a whole section, and the
 * USLM render behind every preview. One caller can stall the reader for
 * everyone without saturating anything.
 *
 * ## What identifies a caller
 *
 * `context.clientAddress`, which the Node adapter fills from the **leftmost**
 * `X-Forwarded-For` value, falling back to the socket peer
 * (`astro/dist/core/app/node.js:121-122`). Leftmost is the client-supplied end
 * of that header, so on its own this would be exactly as spoofable as uvicorn's
 * `--forwarded-allow-ips "*"` was before ADR-0029: one header, a fresh bucket.
 *
 * What makes it trustworthy is `deploy/Caddyfile`, which *overwrites*
 * `X-Forwarded-For` with `{remote_host}` in both handle blocks. That is why the
 * fix belongs at the proxy rather than in either backend — one line per hop
 * fixes both surfaces, and neither has to be taught which hops to believe. Any
 * deployment putting something else in front must do the same.
 *
 * ## The cost, stated
 *
 * The state is per process, like the API's. Honest for ADR-0020's single box and
 * wrong for a second instance, which would need shared state or the limit moved
 * into the proxy.
 */

import { defineMiddleware } from "astro:middleware";

import { RateLimiter } from "./lib/ratelimit";

/**
 * The hover preview (ADR-0024). One request per citation hovered, so a reader
 * moving down a densely cross-referenced section legitimately fires a good many
 * in a row — the burst is sized for that, the sustained rate for a person
 * rather than a script walking every `<ref>` in the corpus.
 */
const preview = new RateLimiter("preview", 60, 5);

/**
 * The reader's redline. Tighter, because `documentDiff` holds the event loop for
 * a whole section and nothing prefetches this — a person reads one redline at a
 * time, and 30 a minute after a burst of 8 is well past attentive reading.
 */
const diff = new RateLimiter("diff", 8, 0.5);

/** `context.url.pathname` carries Astro's `base`, so these are full paths. */
const LIMITED: ReadonlyArray<readonly [string, RateLimiter]> = [
  ["/app/preview/", preview],
  ["/app/diff/", diff],
];

export const onRequest = defineMiddleware((context, next) => {
  const match = LIMITED.find(([prefix]) => context.url.pathname.startsWith(prefix));
  if (!match) return next();

  // Guarded because `clientAddress` throws on an adapter that cannot supply one.
  // Falling into one shared bucket is the safe direction; failing open is not.
  let key: string;
  try {
    key = context.clientAddress || "-";
  } catch {
    key = "-";
  }

  const retryAfter = match[1].check(key);
  if (retryAfter === null) return next();

  return new Response("Too many requests. Please slow down and try again.", {
    status: 429,
    headers: {
      "Retry-After": String(Math.ceil(retryAfter)),
      "Content-Type": "text/plain; charset=utf-8",
      // A shed request is a fact about this caller at this moment, never a
      // cacheable fact about the URL (ADR-0018).
      "Cache-Control": "no-store",
    },
  });
});
