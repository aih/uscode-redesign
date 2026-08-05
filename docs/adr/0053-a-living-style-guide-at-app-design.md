# ADR-0053 — A living style guide at /app/design

- **Status:** Accepted
- **Date:** 2026-08-05
- **Context:** Session 30, workstream C task C2, following [ADR-0052](0052-a-brand-layer-over-uswds-expressed-only-as-tokens.md)
- **Depends on:** [ADR-0039](0039-accessibility-is-a-ratchet-in-the-browser-suite.md) (the axe matrix and the reflow ratchet), [ADR-0042](0042-contrast-is-computed-from-the-tokens.md) (the contrast artifact), [ADR-0038](0038-the-user-guide-is-executable.md) (the guide ratchet)

## Context

ADR-0052 landed a brand as token overrides on USWDS. What it did not land was anywhere to look at
the result. The reader's parts — the type scale, the palette, the status badges, the breadcrumb,
the rail, the timeline, the redline, the copy control, the search result row, and the four things
the site says when it cannot answer — are each visible only on a page that happens to render them,
and several of them only on a page that happens to render them *with the right data*. The status
badge for `renumbered` appears on no route in the corpus; the served-from note appears only when a
release point was never loaded; the rate-limited preview card appears only under load.

That has two costs. Nothing renders the set together, so a change to a token is checked against
whichever pages someone thought to open. And the automated checks are route-driven — ADR-0039's axe
matrix and `make shots` scan a list of URLs — so a component with no route of its own is scanned in
whatever state the corpus puts it in, or not at all. ADR-0042 records the sharper version of this:
the scan could not see a status badge, because no scanned route rendered one, and dark's was 2.25:1
for as long as that was true.

## Decision

One page, `/app/design`, showing every part of the system, and added to the route matrices that
already exist so that the checks reach it.

**It renders components, not likenesses.** Every specimen is either the component imported and
given data, or the output of the library function that builds that markup on the page which uses
it. Where the markup was inline in a page it was extracted first: `Timeline`, `SearchResult`,
`NoResults` and `CitationNotFound` are new components, used by `/app/versions`, `/app/search` and
`/app/goto` as well as here. The hover preview's failure card is built by `lib/preview.ts` and
handed to `CitePreview`'s island as a string with a token where the href goes, because an
`is:inline` script can import nothing and a card built inside one is markup no other page can show
and no test can call.

A style guide of hand-written likenesses is worse than no style guide. It drifts, and it is
believed.

**It reaches no data.** No API call, no database, no release point. The page renders identically on
an empty machine and on the deployed box, which is what lets the screenshot and accessibility
suites treat it as a fixed target — every other route's appearance depends on what the corpus
happens to hold. The specimen provision is under title 0, which OLRC does not publish, so its
citations resolve to nothing and cannot be mistaken for law.

**The contrast table computes itself, in the browser, from the tokens the page resolved.** The
pairs move out of `scripts/contrast.py` into `frontend/src/data/color-pairs.json`, which the script
now reads and the page imports. The script resolves those pairs against `site.scss` and writes
`docs/verification/contrast.json`; the page resolves them against `getComputedStyle` and prints the
ratio in whichever theme is on. `frontend/tests/e2e/design.spec.ts` compares the two, pair by pair,
in both themes.

Two implementations of one formula is the cost, and it is paid for by what the second one can see:
the page reports the colour actually in force, which is precisely the class of defect ADR-0042 was
written about — a USWDS component painting a colour the tokens do not name, invisible to any audit
of the tokens.

The pair list has to live under `frontend/src/` because that is the only tree the reader's build can
import from: `frontend/Dockerfile`'s build context is `./frontend`, so nothing under `docs/` exists
when the image is built. For the same reason the page does not restate the font byte sizes or the
measured characters per line — those are in `docs/verification/` and the page names the command
that regenerates them.

## Consequences

- **A component that is not on this page is covered by none of this.** `make shots` renders
  `/app/design` at 375, 1280, 320 and 1280-at-200%, failing on horizontal overflow; the axe matrix
  scans it at three viewports, in both themes, and under forced colours; the guide ratchet requires
  a chapter to account for it. That is the rule this page exists to make enforceable, and it is
  enforced for whatever is on it and nothing else. `SearchFacets`, `SectionBar`, `Neighbors`,
  `SiteSearch`, `ReleasePicker`, `WatchButton` and `ComingSoon` are not on it yet.
- **Four page-inline blocks became components.** Their markup is unchanged and their pages are
  shorter, but the extraction is a real edit to three live routes and its only test is the existing
  suites.
- **The page carries a 20 KB inline-script budget** (`docs/js-budgets.json`), most of it
  `CopyColumn`'s island, which is on the page because the copy control is part of the system. The
  colour table's own script is about 4 KB.
- **Two implementations of the WCAG contrast formula**, tied together by one e2e test. If that test
  is ever deleted, the page becomes a second unchecked source of numbers.
- **The specimen text is a specimen.** Its links 404. That is the price of a page that reaches no
  data, and the alternative — borrowing a real provision's identifier for words the Code does not
  contain — is worse.
- **`docs/verification/contrast.json` gains a `pairs_declared_in` key** and its comment changes.
  The 20 pairs, 40 checks and 0 failures are unchanged, which is the check that moving the list
  moved nothing else.
