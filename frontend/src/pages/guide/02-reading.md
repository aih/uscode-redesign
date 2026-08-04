---
layout: ../../layouts/GuideLayout.astro
title: Reading the Code
order: 2
summary: Going to a provision by its citation, moving around it, and reading what the badges and notes on it mean.
covers:
  routes: ["/app/us/usc", "/us/usc"]
  adrs: [9, 10, 21, 25, 40, 43]
---

## The address of a provision

A citation corresponds to a url path. Title 16, section 45f is `/us/usc/t16/s45f`; subsection (c)(5) of it is
`/us/usc/t16/s45f/c/5`. Chapters and subchapters work the same way — `/us/usc/t16/ch1` is a table
of contents rather than a section, served at the same kind of address.

```scenario
id: section-by-address
title: Open a section by its citation
demo: true
demoOrder: 20
steps:
  - goto: /app/us/usc/t16/s45f
    caption: The citation is the URL. This is 16 U.S.C. § 45f.
  - expect: { selector: ".doc-title", contains: "45f" }
    caption: The section, with its number and heading as the Code prints them.
```

Ask for a subsection and you get **the whole section, with that subsection highlighted in place**.

```scenario
id: provision-in-context
title: A subsection is shown inside its whole section
demo: true
demoOrder: 30
steps:
  - goto: /app/us/usc/t16/s45f/c/5
    caption: Ask for subsection (c)(5) —
  - expect: { selector: ".target", visible: true }
    caption: — and it is highlighted inside the whole section, never stranded out of context.
```

### The bare citation URL

The address also works without the `/app` prefix. `/us/usc/t16/s45f` is a **citation URL**: it
redirects a browser to the reader and a program to the API, based on what the caller says it can
accept. One URL is safe to paste into a brief, an email or a script.

```scenario
id: citation-url-redirects
title: The bare citation URL leads a browser to the reader
steps:
  - goto: /us/usc/t16/s45f
  - expect: { url: "/app/us/usc/t16/s45f" }
```

From a script, the same address answers with JSON — `curl -L` follows the redirect, and
`-H 'Accept: application/json'` is what makes it land on the API rather than the reader. See
[The API](/app/guide/08-api).

## Site navigation

**The breadcrumb** at the top of every page runs from the title down to the provision on screen:
`Title 16 › CHAPTER 1 › SUBCHAPTER VI › § 45f`. Every level above the current one is a link, and the
current one is marked as the page you are on. It carries the release point you are reading with it,
so moving up a level does not move you back to the present.

```scenario
id: breadcrumb-ends-here
title: The breadcrumb names the provision you are reading
steps:
  - goto: /app/us/usc/t16/s45f
  - expect: { selector: ".usa-breadcrumb__list-item.usa-current", contains: "45f" }
```

**The chapter rail** lists the sections around this one, in reading order, from the subdivision that
contains it. The section you are reading is marked. Beside a wide window it sits to the left of the
text; on a narrow one it is below the section.

The rail is drawn from the newest release point this site holds, and the text beside it is whatever
release point you asked for. When those differ the rail says so.

```scenario
id: chapter-rail
title: The sections around this one, with their status
demo: true
demoOrder: 35
steps:
  - goto: /app/us/usc/t16/s45f
    caption: Beside the section, the rest of the subchapter in reading order.
  - expect: { selector: ".rail__item--here", contains: "45f" }
    caption: The section you are reading is marked in the list.
  - expect: { selector: ".rail .usa-tag", visible: true }
    caption: Repealed and transferred sections show their status here, before you click one.
```

Three more ways to move:

- The **sticky bar** at the top of a section carries previous, next and up-one-level, and stays put
  while you scroll. Each step names its neighbour — `← § 45e`, `§ 45g →` — except on a narrow
  screen, where the row has space for the arrows alone.
- **Previous / next cards** at the foot of the section show what is either side, with headings.
- The **keyboard**: <kbd>←</kbd> or <kbd>j</kbd> for the previous section, <kbd>→</kbd> or
  <kbd>k</kbd> for the next, <kbd>u</kbd> to go up a level. Keys typed into a search box are left
  alone, and so is any combination using Ctrl, Alt, Shift or Cmd.

```scenario
id: neighbors-next
title: Move to the next section from the sticky bar
demo: true
demoOrder: 40
steps:
  - goto: /app/us/usc/t16/s45f
    caption: Reading order is preserved, so you can move through a chapter section by section.
  - click: .sectionbar a[rel="next"]
    caption: The sticky bar carries previous, next and up-one-level.
  - expect: { selector: ".doc-title", contains: "45g" }
    caption: § 45g — the next section, whatever you were reading before.
```

```scenario
id: keyboard-previous
title: Move to the previous section from the keyboard
steps:
  - goto: /app/us/usc/t16/s45f
  - press: j
  - expect: { url: "/us/usc/t16/s45e" }
```

**Repealed and omitted sections keep their place in reading order.** They are not skipped or hidden. A section that was repealed remains part of the structure of the chapter around it. They appear in prev/next with a badge saying what happened to them.

## What the markings mean

**Status badges.** A section can be marked `repealed`, `omitted`, `transferred`, `renumbered` or
`reserved`. The badge prints whatever the source says, rather than mapping it onto a fixed list —
the OLRC uses words this site did not anticipate, and inventing a category for them would be
editorialising.

**Notes and source credit** are collapsed under the text on a narrow screen and open beside it on a
wide one. They come from the source XML unchanged.

Dates inside a note read as part of the sentence they sit in. The source marks every date as its
own element, and the amendment histories are largely made of them — "Pub. L. 95–625 struck out
subsec. (c) effective November 10, 1978" is one sentence, and it is read as one.

```scenario
id: dates-read-inline
title: A date in a note stays in its sentence
steps:
  - goto: /app/us/usc/t16/s45f
    caption: A section whose notes carry amendment dates.
  - expect: { selector: "span.uslm-date", visible: true }
    caption: Each date is part of the running text, not a line of its own.
```

**Occurrence 1 of 2.** Occasionally the source publishes more than one element under a single
identifier at a single release point. The site shows **every** occurrence, in the order they appear
in the file, with a note saying how many there are.

## Notes on formatting

**Section numbers use an en dash, not a hyphen.** The OLRC writes `45a–1` with U+2013 — 5,697
sections in the corpus contain one, and not a single one contains an ASCII hyphen. No keyboard has
that key, so the search box accepts either and finds the right provision; a URL typed with a hyphen
by hand will not resolve on its own.

**Titles sort numerically, and `5a` is its own title.** The appendix titles (`5a`, `11a`, `18a`,
`28a`, `50a`) are separate titles with their own structure, not appendices bolted onto the title
they are named for. Note that a citation in the form `5 U.S.C. App. 3` is understood but resolves
to nothing, because the OLRC publishes no section at that flat address — the site explains this
rather than showing a bare 404.
