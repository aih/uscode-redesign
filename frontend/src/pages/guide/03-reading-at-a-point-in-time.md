---
layout: ../../layouts/GuideLayout.astro
title: Reading at a point in time
order: 3
summary: Release points, the two ways to ask for one, and the three facts every page tells you about the text you are looking at.
covers:
  routes: ["/app/releases"]
  adrs: [18, 36]
---

The Code is republished in full at a **release point**, named for the last public law it includes —
`119-99`, `118-22u1`, `119-102not101`. There are 382 of them, from July 2013 to July 2026, and this
site holds the text at each one.

## Two ways to ask

**By release point**, when you know which one you want:

```scenario
id: release-pin
title: Read a section as it stood at a named release point
demo: true
demoOrder: 50
steps:
  - goto: /app/us/usc/t16/s45f?release=119-99
    caption: Add ?release= to any address to read it as it stood at that release point.
  - expect: { selector: ".doc-meta__rp", contains: "119-99" }
    caption: The page names the release point it answered from — every page does.
```

**By date**, when you know when rather than which. `?date=MM/DD/YYYY` resolves to the latest
release point whose currency date is on or before the date you asked for.

```scenario
id: date-resolves
title: A date resolves to the release point in force then
demo: true
demoOrder: 60
steps:
  - goto: /app/us/usc/t16/s45f?date=07/12/2026
    caption: Or ask by date, and the site finds the release point in force then.
  - expect: { selector: ".doc-meta__rp", contains: "119-102not101" }
    caption: 12 July 2026 resolves to release point 119-102not101.
```

## What every page tells you

Three facts sit in the reading column, never in a tooltip:

**The release point and its date** — what you are looking at.

**The caveat, on a `not` release point.** A label like `119-102not101` means *current through Public
Law 119-102, except 119-101*. The date alone would tell you the text is current through 12 July
2026, and it is not quite: one law enacted before then is not in it. The page says so.

```scenario
id: not-label-caveat
title: A "not" release point says which law it is missing
steps:
  - goto: /app/us/usc/t16/s45f?release=119-102not101
  - expect: { selector: ".caveat", contains: "except" }
```

**Where the answer came from.** Most release points republish a title without changing it, so this
site does not store 382 copies of an unchanged section. If you ask for a release point that was
never separately ingested, the answer comes from the newest one at or before it — which is the
right text — and **the page tells you that it did**. An answer that is right for a reason you
cannot see is not much better than a wrong one.

## Every release point, and how current the site is

[Release points](/app/releases) lists all of them, newest first, with the date each is current
through and which titles it changed. Titles the OLRC changed but this site does not hold are greyed
with a dagger, rather than omitted.

```scenario
id: releases-list
title: See every release point and what each one changed
steps:
  - goto: /app/releases
  - expect: { selector: "main", contains: "119-99" }
```

The same page says when the site last looked for a new release point — *“Checked uscode.house.gov
for new release points 3 hours ago.”* It is a plain line when everything is current and a warning
when it is not, including when the last check **failed**. A mirror that has quietly stopped
updating looks exactly like one with nothing to update, and the only difference a reader can see is
whether the site is willing to say when it last checked. The API answers the same question at
`/api/v1/status`.

## A note on caching

A page you pinned with `?release=` can be cached forever, because that text will never change: a
release point is a fixed thing. A page without a release point — or one asked for by `?date=` — is
cached briefly and revalidated, because tomorrow it may resolve somewhere else. This is why a
pinned URL is the one to put in a citation.
