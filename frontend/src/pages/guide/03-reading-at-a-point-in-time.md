---
layout: ../../layouts/GuideLayout.astro
title: Reading at a point in time
order: 3
summary: Release points, how to ask for one, and what every page tells you about the text you are looking at.
covers:
  routes: ["/app/releases"]
  adrs: [18, 36, 44, 45, 56]
---

The Code is republished in full at a **release point**, named for the last public law it includes —
`119-99`, `118-22u1`, `119-102not101`. As of July 2026, the OLRC has published 382 release points; this site has loaded text at 381: the release point at 114-219u1 is not available on the OLRC site. Individual titles are also missing at two other release points: at 113-21, the first release point, no files exist for the five appendix titles or for Titles 34, 52 and 54, which entered the Code after 2013; and 113-36 lists the Title 18 Appendix as affected while publishing no file for it. \
\
A request for a title at a release point where it is missing is answered from the prior release point available, and the response names that release point in served_from.

## Finding a specific release point

**By release point**, when you know which one you want:

```scenario
id: release-pin
title: Read a section as it stood at a named release point
demo: true
demoOrder: 50
steps:
  - goto: /app/us/usc/t16/s45f?release=119-99
    caption: Add ?release= to any address to read it as it stood at that release point.
  - expect: { selector: ".releasebar__rp", contains: "119-99" }
    caption: The page names the release point it answered from.
```

**By date:** `?date=MM/DD/YYYY` resolves to the latest
release point whose currency date is on or before the date you asked for.

```scenario
id: date-resolves
title: A date resolves to the release point in force then
demo: true
demoOrder: 60
steps:
  - goto: /app/us/usc/t16/s45f?date=07/12/2026
    caption: Or ask by date, and the site finds the release point in force then.
  - expect: { selector: ".releasebar__rp", contains: "119-102not101" }
    caption: 12 July 2026 resolves to release point 119-102not101.
```

**By neither**, which is the default: an address with no `?release=` and no `?date=` answers with
the newest release point this site holds, and follows new ones as they are loaded.

Each page that shows a provision carries all three search options as controls, in the bar under the navigation.
The bar names the release point the page currently displayed — **Release point 119-99** — and that name is
the control: open it for a **Release point** menu whose first entry is *Newest — follows new
releases*, and an **As of date** box. The bar stays on screen as you read, and both are reachable
from any scroll position. Both keep the provision you are reading: switching release on
`/app/us/usc/t16/s45f/c/5` returns `(c)(5)` at the release point you chose.

The switcher opens and closes by clicking its summary. `Esc` does not close it.

The **Release point** menu is rebuilt at most every five minutes. A release point loaded within the
last few minutes may not be listed yet. Typing its label into the address as `?release=` reaches
it immediately, and the release point a page is reading is always read fresh — the menu is the only
thing on that schedule. `/app/releases` lists all release points.

```scenario
id: switch-keeps-provision
title: Switching release point keeps the provision you were reading
demo: true
demoOrder: 65
steps:
  - goto: /app/us/usc/t16/s45f/c/5?release=119-99
    caption: Reading subsection (c)(5) of § 45f, pinned to release point 119-99.
  - click: .rpswitch__summary
    caption: The bar names the release point you are reading, and opens the ways to change it.
  - select: { selector: "#release", value: "119-102not101" }
    caption: Choose a different release point.
  - click: "form:has(#release) button[type=submit]"
    caption: The address keeps the provision, and changes the release point.
  - expect: { url: "/app/us/usc/t16/s45f/c/5?release=119-102not101" }
    caption: Still (c)(5), now at release point 119-102not101.
```

## Information about each section

The following information is shown in one band above the section:

**The release point and its date**.

**Whether it is the newest.** A page pinned to an older release point and a page showing the law in
force are otherwise identical. The band says `newest`, or `not the newest` with a link to the
current text.

```scenario
id: not-newest-is-marked
title: An older release point is marked as such
steps:
  - goto: /app/us/usc/t16/s45f?release=119-99
  - expect: { selector: ".releasebar__older", contains: "not the newest" }
```

**The caveat, on a `not` release point.** A label like `119-102not101` means *current through Public
Law 119-102, except 119-101*. The date alone would tell you the text is current through 12 July
2026, and it is not quite: one law enacted before then is not in it.

```scenario
id: not-label-caveat
title: A "not" release point says which law it is missing
steps:
  - goto: /app/us/usc/t16/s45f?release=119-102not101
  - expect: { selector: ".releasebar__caveat", contains: "except" }
```

**Where the text is from.** Not every release point is separately stored. If you ask for one
that is not, the text comes from the newest release point at or before it, and that is noted on the page.

The [version history](/app/versions/us/usc/t16/s45f) and [redline](/app/diff/us/usc/t16/s45f?from=119-99&to=119-102not101)
pages carry no release band. The first spans each release point at which the section changed; the
second is compares text from two points in time.

## Release points and site currency

[Release points](/app/releases) lists all of them, newest first, with the date each is current
through and which titles it changed. Titles the OLRC changed but this site does not hold are greyed with a dagger.

```scenario
id: releases-list
title: See every release point and what each one changed
steps:
  - goto: /app/releases
  - expect: { selector: "main", contains: "119-99" }
```

The same page says when the site last looked for a new release point — *“Checked uscode.house.gov
for new release points 3 hours ago.”* It is a plain line when everything is current and a warning
when it is not, including when the last check **failed**. The API answers the same question at
`/api/v1/status`.

## A note on caching

A page you pinned with `?release=` can be cached forever. The text at a named release point does
not change. A page without a release point, or one asked for by `?date=`, is cached briefly and
revalidated, since new release points may change the value of the provision retrieved by date.