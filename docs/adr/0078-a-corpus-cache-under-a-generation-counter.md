# ADR-0078: A Redis corpus cache invalidated by a generation counter

**Date:** 2026-09-02 · **Status:** Accepted · **Amends:** ADR-0045 (the release memo's TTL), ADR-0066 (the diff memo's key) · **Relates to:** ADR-0018, ADR-0047, ADR-0073

*(There is no ADR-0077 on this branch's line; the number is claimed by open PR #70. The
investigation this ADR implements is `docs/redis-caching-spec.md` on that PR's branch,
`claude/redis-caching-version-analysis-pwa-9n0ejz`.)*

## Context

ADR-0018 encodes the browser-facing cache contract: `immutable` only when a requested release
label resolved to itself, `max-age=300` otherwise, `no-store` for anything per-user. It cannot
protect a server-side cache, and the site had exactly one — the reader's per-title release memo
(ADR-0045), which served a list up to five minutes stale after a load. The API's own repeat work
was either recomputed every time (the release list is 27 ms and 44 KB at the container, fetched
behind every section page) or held in per-process state lost on every deploy and watchdog restart
(the ADR-0066 diff memo, ~5 s to rewarm per pair) — and the diff memo had a latent staleness bug:
nothing called `clear_diff_cache()` in production, so a `--force` re-load under a changed parser
could leave a pinned pair's redline stale until a restart.

ADR-0047 declined a shared cache *in front of* the spine and stands; this is the origin-side
design its closing section left open.

The Redis integration page (`redis.io/docs/latest/integrate/fastapi/`) recommends
`fastapi-redis-sdk`. Its shapes are taken — a lifespan-owned pool, `REDIS_*` settings, a key
prefix — and its dependency factories declined: its hit path replays stored `Cache-Control` and
an `ETag` computed from the body, where ADR-0018's `Cache-Control` is a function of the
*resolution* and the section ETag is the content hash (ADR-0007). `fastapi-cache2` fails
`test_no_python_module_renders_html` on import (`starlette.templating`) and pins `redis<5`.
The client is redis-py 8, synchronous — the handlers are sync `def`s in a threadpool.

## Decision

**The contract: a cached answer is served only while no ingest write has committed since it was
computed.** Not a TTL (a promise to be stale for at most *n* seconds) and not eviction groups
(invalidation by enumeration, stale wherever someone forgot a tag).

**One counter, bumped by the database itself.** `corpus_state` holds one row; migration
`a3f8c2d1e6b7` puts a statement-level `AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE` trigger on
all fifteen corpus tables, running `generation = generation + 1` inside the writer's own
transaction. No writer can forget it — ingest needs no code change, the same reason ADR-0018
attached `no-store` to routers rather than routes. The account tables are excluded: everything
behind them is `no-store` and never cached.

**The generation is read before the data, and the key carries it.**
`Repository.corpus_generation()` (one `SELECT`, 0.12 ms measured) is read lazily per request by
`api/cache.py`'s `ResponseDataCache` — lazily, so a request rejected by a limiter or validation
still costs no connection (the ADR-0073 property). Keys are `usc:g{G}:{name}:{parts}`. Under
`READ COMMITTED`, a value computed after the generation read is either correct for *G* or stored
under a *G* no later request will ask for — an ingest commit moves the counter atomically with
the data, orphaning every existing key. Orphans expire on TTL (7 days; 30 for diff ops) or fall
to `allkeys-lru`; the TTL plays no part in freshness. Resolved labels may be read before the
generation because they land **in the key**, not in the value.

**Payloads are cached, never HTTP responses.** `through()` stores the Pydantic value a handler
was about to return (`dump_json(by_alias=True)`, revalidated on the way out), so ADR-0018's
header logic — `Cache-Control` from the resolution, the content-hash ETag, `Vary`, the 304 path —
runs on every request and can never be replayed wrongly. Cached: the release list, the title
list, a section's versions, the TOC (keyed on identifier, resolved label, and note), and the
labels batch (resolved label plus a SHA-256 of the identifier list). Not cached: the section
route (one query, a real ETag, the browser holds the copy), search (unbounded query space,
OpenSearch has its own cache), citation (a parse), anything `no-store`. Errors raised inside
`compute` are never stored.

**The diff memo becomes two-tier and generation-keyed.** The 256-entry LRU keys gain the
generation — which retires the stale-after-reload bug outright — and Redis sits behind it under
the same key material, so a restart costs a Redis read instead of seconds of diffing per pair.

**Every response that read the generation says so.** `X-Corpus-Generation` rides on the cached
routes and on the section route (set even with Redis off — the header is a fact about the corpus,
not the cache), and `X-Corpus-Cache: hit|miss` on responses that consulted Redis. The reader's
release memo (ADR-0045) keys its entries on a monotonic tracker fed from the header
(`frontend/src/lib/generation.ts`): an entry is fresh exactly while the generation stands, and
the five-minute window is gone. The pages consult the memo after awaiting their own
section/versions fetch, so the tracker is current when freshness is judged; `TTL_MS` survives
only as the fallback when no generation has been seen.

**The cache is optional and advisory.** `REDIS_URL` unset (the default, and `make dev`) means
every path is a no-op. `storage/cache.py` owns the client — lazy singleton, 0.5 s connect / 1 s
socket timeouts, and a 30-second cooldown after any error so a dead Redis costs one timeout per
half-minute, not one per request. Redis holds nothing authoritative: a restart is a cold cache,
never a wrong one. The compose stacks run `redis:7-alpine` with `maxmemory 256mb`,
`allkeys-lru`, no persistence; `depends_on` is `service_started`, so a broken Redis cannot keep
the site down. `/health` reports `redis: disabled|ok|unavailable` without ever failing on it —
`deploy/watchdog.sh` probes that route, and a cache outage must not read as a site outage.

## What was declined

- **Per-family generation counters** (text / structure / classification), so a classification
  load would not empty the section cache: a route must then declare what it reads, and a wrong
  declaration is a silently stale route. One counter cannot be wrong. Revisit on measured need.
- **Redis `CLIENT TRACKING`** client-side caching: it invalidates on Redis writes, and ingest
  writes Postgres.
- **`LISTEN/NOTIFY`** to push the generation: saves 0.12 ms per request for a listener thread
  and a reconnect story.
- **Caching the classification listings** for now: those routes hold a `ClassificationRepository`,
  a different dependency, so the generation read means a second session or a second protocol
  method — deferred until the plumbing is worth it.
- **Moving the rate limiters to Redis** (the spec's R3): a separate change with its own tests;
  the per-process limiters remain ADR-0029's recorded cost.

## Consequences

- A daily poll that finds nothing still writes one `source_checks` row and empties the whole
  cache once a day; a `load-all` empties it continuously while running. Correct under the
  contract, and loads are a few-times-a-month event.
- Every cached route pays one extra Postgres round trip per request, hit or miss, keeping the
  pool in the request path — so ADR-0073's 2 s shedding still governs.
- `tests/test_corpus_cache.py` holds the contract as a property: warm a route, commit a write in
  a second connection, and the very next response must show it. The suite runs cache-disabled by
  default (`conftest.py` clears `REDIS_URL`); cache tests install fakeredis.
- `docs/verification/loadtest.json` was already stale on three axes and now predates this too;
  regenerating it (the spec's R4) is the standing next step.
