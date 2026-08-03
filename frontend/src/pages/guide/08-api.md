---
layout: ../../layouts/GuideLayout.astro
title: The API
order: 8
summary: The same answers as JSON or as the source XML, at the same addresses, for anyone who would rather ask a program than a browser.
covers:
  routes: ["/app/docs"]
  adrs: [29, 32]
---

Everything the reader shows comes from a public API at `/api/v1`, and the reader has no privileged
access to anything. The full reference — every route, every parameter, generated from the live
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
| `/api/v1/search?q=` | keyword search |
| `/api/v1/releases`, `/api/v1/titles` | the release points, and the titles held |
| `/api/v1/status` | how current this mirror is, and when it last checked |

`?release=` and `?date=` work exactly as they do in the reader, and `?format=xml` returns the
**source USLM verbatim** — the OLRC's own markup for that section, unmodified, which is the thing
to use if you want to parse rather than read.

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

## Two things to know before you build on it

**Caching.** A response to a request that pinned a release point is immutable and safe to cache
forever — that text cannot change. A response without one, or one resolved by `?date=`, carries a
short revalidation window instead. Pin the release point in anything you store.

**Rate limits.** The expensive routes are throttled per caller — the diff most tightly, because it
is CPU-bound and a handful of concurrent requests can take the whole site down with it. Over the
limit you get `429` with a `Retry-After` header saying how long to wait. Honour it and you will not
be refused again; the limits are set well above what reading looks like and well below what a crawl
does.
