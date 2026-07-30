# Backlog

Work that is decided-worth-doing but deliberately not scheduled yet. Items graduate
out of here into a session plan; items that get overtaken by an ADR are deleted with
a note saying which ADR overtook them.

Open debts that are *recorded in an ADR* (email verification and password reset —
ADR-0019; `<ref>` links in the reader redline — ADR-0026) live in that ADR, not here.
This file is for work with no ADR behind it.

---

## B1. The smart sticky header

`--sticky-h: 18rem` between 40em and 64em (`frontend/src/styles/site.scss:106`)
permanently occupies roughly 37% of a landscape-tablet viewport, and
`scroll-margin-top` reserves 296px above every anchor jump so that a deep-linked
provision clears the bar. Below 40em the mitigation is real and well-engineered
(`site.scss:319-331`); the middle breakpoint has none.

The proposal is a "smart scroll" chrome: hide the main `.topbar` on scroll down,
restore it on scroll up, and keep only the compact `SectionBar` pinned at all times.

Costs to weigh before doing it, because they are what make this a session of its own
rather than a patch:

- It needs a scroll-listening island, and ADR-0022's whole position is that islands
  are added one at a time and measured. The refresh in Session 10 added ~3 KB total.
- `--sticky-h` currently drives `scroll-margin-top`. If the bar's height becomes a
  function of scroll direction, the anchor-jump guarantee has to be re-derived — the
  e2e assertion that holds the 18rem figure honest (`make test-e2e`) is testing a
  static number today.
- ADR-0027's measurement is the authority on the real stack height, and it
  disagrees with the 18rem figure quoted in the (now deleted) unapproved UI plan.
  Re-measure before designing.

*Origin: the surviving half of `docs/ui-improvements-plan-unapproved.md`, folded in
here 2026-07-30 when that untracked file was deleted.*

## B2. Break up the monolithic `site.scss`

`frontend/src/styles/site.scss` is ~1,270 lines in one file. Component-specific
rules could move into the `<style>` block of the Astro component they belong to and
get Astro's scoping for free, leaving `site.scss` for tokens, resets, and the USWDS
`@forward` list.

This is worth doing mainly because of what it would have caught: `signup.astro`'s
`usa-hint` class renders unstyled because `site.scss` never `@forward`s that USWDS
package, and nothing about a 1,270-line global file makes that visible. Any refactor
must keep the ADR-0027 theme tokens (`--page`, `--ink`, `--muted`, `--panel`,
`--link`) global — they are stamped on `<html data-theme>` before first paint and
every component reads them.

*Origin: the surviving half of `docs/ui-improvements-plan-unapproved.md`, folded in
here 2026-07-30 when that untracked file was deleted.*

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
  currently one ~3 KB island. Not adopted at that price.
- **Micro-animations / `transition: all 0.2s ease`** — `transition: all` is a
  performance and accessibility footgun, and nothing here honours
  `prefers-reduced-motion`. Not adopted as written.
- **Toast notifications for watch add/remove** — the underlying complaint was real
  (focus and announcement after a client-side mutation) and was fixed directly
  instead: the revealed control takes focus and the status element is a live region.
