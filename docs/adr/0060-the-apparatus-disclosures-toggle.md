# ADR-0060 — The notes and source-credit disclosures look like controls, and toggle

- **Status:** Accepted
- **Date:** 2026-08-07
- **Context:** Session 34, asked for directly — make it apparent that Source and Notes can be
  toggled open and closed
- **Amends:** [ADR-0054](0054-typography-for-statutory-text.md) (the apparatus keeps its
  interface face; how it opens and closes changes), [ADR-0055](0055-navigation-inside-a-section-and-a-keyboard-map.md)
  (`c` and `n` open what they land on)

## Context

`lib/uslm.ts` wraps a section's `<sourceCredit>` and `<notes>` in a `<details>`, rendered closed,
with the element's name as the summary. `site.scss` styled that summary as uppercase muted 0.8rem
text at `display: flex`.

Two things followed from that, and the second is the one that matters.

**There was no caret.** A `<summary>` draws its disclosure triangle as a `::marker` on a
`display: list-item` box. Setting any other `display` removes it, so `display: flex` — there for the
44px touch target — left the word alone on the line. `SOURCE` and `NOTES` read as headings, which is
what they look like.

**On a wide screen the control was inert.** The stylesheet forced the collapsed box visible from
40em up:

```scss
@media (min-width: 40em) {
  .uslm-details::details-content { content-visibility: visible !important; block-size: auto !important; }
}
```

That rule wins over the element's own state, so it applies open or closed. Clicking the summary
flipped the `open` attribute and changed nothing on screen. Every desktop reader who tried the
control got no response from it.

The rule exists because the wide default is open and the narrow default is closed, and CSS cannot
express that: the open state is an attribute, and only the markup or a script can set it. The markup
cannot, because one cached document is served to every width — the reasoning that keeps the theme
out of the HTML (ADR-0018, ADR-0027).

## Decision

### 1. The summary is drawn as a control, on `.rpswitch__summary`'s terms

A box, a caret pointing down closed and up open, a hover fill, and the focus ring `.copybtn` and the
hover card draw:

```
┌───────────┐        ┌───────────┐
│ SOURCE  ▾ │        │ NOTES   ▴ │
└───────────┘        └───────────┘
```

The caret is `::after` content rather than the native marker, which `display: flex` has removed and
which cannot be pointed the other way when the element is open. `width: fit-content` makes the
summary a chip rather than a full-width row, so the caret sits against the word it belongs to.
ADR-0056 chose this shape for the release switcher for the same reason it is chosen here: words that
have been a label for thirty sessions do not become a control by being clickable.

Print drops the box and the caret, both of which point at nothing on paper. The notes still print
open.

### 2. `ApparatusDisclosure.astro` sets the open state, and retires the override

An inline script on the pages that render statutory text — the section page and `/app/design`, not
`Base`, since every route pays for what sits in the layout (ADR-0055):

- at 40em and up, set `open` on every `.uslm-details`;
- stamp `document.documentElement.dataset.apparatus = "live"`;
- open the `<details>` the URL fragment names, on load and on `hashchange`.

The stylesheet's override is now `html:not([data-apparatus="live"])`. Until the script runs the rule
stands and the wide default is what it has always been; after it runs the attribute says what the
screen shows, and the summary toggles for real. Both paints show the same thing, so nothing flashes.

The viewport is read once, at load. A reader who resizes past 40em keeps the state they were reading
in rather than having the page open or shut under them.

### 3. `c` and `n` open what they land on

`KeyboardNav`'s `goTo` sets `open` when the target is a `<details>`. The two keys scroll rather than
navigate, so the fragment never changes and the hash handler above never sees them; without this,
`n` on a phone scrolls to a shut box with the answer inside it.

## Consequences

**With scripting off, the wide screen is exactly where it was.** The override still applies, the
notes are still visible, and the summary still toggles an attribute that changes nothing. That is
the pre-existing behaviour, kept as the fallback rather than repaired — repairing it needs the open
state in the markup, and the markup is shared by every width.

**A reader who resizes from a phone width to a desktop one gets closed disclosures.** The flag is
stamped whatever the width, so the override does not come back to open them. They toggle, which is
the state the reader can act on.

**The hover card opens its own fragment.** A card's HTML arrives after the script has run, and the
override it replaced used to cover the card too. Left alone, a preview of a repealed section — which
is often nothing but apparatus — showed a shut box, and Tab from the trigger stopped dead, because
`focusables()[0]` was a link inside `content-visibility: hidden` and focusing one silently does
nothing. `CitePreview` sets `open` on what it injects, in the same statement that sets the card's
label. Found by `preview.spec.ts`, which asserts ADR-0041's Tab-into-the-card.

**Every section page pays 988 more bytes of inline script**, as served. The count that ADR-0055
started, for the same reason: this is markup-state that cannot be markup.

**The summary chips add a row of chrome to the end of a section.** Each is 46px including its touch
target, where the flat label was the same height and looked like part of the text.
