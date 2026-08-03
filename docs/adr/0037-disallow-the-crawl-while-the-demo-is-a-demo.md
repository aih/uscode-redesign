# ADR-0037: Disallow the crawl while the demo is a demo

**Status:** Accepted
**Date:** 2026-08-03
**Related:** [ADR-0003](0003-guid-as-version-pin.md) (the URL scheme that makes the
space this large), [ADR-0015](0015-one-origin-two-services-renderer-in-the-frontend.md) (why the file is served from the
proxy), [ADR-0018](0018-cache-immutably-only-when-the-release-point-is-pinned.md) (the caching
that makes a pinned page cheap the *second* time), [ADR-0020](0020-deploy-one-ec2-box-compose-caddy.md)
(the two vCPUs this is about), [ADR-0029](0029-request-identity-and-rate-limits.md)
(per-route throttling, which is not this)

## Context

The site went public with no `robots.txt`. Not a permissive one — none: every request for it
returned FastAPI's 404. That was not a decision anyone made; it is a file nobody wrote.

The URL scheme is the reason this matters more here than it would elsewhere. PLAN §4 and ADR-0003
put every provision at every release point at its own address, deliberately, because that is the
product. The arithmetic of that promise is 65,938 sections × 382 release points ≈ **25 million**
reader pages, and separately 96,185,732 `?id=` guids that each resolve to one. Add `/app/versions`,
`/app/diff` between any two of 382 release points, and `?date=` as a third spelling of the same
axis, and the addressable space is effectively unbounded. Every one of those URLs returns a real
200 with real law in it, so nothing about a crawl of them looks like an error.

One hour of the proxy log, 2026-08-03:

| | |
|---|---|
| requests | **43,068** (~12/s sustained) |
| ClaudeBot | 33,937 (79%) |
| GPTBot | 9,079 (21%) |
| everything from a human browser | **~48** |
| carrying `?release=` | 36,465 (**85%**) |
| requests for `/robots.txt` | 5, all 404 |

99.9% of the traffic was two well-behaved, self-identifying crawlers, and 85% of it had already
found the version dimension. There is no crawl budget that finishes 25 million pages, so this had
no natural end: the box sat at load average 2.06 on 2 vCPUs with essentially nobody reading it.

That is what had `uscode-cpu-credits-low` in alarm — an alarm that had been read as "the box is
undersized for what it is being asked to do", which was true and told us nothing, because the thing
it was being asked to do was serve a crawl of a combinatorial space. On a `t4g` in unlimited mode
the surplus credits are billed, so this was also the one part of the deployment quietly costing
more than the estimate.

ADR-0029's rate limits do not address it. Those bound the expensive *routes* — diff, search,
preview — and are working: only 57 diff requests appear in that hour. The section reader is cheap
per request and was never throttled, correctly, because throttling the thing the site is for would
degrade it for the readers it was built for. The problem is not per-request cost. It is that
nothing had told anyone which requests were worth making.

## Decision

**Serve `/robots.txt` from the Caddyfile, disallowing everything, for now.**

```
User-agent: *
Disallow: /
```

**It is served by the proxy, not by either surface.** `robots.txt` is a property of the host, and
under ADR-0015 the host is owned by one Caddy sitting in front of two independently deployable
services. Serving it there is what makes one answer true for `/app` and `/api/v1` alike, including
for a request that arrives while one of them is restarting — and it means the policy cannot drift
between the two, which it would the moment it existed in a `frontend/public/` file and a FastAPI
route.

**`Disallow: /` is the blunt setting, chosen knowingly and not as the safe default.** The site is a
demo being shown to a specific audience; being discoverable in search is not currently worth
anything, and it is being paid for in surplus CPU credits. Blunt is also the setting that is
correct on the least information: it needs no prediction about which crawler will find which axis
next.

**The shaped version is the one to come back to, and it is a change to one Caddy block.** When the
site should be discoverable — allow the ~66k canonical current-text section pages, disallow the
permutation space (`?release=`, `?date=`, `?id=`, `/app/diff`, `/app/versions`, `/api/v1`). That
keeps what a search engine should have, which is one good page per section, and refuses what no
crawler should be walking. It is recorded here so the return is a decision rather than a discovery.

## Consequences

**Good.** The load has a ceiling again, set by readers rather than by a combinatorial space. The
CPU-credit alarm can go back to meaning what it says. The billing matches the estimate in
`docs/deploy-status.md`. And the site now states a policy where it previously stated nothing, which
is the difference between a crawler behaving well and a crawler guessing.

**Costs, named.**

- **The site is invisible to search, including to conventional search engines.** That is the
  intended effect and it is total: nothing gets indexed, so nobody finds it who was not sent the
  link. For a demo that is the right trade and for a public reference site it would be the wrong
  one, which is why this ADR has a return path rather than a conclusion.
- **`robots.txt` is advisory and binds only the polite.** It works here precisely because the
  measured traffic is two crawlers that declare themselves and honour it. A crawler that ignores it
  is unaffected, and nothing in this ADR is a defence against one; that would be rate limiting or
  blocking at the proxy, and neither is warranted by anything measured.
- **It takes effect on the crawlers' schedule, not ours.** `robots.txt` is typically cached for up
  to 24 hours, so the traffic decays rather than stopping.
- **A `Disallow` is not an access control and must never be read as one.** Every URL still resolves
  to exactly what it did before. This governs crawling, and nothing else — the security posture is
  ADR-0029 and ADR-0030, unchanged.
- **The measurement window was one hour, on one day.** It is enough to establish the shape (two
  crawlers, the version axis, three orders of magnitude more bot traffic than human) and not enough
  to characterise seasonal behaviour. Nothing here depends on the precise ratio.
