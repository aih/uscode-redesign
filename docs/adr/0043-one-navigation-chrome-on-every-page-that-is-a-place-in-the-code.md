# ADR-0043: One navigation chrome on every page that is a place in the Code

**Status:** Accepted
**Date:** 2026-08-04
**Related:** [ADR-0006](0006-toc-from-structural-elements.md) (the unversioned structure this rail
shows), [ADR-0011](0011-astro-uswds-frontend-at-app.md) (the design system whose breadcrumb this
extends), [ADR-0038](0038-the-user-guide-is-executable.md) (the ratchet that makes the guide account
for it), [ADR-0044](0044-release-context-belongs-in-the-chrome.md) (the release half of the same
chrome)

## Context

The complaint this answers is "clunky; navigation extremely slow". Most of the machinery for good
navigation already existed — `ancestors` come back on every section, `Neighbors` already names
prev/next, `SectionBar` already pins the section's identity. `docs/ia-map.md` was written first, from
the guide ratchet's own route list rather than from memory, to find out what was actually missing.

Four things, all checkable:

1. **Only one page carried any chrome.** `us/usc/[...identifier].astro` was the sole caller passing
   `crumbs`, `release` or `bar` to `Base`. `/app/versions` and `/app/diff` rendered
   `<Base title={…}>` and nothing else, so two of the reader's seven surfaces had no trail at all.
2. **The breadcrumb stopped at the parent.** `crumbs = section.ancestors`, so `/us/usc/t16/s45f`
   rendered `Title 16 › CHAPTER 1 › SUBCHAPTER VI` — every level except the one on screen — and
   nothing carried `aria-current`.
3. **prev/next in the sticky bar were bare arrows.** The neighbour's number was in `aria-label`
   alone, so a sighted reader could see that there was a next section and not which.
4. **A section gave no view of its neighbourhood.** The reader could step one section at a time or
   go up to the subdivision's table of contents and come back. Repealed and omitted sections keep
   their place in reading order (gotcha 9), and nothing showed that until the reader clicked one.

The map also looked for the failure the task assumed — two ways to reach the same state — and did not
find one. `/app/goto` routes to `/app/search` rather than duplicating it; `SectionBar`, `Neighbors`
and `KeyboardNav` are the two ends of the text plus the keyboard. Those findings are recorded in the
map so the question is not re-opened. What the map found instead was the opposite defect:
**`/app/settings` has no inbound link from any rendered page**, because `AuthNav` is its only linker
and `SiteHeader` does not render `AuthNav` while accounts are off (ADR-0034).

## Decision

**One chrome, assembled in `Base`, on every page that is a place in the Code.**

- **The breadcrumb ends at the thing being read.** `Breadcrumbs` takes a `current` node and renders
  it as a `usa-current` item with `aria-current="page"` and no link.
- **`SectionBar`'s steps name their neighbour** — `← § 45e`, `§ 45g →` — from 40em up. Below that the
  label hides and the arrow stands alone, because that row is the only thing left pinned on a phone
  and may not wrap. The accessible name stays the `aria-label` and contains the visible text, so the
  two agree at every width (WCAG 2.5.3).
- **`ChapterRail` shows the parent subdivision's sections**, in reading order, with the section being
  read marked `aria-current` and every status badge rendered in place. A left rail from 64em, and
  after the text below it.
- **`/app/versions` and `/app/diff` get the trail.** The versions endpoint answers
  `{identifier, versions}` and has no ancestors to give, so that page pays one extra
  `fetchIdentifier` for them, allowed to fail.
- **The search-and-citation box stays in one place.** Verified rather than changed: `SiteSearch` is
  mounted in `SiteHeader` and nowhere else, and a page showing results prefills it through `Base`'s
  `searchValue`.

## Costs

**One more API call per section view.** The rail is fed by `fetchToc(section.parent_identifier)` —
the same call this page deliberately dropped in Day 6b, when the breadcrumb moved onto the section
and only two fields of a whole table of contents were still wanted. It is back, and this time the
sections list is the point rather than a byproduct. It joins the existing `Promise.all` and is
allowed to fail like the labels are: without it the reader loses the rail and still has the section,
the sticky bar and the neighbours. B3 owns re-measuring what it costs;
`docs/verification/loadtest.json` last measured that exact route at 156 rps and 9,794 bytes on
2026-07-29 and is stale for every other reason too.

**The rail shows the newest release's structure.** `structure_nodes` holds one row per node rather
than one per release point (ADR-0006), so a rail rendered beside text from `119-99` lists the
subdivision as the newest loaded release has it. The rail says so, in the rail, whenever the release
being read is not the newest. It is not fixable here — per-release structural history is a schema
change, and it is already an open debt.

**Section pages are 62rem wide, not 46rem.** The reading measure is unchanged: the rail takes the
extra 16rem and the text column keeps its measure. It does mean the sticky chrome spans 62rem on
those pages, so `.contextbar__inner` and `.sectionbar__inner` widen with it.

## What was tried and dropped

**A `<details>` disclosure above the text, open at desktop width.** CSS can force the panel visible
at 64em but cannot open the element, so the summary would have reported itself collapsed with its
content on screen — a `<summary>`'s expanded state is not decoration. The grid-`order` arrangement
`.guide__nav` already uses does the same job with no such claim.

**A sticky rail.** `position: sticky; top: calc(var(--sticky-h) + 1rem)` is the obvious form and is
wrong for the reason `.guide__nav` records: `--sticky-h` is a scroll-margin budget rather than a
measurement of the chrome — 19rem at that breakpoint — so a rail honouring it as an offset starts a
third of the way down the page before anything has scrolled.

## Two things this cost to find

**`Astro.slots.has(name)` does not answer "was this slot filled".** A page whose slot content sits
behind a false condition still reports `true`, so every table-of-contents page took the two-column
layout and the wide measure with an empty first column. `Base` takes an explicit `rail` prop.

**USWDS's breadcrumb separator is scoped to 480px and up**, where its own breadcrumb collapses to a
single back link. The `--wrap` variant shows the whole trail at every width, so below 480px the items
ran together as `Title 16CHAPTER 1SUBCHAPTER VI`. Pre-existing, and a fourth item made it plain.

## Not done here

`/app/settings` is still unreachable and `/app/diff` is still two hops from the text it compares.
Both are recorded in `docs/ia-map.md`; the second is task B5's.
