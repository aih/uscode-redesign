---
layout: ../../layouts/GuideLayout.astro
title: Checking this site
order: 9
summary: How to verify that what you are reading is what the OLRC published, and what this site does not guarantee.
covers:
  routes: []
  adrs: [7, 13]
---

This is not an official publication, so the right posture toward it is verification rather than
trust. This chapter is about how to do that.

## Follow any page back to its source

Every section page names the release point its text came from and links to the OLRC file it was
parsed from. `?format=xml` on the API returns the source USLM **verbatim** — not a
re-serialisation, the stored fragment as published — so you can compare what you are reading with
what the OLRC put out, byte for byte, without taking this site's word for anything.

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

## What is checked, and how

`make verify --deep` independently recounts every title-release against the source XML. It has been
run over the whole corpus: **3,153 of 3,153 title-versions recounted, 0 source mismatches, 0
incomplete loads.** The result is committed to the repository as a file, not asserted in prose,
because a reliability claim that is not a re-runnable command is an opinion.

The six count mismatches it does report are the source publishing several elements under one
identifier at one release point, which is [shown rather than smoothed away](/app/guide/02-reading).

## What this site does not promise

- **It is not official.** For the official text or the official currency of a title, go to
  [uscode.house.gov](https://uscode.house.gov/).
- **Structural history is not versioned.** The text is, at every release point; the hierarchy
  around it — which chapter a section sits in — is held as the newest loaded view rather than
  per release point.
- **The corpus stops where the OLRC's electronic publication does**, in July 2013. There is no
  earlier release point to ask for.
- **Two titles' appendix sections are unreachable by a flat citation**, as described in
  [Reading the Code](/app/guide/02-reading).

## Built in the open

The source, every design decision, and a session-by-session build log are public at
[github.com/aih/uscode-redesign](https://github.com/aih/uscode-redesign). The decisions are
individually written up — including the costs each one incurred — so what this site got wrong is as
readable as what it got right.
