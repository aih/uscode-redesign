# ADR-0059 — The theme and density toggles drop their words below 64em

- **Status:** Accepted
- **Date:** 2026-08-07
- **Context:** Session 35. The deployed site was three merges behind because CI had been red since
  session 33, on one assertion in `typography.spec.ts`.
- **Amends:** [ADR-0054](0054-the-statute-is-set-to-a-spec.md) (the density label's reserved width no
  longer applies at every width), [ADR-0058](0058-the-site-menus-collapse-into-a-hamburger.md) (the
  same band, the same move applied to two more controls)

## Context

`typography.spec.ts`'s "costs the sticky stack nothing" hides the density control and asserts the
header is the height it was. It failed at 640px, and only at 640px, reporting **11.515625px** — the
same number in four consecutive runs, before and after a change written to fix it.

It is not a wrapped row. The sibling assertion measures the row's slack and passed throughout. At
640px `.navtools` is 530px wide and carries:

| item | width |
|---|---|
| search box | 166 |
| account control | 149 |
| `≡ Compact` | 119 |
| `☾ Dark` | 60 |
| three gaps | 36 |

The search box is what is left over, and **164px is what it needs** to keep "Search or go to a
citation" on one line beside the `ⓘ`. Two pixels. In CI it does not have them — `.authnav` measures
149px on macOS and 154 on Linux — so the label runs to a second line, `.sitesearch` grows 11.515625px,
and the header grows with it. Hiding the density control returns 131px, the label fits again, and
the difference is the whole of the failure.

The assertion was right. A control that decides whether the box beside it wraps *is* a control that
costs `--sticky-h`. The measurement it makes is also a description of what the band looked like: the
input at that width was ~120px.

An earlier attempt set `.navtools .sitesearch`'s `flex-basis` to `0` in the band, on the theory that
the row was wrapping. That is a correct statement about the row — it removes the box from the flex
line's break calculation — and it does not change the box's rendered width, which is what wraps here.
It is kept; it is not the fix.

## Decision

Below 64em the theme and reading-density toggles render their icons and not their words.

1. `.density-toggle__label` and `.theme-toggle__label` are `display: none` in `max-width: 63.99em`.
   This is the move ADR-0058 made for the nav, in the same band and for the same reason.
2. The rule sits immediately after `.density-toggle__label`'s base declaration rather than beside the
   other small-width nav rules. `display: inline-block` on that base rule is later in `site.scss`
   than the 40–64em block, and a media query adds no specificity, so an override written up there
   loses on source order — and loses for one of the two labels, which is worse than losing for both.
3. `display: none`, not a visually-hidden class. Both buttons already set `aria-label` and `title`
   from their own islands, naming the destination of the click; the words on screen are the visible
   half of a name that is stated twice.
4. ADR-0054's `min-width: 6.6em` on the density label stays as written and stops applying with the
   label. It exists so the theme toggle does not move when the word alternates between "Compact" and
   "Comfortable"; with no word rendered there is nothing to alternate, and
   `typography.spec.ts`'s "does not move the theme toggle when it changes" runs at 1280 where the
   label is still there.

Measured after, on `/app/us/usc/t16/s45f`, in the Linux Chromium the CI job uses:

| width | search box | header | cost of the density control |
|---|---|---|---|
| 375 | 265 | 232 → 176 | 56 → 0 |
| 640 | 166 → 301 | 120 | 11.5 → 0 |
| 700 | 225 → 361 | 120 | 0 |
| 1024 | 357 | 124 | 0 |
| 1280 | 357 | 124 | 0 |

## Consequences

- The 640px slack is a control's width rather than a rounding error, and the search input at that
  width is usable.
- 375px gains the same thing without being asked: the tools row no longer wraps there, so the header
  is 176px against 232.
- The words are gone in the band. A reader who does not hover, does not use a screen reader and does
  not recognise `≡` has an unlabelled icon; the guide states what the two icons are (chapter 02).
- Two controls now read differently either side of 1024px. `/app/design` renders neither, so the only
  place either one is seen is the live chrome.
- A layout with two pixels of slack passes on one operating system and fails on the next. The row's
  slack assertion exists for exactly this and did not catch it, because what wrapped was one level
  down. Nothing added here measures the search box's own label against the width it is given.
