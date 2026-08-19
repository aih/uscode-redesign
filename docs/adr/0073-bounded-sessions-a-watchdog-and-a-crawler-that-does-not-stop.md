# ADR-0073 — Bounded sessions, a watchdog, and a crawler that does not stop when asked

**Status:** accepted (2026-08-19)

**Task:** Day 7 hardening — the site was down for about ten hours and nothing said so.

**Amends:** ADR-0037 (`Disallow: /`, which is advisory and was ignored); ADR-0029 (which limits
per caller, and this traffic was not one caller).

## Context

`https://uscode.linkedlegislation.org` served nothing from roughly 12:00 to 22:15 UTC on
2026-08-19. TCP connections were accepted, so the outage looked like a hang rather than a refusal;
every request timed out after 25 seconds with no bytes returned.

The box was fine. Load average 0.73 on 2 vCPUs, 44% of the root volume, 37% of the data volume,
2 GB of memory free and 6 GB of swap barely touched, the api container at 2.1% CPU and Postgres at
0.0%. All six CloudWatch alarms read `OK` for the entire outage, and continued to.

Three measurements found it:

- The api container's Docker healthcheck had a **failing streak of 2,710** — about ten hours at one
  probe every thirteen seconds. Its only effect was the word `unhealthy` in `docker ps`.
- Its log was one repeated exception:
  `QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00`.
- `pg_stat_activity` showed **fifteen backends `idle in transaction`**, every one waiting on
  `ClientRead`, the oldest for 8m43s — the whole pool, held by requests whose clients had gone.
  One backend was `active`. Postgres was not busy; it was being held.

The traffic behind it was a crawl. In the hour before the fix, **7,155 of 7,172 requests were
Meta's `meta-externalagent`**, spread over about sixty addresses in `57.141.0.0/24` at roughly two
requests per minute each. It was walking the `?release=` axis — the same ~25-million-page
permutation space ADR-0037 measured ClaudeBot and GPTBot walking. It had fetched `/robots.txt`
**21 times in 24 hours**, received `Disallow: /`, and carried on.

The individual pages were never slow. Measured after recovery, against the same URLs it was
requesting: 0.42s, 0.74s, 1.01s, 0.33s. Nothing here is a performance problem.

### How a busy minute became a ten-hour outage

The pool was SQLAlchemy's untouched default — 5 connections, 10 overflow, a 30-second wait. Two
requests a second of multi-call reader pages sits close to that. Once demand crossed it, three
properties turned a temporary shortage into a permanent one:

1. A request that got a connection, ran its query, and then could not finish writing its response
   to a client that had gone **kept its transaction open**. FastAPI closes a dependency's session
   after the response is sent, so a response that is never sent is a session that is never closed.
   Nothing on either side timed that out, and Postgres will hold `idle in transaction` forever.
2. A request that could not get a connection waited **thirty seconds** — longer than the proxy was
   willing to wait — occupying a worker on behalf of a client already given up on.
3. Nothing acted on any of it. The healthcheck observed, the alarms watched the box, and the box
   was healthy throughout.

The result is self-sustaining: it does not recover when the load stops, because the connections are
not held by load, they are held by transactions nobody will ever close.

## Decision

### 1. `Disallow: /` is enforced at the proxy for agents that ignore it

`deploy/Caddyfile` matches declared crawlers on User-Agent and answers 403 before either backend or
the database is reached. This is enforcement of the policy ADR-0037 already stated rather than a new
policy: the robots.txt beside it has said `Disallow: /` to every agent since 2026-08-03.

Matching is on the User-Agent because that is what a crawler volunteers, and forging it is not
defended against — an agent that lies about being a crawler is indistinguishable from a reader, and
everything below is what holds in that case. Measured twice now, self-declared crawlers are all of
the traffic that has actually knocked this site over.

Per-caller rate limiting (ADR-0029) is not the tool here and would not have helped: at two requests
per minute per address, across sixty addresses, no per-IP bucket ever fills. The aggregate was the
problem and no single caller was.

### 2. An API session cannot hold a connection indefinitely

`storage/session.py` sets `statement_timeout` (20s) and `idle_in_transaction_session_timeout` (30s)
on every request-scoped session. The second is the direct answer to the fifteen held backends:
Postgres now ends that state itself, the pool reclaims the connection, and the site degrades under a
crawl instead of stopping under one.

Both are set with `set_config(..., true)` — `SET LOCAL`, scoped to the transaction — and applied
from an `after_begin` listener on a sessionmaker belonging to storage. Two boundaries make that the
shape:

- **Ingest must stay unbounded.** It shares `db/base.py` in its own process and holds one
  transaction open across minutes of parsing by design. A 20-second statement timeout on a bulk
  load is a corpus that will not load. Setting the bounds on the engine or the connection would
  have reached it; scoping them to the transaction, from storage's own sessionmaker, does not.
- **Laziness is worth keeping.** SQLAlchemy connects on first query, so a request the route rejects
  before it queries anything — an over-long `/api/v1/labels` batch, a malformed identifier — costs
  no connection. Applying the bounds when the session is constructed would have made every refusal
  need a database, which the first draft did and `tests/test_rate_limit.py` caught.

`tests/test_session_bounds.py` asserts all four properties: the bounds are in force, ingest's
sessions are not bounded, the bounds do not follow a connection back into the pool, and each one
actually fires.

### 3. The pool sheds rather than queues

10 connections with 20 of overflow, `pool_pre_ping`, a 30-minute recycle, and a **2-second**
`pool_timeout` in place of 30. The timeout is the change of character: a request that cannot be
served fails while someone is still waiting for it. `pool_pre_ping` stops being optional once
Postgres is terminating backends, since a terminated backend otherwise leaves a dead connection for
the next request to discover.

Pool exhaustion answers **503 with `Retry-After`** rather than 500. Unhandled, SQLAlchemy's
`TimeoutError` is a 500, which says the site is faulty when what is true is that it is full — and a
500 carries no `Retry-After`, so a caller's only guide is how long it feels like waiting.

`--limit-concurrency 64` on uvicorn is the same decision one layer out — past 64 requests in flight,
new ones get an immediate 503 rather than a place in a queue. Caddy gains `dial_timeout` and
`response_header_timeout` on both upstreams, so a wedged backend does not become a growing pile of
held connections at the proxy as well.

### 4. Something watches whether the site answers, and acts

`deploy/watchdog.sh` runs every minute from `/etc/cron.d/uscode`. It probes `/health` and a reader
page through the proxy over the real hostname, publishes `USCode/SiteUp`, and restarts the HTTP
services after three consecutive failures — taking the deploy lock first, so it cannot fight a
deploy, and with a ten-minute cooldown, so a restart that did not help is not tried in a loop.

The `uscode-site-down` alarm is driven by that metric, `Minimum` over five one-minute periods, with
**`--treat-missing-data breaching`**: a box too wedged to run cron publishes nothing at all, and
that is the worst case rather than a quiet one. It is also why the watchdog publishes its metric
before it attempts any repair.

## Consequences

**The alarms now watch the service and not only the machine.** Every alarm this deployment had was
a resource tripwire, which is what ADR-0020 wrote them as ("the do-I-need-to-pay-for-more
tripwires, not a monitoring system"). That was a defensible reading of one demo box right up to the
first outage that used no resources.

**A crawler that forges a browser User-Agent is not blocked**, and is not meant to be. What has
changed is the consequence: the same traffic now meets a pool that sheds, transactions Postgres
ends, a proxy that gives up, and a watchdog that restarts what is left. The site gets slow and
returns some 503s instead of stopping.

**The reader's ordinary section pages are still not rate-limited.** Only `/app/preview/` and
`/app/diff/` are (ADR-0029). Adding a per-IP limit to section pages was considered and rejected for
this traffic specifically — sixty addresses at two requests a minute defeats it — and it would
throttle a reader working through a chapter, which is the behaviour the site is for.

**The watchdog can restart a container that a human was mid-way through debugging.** The deploy
lock covers deploys and nothing else. Running with `PROBE_ONLY=1`, or commenting the cron line, is
the way to hold it off; nothing enforces that.

**A restart is a blunt repair and it is deliberately blunt.** It does not diagnose, and a site that
is down for a reason a restart cannot fix will be restarted once every ten minutes while the alarm
mails someone. That is the trade against ten hours of nothing.

**`--limit-concurrency` makes an overloaded API return 503**, which the reader's server-side fetches
will surface as errors on a page rather than as a slow page. That is the intended shape and it is
the first time this site has had a visible degraded mode.

**The Caddyfile's crawler list needs maintenance** and will always be behind. The generic `bot`,
`crawler` and `spider` markers are there so the next well-behaved-but-unlisted agent is caught
without an edit, and the named list is what makes the common cases greppable.
