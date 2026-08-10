# ADR-0063 — The footer's links are grouped under four headings

- **Status:** Accepted
- **Date:** 2026-08-10
- **Context:** Session 42, task B8 of `docs/menu-refinement-spec.md`
- **Amends:** [ADR-0058](0058-the-site-menus-collapse-into-a-hamburger.md) (the same nine links,
  behind the same disclosure, in a different arrangement)

## Context

`SiteFooter` carried nine links in one `usa-list--unstyled`: Titles, Release points, User guide,
Search guide, Keyboard shortcuts, API documentation, Design system, About, Source XML (OLRC). A
wrapping flex row on a wide window, a stacked column behind the **Site links** disclosure below
64em.

Nine link texts in one run is a list a reader has to read through to search. Six of the nine name
their destination in a way that only means something if you already know the site: "Search guide"
and "User guide" are two different documents, "Design system" and "API documentation" are for two
different audiences, and "Source XML (OLRC)" leaves the site altogether.

`docs/ia-map.md` also records `/app/design` as reached from `SiteFooter` and nothing else, and the
Keyboard shortcuts link as the no-script fallback for the `?` dialog. So a rearrangement has to be
checked against that table rather than eyeballed: dropping one row here takes a page off the site.

## Decision

### 1. Four groups, each named by a real heading

| group | links |
|---|---|
| Browse | Titles, Release points |
| Learn | User guide, Search guide, Keyboard shortcuts |
| Developers | API documentation, Source XML (OLRC), Design system |
| Site | About |

The same nine hrefs, unchanged, in the order `docs/menu-refinement-spec.md` sets. `Accounts (SOON)`
appears in that document's mockup and is **not** here: the task specified the same nine links, the
header already carries one `ComingSoon` control for accounts, and a second one in the footer is a
second dead affordance for a feature ADR-0034 switched off.

Each label is an `<h2 class="footnav__label">` with an `id`, and the `<ul>` under it carries
`aria-labelledby` pointing at that id. So the groups are four headings a screen reader can jump
between and four named lists, rather than type set to look like headings. The words are written in
sentence case and uppercased in CSS, so the accessible name is "Browse" and not "B R O W S E".

### 2. Four columns from 40em, two from 25em, one below

A CSS grid on `.footnav`, at the breakpoints the spec sets. `.usa-footer__nav` needs
`flex: 1 1 100%` to get them: it is a flex item of `.usa-footer__primary-container.grid-row` and
shrinks to its content there, which would size the columns to the longest label rather than to the
footer.

The **disclosure is untouched** — ADR-0058's `.footmenu` still collapses all four groups below 64em,
and the disclaimer still sits outside it. So the columns at 40em–64em are what a reader sees after
opening **Site links**, not instead of it.

### 3. USWDS's per-link rule goes below 64em

`.usa-footer__primary-link` carries `border-top: 1px solid` below 64em — the divider a stacked list
of nine links wants. With the links in groups, the rule above each group's first link lands directly
under that group's label and reads as an underline on the heading. The groups are the structure now,
so the rule is dropped in that band.

## Consequences

`.usa-footer__nav` on `/app/us/usc/t16/s45f`, disclosure open, before and after
(`make footnav` → `docs/verification/footnav.json`; the before column is the same command against a
tree at `f5d49a0`):

| width | before | after | columns |
|---|---|---|---|
| 320 | 576px | 675px | 1 |
| 375 | 576px | 675px | 1 |
| 420 | 576px | 442px | 2 |
| 640 | 566px | 290px | 4 |
| 700 | 566px | 290px | 4 |
| 1280 | 124px | 195px | 4 |

Closed, the footer is one 44px summary at every width below 64em, as it was.

### What it cost

**99px more open footer at 320 and 375 CSS px.** Below 25em there is one column, so the four labels
and the gaps between the groups are added to a list that was already one link per line. That is the
worst case in the table and the width ADR-0058 was arguing about. Two columns at 320px would take it
back — 144px per column, which "API documentation" and "Keyboard shortcuts" would each wrap in — and
the spec sets the second column at 25em. Left at the spec's breakpoint; task B9 owns the phone
chrome and can revisit it with the header measurements in hand.

**71px more footer at 1280.** The nine links were one wrapping row, 44px tall; four columns with a
label row and three links in the longest of them cannot be. This is the trade the grouping is, and
it is paid on every page.

**Four more `<h2>`s in every page's heading outline.** A screen reader listing the headings on a
section page now finds Browse, Learn, Developers and Site after the provision's own. That is what
makes the groups navigable, and it is the reason they are headings rather than styled `<span>`s.

**Three labels wrap to two lines between 40em and 64em.** Four columns of 128px at 640px, against
which "Keyboard shortcuts", "API documentation" and "Source XML (OLRC)" each take 83px of row where
the six others take 57px. Only a reader who has opened the disclosure at a tablet width sees it.
