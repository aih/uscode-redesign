---
layout: ../../layouts/GuideLayout.astro
title: Reading the Code
order: 2
summary: Going to a provision by its citation, moving around it, and reading what the badges and notes on it mean.
covers:
  routes: ["/app/us/usc", "/us/usc"]
  adrs: [9, 10, 21, 25]
---

## The address of a provision

A citation is a path. Title 16, section 45f is `/us/usc/t16/s45f`; subsection (c)(5) of it is
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
That is deliberate: a provision read out of its section is a provision read without its
definitions, its exceptions and its chapeau, and the reader should never have to reconstruct the
context it was quoted out of.

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

## Moving around

Three ways, all of them doing the same thing:

- The **sticky bar** at the top of a section carries previous, next, and up-one-level, and stays
  put while you scroll.
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

**Repealed and omitted sections keep their place in reading order.** They are not skipped and not
hidden — a section that was repealed is part of the shape of the chapter around it, and being
unable to find it is its own kind of wrong answer. They appear in prev/next with a badge saying
what happened to them.

## What the markings mean

**Status badges.** A section can be marked `repealed`, `omitted`, `transferred`, `renumbered` or
`reserved`. The badge prints whatever the source says, rather than mapping it onto a fixed list —
the OLRC uses words this site did not anticipate, and inventing a category for them would be
editorialising.

**Notes and source credit** are collapsed under the text on a narrow screen and open beside it on a
wide one. They come from the source XML unchanged.

**Occurrence 1 of 2.** Occasionally the source publishes more than one element under a single
identifier at a single release point. The site shows **every** occurrence, in the order they appear
in the file, with a note saying how many there are. Picking one and discarding the other would be
a silent editorial decision about which of two published texts is the law.

## Two things that will catch you out

**Section numbers use an en dash, not a hyphen.** The OLRC writes `45a–1` with U+2013 — 5,697
sections in the corpus contain one, and not a single one contains an ASCII hyphen. No keyboard has
that key, so the search box accepts either and finds the right provision; a URL typed with a hyphen
by hand will not resolve on its own.

**Titles sort numerically, and `5a` is its own title.** The appendix titles (`5a`, `11a`, `18a`,
`28a`, `50a`) are separate titles with their own structure, not appendices bolted onto the title
they are named for. Note that a citation in the form `5 U.S.C. App. 3` is understood but resolves
to nothing, because the OLRC publishes no section at that flat address — the site explains this
rather than showing a bare 404.
