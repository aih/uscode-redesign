# ADR-0018: Cache immutably only when the release point is pinned

**Date:** 2026-07-29 · **Status:** Accepted · **Implements:** Day 6a (PLAN.md)

## Context

PLAN §6 puts "HTTP caching (immutable per (identifier, RP) → cache-forever ETags)" in Day 6, and
Session 4 had already laid the groundwork: `_section_response` has emitted an `ETag` equal to the
ADR-0007 content hash since the API was written, above a comment reading *"PLAN Day 6's
cache-forever plan starts here."*

It never went further. There was no `Cache-Control` anywhere in the repository, and although the
ETag was emitted it was never *compared* — `If-None-Match` was ignored, so a client holding a
current copy still paid for full resolution, serialization and transfer.

The obvious reading of the plan is "a section at a release point is immutable, so mark it
`immutable`". That reading is wrong in a way that would be silent and would serve superseded law.

## Decisions

**1. Immutability is a property of the resolution, not of the URL.**

`/api/v1/us/usc/t16/s45f?release=119-102not101` names a release point. It can never mean a
different one, and Title 16 as published at 119-102not101 can never change. That response is
genuinely immutable.

`/api/v1/us/usc/t16/s45f` names no release point, and `?date=07/12/2026` names a date rather than
a release point. Both are answered by *"the newest ingested release point at or before"* —
gotcha 10, the rule that lets the site answer for release points it never ingested. That answer
changes the moment a newer release point is loaded. Marking it `immutable` would pin superseded
text into browser and CDN caches with no way to invalidate it, and the reader would have no idea:
the response would look perfectly well-formed, just old.

`ResolvedRelease` already carries exactly what distinguishes them — `requested_label` and
`is_exact` — so the rule is one function in `params.py`:

| response | `Cache-Control` |
|---|---|
| a label was requested and resolved to itself | `public, max-age=31536000, immutable` |
| no release parameter, or `?date=`, or a label that resolved elsewhere | `public, max-age=300` |
| TOC, neighbours, versions, releases, titles, labels | `public, max-age=300` |
| a diff whose two endpoints are both pinned | `public, max-age=31536000, immutable` |
| anything under `/api/v1/auth` or `/api/v1/watchlist*` | `private, no-store` + `Vary: Cookie` |

A bare `119-102` resolving to `119-102not101` is in the *unpinned* row, which is worth spelling
out: the URL asked for a release point that was never published, and if one ever is, the same URL
will mean something else. It is not pinned even though it looks like it.

Tables of contents revalidate even when a release point is pinned, because `structure_nodes` holds
one row per node — the newest loaded release's view (ADR-0006) — rather than one per release
point. The data behind them is not versioned, so a promise that it will not change would be a lie.

**2. Conditional requests short-circuit to 304, with the full `If-None-Match` grammar.**
Comma-separated lists, weak validators (`W/"…"`), and `*` all mean "I already have it"
(RFC 9110 §13.1.2). The 304 carries the same `ETag`, `Cache-Control` and `Vary`, and no body.

**3. `no-store` is attached to the auth and watchlist *routers*, not their routes** — so a route
added later cannot forget it — **and re-applied by path in the error handler.** The second half is
not redundancy: a raised `HTTPException` never reaches the `Response` the dependency wrote to,
because the handler builds a fresh one. Without it every 401 from those surfaces went out with no
cache directives at all, which is exactly the response a shared cache is most likely to store
heuristically and hand to the next reader.

**4. Caddy adds no cache of its own and does not touch these headers.** Caddy 2 has no built-in
cache; adding one means a third-party module, and the module would be making decisions that only
the resolver can make correctly (decision 1). Origin headers pass through untouched. They are
already exactly what a CDN reads, so CloudFront becomes a drop-in whenever it is wanted.

**5. The reader mirrors the same rule** in `frontend/src/lib/cache.ts`, rather than inheriting
anything from the API. Section pages are `public` because they carry no per-user state — the Watch
button is a client-side island that asks `/api/v1/auth/me` after paint — while `/app/provisions`,
`/app/login` and `/app/signup` are `no-store` with `Vary: Cookie`.

## Consequences

- A pinned section can be cached forever by anything, which is the whole point: a citation to a
  published release point is the one thing on this site that is guaranteed never to change.
- Unpinned URLs — including the demo URL, which uses `?date=` — get a 5-minute freshness window
  and then revalidate. Revalidation is cheap because the ETag is the content hash, so a section
  whose text is unchanged across release points validates without re-sending.
- **The 304 path is not a latency win on a local network.** Measured on loopback: 183.7 rps for
  revalidated requests against 159.1 for full responses. What it actually saves is the body —
  28,348 bytes for §45f — which matters over a real network and not at all in the load test.
- Two places now encode the same rule, one in Python and one in TypeScript. They are tested
  separately (`tests/test_api.py`, `frontend/tests/cache.test.ts`) and can drift; the alternative
  was for the reader to read `Cache-Control` off its own API calls and re-emit it, which couples
  page freshness to fetch order and is worse.
- **HEAD is 405 on every `/api/v1` route.** FastAPI's `APIRouter` registers `GET` alone where
  Starlette's own `Route` would add `HEAD`. Caches, CDNs and uptime monitors use HEAD, so this
  should be fixed before a CDN goes in front — it is recorded here rather than fixed because it is
  a routing decision that touches every route, not a caching one.
