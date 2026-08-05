# ADR-0050 — The chapter rail is pinned, and scrolls on its own

- **Status:** Accepted
- **Date:** 2026-08-05
- **Context:** Session 29, asked for directly during workstream B task B4
- **Reverses:** [ADR-0043](0043-one-navigation-chrome.md)'s decision that the rail is not sticky

## Context

ADR-0043 introduced `ChapterRail` and recorded that it is deliberately not sticky. The reason given
was measured and correct as far as it went: `--sticky-h` is 19rem at the desktop breakpoint, so
`position: sticky; top: var(--sticky-h)` starts the rail 304px down the viewport, a third of the
way down the page, before anything has scrolled.

The request here is the opposite: keep the rail in place while the text scrolls, and give it its
own scrollbar.

## Decision

Pin it from 64em, and bound its height to what is left of the viewport underneath the chrome:

```scss
position: sticky;
top: calc(var(--sticky-h) + 0.5rem);
max-height: calc(100vh - var(--sticky-h) - 1.5rem);
overflow-y: auto;
overscroll-behavior: contain;
```

The height is the half ADR-0043's attempt was missing. Setting `top` alone pins the rail and then
lets it run to whatever length the subdivision happens to be, so a long subchapter pushes its own
tail below the viewport with no way to reach it except scrolling the document — which moves the
text the reader was trying to hold still. Bounded and scrollable, the rail is a panel; unbounded,
it is a list that happens not to move.

`overscroll-behavior: contain` stops a scroll that reaches the end of the rail from continuing into
the document beneath it.

Below 64em nothing changes: the rail is after the text, at the foot of the page, and pinning it
there would put a table of contents between the reader and the section they asked for.

## Consequences

- **The rail's usable height is what `--sticky-h` leaves.** At the desktop breakpoint that is
  `100vh − 304px − 24px`, so a 900px window gives the rail 572px. On a short window it is thin, and
  the chrome above it is the reason. `--sticky-h` growing takes room from the rail as well as from
  every anchor jump, which is one more thing hanging off a token `docs/backlog.md` already flags.
- **A new scrollable region.** It contains links, so it is reachable by keyboard and does not add
  to the two regions `docs/a11y/known-violations.json` already carries for
  `scrollable-region-focusable`. Asserted in `frontend/tests/e2e/sticky.spec.ts`.
- **ADR-0043's standing decision 3 no longer holds** and `claude-code/WORKSTREAM-B-STATE.md` is
  updated. The `<details>` half of that decision is untouched: CSS still cannot force the element
  open, so at desktop width the summary would report itself collapsed with its content on screen.
