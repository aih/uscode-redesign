---
layout: ../../layouts/GuideLayout.astro
title: The API
order: 8
summary: The same answers as JSON or as the source XML, at the same addresses, for anyone who would rather ask a program than a browser.
covers:
  routes: ["/app/docs"]
  adrs: [29, 32, 57]
---

Everything the reader shows comes from a public API at `/api/v1`. The reader calls the same routes
any caller can. The full reference — every route, every parameter, generated from the live
schema — is at [API documentation](/app/docs), with an interactive "try it" version at `/docs` and
a reference layout at `/redoc`.

```scenario
id: api-reference-in-site
title: The API reference renders inside the site
steps:
  - goto: /app/docs
  - expect: { selector: "main", contains: "/api/v1" }
```

## The shape of it

| Route | Answers |
|---|---|
| `/api/v1/us/usc/{identifier}` | a provision, section or table-of-contents node |
| `/api/v1/us/usc/?id={guid}` | the provision that guid pins |
| `/api/v1/sections/{identifier}/neighbors` | previous and next in reading order |
| `/api/v1/sections/{identifier}/versions` | the release points at which the text changed |
| `/api/v1/sections/{identifier}/diff?from=&to=` | a redline between two of them |
| `/api/v1/search?q=` | keyword search: also `?sort=`, `?limit=`, `?offset=`, `?release=`, `?date=` |
| `/api/v1/citation?q=` | a citation in any accepted written form, resolved to an identifier |
| `/api/v1/labels?identifier=&identifier=` | the num and heading of up to 100 identifiers at once |
| `/api/v1/releases`, `/api/v1/titles` | the release points, and the titles held |
| `/api/v1/status` | how current this mirror is, and when it last checked |

`?release=` and `?date=` work exactly as they do in the reader, and `?format=xml` returns the
**source USLM verbatim** — the OLRC's own markup for that section, unmodified.

On `/api/v1/search`, `?sort=` takes `relevance`, `citation` or `recent`; `?limit=` is 1 to 100 and
defaults to 20; `?offset=` runs to 1000.

There are also routes for accounts, watchlists and per-account settings —
`/api/v1/auth/*`, `/api/v1/watchlists*`, `/api/v1/settings`. Accounts are switched off in the
reader, which is a decision about the reader: these routes still work for a caller that addresses
them directly. See [Accounts and watchlists](/app/guide/07-accounts).

```scenario
id: api-json
title: The same address answers a program with JSON
steps:
  - goto: /api/v1/us/usc/t16/s45f?release=119-99
  - expect: { selector: "body", contains: "/us/usc/t16/s45f" }
```

## The citation URL from a script

`/us/usc/t16/s45f` redirects rather than answering, and where it sends you depends on what you say
you accept. From `curl`, ask for JSON and follow the redirect:

```
curl -L -H 'Accept: application/json' https://uscode.linkedlegislation.org/us/usc/t16/s45f
```

Without `-L` you get the 307 itself; without the `Accept` header you get whatever the default is
for your client, which for a browser is the reader.

## Notes for developers

**Caching.** A response to a request that pinned a release point is immutable and safe to cache
forever. A response without one, or one resolved by `?date=`, carries a short revalidation window
instead.

**Rate limits.** Five routes are throttled per caller. Each is a token bucket — a burst up to the
capacity, refilled at a sustained rate:

| Route | Burst | Sustained |
|---|---|---|
| `/api/v1/search` | 120 | 10 a second |
| `/api/v1/citation` | 120 | 10 a second |
| `/api/v1/labels` | 300 | 30 a second |
| `/api/v1/sections/{identifier}/diff` | 5 | 1 every 5 seconds |
| `POST /api/v1/auth/signup` | 10 | 30 an hour |

Over the limit you get a `429` with a `Retry-After` header saying how long to wait.
`POST /api/v1/auth/login` is throttled by failure count instead: five failures for one email
address, or fifty from one caller, and further attempts answer `429`.

**`HEAD` is not routed.** Every `/api/v1` route is registered for its own method alone, so a `HEAD`
request answers `405`.
