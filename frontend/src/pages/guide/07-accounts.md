---
layout: ../../layouts/GuideLayout.astro
title: Accounts and watchlists
order: 7
summary: What an account will be for, its current status, and what works without one.
covers:
  routes: ["/app/provisions", "/app/login", "/app/signup"]
  adrs: [17, 19, 34]
---

**Accounts are currently inactive.** So are bulk downloads. Their controls are still on the page,
saying what they would do.

```scenario
id: accounts-explain-themselves
title: An inactive feature explains its intended functionality
steps:
  - goto: /app/provisions
  - expect: { selector: ".usa-alert__heading", visible: true }
```

## Status

The accounts system is built and tested. It has no email integration, so there is no address
verification and no password reset, and the user interface for accounts is switched off. The API
routes are unaffected and answer a direct caller — see [The API](/app/guide/08-api).

## What an account will be for

**My Provisions** — a watchlist of provisions, each optionally pinned to a release point and each
carrying your own note. A pinned item reopens at the text as it stood at that release point.

## Features that don't require an account

- reading any provision at any of the 381 loaded release points;
- seeing which titles each release point changed;
- the version history of a section, and a redline between any two release points;
- search, and going straight to a citation;
- the whole API.

In the meantime, you can use URLs to keep track of things. A pinned address (`?release=`) is a bookmark to
an exact text, a guid is a permanent citation to one, and the version-history page for a section tracks how the section changed.
