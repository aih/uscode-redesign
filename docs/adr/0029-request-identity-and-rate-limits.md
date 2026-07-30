# ADR-0029 — Request identity, and rate limits that rest on it

- **Status:** Accepted
- **Date:** 2026-07-30
- **Context:** Session 13, cleanup phase 1 (S1, S2, S4, S5); `docs/cleanup-plan.md`
- **Amends:** ADR-0019 (login throttle), which assumed a trustworthy client address

## Context

Five ADRs — [0016](0016-diff-two-release-points.md),
[0020](0020-deploy-single-box-ec2-caddy.md),
[0024](0024-reference-previews-render-server-side.md),
[0026](0026-diff-the-reading-text-not-the-xml.md),
[0028](0028-keyword-search-opensearch-current-by-default.md) — plus
`docs/deploy.md` and `docs/verification/loadtest.json` each say some route "must
be rate-limited before the URL is advertised". None of them implemented it, and
deploy is the declared next step.

These are one subject, not two, and that is why they are one ADR: **you cannot
limit by client until you can identify the client.** A limiter keyed on a value
the caller chooses is not a limiter, it is a formality. So the identity question
has to be settled first, and settling it turned up a live hole.

### The hole

`api/auth.py`'s per-IP login throttle (ADR-0019) rests on `request.client.host`,
which uvicorn fills from `X-Forwarded-For`. Both compose files start uvicorn with
`--forwarded-allow-ips "*"`, and in that mode its proxy-headers middleware
returns `x_forwarded_for_hosts[0]` — the **leftmost**, entirely client-supplied
value (`uvicorn/middleware/proxy_headers.py:176-177`). The reverse scan that
finds the first untrusted hop runs only when trust is *not* `*`. Astro's Node
adapter reads the leftmost value too, unconditionally
(`astro/dist/core/app/node.js:121-122`), so both surfaces share the shape.

`api/auth.py:85-95` documented the exact opposite.

The mechanism needed measuring rather than assuming, and measuring it corrected
the first account of it (`docs/verification/xff.md`). Caddy does **not** simply
append: it preserves an inbound `X-Forwarded-For` only from a peer that is a
*trusted proxy*, and replaces it otherwise. `deploy/Caddyfile`'s global block
sets `trusted_proxies static private_ranges` — for `X-Forwarded-Proto`, which
decides the `Secure` cookie — and the effect is that any peer on a private
network is trusted to name its own client:

| `trusted_proxies` | `header_up` | `curl -H 'X-Forwarded-For: 1.2.3.4'` |
|---|---|---|
| unset | absent | `192.168.65.1` |
| `static private_ranges` | absent | **`1.2.3.4, 192.168.65.1`** |
| `static private_ranges` | `{remote_host}` | `192.168.65.1` |

So `MAX_FAILURES_PER_IP = 50` fell to a rotating header — defeating precisely
the credential-stuffing case ADR-0019 wrote it for — and `login_attempts.ip`, an
unbounded `String`, became an attacker-controlled write.

**The exposure was narrower than "always", and the ADR says so rather than
overstating its own finding.** Facing the internet directly, as ADR-0020 deploys
it, client peers are public addresses: outside `private_ranges`, untrusted, so
Caddy already discarded what they sent. What was exposed is the dev stack and
any shape with a CDN, load balancer or sidecar in front — which ADR-0018
explicitly anticipates. A latent hole in the deployment most likely to come
next, not a live one in the deployment that exists.

### What the routes cost

- `POST /api/v1/auth/signup` — unthrottled argon2id at defaults: **64 MiB and 4
  threads per request**, plus a durable `users` row. The login throttle does not
  cover signup.
- `GET /api/v1/sections/{id}/diff` — `api/diff.py` sets `Diff_Timeout = 0`,
  deliberately removing diff-match-patch's only runtime bound. Measured at
  ~0.45 rps, failing entirely past ~10 concurrent.
- `GET /api/v1/search` — `offset` was bounded below but not above, so deep paging
  past OpenSearch's `max_result_window` both throws and pressures the heap.
- `GET /api/v1/labels` — `identifier: list[str]` with no bound, fanning into one
  `IN (...)`.
- `/app/preview` and `/app/diff` — server-rendered in the frontend process.

The amplifier: every handler under `api/` is a sync `def`, so all share
Starlette's 40-slot threadpool. Saturating it stalls `/health` and every read
route, which turns "an expensive endpoint" into "an outage". Node is worse — one
event loop, and both reader routes occupy it synchronously.

## Decision

**1. The proxy decides who the caller is.** `deploy/Caddyfile` sets
`header_up X-Forwarded-For {remote_host}` in **both** handle blocks, which
overwrites rather than appends. Nothing a caller sends survives to be read.

This is the right layer for a reason worth naming: it is one line per hop, it
fixes both backends at once, and it does not depend on the `trusted_proxies`
setting staying as it is — a setting that lives in a different file from the code
relying on it. Narrowing `--forwarded-allow-ips` to a literal CIDR was rejected:
Docker assigns the compose network's range and it changes.

Any deployment putting something else in front must do the same. That is a real
obligation and it is written down here because it is invisible from the code.

**2. Token buckets, in the two places that can see a caller.** `params.py` gets
`rate_limit(name, capacity, per_second)`, a dependency factory returning 429 with
`Retry-After` — reusing the shape ADR-0019's login throttle established, so a
caller meets one error surface rather than two. It lives in `params.py` because
that module already owns what the surfaces share (`public_cache`, `no_store`,
`cookies_are_secure`) and because `api/` and `citation.py` may not import each
other (ADR-0010).

`frontend/src/middleware.ts` gets the same algorithm over
`frontend/src/lib/ratelimit.ts` — in `lib/` because that is where this project
puts logic it intends to test.

| Route | Burst | Sustained | Sized for |
|---|---|---|---|
| `/api/v1/auth/signup` | 10 | 30/hour | a person |
| `/api/v1/sections/…/diff` | 5 | 12/min | a person |
| `/api/v1/search` | 120 | 10/s | a server |
| `/api/v1/labels` | 300 | 30/s | a server |
| `/api/v1/citation` | 120 | 10/s | a server |
| `/app/preview` | 60 | 5/s | a person |
| `/app/diff` | 8 | 30/min | a person |

**3. The reader's server-side calls share one bucket, and the limits admit it.**
`frontend/` renders on the server and calls `/api/v1` over HTTP, so every
reader's page view arrives at `/labels`, `/search` and `/citation` from the
frontend container's single address. Those three are therefore sized for a
server and bound fan-out rather than people. The per-person limit for readers is
in the Astro middleware, where the browser's own address is visible. The routes a
browser calls directly (signup) and the ones the reader never calls (diff — ADR-0026
moved the reader onto its own text redline) are the tight ones.

**4. Bound the inputs too**, since a limit on rate is not a limit on size:
`max_length=100` on the labels list, `le=1000` on search `offset`, and
`min_length=1, max_length=500` on the search query.

**5. Stop leaking the cluster into error bodies.** `api/search.py` returned
`f"Search failed: {e}"` — the raw opensearch-py exception, carrying internal
hostnames, ports and index names, to any stranger. The exception goes to the log;
the caller gets a status and a fixed sentence.

**6. OpenSearch stops being configured by default.** `storage/search.py`
hardcoded the dev password as a default and sent admin credentials with
`verify_certs=False, ssl_assert_hostname=False`, while
`docker-compose.prod.yml` had **no `opensearch` service at all** — so a deploy
would have pointed at `https://localhost:9200` with a password published in this
repository. Now: no default (raise `SearchNotConfigured` instead), TLS verified
unless `SEARCH_VERIFY_CERTS=false` says otherwise, the dev password moved to
`.env`, and the service added to the production stack. Hostname assertion follows
`verify_certs` rather than being a separate knob, because verifying a certificate
without checking who it was issued for verifies almost nothing.

`get_search_client()` also became a module-level singleton; it was building a
fresh client, pool and TLS handshake on **every request**.

## Consequences

**The state is per process.** Honest for ADR-0020's single box, wrong for a
second instance, which would need shared state (Redis, or the limit moved into
the proxy). Recorded here rather than discovered later.

**A shared address is one bucket.** An office or campus behind one NAT is one
caller, which is why the signup limit is 30/hour and not 3 — the same reasoning
that makes `MAX_FAILURES_PER_IP` so much larger than the per-email limit.

**`verify_certs` is false in `docker-compose.prod.yml`, deliberately.** The
OpenSearch image generates its own self-signed certificate at first boot, so a
stack brought up from that file as written cannot verify it, and a default of
true would mean production search fails closed on day one. The connection is
between two containers on a private network with no published port, so the
residual risk is an attacker already inside the host. That cost is accepted *in
that file, for that deployment* — not in `storage/search.py`, where it used to
apply to every environment forever.

**Ingest tolerates an unconfigured cluster.** Removing the default meant client
construction can now raise, outside the try blocks that already treated a failing
cluster as a warning. `ingest/search_sync.py` catches `SearchNotConfigured` and
warns once, so forgetting `SEARCH_PASSWORD` degrades a stale index rather than
failing a corpus load.

**Not done here:** CSP nonces, which want this middleware and are
[ADR-0030](0030-browser-security-headers.md)'s stated follow-up. Shared-state
limiting. Per-account limits — these are all per-address, so a logged-in abuser
gets no separate budget.

## Verification

- `tests/test_rate_limit.py` — the limits, asserted rather than got out of the
  way of; `tests/conftest.py` empties every bucket between tests.
- `tests/test_auth.py` — a forged `X-Forwarded-For` does not open a fresh
  throttle bucket, and nothing a caller sends reaches `login_attempts.ip`.
- `frontend/tests/ratelimit.test.ts` — burst, refill rate against an injected
  clock, per-caller isolation, an obeyable `Retry-After`, and that the sweep
  forgets refilled buckets without handing a spent one a fresh burst.
- `docs/verification/xff.md` — the proxy measurement above, reproducible.
- `git grep Usc0deSearch` finds the credential in `.env.example` only.
