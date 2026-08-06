---
layout: ../../layouts/GuideLayout.astro
title: Checking this site
order: 9
summary: How to verify that what you are reading is what the OLRC published, and what this site does not guarantee.
covers:
  routes: ["/app/design"]
  adrs: [7, 13, 39, 42, 53]
---

This chapter is how to check the text on this site against the official sources.

## Follow any page back to its source

Every section page names the release point its text came from and links to the OLRC file it was
parsed from. `?format=xml` on the API returns the stored fragment as published — the source USLM
verbatim, not a re-serialisation — which compares byte for byte against what the OLRC put out.

Every ingest also writes a provenance manifest: the source URL, the download timestamp, the sha256
of the zip, and per-title element counts. Anyone can re-download the same zip and confirm the hash.

## What the numbers mean

The corpus is 3,153 title-releases across 58 titles and 381 loaded release points: 65,938 distinct
sections, 5,466,652 (section, release) pairs, stored as 489,738 texts.

The Code republishes every title at every release point whether or not anything in it changed, so
about 91% of those pairs are republications of text that already existed. Each is stored once and
pointed at by every release point that publishes it, which is what makes the corpus 27 GB.

The deduplication is done on the text with the `@id` guids stripped out. Guids regenerate at every
release point by design, so hashing the raw XML dedupes nothing: of 5,095 Title 16 sections between
two adjacent release points, zero were byte-identical and 5,093 were identical once the guids were
removed.

A deduplicated fragment carries the guids of the release point where its text first appeared. The
guid the site resolves for a `(provision, release point)` pair is still correct; the guids *inside*
a shared fragment belong to that first release.

## Automated verification

`make verify --deep` independently recounts every title-release against the source XML. It has been
run over the whole corpus: **3,153 of 3,153 title-versions recounted, 0 source mismatches, 0
incomplete loads.** The result is committed to the repository as a file.

The six count mismatches it does report are the source publishing several elements under one
identifier at one release point. The reader [shows every occurrence](/app/guide/02-reading).

## Accessibility

The reader is scanned against WCAG 2.1 Level AA on every push. The scan covers every route in a
declared matrix at three widths — 320, 375 and 1280 pixels — in both themes, once with forced
colours, and in nine interactive states: a citation preview opened by keyboard, the same preview
dismissed with Escape, the copy control after use, the theme immediately after toggling, the
compact reading density in force, the keyboard shortcut list open as a dialog, the release switcher
open in the sticky bar, the redline with its source pane rendered, and the search box holding a
query. The results are committed to the repository as a file.

Violations that are known and not yet fixed are listed with the task that owns each. The list
currently holds two horizontally scrollable regions with no keyboard route into them, the API
reference pages missing a language attribute, and the Swagger UI and ReDoc pages, which carry
violations from the bundles the site vendors.

Colour is checked separately, since a scan only sees the pages it is pointed at. Every pair of
colours the design defines — text on its background, a link, a form control's edge, the focus ring —
is computed in both themes and committed as a file. Text meets 4.5:1 and controls and focus rings
meet 3:1; dividers are reported without being held to a ratio, and the numbers are in the file
either way.

Status badges do not rely on colour. A repealed section says "repealed", and each status is drawn
with a different border, so the distinction survives a monochrome print. The site also honours the
system's high-contrast and reduced-motion settings.

Two further checks run at the same time: every page in the screenshot set must lay out without
scrolling sideways at 320 pixels, and again at 1280 pixels with the page zoomed to 200%.

Automated scanning answers about half of WCAG 2.1 AA. It does not see focus order, reading
sequence, whether a live region announces, or whether a visible label and its accessible name
agree.

## The design system page

[/app/design](/app/design) shows every part the reader is built from on one page: the two
typefaces and the roles they are used in, the reading measure, the colour palette, the focus ring,
the status badges, the navigation chrome — breadcrumb, chapter rail, section bar, neighbour cards,
release switcher and release context band — the section contents panel and the keyboard shortcut
list, the version timeline, the redline, the statutory text with its copy control, the two reading
densities, the print layout, a search result row, and each message the site can show when it cannot
answer — no results, a rate-limited preview, a citation that parses and names nothing, and a
release point that answered for another.

Each specimen is the component itself, given specimen data. The page reaches no data of its own.
The provision it shows is under title 0, which the Office of the Law Revision Counsel does not
publish: its citations resolve to nothing and its words are not law.

The colour table on that page computes its ratios in your browser, from the colours the page has
resolved, and is correct in whichever theme you are reading. Switching the theme with the control
in the header recomputes it. The same pairs are computed from the stylesheet by
`scripts/contrast.py` and committed as a file; the two are compared in the browser test suite.

```scenario
id: design-system-contrast
title: The design page reports contrast for the colours it is painted with
steps:
  - goto: /app/design
  - expect:
      selector: "[data-pairs]"
      contains: "--ink"
  - expect:
      selector: "[data-pairs]"
      contains: "pass"
  - expect:
      selector: ".status-tag--vacated"
      contains: "vacated"
```

An unrecognised status is the last of those steps. A status this site does not know keeps the plain
badge and prints its own word. The set of statuses is not fixed: the source may publish one this
site has never seen.

## Limitations

- **The site claims no accessibility conformance yet.** The known defects are listed above.
- **It is not official.** For the official text or the official currency of a title, go to
  [uscode.house.gov](https://uscode.house.gov/).
- **Structural history is not versioned.** The text is versioned at every release point; however, the hierarchy
  around it — which chapter a section sits in — is held as the newest loaded view.
- **The corpus stops where the OLRC's electronic publication does**, in July 2013.
- **Two titles' appendix sections are unreachable by a flat citation**, as described in
  [Reading the Code](/app/guide/02-reading).

## Built in the open

The source, every design decision, and a session-by-session build log are public at
[github.com/aih/uscode-redesign](https://github.com/aih/uscode-redesign). The decisions are
individually written up as ADRs, and the code is MIT-licensed.
