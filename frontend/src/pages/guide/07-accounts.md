---
layout: ../../layouts/GuideLayout.astro
title: Accounts and watchlists
order: 7
summary: What an account will be for, why it is switched off, and everything that works without one.
covers:
  routes: ["/app/provisions", "/app/login", "/app/signup"]
  adrs: [17, 19, 34]
---

**Accounts are switched off.** So are bulk downloads. Their controls are still where they belong,
and they explain what they will do rather than failing, greying out, or disappearing — a control
that vanishes teaches a reader the feature does not exist, and one that is greyed with no
explanation teaches them nothing at all.

```scenario
id: accounts-explain-themselves
title: A switched-off feature says what it will be
steps:
  - goto: /app/provisions
  - expect: { selector: ".usa-alert__heading", visible: true }
```

## Why they are off

The accounts system is built: sign-up, log-in, server-side sessions that can be revoked, argon2
password hashing, CSRF protection, login throttling, watchlists with notes and release pins. It
works, and it is tested.

What it does not have is **email**. No verification and no password reset — so an account whose
password you forget is an account you cannot recover, and an address you never proved is yours can
be signed up by someone else. That is acceptable in development and not on a public site, so the
reader's half is turned off until email exists. It is a decision written down rather than a gap
left open.

The switch is in the user interface only. It is not a security control, and the API routes behind
it are untouched and still tested.

## What an account will be for

**My Provisions** — a watchlist of provisions you care about, each optionally pinned to a release
point, so you can come back to *this section as it stood then* in one click, with your own note on
it.

## What works without one

Everything else, and it will keep working without one:

- reading any provision at any of 382 release points;
- seeing which titles each release point changed;
- the version history of a section, and a redline between any two release points;
- search, and going straight to a citation;
- the whole API.

In the meantime, URLs do the work an account would. A pinned address (`?release=`) is a bookmark to
an exact text, a guid is a permanent citation to one, and the version-history page for a section is
a standing answer to "has this changed".
