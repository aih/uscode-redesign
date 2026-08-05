# ADR-0047: Do not put a shared cache in front of the spine

**Date:** 2026-08-04 · **Status:** Accepted · **Implements:** Workstream B task B3, fix 1 — declined

## Context

B3's first fix reads: *"Cache the spine. Title list, chapter TOCs and section pages at the newest
release are the hot path and change only when OLRC publishes (ADR-0036 already knows when that is).
Audit ADR-0018's cache policy against reality; give the spine long `s-maxage` with explicit
invalidation keyed to the load chain, and let Caddy serve it."*

B3 also says to stop when the numbers are good enough. These are the numbers.

**The audit of ADR-0018 found nothing wrong.** Checked live against the deployed host by
`scripts/loadtest.sh`, which now re-verifies it on every run rather than restating it:

| response | `Cache-Control` |
|---|---|
| pinned, `?release=119-102not101` | `public, max-age=31536000, immutable` |
| unpinned | `public, max-age=300` |
| a table of contents, even pinned | `public, max-age=300` |

That is exactly ADR-0018's table, including ADR-0043's rule that `structure_nodes`-backed responses
revalidate because the data behind them is unversioned. The headers a shared cache would read are
already correct.

**What is missing is a shared cache to read them.** Caddy has no built-in cache; adding one means a
plugin and a custom Caddy build. And `deploy/Caddyfile` already says why it holds none — the
`Cache-Control` decision belongs to the origin, and the immutable headers are what a CDN in front
would read *if one is ever added*.

**The origin is not the constraint.** From `docs/verification/navprofile.json`, warm p50 for a
reader's four clicks down the spine: **823 ms total, of which 221 ms is the origin and 601 ms (73%) is
the network** — TLS handshake on the first request, then one round trip per click. Postgres is under
2 ms per repository call. A cache sitting on the box removes origin time, which is the 27%.

## Decision

**Do not build a caching layer in Caddy, and do not add `s-maxage` with an invalidation hook.**

The two changes B3 proposes are separable, and both are declined for the same measurement:

1. *A cache in Caddy* would need a plugin, a custom image, and an invalidation path wired to the load
   chain — against a 221 ms origin inside an 823 ms journey, on a box idling at load average 0.03.
2. *`s-maxage` with explicit invalidation* is a header for a shared cache that does not exist. Adding
   a directive nothing reads, plus the machinery to invalidate through it, is code with no behaviour
   until someone puts a CDN in front.

**The thing that would actually move the 601 ms is a CDN**, which cuts round-trip time by terminating
near the reader. That is a deployment decision — ADR-0020's territory, and a change to the DNS and
certificate story — not a code change. When it happens, the headers are already right for it, and
`s-maxage` plus invalidation becomes worth having on that same day.

## Consequences

**The spine keeps being computed per request.** Every reader page costs the box an SSR render and, at
present, three API calls. That is affordable at this traffic (48 human requests an hour, ADR-0037) and
is not affordable at a much larger one; this ADR is scoped to the former.

**The measurement that justifies this is a single vantage.** `navprofile.json`'s edge numbers are one
laptop on one network to `us-east-1`. A reader much closer to the box would see the network share fall
and the origin share rise, and this decision with it. The origin-side numbers are the transferable
ones, and they say the origin is fast.

**Two cheaper things were done instead**, from the same measurement: ADR-0045 removes the release list
from the per-view fan-out, and the `structure_nodes.identifier` index (migration `d5c81f27a930`)
removes the only sequential scan on the spine.

**Revisit when any of these changes:** a CDN goes in front; a second instance appears; or the reader
page's throughput under concurrency (measured at 11.0 rps, 702 ms p50 at 8 concurrent) stops being
enough.
