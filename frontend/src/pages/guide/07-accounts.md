---
layout: ../../layouts/GuideLayout.astro
title: Accounts and watchlists
order: 7
summary: What an account will be for, why it is switched off, and everything that works without one.
covers:
  routes: ["/app/provisions", "/app/login", "/app/signup"]
  adrs: [17, 19, 34]
---

**Accounts are currently inactive.** So are bulk downloads. Their controls are still visible on the page to explain their intended functionality.

```scenario
id: accounts-explain-themselves
title: An inactive feature explains its intended functionality
steps:
  - goto: /app/provisions
  - expect: { selector: ".usa-alert__heading", visible: true }
```

## Why they are inactive

The accounts system has been built but currently lacks an email integration for verification and password resets. Until this is added, the user interface for accounts is turned off. The underlying API routes remain active and tested.

## What an account will be for

**My Provisions** — a watchlist of provisions you care about, each optionally pinned to a release
point, so you can come back to *this section as it stood then* in one click, with your own note on
it.

## Features that don't require an account

The core features that do not require accounts:

- reading any provision at any of the 381 loaded release points;
- seeing which titles each release point changed;
- the version history of a section, and a redline between any two release points;
- search, and going straight to a citation;
- the whole API.

In the meantime, you can use URLs to keep track of things. A pinned address (`?release=`) is a bookmark to
an exact text, a guid is a permanent citation to one, and the version-history page for a section tracks how the section changed.
