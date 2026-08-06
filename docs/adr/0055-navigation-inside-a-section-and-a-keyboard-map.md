# ADR-0055 — Navigation inside a section, and one keyboard map for the site

- **Status:** Accepted
- **Date:** 2026-08-06
- **Context:** Session 31, asked for directly — a preview card cutting text off, no way into a long
  section, and keyboard navigation to be reviewed and documented
- **Amends:** [ADR-0054](0054-typography-for-statutory-text.md) (the ladder reaches the hover card),
  [ADR-0043](0043-one-navigation-chrome.md) (the section bar gains a second job)

## Context

Three defects, one of them a regression from the session before.

**The hover card cut text off on the left.** ADR-0054 gave the reading column an indentation ladder
and, alongside it, named the source's own `indentN` and `firstIndent-N` classes as global rules.
`firstIndent-N` is a negative `text-indent` of one to four steps — the printed Code's hanging
paragraph. The card was never in the ladder's selectors, so nothing there spent the padding those
rules hang back into, and the card's own scale was a `[class*="indent"]` override that halved
`margin-left` and could not reach `text-indent` at all. On `/us/usc/t16/s1391` the card rendered
`(a)`, `(b)` and `(c)` outside its own padding box, where `overflow-y: auto` clipped them: the
designators were invisible and every line under them lost its first character. In LTR there is no
scroll position that recovers content overflowing to the inline start, so it was not merely hidden.

**There was no way into the section on screen.** Every other navigation the reader has moves between
sections — the breadcrumb, the rail, the section bar, the neighbours. 16 U.S.C. § 45f is 7,300px
tall at 1280px, and its source credit and notes — the two blocks a drafter reaches for most — sit
past all of it, with nothing naming them and nothing linking to them.

**The keyboard had three keys and one paragraph.** `KeyboardNav` was on the section page alone and
bound ←/→ or j/k and `u`. The search box was reachable only by tabbing past the whole navbar, and
the list of what existed was a sentence at the foot of the one page whose shortcuts it described.

## Decision

### 1. The ladder is shared with the hover card; the scale is not

`.section-body .prov` becomes `.section-body .prov, .cite-preview__body .prov`, and the card sets
`--indent-step: 1em` on its own body.

This is the comma-joined selector the card's block already refuses for sizes, and it is right here
for the reason that one is wrong there: the two surfaces render the same markup and need the same
*structure*, and the only thing that differs — how wide a rung is — is a variable. Sharing the rule
shares the structure and leaves the scale local. Halving the variable also halves `firstIndent-N`,
which the `[class*="indent"]` override it replaces could not do, and which was the actual bug.

1em is the step the page itself spends below 40em, so it is a width the ladder is already known to
hold rather than a third number. The override it replaces is deleted: it matched `indent0`,
`indentUp2` and `indentTo54pts` alike — the same defect ADR-0054 removed from the page.

### 2. A section has its own contents, from `outline()`

`uslm.outline(fragment)` returns the top-level provisions with their numbers and headings, then the
source credit and the notes. `SectionContents.astro` renders it above the text as a bounded panel,
two columns from 40em, scrolling inside itself past about nine rows.

Top level only. The ladder goes seven deep (`docs/verification/ladder.json`), and a contents list
that recursed would be longer than the section it indexes for anything below `(a)(1)`.

Provisions need no new anchor: `@identifier` is already the `id` every provision renders with. The
apparatus does, because a `<notes>` container carries no attribute distinguishing it from any other,
so `RenderOptions.anchors` names the section's own two `#section-source` and `#section-notes`. It is
**opt-in and used once per document**: three things render this markup into one page — the section,
a further occurrence under the same identifier (ADR-0021), and the hover card, which inserts a
different section's body into the page the reader is on.

### 3. The section bar's number is the way back to the top

`§ 45f` in the sticky row links to `#main`, named "Back to the top of § 45f".

Nothing new may be pinned. `--sticky-h` is what `scroll-margin-top` spends (ADR-0044), so a second
sticky row would move every anchor jump on the page by its own height. The section bar is the only
chrome that stays put at every width, and it had a number in it that was not doing anything.

### 4. One keyboard map, in `Base`, from one list

`KeyboardNav` moves into the layout and gains `t` (top), `c` (contents), `[`/`]` (previous/next
subsection), `s` (source credit), `n` (notes), `/` (search) and `?` (the shortcut list). The list is
`lib/shortcuts.ts` and it is the single source: the dialog renders it, `/app/design` renders the
same component as a panel, and the island receives `keyMap()` as JSON, because an `is:inline` script
can import nothing and a binding written in the script would be a second copy of the printed one.

The help is a modal `<dialog>` opened with `showModal()` — the one element that gives a focus trap,
`Escape`, an inert background and the top layer without any of them being written here. The hover
card next door is a `popover` for the opposite reason: it appears beside the thing it describes and
the reader goes on reading past it.

The footer's control is an `<a>` to the guide chapter, upgraded by the island into a dialog opener.
A `<button>` would be a control that does nothing when the script has not run.

In-page jumps move focus as well as the scroll position — `tabindex="-1"` set at the moment of the
jump, then `focus({ preventScroll: true })`. Scrolling alone leaves a keyboard reader's next Tab
back at the top of the document.

## Consequences

- **Every route pays 3,678 bytes it did not pay before**, because `KeyboardNav` is now in `Base`.
  `/app/` goes from 9,000 to 13,000 in `docs/js-budgets.json` and `/app/us/usc` from 34,500 to
  37,500. That is the price of `/` and `?` being site-wide, and it is the reason the island's
  rationale is in its frontmatter docstring rather than beside the code: an inline script ships
  verbatim, so a comment in one is a comment every reader downloads. Written the ordinary way it was
  6,500 bytes a route.
- **`j` is previous and `k` is next**, which is the reverse of the convention every reader who knows
  those keys from elsewhere has. It is the binding ADR-0038's guide already documents and
  `guide.spec.ts` already asserts, and reversing it was not asked for. Now that the pair is printed
  in a dialog on every page rather than in one sentence at the foot of one page, the inconsistency
  is more visible than it was. Left as it is, and recorded here as owed.
- **Single letters navigate.** `t`, `s`, `n`, `c` and `u` fire on their own, so a reader who expects
  a letter to do nothing outside a text field will be surprised once. Form controls and
  `contenteditable` are excluded, as is anything held with Ctrl, Alt or ⌘; Shift passes only for
  `?`, which needs it on most layouts.
- **`[` and `]` need the contents list.** They read their targets off `.contents__link`, so a section
  with no top-level provisions — a one-paragraph repeal — has nothing to step through and the keys do
  nothing. The alternative was a second definition of "top-level provision" in the island, in a
  language that has no selector for it.
- **The contents panel costs vertical space above the text.** About 100px at 1280px for a section
  with eight subsections, more on a phone, where the two columns collapse to one. Bounded at 14rem,
  which is roughly nine rows; past that it scrolls rather than pushing the section's first sentence
  off the screen.
- **`#section-source` and `#section-notes` are reader-invented names in a namespace of
  identifiers.** Every other `id` in the statutory text is an `@identifier` from the source. These
  two are not, and they are prefixed so they cannot collide with one — no identifier begins
  `section-`, because all of them begin `/us/usc/`.
- **A jump to the apparatus below 40em lands on a closed `<details>`.** The reader sees the "Notes"
  summary and opens it. Above 40em `site.scss` forces the panel visible without opening the element,
  which is the mismatch ADR-0043 already recorded against `ChapterRail`; this decision inherits it
  rather than fixing it.
