# Backlog

Work that is decided-worth-doing but deliberately not scheduled yet. Items graduate
out of here into a session plan; items that get overtaken by an ADR are deleted with
a note saying which ADR overtook them.

Open debts that are *recorded in an ADR* (email verification and password reset —
ADR-0019; `<ref>` links in the reader redline — ADR-0026) live in that ADR, not here.
This file is for work with no ADR behind it.

---

## B1. The smart sticky header

*Partly overtaken by ADR-0056 (2026-08-05), which answers the "re-measure before
designing" item below. The rest of the proposal stands.*

`--sticky-h: 19rem` between 40em and 64em (`frontend/src/styles/site.scss:442`)
permanently occupies roughly 37% of a landscape-tablet viewport, and
`scroll-margin-top` reserves that much plus 0.5rem above every anchor jump so that a
deep-linked provision clears the bar (`site.scss:775`). Below 40em the mitigation is
real and well-engineered; the middle breakpoint has none.

The proposal is a "smart scroll" chrome: hide the main `.topbar` on scroll down,
restore it on scroll up, and keep only the compact `SectionBar` pinned at all times.

Costs to weigh before doing it, because they are what make this a session of its own
rather than a patch:

- It needs a scroll-listening island, and ADR-0022's whole position is that islands
  are added one at a time and measured. The refresh in Session 10 added ~3 KB total.
- `--sticky-h` currently drives `scroll-margin-top`. If the bar's height becomes a
  function of scroll direction, the anchor-jump guarantee has to be re-derived — the
  e2e assertion that holds the 19rem figure honest (`make test-e2e`) is testing a
  static number today.
- The stack has since been measured three times: ADR-0044 (19px of headroom under
  `--sticky-h` at 700px), ADR-0054 (0px of `--sticky-h` at 700, 1024 and 1280, and
  56px of non-sticky header on a phone) and ADR-0056 (89px at 700px, asserted in
  `frontend/tests/e2e/sticky.spec.ts`). Those are the figures to design against.

*Origin: the surviving half of `docs/ui-improvements-plan-unapproved.md`, folded in
here 2026-07-30 when that untracked file was deleted.*

## B2. Break up the monolithic `site.scss`

`frontend/src/styles/site.scss` is ~4,900 lines in one file. Component-specific
rules could move into the `<style>` block of the Astro component they belong to and
get Astro's scoping for free, leaving `site.scss` for tokens, resets, and the USWDS
`@forward` list.

This is worth doing mainly because of what it would have caught: `signup.astro`'s
`usa-hint` class renders unstyled because `site.scss` never `@forward`s that USWDS
package, and nothing about a 4,900-line global file makes that visible. Any refactor
must keep the ADR-0027 theme tokens (`--page`, `--ink`, `--muted`, `--panel`,
`--link`) global — they are stamped on `<html data-theme>` before first paint and
every component reads them.

*Origin: the surviving half of `docs/ui-improvements-plan-unapproved.md`, folded in
here 2026-07-30 when that untracked file was deleted.*

---

## B3. Version-data page findings from the PR #75 review

PR #75's review (2026-09-02) confirmed four defects in code that predates that PR —
the version-data page wave (ADR-0076) — and they were left out of the PR to keep it
scoped. All four are in files main already carries:

1. **`aria-sort` is inverted on the three count columns** of
   `frontend/src/pages/data/version-changes.astro`: the forward (no-suffix) sort is
   largest-first, i.e. descending, but `ariaSort()` maps it to `"ascending"` — the
   arrow glyph and the sr-only text say the opposite of the actual order, and
   `docs/a11y/routes.json`'s `version-data-sorted` entry bakes the inverted
   attribute into the baseline. Only the Title column is correct.
2. **`?sort=classified-desc` puts the null-share rows first**: `sortTitleRows`
   (`frontend/src/lib/versiondata.ts`) sorts null `textClassifiedShare` last in the
   forward order and `-desc` is a bare reverse, so title 18a's em-dash row ranks
   above the genuinely smallest shares. ADR-0071's classification sort keeps nulls
   last in both directions via a direction-aware flag; this one should too, and
   `versiondata.test.ts` asserts null placement only forward.
3. **The sortable column-heading block is a verbatim second copy** of
   `ClassificationTable.astro`'s (`ariaSort()`, `headingHref()`, the arrow glyphs,
   the sr-only strings). Fixing item 1 in one copy alone entrenches the divergence;
   extract a shared sort-heading component first.
4. **Guide chapter 09 carries two justifying clauses** ("…rather than from the
   database, so the page reads the same on any copy of this site", "…because the
   classification tables begin at the 104th Congress…") that Documentation duties 7
   prohibits; the rationale belongs to ADR-0076.

Items 1–3 are one small session together (1 and 2 change sorted output, so the a11y
baseline and `versiondata.test.ts` move with them); item 4 is a two-sentence edit
that can ride along.

---

## Deleted from the unapproved UI plan, and why

The rest of `docs/ui-improvements-plan-unapproved.md` was dropped rather than folded
in, so that a later reader does not go looking for it:

- **Explicit theme toggle** — done. Superseded by **ADR-0027** the same day the
  proposal was written; the toggle ships in `SiteHeader`, stamped on
  `<html data-theme>` before first paint and remembered in `localStorage`.
- **Glassmorphism on the sticky chrome** (`backdrop-filter: blur(10px)`) — a
  translucent bar over statutory text is a contrast hazard, and the site's whole
  claim is that the law is legible. Not adopted.
- **Typography upgrade to a webfont** (Inter for the UI apparatus) — a webfont is a
  render-blocking external asset on a server-rendered site whose page weight is
  currently one ~3 KB island. Not adopted at that price. *Overtaken by ADR-0052
  (2026-08-05): two faces are now served from this origin, Latin-subset WOFF2 built
  by `scripts/fonts.py` — 125,720 bytes, 45,872 of it preloaded, no external host.*
- **Micro-animations / `transition: all 0.2s ease`** — `transition: all` is a
  performance and accessibility footgun, and nothing here honours
  `prefers-reduced-motion`. Not adopted as written.
- **Toast notifications for watch add/remove** — the underlying complaint was real
  (focus and announcement after a client-side mutation) and was fixed directly
  instead: the revealed control takes focus and the status element is a live region.
