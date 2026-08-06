# ADR-0058 — The site menus collapse into a hamburger below 64em

- **Status:** Accepted
- **Date:** 2026-08-06
- **Context:** Session 33, asked for directly — the menus alone take up a lot of space on mobile and
  should collapse at smaller widths
- **Amends:** [ADR-0011](0011-astro-uswds-frontend-at-app.md) (the nav is no longer a plain wrapping list at
  every width), [ADR-0056](0056-the-release-switcher-returns-to-the-sticky-bar.md) (the same
  disclosure, applied to the site chrome)

## Context

`SiteHeader` carried this reasoning in its own docstring:

> USWDS's basic header, and no JavaScript: the nav is a plain list that wraps on a phone rather than
> a menu that has to be opened. A menu you must tap to see is worse than four links you can already
> read.

That was written when there were four links. There are seven — Titles, Release points, My
Provisions, User guide, API docs, About, Downloads — and the footer carries nine. Measured on
`/app/us/usc/t16/s45f` before this change:

| width | header | footer nav |
|---|---|---|
| 320 | 416px | 392px |
| 375 | 416px | 326px |
| 640 | 272px | 124px |
| 700 | 216px | 124px |
| 1280 | 124px | 124px |

At 375px that is 742px of menu on a 812px screen, before a word of statutory text.

Between 40em and 64em it is worse than tall, because in that band the header is sticky and counted
in `--sticky-h`, which is what `scroll-margin-top` spends. ADR-0044's own note records the
mechanism: "About" and "Downloads" joining the nav added a 44px band and pushed the measured stack
to 386px against a 352px token, so every anchor jump in the band landed 34px behind the bar.

## Decision

### 1. Both menus are a native `<details>`, collapsed below 64em

`.navmenu` wraps the navbar's `<ul class="usa-nav__primary">`; `.footmenu` wraps the footer's list.
The summary is a hamburger reading **Menu** in the header and **Site links** in the footer, with a
bars icon that becomes a cross while the panel is open.

Native `<details>`, for the reason ADR-0056 chose it for the release switcher: it costs no script,
it works with scripting off, and `<summary>` is exposed as a button carrying its own expanded state,
so there is no `aria-expanded` to keep in sync. Per-route inline script bytes are unchanged, which
is what `tests/jsbudget.test.ts` asserts.

The header's panel is `position: absolute`. In the 40em–64em band the header is sticky, so a panel
in flow would be `--sticky-h` growing while it happens to be open; out of flow, opening it moves
nothing. `sticky.spec.ts` measures the header's box open against closed at 700px. The footer's panel
is in flow: nothing down there is pinned, and a reader who asked for the links wants the page to
grow.

The footer's disclaimer — "not an official publication of the United States government" — is outside
the disclosure. It is the sentence someone arriving from a search engine most needs, and it stays on
screen.

### 2. From 64em up the summary is hidden and `::details-content` is forced visible

```scss
@media (min-width: 64em) {
  .navmenu__summary, .footmenu__summary { display: none; }
  .navmenu::details-content, .footmenu::details-content { content-visibility: visible; }
}
```

A closed `<details>` hides its content through that pseudo-element and through nothing else — the
light-DOM children cannot be reached by any other selector — so this is what makes one element serve
as a drawer at one width and a row of links at another.

Where the browser does not implement `::details-content`, `@supports not selector(::details-content)`
leaves the summary on screen at desktop widths as well. A hamburger on a desktop is a worse menu; a
menu with no way into it is not a menu.

### 3. `--sticky-h` drops from 25rem to 23rem in the 40em band

The token has to stay at least as large as whatever actually sticks. Re-measured after the change,
on `/us/usc/t16/s470a`, scrolled:

| width | sticky stack before | after |
|---|---|---|
| 640 | 393px | 297px |
| 700 | 337px | 241px |
| 1280 | 218px | 218px |

23rem is 368px: 71px of headroom at 640px, which is the worst case in the band because it is the
narrowest width in it and the breadcrumb wraps furthest. That is 32px of every anchor jump in the
band given back to the text. The desktop token is untouched.

## Consequences

Measured after, on the same page:

| width | header | footer nav |
|---|---|---|
| 320 | 276px | 45px |
| 375 | 232px | 45px |
| 640 | 176px | 44px |
| 700 | 120px | 44px |
| 1280 | 124px | 124px |

### What it cost

**Two links to reach a link, on a phone.** Every destination in the site chrome is now behind a tap.
That is the trade the measurements above are the case for, and it is the one `SiteHeader`'s old
docstring refused when there were four links to refuse it for.

**`Escape` does not close either menu.** The same cost ADR-0056 recorded for the release switcher,
and for the same reason: the disclosure is native, so dismissal is the summary and nothing else.

**The search box is narrower on a phone.** The hamburger shares its line with `.navtools`, which
leaves the box 265px at 375px rather than the 343px it had. Measured both ways: giving `.navtools`
the whole line puts the hamburger on a line of its own *and* the account control and the two toggles
then need two lines between them — 276px of header against 232px for this.

**The account control and the two reading toggles stay outside the menu.** They are in `.navtools`,
not in the nav list, so they are still two rows of a phone's header. Folding them in would move
components between containers that `/app/design`, the theme e2e suite and the a11y state matrix all
address where they are.

### The trap this found

`*, ::before, ::after { box-sizing: inherit }` is USWDS's reset, and it matches no pseudo-element.
`::details-content` is a box the disclosure inserts between the element and its panel, so the
inheritance chain broke there and every link in both menus inherited `content-box`. Below 64em
nothing showed it. From 64em up, where USWDS gives `.usa-nav__link` `height: 100%` on top of 1rem of
padding, it was 28px of extra header on every desktop page — chrome `--sticky-h` pays for, at the
widths that never see the hamburger at all. `.navmenu::details-content { box-sizing: border-box }`
is the fix, and the desktop stack measures exactly what it did before the disclosure existed.

The second one, smaller: USWDS's small-width `.usa-nav` is the off-canvas drawer, so it is a centred
flex **column**. Overriding it with `display: flex` alone left `flex-direction: column` in force,
which stacked the hamburger above the search box above each toggle and read `.navtools`' 16rem
`flex-basis` as a height — 308px of header at 700px, where the whole exercise was to spend less.

## How to check it

```
make test-web      # jsbudget: no route pays a byte more of inline script
make test-e2e      # chrome.spec: hidden at 375, a row at 1280, opens over the page
                   # sticky.spec: the header is the same height open as closed at 700
make test-a11y     # the `menus-open` state — both panels open at 375, scanned
make shots         # nothing scrolls sideways at 320, panel included
```
