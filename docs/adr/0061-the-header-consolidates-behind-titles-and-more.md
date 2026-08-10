# ADR-0061 — The header consolidates behind Titles and More

- **Status:** Accepted
- **Date:** 2026-08-10
- **Context:** Session 35, workstream B task B7 — the Header spec of
  [`docs/menu-refinement-spec.md`](../menu-refinement-spec.md)
- **Amends:** [ADR-0011](0011-astro-uswds-frontend-at-app.md) (the nav is no longer a flat list of
  every destination), [ADR-0023](0023-one-box-search-and-citation.md) (the box loses its visible
  label and gains a row it shares), [ADR-0058](0058-the-site-menus-collapse-into-a-hamburger.md)
  (the hamburger now holds two nested disclosures), [ADR-0059](0059-the-toggles-drop-their-words-below-64em.md)
  (retired — neither toggle is on the chrome's row)

## Context

`SiteHeader` held eleven interactive items: seven links (Titles, Release points, My Provisions,
User guide, API docs, About, Downloads), an account control, two display toggles, and the search
box with its button. Seven of them are destinations a reader visits once and never again; two are
settings; one is the control the site is built around.

The cost was a second band of chrome. From 64em up the search box had a row of its own, because the
nav row could not spare the width: `.usa-nav-container` is USWDS's 1024px grid container, the
wordmark takes 238px and seven links took ~380px, which left the box 172px — not enough to read
`11 U.S.C. § 523(a)(1)(B)(ii)` in. ADR-0044 recorded the trade and named its price: the navbar is
sticky, so a band of chrome is viewport permanently spent and `scroll-margin-top` above every
anchor jump.

Below 64em the same eleven items were a hamburger plus four loose controls sharing a row that did
not fit — the measurement ADR-0059 was written about, where the search box got 166px against the
164px its own label needed and CI lost the two pixels.

## Decision

### 1. Four items at the top level

**Titles**, **My Provisions**, the one search box, and **More**. The contextbar's release switcher
(ADR-0056) is a different control on a different bar and is untouched; the header's "Release points"
link was only the archive page, and it is in More.

More holds, in order: REFERENCE (Release points, Downloads), HELP (User guide, API docs, About),
DISPLAY (the reading density and the theme, as the same two islands they have always been), and an
Accounts row last. That row is the slot `AuthNav` takes when `ACCOUNTS_ENABLED` flips (ADR-0034);
with accounts off it is the `ComingSoon` control it was in the navbar.

Titles offers seven titles and "All titles →". The shortlist is editorial and
`frontend/src/data/nav-titles.ts` says so where it is written: this site records no per-title
traffic, and the header reaches no data at all because `/app/design` renders it and is required to
make no API call (ADR-0053). The row reads "All titles", not "All 54 titles": a count in the chrome
is a number nothing re-derives, and this file would be its only source.

### 2. Both are `<details>`, and a script closes them

The disclosure is ADR-0056's and ADR-0058's — a `<summary>` is exposed as a button carrying its own
expanded state, so neither menu keeps an `aria-expanded` attribute in sync and neither needs a
script to open.

Closing is what `<details>` does not do. Two open menus overlapping, and a menu left open behind the
reader halfway down a section, are both real states of that markup. So `SiteHeader` ships the first
script the site chrome has had: Escape, an outside pointer, and one open at a time.

It is deliberately not `<details name>`, the platform's exclusive-accordion grouping. That closes
any same-named sibling including an ancestor, and below 64em both dropdowns sit *inside* `.navmenu`.
The script closes what does not contain what is being opened, which is the same rule with the
nesting case right.

The Escape handler steps aside for an open popover, because a popover owns Escape first: pressing it
over the Downloads explanation should shut the explanation, not the menu it was opened from.

### 3. The search box shares the nav's row, and its label is its placeholder

Three items instead of seven leaves room. Measured at 1024, 1280 and 1440 (the container caps at
1024 at all three): the input is **328px** on a shared row, against 172px when the row was last
tried and 544px on a row of its own. The visible label above the input is now `usa-sr-only` — the
name is still there for assistive technology, the placeholder carries the words on screen.

The proposal asked for a 620px cap and the placeholder "Search, or go to a citation — 11 usc
523(a)(1)". The cap is in the stylesheet and the 1024px container never reaches it; the placeholder
is not, because at 328px it truncates at "…11 usc 52". The box keeps "11 usc 523(a)(1), or any
words", which names both halves and fits.

The "i" moved with the label: it is a flex item of the box's own row now, between the input and its
button.

### 4. More is in the list, not at the far right

The proposal put a spacer between the search box and More. That needs either `order` on a flex item
or the search box in front of the menus in the markup, and both make the tab order differ from the
reading order at one width or the other. In the list, the reader tabs the header in the order they
see it at every width, and below 64em there is one menu rather than a hamburger with a second
disclosure loose beside it.

### 5. `--sticky-h` drops twice

The token is a hand-maintained budget that has to stay at least as large as whatever actually
sticks. Measured after this change on five sections including a subsection deep link, at every width
in each band:

| band | before | after | token before | token after |
|---|---|---|---|---|
| 40–64em (640, 700, 800, 1023) | 297 / 241px | 225px | 23rem (368px) | 18rem (288px) |
| ≥64em (1024, 1280, 1440) | 287px | 168px | 19rem (304px) | 15rem (240px) |

Below 40em nothing here is sticky and the token is unchanged at 3.25rem. Both new values keep the
60px of headroom `sticky.spec.ts` requires an addition to the chrome to argue its way past — 63px in
the band, 72px above it.

The guide's pinned chapter list carries its own offset, because `--sticky-h` is rounded up over a
*section* page's chrome and a guide page carries neither a context bar nor a section bar. That
number drifted with this change too: a guide page's sticky chrome measures **74px** at 1024, 1280
and 1440, where it was 124px, so the offset goes 8rem → 5rem.

The header itself: **74px** at 1280 (was ~120), **104px** at 375 and 700 (was 176 and 120),
**148px** at 320.

## Consequences

### What this costs

**Five links are a rung further away.** Release points, Downloads, User guide, API docs and About
were one click from any page and are now two — open More, then click. Nothing on the page says they
are in there beyond the word "More". This is the discoverability the consolidation spends: a
reader who knows the site loses a click on pages they visit rarely, and a reader who does not know
the site can no longer read the whole map without opening anything. The footer still lists all nine
destinations in the open, which is the mitigation and is B8's to arrange.

**Both display switches are two taps away on a phone**, where they were one. They are rows of More
at every width, because each island queries the document for a single button and a second copy for a
second width is not available. B9's mobile bar puts the theme toggle back on the bar.

**The site chrome ships JavaScript for the first time.** ADR-0011 and ADR-0058 both hold that the
chrome needs none, and both remain true of *opening* a menu — the disclosures work with scripting
off, and what is lost without it is Escape, outside-click and exclusivity. Every route pays the
bytes; `docs/js-budgets.json` records the ceilings and BUILDLOG 035 the growth.

**The search box is 328px rather than 544px** at desktop. The band of chrome it bought was the more
expensive of the two.

**The visible label is gone.** A placeholder disappears the moment someone types, which is why
USWDS asks for a visible label; the label is still the accessible name, so this is a usability cost
rather than a conformance one.

### What it buys

One band of chrome at every width from 40em up: 80px of `--sticky-h` in the 40–64em band and 64px
from 64em up, given back to the text on every anchor jump. A header of four things instead of
eleven. And a mobile header of 104px where it was 176.

### Traps hit here

**`::details-content` breaks `box-sizing: inherit` a third time.** USWDS's reset is
`*, ::before, ::after { box-sizing: inherit }`, which matches no pseudo-element, so every row inside
the new panels inherited `content-box` and a `min-height: 44px` row rendered at 60px. ADR-0058
recorded this for `.navmenu` and `.footmenu`; `.navdrop` joins that rule.

**Every `<summary>` in this site computes `content-box`** while the `<details>` above it computes
`border-box` — measured on `.navmenu__summary`, `.rpswitch__summary` and `.uslm-details > summary`,
against a bare `<summary>` appended to `<body>`, which computes `border-box`. USWDS's reset says
otherwise and does not win. Vertical padding on a summary therefore adds to `min-height` rather than
spending inside it, so the menu rows carry none and the 44px is `min-height` alone.
