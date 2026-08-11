# ADR-0064 — A bar and a search row below 64em

- **Status:** Accepted
- **Date:** 2026-08-10
- **Context:** Session 42, workstream B task B9 — the Mobile section of
  [`docs/menu-refinement-spec.md`](../menu-refinement-spec.md)
- **Amends:** [ADR-0058](0058-the-site-menus-collapse-into-a-hamburger.md) (the sheet is flat, and
  the hamburger sits on a bar rather than beside the search box),
  [ADR-0059](0059-the-toggles-drop-their-words-below-64em.md) (un-retired for the theme: it is on
  the chrome again below 64em, icon-only, which is what that ADR measured),
  [ADR-0061](0061-the-header-consolidates-behind-titles-and-more.md) (More is not a disclosure below
  64em, and the theme is one tap rather than two)

## Context

ADR-0061 left the header below 64em as two rows: USWDS's `.usa-navbar` carrying the wordmark, and
the nav's own row carrying the hamburger with the search box beside it. Everything else — five
links, two display switches and the account row — was behind **More**, which was behind **Menu**.

Three things were wrong with that on a phone.

The **theme was two taps and a scroll**: open Menu, open More, scroll to DISPLAY. ADR-0061 recorded
that as a cost and named B9 as the place it would be paid back.

The **search box shared a line** with the hamburger. That sharing is what ADR-0058's `flex-basis: 0`
addendum and ADR-0059 were both about: a flex line breaks on the sum of its items' hypothetical
sizes before any of them shrinks, so the box's own basis decided whether the row wrapped, and at 640
it got 166px against the 164px its label needed and CI lost the two pixels.

And **the sheet held a menu inside a menu**. More is a dropdown because a desktop row has no space
for eleven items; a sheet that already occupies the width of the screen has space for all of them.

## Decision

### 1. A 52px bar: Menu, the wordmark, the theme

`.navbar` is one flex row below 64em — the hamburger, the site's name, and the light/dark switch —
at `min-height: 3.25rem`, which is a 44px control with 4px of air above and below it. Above 64em it
is `display: contents` and its three children are items of the nav's own row, which is the
arrangement ADR-0061 built: the bar's wordmark and the bar's theme button are `display: none` there,
`.navmenu` is `display: contents`, and what is left is the list.

### 2. The search box has a row of its own, always on screen

`.navtools` is `flex: 1 1 100%` below 64em. Nothing shares its line, so ADR-0058's addendum and the
two band-scoped bases it left behind are gone: a wrap calculation over one item has one answer.

### 3. The sheet is flat

Below 64em `.navdrop--more`'s summary is `display: none` and its `::details-content` is forced
visible — `.navmenu`'s desktop arrangement run the other way round, since a closed `<details>` hides
its content through that pseudo-element and nothing else can reach it. The sheet reads Titles, My
Provisions, REFERENCE, HELP, DISPLAY, Accounts. There is an
`@supports not selector(::details-content)` fallback that leaves the summary, for the reason
ADR-0058 gives: a rung further in is a worse menu, and a menu with no way in is not one.

The spec asked for bare dividers between the three blocks. The group labels are the dividers
instead: they draw the same rule and also name what is under it, which is what
`aria-labelledby` on each list already claimed. The one row that moves against the spec's listing is
Downloads, which stays with Release points under REFERENCE rather than ending the block.

### 4. The wordmark is written twice

The two bands want it in a different place in the **document**, not only on screen: `.usa-navbar`'s
copy leads the desktop row, and `.navbar__brand`'s sits between the menu and the theme on the bar.
Exactly one of the two is `display: none`, so there is one home link in the accessibility tree and
one in the tab order — asserted in `chrome.spec.ts`.

The alternative is one wordmark and `order` on a flex item, and it is not available: the wordmark
must precede the menu at desktop and follow it on the bar, so whichever band gets the `order`
declaration is the band where the reader tabs a row in a sequence they cannot see. That is what
ADR-0061 decision 4 refused. Six lines of markup, hidden per band, is the cheaper of the two.

`display: contents` on the `<nav>` would also have reached the same layout without moving anything,
and was rejected: whether a boxless landmark stays in the platform accessibility tree is a claim
this project cannot check with the tools it has, and `.navbar` is a plain `<div>` where the same
declaration costs nothing.

### 5. The theme is two buttons and one script

`ThemeToggle` renders on the bar and in DISPLAY. Its script binds every `[data-theme-toggle]` and
paints all of them, so the copy that is not on screen is already correct when a resize reveals it.
It ships once, from the **last** instance in the document — an inline script runs where the parser
reaches it, and a copy emitted before the second button cannot bind it. `script={false}` is how the
earlier instance says so.

## Consequences

### What this costs

**The theme is reachable twice below 64em** — on the bar and in the sheet's DISPLAY group. The
Mobile section of the spec asks for both and this implements both. They are one setting and they
stay in step, so nothing can disagree; it is still two controls for one thing on one screen, and
dropping the sheet's row is a one-line change if that reads worse in use than it does on paper.

**The header is 112px where it was 104** at 375 through 1023, and 112 where it was 148 at 320 —
before the padding trim below. A bar that carries three things is taller than a row that carries
the wordmark alone.

**8px of the search row's padding is spent on `--sticky-h` rather than on air.** The first version
gave `.navtools` and `.usa-nav` half a rem each; measured, that put the sticky stack at 233px against
an 18rem (288px) token, and `sticky.spec.ts` asks an addition to leave 60px spare. A quarter rem each
returns the stack to ADR-0061's 225px and the headroom to 63px. The search box sits 4px under the
bar's rule rather than 8.

**`.navdrop--more` keeps an `open` attribute nothing reads below 64em.** `SiteHeader`'s script still
closes it as one of the `[data-navmenu]` set; the CSS forcing its content visible outranks that, so
the attribute is inert rather than wrong.

### What it buys

The light/dark switch is one tap from any page on a phone, where ADR-0061 left it two. The search
box is the full width of the screen on a row nothing else can wrap, and is on screen without opening
anything. The sheet is one list rather than a list containing a list. And at 320px the header is
36px shorter than it was.

### Traps hit here

**The `content-box` `<summary>` trap has a horizontal half, and it was live.** ADR-0061 recorded
that every `<summary>` in this site computes `content-box` while the `<details>` above it computes
`border-box`, and answered it by spending no vertical padding on a menu row. Horizontally the same
trap made `.navdrop__summary`'s `width: 100%` plus 2rem of side padding 32px wider than the sheet
holding it, which put the Titles caret past the right edge of a panel whose `overflow-y: auto` clips
the other axis too. The caret was drawn on every narrow window and could not be seen.
`box-sizing: border-box`, written out, is the fix.

**`:root[data-theme="dark"] a` is 0-2-1 and outranks a two-class rule.** The bar's wordmark came out
ink on a light bar and link-blue on a dark one — the same count `.contents__link` and
`.sectionbar__top` are already written against, met for the third time.
