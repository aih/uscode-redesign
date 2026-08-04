---
layout: ../../layouts/GuideLayout.astro
title: Checking this site
order: 9
summary: How to verify that what you are reading is what the OLRC published, and what this site does not guarantee.
covers:
  routes: []
  adrs: [7, 13, 39, 42]
---

This is not an official publication. This chapter explains how to verify the text against official sources.

## Follow any page back to its source

Every section page names the release point its text came from and links to the OLRC file it was
parsed from. `?format=xml` on the API returns the source USLM **verbatim** — not a
re-serialisation, but the stored fragment as published — so you can compare what you are reading directly with
what the OLRC put out, byte for byte.

Every ingest also writes a provenance manifest: the source URL, the download timestamp, the sha256
of the zip, and per-title element counts. Anyone can re-download the same zip and confirm the hash.

## What the numbers mean

The corpus is 3,153 title-releases across 58 titles and 381 release points: 65,938 distinct
sections, 5,466,652 (section, release) pairs, stored as 489,738 texts.

That last pair of numbers is the one worth understanding. The Code republishes **every** title at
**every** release point whether or not anything in it changed, so about 91% of those pairs are
republications of text that already existed. Storing them once and pointing many release points at
the same text is what makes the corpus 27 GB instead of hundreds.

The deduplication is done on the text with the `@id` guids stripped out, because guids regenerate
at every release point by design — hashing the raw XML dedupes nothing at all, which was measured
rather than assumed: of 5,095 Title 16 sections between two adjacent release points, **zero** were
byte-identical, and 5,093 were identical once the guids were removed.

One consequence you can see: a deduplicated fragment carries the guids of the release point where
its text first appeared. The guid the site resolves for a `(provision, release point)` pair is
still correct, but the guids *inside* a shared fragment belong to that first release.

## Automated verification

`make verify --deep` independently recounts every title-release against the source XML. It has been
run over the whole corpus: **3,153 of 3,153 title-versions recounted, 0 source mismatches, 0
incomplete loads.** The result is committed to the repository as a file.

The six count mismatches it does report are the source publishing several elements under one
identifier at one release point, which is [shown rather than smoothed away](/app/guide/02-reading).

## Accessibility

The reader is scanned against WCAG 2.1 Level AA on every push. The scan covers every route in a
declared matrix at three widths — 320, 375 and 1280 pixels — in both themes, once with forced
colours, and in six interactive states: a citation preview opened by keyboard, the same preview
dismissed with Escape, the copy control after use, the theme immediately after toggling, the
redline with its source pane rendered, and the search box holding a query. The results are
committed to the repository as a file.

Violations that are known and not yet fixed are listed with the task that owns each. The list
currently holds two horizontally scrollable regions with no keyboard route into them, the API
reference pages missing a language attribute, and the Swagger UI and ReDoc pages, which carry
violations from the bundles the site vendors.

Colour is checked separately, because a scan only sees the pages it is pointed at. Every pair of
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
