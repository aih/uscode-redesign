# Redis caching with a never-stale invalidation contract — spec

**Status:** investigation and design, 2026-09-02. Nothing in this document is built. It records
what was examined, what was measured, and the design recommended if the work is scheduled.
Decisions that get taken become an ADR; this file is the reasoning they would cite.

**Asked:** investigate Redis caching for the FastAPI API using the integration Redis documents at
`redis.io/docs/latest/integrate/fastapi/`, and design an invalidation process under which stale
data is never served.

---

## 1. What "never stale" has to mean here

A response served from a cache is stale when it differs from what the origin would compute at the
moment the response is sent. On this site the origin's answer depends on two things that move:

- **Which release point an unpinned request means.** `/api/v1/us/usc/t16/s45f` with no `?release`
  resolves to the newest release point for which `title_versions` holds a row for Title 16
  (`storage/postgres.py:171-186`). That answer moves the instant `ingest/load.py` inserts the row —
  per title, in the middle of a `load-all`, not at its end.
- **What the stored tables say.** Every table the API reads is written by an ingest command:
  `load` (release_points, titles, title_versions, structure_nodes, sections, section_versions,
  section_release_map, guid_map), `version-changes` (section_version_changes,
  section_version_change_laws, the two hash columns), `classification` (the four classification
  tables), `inventory`/`check` (release_points, source_checks). `structure_nodes` is unversioned
  (ADR-0006), so a table of contents at a *pinned* release point can change on a later load, which
  is why ADR-0018 gives every TOC `max-age=300` rather than `immutable`.

ADR-0018 already encodes the browser-facing half of the contract: `immutable` only when a label was
requested and resolved to itself, `max-age=300` otherwise, `no-store` for anything per-user. What
that contract cannot do is protect a *server-side* cache: a five-minute window is a five-minute
window, and the site already has one cache that serves stale data on exactly that term —
`frontend/src/lib/releasecache.ts` (ADR-0045) memoises `/api/v1/releases?ingested_title=` for
300 s, so for up to five minutes after a load the release picker on every section page of that
title omits the release point that was just loaded.

The contract this spec adopts is stronger than a TTL and stated so it can be tested:

> A cached response is served only if it was computed from a database state that no ingest write
> has changed since. A change committed by ingest is visible to the next request, with no window.

## 2. The libraries

Three were installed and imported in this session's environment (Python 3.12, FastAPI 0.140,
redis-py 8.1.0 available from PyPI through the proxy; `redis-server` 7.0.15 on the box image).

### 2.1 `fastapi-redis-sdk` 0.8.0 — the one the Redis page recommends

`redis.io/docs/latest/integrate/fastapi/` now documents Redis's own SDK (`pip install
fastapi-redis-sdk`, imported as `redis_fastapi`), built on redis-py, requiring `redis>=6`,
`fastapi>=0.115`, `pydantic-settings`, `anyio`. Imports clean: no Jinja2, no `starlette.templating`
in `sys.modules` afterwards, so `tests/test_architecture.py`'s template-engine rule is not
touched. What it offers, read from the installed source rather than the page:

| Piece | What it is | Fit here |
|---|---|---|
| `FastAPIRedis(app).lifespan()` | Opens a connection pool at startup, closes it at shutdown, wraps any existing lifespan | Take the shape. `main.py` has no lifespan today; one is needed anyway |
| `RedisSettings` | pydantic-settings from `REDIS_URL` / `REDIS_HOST`… / `REDIS_PREFIX` / `REDIS_DEFAULT_TTL` / `REDIS_MAX_CONNECTIONS` | Take the shape. `db/config.py` is `extra="ignore"`, so a `REDIS_URL` that is not declared there is silently dropped — declare it |
| `cache(ttl, eviction_group)` / `cache_evict` / `cache_put` | Dependency factories keyed by `default_key_builder` (route + query); the hit path returns the stored body with `X-Redis-Cache: HIT`, a weak `ETag` from `blake2b(body)`, and **`Cache-Control` computed from the entry's TTL** (`cache.py:155-175`, `:670-681`) | **Decline.** The `Cache-Control` it writes is a function of the TTL and would overwrite ADR-0018's, which is a function of the *resolution*. The section route's real ETag is the content hash (ADR-0007) and must not be replaced by a body digest. Eviction groups are invalidation by enumeration (§4.4) |
| `CacheBackend` / `SyncCacheBackend` | `get` / `set` / `delete` / `has` / `delete_group` (SCAN + DEL, or a Lua script), JSON coder, key `{prefix}:{group}:{key}` | Usable as a client wrapper. A 60-line module of the site's own does the same without a dependency whose DI layer is unused |
| `rate_limit(rate=…)` + `RateLimitBackend` | Fixed-window counter: `INCREX key … EX window` on Redis ≥ 8.8, a Lua `INCR`+`EXPIRE` script below (`ratelimit_backend.py:1-45`); IETF `RateLimit-*` headers; `rate_limit_fail_closed` setting | **Decline the algorithm.** ADR-0029's limiters are token buckets (`params.py:249-306`) with a burst and a sustained rate, and the `Retry-After` they compute is the time until one whole token. A fixed window at the same numbers admits 2× the burst at a window boundary and changes what the load-test artifact measured. The bucket is ~20 lines of Lua (§5.3) |
| `.otel()` | OpenTelemetry spans per cache op | Not now; nothing here consumes OTel |

### 2.2 `fastapi-cache2` 0.2.2

Declined on import: `fastapi_cache/coder.py:19` imports `starlette.templating`, which raises without
Jinja2 — the exact import `test_no_python_module_renders_html` forbids — and it pins
`redis<5.0.0` against the current 8.x. It is the library "redis-fastapi" searches usually surface;
it is not the one Redis recommends and it is not usable here.

### 2.3 `redis-py` 8.1.0

The client under both. The API's handlers are synchronous `def`s run in a threadpool (`params.py`'s
`RateLimiter.check` docstring says so), so the sync `redis.Redis` with its thread-safe
`ConnectionPool` is the right client, not `redis.asyncio`. The production checklist Redis publishes
for it (`develop/clients/redis-py/produsage`) is: `Retry(ExponentialBackoff(), n)`,
`health_check_interval`, socket timeouts, handle `ConnectionError`/`TimeoutError`. Its **server-
assisted client-side caching** (RESP3 `CLIENT TRACKING`, redis-py ≥ 5.1) keeps a per-process
local copy of keys and receives invalidation pushes when they change — attractive, but it
invalidates on *Redis* writes, not on *Postgres* writes, so it answers a different question from
this spec's (§4.5).

**Recommendation:** build on redis-py directly. Borrow the SDK's two shapes — lifespan-owned pool,
`REDIS_*` pydantic settings with a key prefix — and none of its dependency factories.

## 3. What the site holds in memory today, and what it costs

From the codebase (file:line as of `3fa913b`):

| State | Where | Keyed on | Bounded by | Lost on |
|---|---|---|---|---|
| 7 rate-limit token-bucket tables (ADR-0029) | `params.py:249-354`; instances in `api/routes.py:90-101`, `api/search.py:54`, `api/classification.py:87,100`, `api/auth.py:81` | caller address | 600 s sweep | every process restart |
| Diff memo, 256-entry LRU (ADR-0066) | `api/diff.py:76-119` | `(identifier, from, to, strip)`, **resolved** labels, both pinned | 256 entries | every process restart |
| Release list per title, 5-minute TTL (ADR-0045) | `frontend/src/lib/releasecache.ts:47-110` | title number | TTL only, never evicted | frontend restart; **serves stale for ≤ 300 s after a load** |
| Two frontend limiters (preview 60@5/s, diff 20@1/s) | `frontend/src/middleware.ts:55,70`, `lib/ratelimit.ts` | `context.clientAddress` | 600 s sweep | frontend restart |
| OpenSearch client singleton | `storage/search.py:44-91` | — | — | not data |

Restarts are not rare: `deploy/deploy-on-box.sh:74` recreates `api` and `frontend` on every deploy,
and `deploy/watchdog.sh:145` restarts both after three failed probes. `api/diff.py:84-86` and
`params.py:225-227` each record that their state is per-process and "wrong for a second instance";
those are the two shared-state debts CLAUDE.md carries.

What a cache would skip, measured in-process on this session's fixture corpus (Title 16 at two
release points, so smaller than the box's) against a loopback Redis:

| Call | p50 | p95 |
|---|---|---|
| `SELECT 1` — the cost of reading a generation (§4.2) | 0.12 ms | 0.19 ms |
| `repo.list_releases()` (382 release points) | 4.75 ms | 5.39 ms |
| `repo.list_releases(title_num="16")` | 2.49 ms | 2.96 ms |
| `repo.list_titles()` | 0.58 ms | 1.06 ms |
| `repo.versions("/us/usc/t16/s45f")` | 2.59 ms | 4.30 ms |
| `repo.get_section(…)` | 4.25 ms | 8.37 ms |
| `repo.get_toc("/us/usc/t16/ch1/schVI")` | 3.86 ms | 4.80 ms |
| `repo.neighbors(…)` | 4.16 ms | 5.06 ms |
| `repo.labels(2 identifiers)` | 2.27 ms | 3.44 ms |
| Redis `GET`, 30 KB value | 0.07 ms | 0.11 ms |
| Redis `GET`, 600 B value | 0.06 ms | 0.08 ms |

The deployed numbers (`docs/verification/loadtest.json`, 2026-08-05, from one laptop at 8
concurrent) are dominated by the network: section JSON 129 ms p50, `/releases?ingested_title=16`
319 ms, `/titles` 229 ms, the SSR section page 480 ms for its five API calls, the diff endpoint
5,125 ms before ADR-0066's memo and 1.8 ms after it. ADR-0047 measured the spine at 221 ms of
origin inside an 823 ms journey and declined a shared cache in front of it on that basis. Nothing
here contradicts that measurement. What it did not weigh is the other column of the table above:
the state that is lost on every restart, wrong for a second instance, and — for the release list
— already serving stale answers.

## 4. The invalidation design

### 4.1 Why not a TTL, and why not eviction groups

A TTL is a promise to be stale for at most *n* seconds. The release cache is the existing example.
The SDK's `eviction_group` / `delete_group` is invalidation by enumeration: every cached entry is
tagged with the groups it belongs to, and the writer deletes the groups it knows it affected. A
route that someone forgets to tag, or a write path that someone forgets to teach, is stale until
its TTL — silently, and the corpus is exactly the kind of data where a silently stale page looks
perfectly well-formed (ADR-0018's own words).

### 4.2 A corpus generation, read from Postgres first

One row, `corpus_state (id = 1, generation bigint)`. Every table the API reads for corpus data
carries a **statement-level `AFTER INSERT OR UPDATE OR DELETE` trigger** that runs
`UPDATE corpus_state SET generation = generation + 1`. The bump is therefore inside the writer's
own transaction, and no writer can forget it — the same reason ADR-0018 attached `no-store` to
routers rather than routes.

The API reads the generation as the **first statement of the request**, through the repository
(`Repository.corpus_generation() -> int`, one new method on the protocol, implemented in
`PostgresRepository` with `SELECT generation FROM corpus_state`). Every cache key is prefixed with
it: `usc:g{generation}:…`. A write orphans every existing key at commit, and orphaned keys expire
on their TTL.

Why this is airtight, stated for the reviewer: under `READ COMMITTED` each statement sees the data
committed before it began. If the generation read returns *G*, every later data read in that
request sees a state at least as new as *G*'s. An ingest commit between the two moves the
generation to *G+1* and the request may compute from the newer data, but it stores that under
*G*, a key no later request will ask for — harmless. A request that read *G* and computed from
*G*'s data stores a value that is correct for *G*; a later request asks for *G* only while the
generation is still *G*, that is while no write has committed. There is no ordering of reads and
commits under which a key is served after the state it was computed from has changed. The
generation must be read *before* the data, never after; the dependency order in FastAPI gives that
for free.

The cost is one round trip to Postgres on every request, hit or miss — 0.12 ms here, and it keeps
the database pool in the request path, so ADR-0073's `pool_timeout` 2 s shedding still governs.
That is the price of the guarantee and it is worth stating that no design without a consistent read
gets the guarantee: a generation held in Redis and bumped by ingest *after* commit has a
commit-to-bump window in which a request can compute old data and store it under the current
generation; bumping *before* commit is worse (a request computes pre-commit data under the new
generation). Redis holds nothing authoritative in this design, so a Redis restart is a cold cache
and never a wrong one.

### 4.3 What bumps, and how often

Tables with the trigger: `release_points`, `titles`, `title_versions`, `sections`,
`section_versions`, `section_release_map`, `guid_map`, `structure_nodes`,
`section_version_changes`, `section_version_change_laws`, `classification_files`,
`classification_entries`, `ecct_entries`, `classification_source_checks`, `source_checks`.
Excluded: `users`, `sessions`, `watchlists`, `login_attempts`, `user_settings` — everything under
`no-store`, which is never cached.

A `load-all` that loads something bumps once per batch statement — thousands of times over
a title — and the cache is effectively empty for the duration. That is the correct behaviour under
the contract; loads happen when OLRC publishes, a few times a month, at 06:41 UTC. The daily poll
that finds nothing writes one `source_checks` row and bumps once; a `--force` sweep with nothing to
load runs `version-changes` as a skip scan and writes nothing. Two ingest transactions bump the
same row and the second waits on the first's row lock until it commits; `update-corpus.sh`
serialises its steps under `flock` already (`:74-78`), and `deploy-on-box.sh` runs
`alembic upgrade head` under the deploy lock.

**Per-family generations** (one counter each for text, structure, annotations, classification, so a
classification load does not empty the section cache) are the obvious refinement and are declined
for the first build: a route has to declare which families it reads, and a wrong declaration is a
stale route. One counter cannot be wrong. Revisit if a measured hit rate says the daily bump
matters.

### 4.4 The frontend gets the generation as a header

Every API response carries `X-Corpus-Generation: G` — the dependency has already read it. The
Node reader keys its release-list memo on `(title, generation)` instead of on time: the section
response it fetched first carries the header, and the memo is consulted with it. `TTL_MS` goes;
what bounds the map is the count of titles, and entries under an old generation are evicted when
a newer one is seen. The reader then serves the picker stale for zero seconds rather than 300. The
same header lets `preview/[...identifier].ts` and any future reader-side memo key on a fact rather
than a clock.

### 4.5 What was declined

- **Redis server-assisted client-side caching** (`CLIENT TRACKING`): invalidates on Redis writes,
  and Redis here is never written by ingest. It would be a second cache in front of the first with
  no new guarantee.
- **`s-maxage` + purge hooks in Caddy**: ADR-0047 declined it and nothing has changed. Caddy has no
  cache; this design needs none of it.
- **Postgres `LISTEN/NOTIFY`** to push the generation into the API processes: removes the 0.12 ms
  read at the cost of a listener thread per process and a reconnect story. Not worth it at this
  size.

## 5. What gets cached

### 5.1 Response-level, in `api/`

A dependency `cached_response(name)` on the routes below. Hit: `GET usc:g{G}:{name}:{canonical
query}` returns the stored `(status, headers, body)` and the handler does not run;
`Cache-Control`, `ETag`, `Vary`, `X-Release-Point`, `X-Served-From` and `X-Release-Caveat` come
back exactly as the origin wrote them, so ADR-0018's policy is preserved byte for byte and a
pinned diff stays `immutable` while an unpinned section stays `max-age=300`. Miss: the handler
runs; the response is stored with `SET … NX EX ttl`. Only `200` responses are stored; a 304 is
answered from the stored `ETag` by the existing `If-None-Match` code path.

| Route | Why | Key beyond the generation | TTL |
|---|---|---|---|
| `GET /api/v1/releases[?ingested_title=]` | the slowest unlimited route on the box (319 ms p50); one answer per title; every section page wants it | `title` | 7 d |
| `GET /api/v1/titles` | the front page; one answer | — | 7 d |
| `GET /api/v1/sections/{id}/versions` | one row set per section; `n` queries; read by the section page and the versions page | identifier | 7 d |
| `GET /api/v1/us/usc/{structural identifier}` (a TOC) | `structure_nodes` is unversioned, so today it can only be `max-age=300`; under the generation it is safe to hold server-side for as long as nothing loads | identifier, resolved release | 7 d |
| `GET /api/v1/classifications/*` lists | paged listings over 144,837 rows; change only on a classification load | path, canonical query | 7 d |
| `GET /api/v1/labels?…` | batched, up to 100 identifiers, fanned out per section page | resolved release, sorted identifiers | 7 d |

Not cached: the **section route** itself (one query, 4 ms, a real ETag already; the reader's copy
is the browser's), `search` (OpenSearch has its own cache and the query space is unbounded),
`citation` (a parse), anything `no-store`.

The dependency lives in `api/cache.py` and may not import SQLAlchemy
(`test_only_storage_writes_sql`); it reaches the generation through `RepositoryDep`. The Redis
client lives in `storage/cache.py` beside `storage/session.py`, exposed as a FastAPI dependency
the way `get_repository` is, and `storage/` may not import `params` or `api`
(`test_storage_does_not_import_the_api`) — the constant strings it needs are its own.

### 5.2 The diff memo

`api/diff.py`'s `cached_diff_ops` becomes two-tier: the 256-entry LRU in front, Redis behind it
under `usc:g{G}:diff:{identifier}:{from}:{to}:{strip}`, value the JSON `DiffOp` list, TTL 30 d. A
pinned pair is immutable in the sense of ADR-0018 and *also* keyed on the generation, so a
re-load of a title-release with a changed parser — the one way a pinned text can change — cannot
serve a memo computed from the old text. A deploy or a watchdog restart no longer costs 5 s per
first comparison.

### 5.3 The rate limiters

The seven API limiters and the two frontend limiters move to one Lua token bucket, run with
`EVALSHA`, one key per `(limiter name, caller address)`:

```lua
-- KEYS[1] = usc:rl:{name}:{addr}   ARGV = capacity, per_second, now_ms
local b = redis.call('HMGET', KEYS[1], 'tokens', 'updated')
local tokens = tonumber(b[1]) or tonumber(ARGV[1])
local updated = tonumber(b[2]) or tonumber(ARGV[3])
tokens = math.min(tonumber(ARGV[1]), tokens + (tonumber(ARGV[3]) - updated) / 1000 * tonumber(ARGV[2]))
local retry = 0
if tokens < 1 then retry = math.max(1, (1 - tokens) / tonumber(ARGV[2])) else tokens = tokens - 1 end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated', ARGV[3])
redis.call('PEXPIRE', KEYS[1], math.ceil(tonumber(ARGV[1]) / tonumber(ARGV[2]) * 1000))
return retry
```

Same capacity, same refill, same ceil-to-a-whole-token `Retry-After` as `params.py:284-296`, so
`docs/verification/loadtest.json`'s "over budget" rows measure the same thing. The key's expiry is
the time a bucket takes to refill — the sweep rule `_sweep` implements, done by Redis. **On a
Redis error the limiter falls back to the process-local bucket and logs once**: a limiter that
fails closed turns a cache outage into a site outage, which is the shape ADR-0073 was written
against. The frontend's two limiters use the same script from Node (`ioredis` is already in
`frontend/package-lock.json` as a transitive dependency; it becomes a direct one).

### 5.4 Sizes and memory

A section JSON body is ~30 KB uncompressed (7.5 KB on the wire); a release list ~15 KB; a
versions payload 1.5–60 KB. None of the cached routes is per-section-per-release except `labels`
and the TOC, and both are bounded by what readers actually open. `maxmemory 256mb`,
`maxmemory-policy allkeys-lru`, no persistence (`--save "" --appendonly no`): the cache is
reconstructible and a restart is a cold start. The t4g.large has 8 GB; Postgres and OpenSearch
are the tenants that matter.

## 6. Deployment

- `docker-compose.yml` and `docker-compose.prod.yml` gain a `redis` service (`redis:7-alpine`,
  `expose: 6379`, the flags above, a `redis-cli ping` healthcheck), on the compose network only.
- `db/config.py` declares `redis_url: str | None = None`. Unset means **no cache, no shared
  limiter, and every test still passes** — the site runs as it does today. CI adds one job with a
  Redis service so the cached paths are exercised.
- Migration: `corpus_state` seeded at generation 1, and the fifteen triggers. `alembic downgrade`
  drops them.
- `main.py` gains a lifespan that opens and closes the pool; `/health` reports
  `redis: ok | unavailable | disabled` without failing on it, since `deploy/watchdog.sh` probes
  `/health` and a cache outage must not trigger a restart loop.
- `deploy/deploy-on-box.sh` needs nothing new: the migration runs before the stack comes up, and a
  recreated `api` container reconnects.

## 7. Tests

- **Architecture:** `api/cache.py` imports no SQLAlchemy; `storage/cache.py` imports no `api`; the
  protocol gains `corpus_generation` and the Postgres implementation has it (the existing
  agreement test covers that automatically).
- **The contract, as a property:** on the fixture corpus, warm `/api/v1/titles`; in a second
  connection insert a `titles` row and commit; the next `GET` must show it. Repeat for
  `structure_nodes` → a pinned TOC, and for `title_versions` → an unpinned section's
  `X-Release-Point`. Each is the test that would have caught the release cache's five minutes.
- **The limiter:** the Lua bucket against `tests/test_rate_limit.py`'s existing cases, plus the
  fallback: with `REDIS_URL` pointing at a closed port, every limited route answers as it does
  today.
- **The reader:** `releasecache.test.ts` keyed on generation, no timers.
- **Ratchets:** `/health`'s new field appears in the API docs; no reader route is added, so the
  guide ratchet, the a11y matrix and the JS budgets are untouched.

## 8. Measurement before and after

`docs/verification/loadtest.json` is stale on every axis CLAUDE.md lists and is the artifact to
regenerate first, so there is a before. After R2: the same run, plus a `make cachecost` target
that reports hit and miss latency per cached route and the hit rate over a scripted reader session
(the guide's demo scenarios are a ready-made one). The number to publish is the SSR section page
at 8 concurrent, 480 ms p50 today with five API calls behind it.

## 9. Phases and model assignment

| Phase | Work | Model | Why |
|---|---|---|---|
| R1 | `corpus_state`, triggers, `Repository.corpus_generation`, `X-Corpus-Generation` on every response, the reader's release memo keyed on it | Opus 5 | schema and protocol change; small, but the guarantee in §4.2 rests on getting the order of reads right, and it is the piece a reviewer must be able to follow |
| R2 | `storage/cache.py`, `api/cache.py`, the six routes, `/health`, compose, CI job | Opus 5 | well-specified; mostly plumbing |
| R3 | Lua bucket for the nine limiters with fallback; the two-tier diff memo | Opus 5 | the semantics are pinned by existing tests |
| R4 | `make cachecost`, regenerate `loadtest.json`, the ADR | Opus 5 | measurement and writing |
| Review | fresh-context read of R1's diff against §4.2 before R2 starts | Fable 5.1 | the one place a subtle ordering bug would be silent |

Total: four small PRs. R1 is worth doing on its own even if R2–R4 wait: it costs one table, one
header and one changed memo, and it retires the only stale-serving cache the site has.

## 10. Relation to ADR-0047

ADR-0047 declined a shared cache *in front of* the spine because the origin was 27% of a
reader's journey and the box was idle. This spec is not that proposal: it is origin-side, keyed on
a fact rather than a clock, and aimed at the routes whose origin cost is real, the state lost on
every restart, and the two shared-state debts a second instance would call in. ADR-0047's own
revisit conditions are a CDN, a second instance, or throughput; R1 stands without any of them,
and R2–R4 wait for one.
