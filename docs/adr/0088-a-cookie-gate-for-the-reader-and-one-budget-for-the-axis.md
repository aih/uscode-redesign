# ADR-0088 — A cookie gate on the reader, and one budget for the permutation axis

**Status:** accepted (2026-09-20)

**Builds on:** ADR-0029 (per-caller rate limits), ADR-0037 (`Disallow: /`), ADR-0073 (declared
crawlers get 403; pool and timeout bounds), ADR-0086 (the log and disk limits from the last
incident).

## Context

The site was down for about four hours on 2026-09-19 — 232 consecutive failed watchdog probes,
`api=000 app=000`, ending 14:22 UTC — and has been failing single probes every hour or two since.
`uscode-cpu-credits-low` has been in alarm since 15:37 PT on 2026-09-19. The box's CPU credit
balance is empty, so a t4g.large is throttled to its 30% baseline, and the reader's renders queue
behind that.

One hour of this project's proxy log, 2026-09-20 12:22–13:22 UTC:

| | |
|---|---|
| requests | 15,307 |
| distinct client addresses | 11,835 (1.3 requests each) |
| distinct /16s | 3,758 |
| carrying `?release=` or `?date=` | 12,895 (84%) |
| `/app` requests | 14,400 |
| `/app` requests carrying a `Cookie` header | **0** |
| asset requests (`/_astro`, fonts, icons) | **21** |
| `Accept: */*` with no `Sec-Fetch-*` headers | 9,726 |
| top two /16s (47.82, 47.79) | 25% |

Every request presented a plausible Chrome `User-Agent`. This is the same ~25-million-page
permutation space ADR-0037 and ADR-0073 measured being walked, now behind a rotating address pool.

Neither existing control can see it:

- **ADR-0037's crawler list** matches a `User-Agent` that declares itself. Nothing here declares
  anything.
- **ADR-0029's per-caller budgets** key on the address. At 1.3 requests per address, every bucket
  they met was full. A per-caller limit cannot be set low enough to matter without refusing
  the first request from every real reader.

What separates this traffic from a reader is not the address and not the `User-Agent`: it is that
it keeps no cookies and fetches no assets. 0 of 14,400 is not a ratio that needs a threshold.

## Decision

### 1. The reader is served only to a client that carries a cookie

`deploy/Caddyfile` answers a request for `/app*` with no `usc_h` cookie with a 403 carrying
`Set-Cookie`, a one-line explanation and a four-line script that reloads once per browsing session.
A browser passes it once a month and sees a flash. An HTTP client with no cookie jar gets no
statutory text, at the proxy — before Astro's render and the four API calls behind it, which is
what the scrape actually costs.

Exempt: `/app/sw.js`, `/app/manifest.webmanifest`, `/app/offline`, `/app/_astro/*`, `/app/icons/*`,
`/app/fonts/*`.

The gate is keyed on the hostname. `USC_GATE_HOST` defaults to `gate.invalid`, which matches no
request, so the dev stack, the Playwright suite and `make shots` are unaffected and the gate exists
only where it was measured. `deploy/watchdog.sh` sends the cookie; without that its probe of
`/app/us/usc/t16/s45f` would read the gate as an outage and recreate the containers every ten
minutes for ever.

### 2. `/api/v1` is not gated, and the axis carries one budget for everyone

Programmatic use of the API is the point of the API. What bounds it instead is a second kind of
limit: `global_rate_limit` in `params.py` is one token bucket for every caller outside the
deployment at once, attached to the two routes that take a pinned release point — `?release=`,
`?date=`, `?id=` — at a burst of 120 and 6 a second sustained. An unpinned request, which is the
current text of one section, is not charged.

The reader's own server-side calls are exempt by address (`is_internal_caller`): they arrive from
the compose network, and the readers behind them are bounded by the gate above and by
`frontend/src/middleware.ts`.

### 3. What is deliberately not done

- **Blocking the networks.** The top two /16s are a quarter of the traffic and the rest is 3,756
  more. A list of addresses cannot be finished.
- **Defending against a scraper that keeps cookies.** The token is one static value; copying it is
  one line of their code. This buys an escalation step, and the next rung — a proof-of-work
  interstitial such as Anubis, or a CDN with a managed challenge in front of the box — is a
  decision about what this demo is for, to be taken when the cost is paid rather than pre-empted.
- **Making the box bigger.** Buying baseline CPU to serve a scrape is the same trade the site
  already refused at ADR-0037.

## Consequences

- A reader with cookies disabled cannot use `/app`. The gate page says so and points at `/api/v1`.
- Any client of `/app` that is not a browser — a link checker, a monitor, `curl` — needs the
  cookie. The watchdog carries it; anything else added later has to.
- A burst of legitimate pinned API traffic can meet a 429 raised by somebody else's scrape. That is
  what a shared budget means, and it is the better of the two ways this ends.
- The gate is a new failure surface in front of the whole reader: a wrong `USC_GATE_HOST` serves
  403 to everyone. CI validates the Caddyfile with the gate both off and on, and the watchdog's
  probe exercises the cookie path once a minute in production.
