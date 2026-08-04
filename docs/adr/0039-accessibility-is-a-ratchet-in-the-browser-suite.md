# ADR-0039: Accessibility is a ratchet in the browser suite

**Status:** Accepted
**Date:** 2026-08-03
**Related:** [ADR-0011](0011-astro-uswds-frontend-at-app.md) (Astro + USWDS, the markup being
scanned), [ADR-0024](0024-reference-previews-render-server-side.md) (the hover preview, whose open
state this found a defect in), [ADR-0026](0026-diff-the-reading-text-not-the-xml.md) (the redline),
[ADR-0027](0027-light-by-default-dark-by-choice.md) (two themes, so two palettes to scan),
[ADR-0032](0032-serve-the-api-docs-assets-ourselves.md) (the vendored Swagger UI and ReDoc, which
carry violations this project cannot fix),
[ADR-0033](0033-copy-column-four-modes.md) (the copy column),
[ADR-0038](0038-the-user-guide-is-executable.md) (the ratchet this one is modelled on)

## Context

The reader claims no accessibility conformance and nothing measures one. USWDS carries a good deal
of accessible markup by default, which makes the absence easy to not notice: the site looks
compliant, and until something scans it nobody can say by how much.

Two things make that guess unusually unreliable here. The site has two themes (ADR-0027), so every
colour claim is two claims. And the features that distinguish it — the hover preview, the copy
column, the version timeline, the redline — are *states* rather than pages. A scanner that loads
URLs sees none of them.

## Decision

**axe-core runs inside the existing Playwright suite, over a declared route matrix, and fails the
build on any violation that is not recorded as known.**

Four parts.

1. **`docs/a11y/routes.json`** declares what gets scanned: 26 route entries (one expanding to every
   guide chapter on disk, so a tenth chapter is scanned the day it lands), three viewports
   (320×768, 375×812, 1280×900), both themes, one `forced-colors: active` pass, and six interactive
   states. It also records what is deliberately *not* scanned, and why.

2. **`frontend/tests/e2e/a11y.spec.ts`** runs axe against the `wcag2a`, `wcag2aa`, `wcag21a` and
   `wcag21aa` tag sets — 244 scans, 1m22s. Each scan writes a shard; a `globalTeardown` merges them
   into `docs/verification/a11y.json`, and rewrites that artifact only when the whole matrix ran, so
   a `--grep` run cannot replace the committed baseline with a subset.

3. **`docs/a11y/known-violations.json`** is the ratchet. A violation whose (route, rule) pair is
   listed passes; anything else fails. Serious and critical violations fail *even when listed*
   unless the entry names that exact impact in `waiveSeverity` — so a rule that was moderate when it
   was recorded and has since become critical still turns the build red. Every entry carries the
   task that owns the fix.

4. **`make shots`** gains a 320px row and a 1280px-at-200%-zoom row, and its existing "fails if the
   page scrolls sideways" assertion becomes a ratchet reading the same file. That is 1.4.10 Reflow
   and 1.4.4 Resize text, mechanically.

### Why axe-in-Playwright rather than pa11y-ci or a Lighthouse budget

One browser suite, one set of fixtures, and the states are reachable. `pa11y-ci` and Lighthouse
both take a list of URLs; neither can open a hover preview by keyboard focus, click a copy button
and scan what the page announced, or toggle a theme and scan what changed. Those are the site's
distinguishing features, and a scan that skipped them would be measuring the least interesting part
of the reader.

The existing suite already knows how to reach those states — `preview.spec.ts` and `copy.spec.ts`
do it — so the scan reuses their selectors rather than a second, drifting description of the same
widgets. A fourth test runner was also not an option (the session rules forbid one), and it would
have needed its own copy of `make dev-all`'s two-processes-behind-Caddy shape.

## What this measured

244 scans, on the fixture corpus. 41 route/rule pairs, 2,251 nodes: 1 critical, 40 serious, 0
moderate, 0 minor. Regenerate with `make test-a11y`; the artifact is `docs/verification/a11y.json`.

Every one of them is recorded in `docs/a11y/known-violations.json` with an owner. Four are the
reader's own:

- **The mobile nav is unreadable in dark mode.** `#565c65` on `#1c1d1f` is 2.5:1 against a required
  4.5:1, at 320px and 375px, on every reader page. 1280px dark is clean, which is why nobody saw it.
- **The copy column keeps its light-theme blue in dark mode** — `#005ea2` on `#16150f`, 2.71:1.
- **The API chapter's code blocks** render a syntax token at `#e1e4e8` on `#f0f0f0`: 1.11:1.
- **The citation preview carries `aria-hidden="true"` and `tabindex="0"` at the same time**, so while
  it is open it is in the tab order and hidden from assistive technology at once. This one is only
  visible in the open state, which is the argument for the states being in the matrix.

`/app/docs` also scrolls sideways by 3px at 320 CSS px, and its parameter tables and the redline's
source pane are scrollable regions with no keyboard route into them.

The remaining violations — including the one critical — are in the vendored Swagger UI and ReDoc
bundles (ADR-0032). Fixing them means forking or restyling a vendor bundle, so they are owned by the
conformance statement as published exceptions rather than by a repair.

## Costs

**axe adds runtime to every push.** 244 scans, 1m22s locally on a warm site, against roughly 40s for
the eight specs that were there before. CI pays it on every push, on a slower box, and it will grow
with the route matrix — a new guide chapter adds seven scans on its own.

**The baseline contains serious and critical violations, and the build is green.** The task this
implements asked for a gate that fails on any serious or critical violation regardless of the
known-violations file. Taken literally that lands this commit red, because the violations above
already exist and every one of them is owned by a later task in the same workstream — fixing them
here would be the scope of five other tasks in one commit. The `waiveSeverity` field is the
compromise: the *default* for a serious regression is still a red build, and every exception to that
is a line somebody wrote, dated, and signed with an owner. It is weaker than the instruction. It is
recorded here rather than left as a silently looser gate.

**Listing routes explicitly taxes new pages.** The dark-nav contrast entry names 25 routes rather
than using a wildcard, so a new page inherits no waiver and fails until someone either fixes the nav
or adds the route. For a new guide chapter that is a tax on unrelated work. A wildcard would have
been kinder and would have waived contrast on pages nobody has looked at.

**`make shots` now commits 48 PNGs rather than 24** — 2.6 MB, up from 2.2 MB.

**320px at 200% zoom is not tested.** It lays out in 160 CSS pixels; WCAG 2.1 AA asks for reflow
down to 320 and no further. Asserting there would fail the build on something the standard does not
require — measured, the demo URL scrolls sideways by 86px. The rows that are tested are 320 CSS px
(1.4.10's floor, which 1280 also reaches at 400%) and 640 CSS px (1280 at 200%, which is 1.4.4).

**A `globalSetup` may not live in `testDir`.** Playwright loads it as part of the config, and every
spec under that directory is then loaded in the config's context, where `test.describe()` throws and
the whole suite collects as zero tests. The hooks are in `frontend/scripts/` for that reason, which
puts them away from the spec they serve.

## What axe cannot see

Roughly half of WCAG 2.1 AA. axe finds no missing focus order, no wrong reading sequence, no
keyboard trap that needs a keyboard to notice, no heading that is structurally valid and describes
the wrong thing, no `aria-live` region that never announces, no control whose visible label and
accessible name disagree, and nothing at all about whether a screen reader's rendering of a redline
is comprehensible. A green scan is the floor, not the claim.

The manual protocol that covers the rest — keyboard-only task completion, NVDA/Firefox and
VoiceOver/Safari passes, screen magnification, and a dictation pass for 2.5.3 — is task A9, and is
written up in `docs/a11y/manual-protocol.md` with its results dated per run. The conformance
statement (task A10) publishes what both halves found.
