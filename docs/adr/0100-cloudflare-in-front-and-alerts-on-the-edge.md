# ADR-0100 — Cloudflare in front of the reader, and alerts on what the edge sees

**Status:** accepted (2026-11-24)

**Related:** ADR-0088 (the cookie gate), ADR-0090 (alert rules as code), ADR-0097 (the edge's access
log in Grafana), ADR-0098 (landing pages open to Google and Bing), the statutes repository's
ADR-0042 (the edge's side of this decision).

## Context

ADR-0088 recorded what the cookie gate leaves open: a scraper that keeps cookies. The edge log
(ADR-0097) shows one. In 06:30–08:00 UTC on 2026-11-24, 62,725 requests reached the site, every one
with an ordinary Chrome or Firefox User-Agent, almost all from ISP networks in more than ten
countries, with more than 500 distinct addresses in a single ten-minute window. After the gate's 403
the next request names the gate page as its referer, so the client runs the reload script and keeps
the cookie. Reader pages served went from 103,189 a day (2026-11-17) to 234,532 (2026-11-23), reader
5xx from 184 to 3,783 a day, and the API's weekly requests from 310,761 to 1,579,133 in two weeks.
`uscode-site-down` fired 07:05–07:59 UTC on 2026-11-24, during a burst of 27,180 requests to the gate
in ten minutes.

The "Traffic spike" rule fired 18 times on `uscode-api` in five weeks, mostly at 2.3–3.1 requests a
second: its 2/s floor was below the week's average of 2.6. The reader's 5xx never reached the
"Server errors" rule, which reads the API's metrics, and the API returned none.

## Decision

1. Cloudflare proxies `uscode.linkedlegislation.org` with a Managed Challenge on `/app` (except
   `/app/healthz`) for clients outside Cloudflare's verified-bot list. `/api/v1` and the citation URL
   `/us/usc/…` are not challenged. The edge trusts Cloudflare's ranges for `CF-Connecting-IP` and
   refuses the hostname to public peers outside them. The edge and the Cloudflare steps belong to the
   statutes repository (`deploy/edge/README.md`, its ADR-0042), since that repository owns the edge.
2. This repository's cookie gate, crawler 403 and per-caller limits stay. Behind the edge they see
   the client address Cloudflare names.
3. "Traffic spike" needs over 8 requests a second, as well as three times the same ten minutes a week
   earlier.
4. "Reader errors" reads the edge log: over 5% of reader requests past the 403s answering 5xx, at over
   300 requests in ten minutes, for ten minutes. Measured over the 24 hours to 11:30 UTC on
   2026-11-24, the share ran 0.3% to 7.9% in half-hour samples.
5. All rules use `execErrState: KeepLast`: a failed query keeps a rule's state, so an outage on
   Grafana's side no longer mails as a site failure.

## Consequences

- `apply.py` finds the stack's logs data source and leaves out a rule that reads it when there is
  none.
- Until Cloudflare is in front, "Reader errors" fires while the crawl lasts.
- A reader may see Cloudflare's challenge page before the first page.
- A crawler that solves Cloudflare's challenge is not covered. Cloudflare's rate-limiting rule is
  the next step if one does.
