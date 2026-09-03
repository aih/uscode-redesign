# ADR-0081 — One install row, and no banner

- **Status:** Accepted
- **Date:** 2026-09-02
- **Context:** `docs/pwa-spec.md` Phase P4 (findings 8, 11, 15, 19);
  ADR-0079 (the manifest and standalone behaviour), ADR-0080 (the service
  worker and the offline page), ADR-0061 (the More menu), ADR-0064 (the
  mobile sheet). Session 97.

## Context

ADR-0079 made the reader installable and gave the site nothing that says so.
Chromium's own affordance is an omnibox icon most readers never notice; iOS
has no affordance at all beyond the Share sheet (finding 15). The spec asks
for one install surface: a row in the More menu's HELP group, and nothing
else.

## Decision

1. **One row, hidden by default.** `InstallApp.astro` renders a button and a
   link into the HELP group of More, both `hidden`. The island reveals at
   most one of them, so a browser where installation is not on offer shows
   no row at all — the menu is unchanged for most readers most of the time.
   Below 64em the More panel is the open sheet (ADR-0064), so the row is in
   the same HELP group there without further work.

2. **Chromium: stash the event, prompt on click.** `beforeinstallprompt` is
   Chromium-only (finding 19). The handler calls `preventDefault()` —
   otherwise Android shows its own mini-infobar — stashes the event and
   reveals the button; the click calls `prompt()`. The stashed event is
   single-use, so the click also hides the button and drops the stash; a
   dismissed prompt is re-offered only when Chromium refires the event,
   which is the browser's own throttle rather than one written here.
   `appinstalled` hides everything.

3. **iOS Safari: a link to the instructions.** There is no prompt API; the
   row is a link to guide chapter 02's install section, which describes
   Share → Add to Home Screen. Revealed on iOS and iPadOS (which reports
   itself as a Mac with touch points) when not standalone, and not in the
   WebKit shells whose share sheet the guide does not describe (CriOS,
   FxiOS, EdgiOS).

4. **Never in an installed window.** The script checks
   `display-mode: standalone` / `navigator.standalone` before wiring
   anything, and a `@media (display-mode: standalone)` rule hides the row in
   the stylesheet as well — covering the interval between `appinstalled` in
   another window and this one's next load.

5. **No banner.** An install banner interrupts the reading it is trying to
   sell, is dismissed once and resented after, and Chromium's mini-infobar
   already exists for browsers that want one. The menu row is discoverable
   exactly where every other site-level control lives and costs a reader
   who never wants it nothing.

## Consequences

- **Every route's JS budget rises a third time** (after ADR-0079 and
  ADR-0080): the island is in `SiteHeader`, which every route renders.
  Ceilings re-measured per `docs/js-budgets.json`'s headroom rule.
- **The row is invisible to the axe matrix and `make shots`**: CI's
  Chromium fires no `beforeinstallprompt` and is not iOS, so every scan sees
  the hidden state. The revealed states are covered by the manual device
  pass `docs/deploy-status.md` owes.
- **Firefox never shows the row.** It implements neither
  `beforeinstallprompt` nor an install flow for this shape of site; the
  guide's install section is still reachable through the guide itself.
- **The iOS link shows in tab Safari on macOS Sonoma+ only if the UA
  matches iOS strings, which it does not** — macOS Safari readers install
  via File → Add to Dock, documented in the guide and offered by no row.
  Accepted: a row for a flow with no API and no distinguishing signal would
  show for every macOS reader on every page.
- **The not-Safari UA exclusion is a list, and the list misses shells** —
  OPiOS, DuckDuckGo, and desktop-UA Chrome on iPad (which drops `CriOS` and
  passes the Mac-with-touch test) all get the Safari share-sheet
  instruction. Since iOS 16.4 their own share menus also offer Add to Home
  Screen, so the guidance lands a menu away rather than wrong.
