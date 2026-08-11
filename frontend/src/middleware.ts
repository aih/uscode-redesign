/**
 * Two things every reader request passes through: a canonical redirect that
 * drops empty `?release=`/`?date=`, and the rate limits below.
 *
 * ## Rate limits for the reader's two expensive server-rendered routes (ADR-0029)
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
 * The reader's redline. Still the tightest budget here — `documentDiff` holds
 * the event loop for a whole section and nothing prefetches this — but no
 * longer sized for a page three clicks away.
 *
 * ADR-0029 set it at 8 with 30 a minute after, when reaching a redline meant
 * section → version history → pick two release points. ADR-0066 put "Compare
 * with…" on every section header, so a comparison is now one click from any
 * provision and a reader working through a chapter makes them at the rate they
 * open sections. 20 with 60 a minute after is the same kind of bound — it still
 * sheds a script walking the `?from=`/`?to=` axis, which is the traffic ADR-0037
 * exists for — against a reader who now has a reason to ask more often.
 */
const diff = new RateLimiter("diff", 20, 1);

/** `context.url.pathname` carries Astro's `base`, so these are full paths. */
const LIMITED: ReadonlyArray<readonly [string, RateLimiter]> = [
  ["/app/preview/", preview],
  ["/app/diff/", diff],
];

/**
 * The two parameters that mean "a moment in time", and are meaningless empty.
 *
 * The release switcher is a plain GET form with no JavaScript (ADR-0044), and a
 * GET form submits every named control it has. Its "Newest — follows new
 * releases" option carries an empty value, because an absent `?release=` is
 * already how the whole site spells "newest" — so choosing it produces
 * `/app/us/usc/t16/s45f?release=`. That answers correctly, and it is also the
 * URL the reader is invited to copy and cite. Redirecting to the clean form
 * once, here, is cheaper than teaching every page to strip it.
 */
const EMPTY_PARAMS = ["release", "date"] as const;

/** Strip `?release=` / `?date=` with no value, or null if there are none. */
function canonicalUrl(url: URL): URL | null {
  const empties = EMPTY_PARAMS.filter((name) => url.searchParams.getAll(name).some((v) => v === ""));
  if (empties.length === 0) return null;

  const clean = new URL(url);
  for (const name of empties) {
    const kept = clean.searchParams.getAll(name).filter((value) => value !== "");
    clean.searchParams.delete(name);
    for (const value of kept) clean.searchParams.append(name, value);
  }
  return clean;
}

export const onRequest = defineMiddleware(async (context, next) => {
  if (context.request.method === "GET") {
    const clean = canonicalUrl(context.url);
    // `pathname + search` rather than the absolute URL: the reader sits behind
    // Caddy (ADR-0015), so `context.url`'s origin is this container's, not the
    // one the browser asked for.
    if (clean) return context.redirect(`${clean.pathname}${clean.search}`, 307);
  }

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

  const headers = {
    "Retry-After": String(Math.ceil(retryAfter)),
    // A shed request is a fact about this caller at this moment, never a
    // cacheable fact about the URL (ADR-0018).
    "Cache-Control": "no-store",
  };

  // `/app/diff/` is limited and is a page a reader navigates to, so shedding it
  // used to hand back plain text with no chrome and no way back — the dead end
  // task B6 names. A navigation gets the error page at the URL it asked for;
  // `/app/preview/`'s fetch does not send `Accept: text/html` and still gets the
  // text body `CitePreview` was already handling by status (ADR-0041).
  if ((context.request.headers.get("accept") ?? "").includes("text/html")) {
    const rendered = await context.rewrite(
      new Request(new URL("/app/429", context.url), {
        // The page offers the way back to what was refused, and after the
        // rewrite it can no longer see which URL that was.
        headers: { "x-usc-wanted": wantedIdentifier(context.url.pathname) },
      }),
    );
    const response = new Response(rendered.body, rendered);
    for (const [name, value] of Object.entries(headers)) response.headers.set(name, value);
    return response;
  }

  return new Response("Too many requests. Please slow down and try again.", {
    status: 429,
    headers: { ...headers, "Content-Type": "text/plain; charset=utf-8" },
  });
});

/** `/app/diff/us/usc/t16/s45f` → `/us/usc/t16/s45f`. The identifier under a
 *  limited route, or an empty string when the path carries none. */
function wantedIdentifier(pathname: string): string {
  const match = /^\/app\/(?:diff|preview)(\/us\/usc\/.+)$/u.exec(pathname);
  return match ? match[1] : "";
}
