# ADR-0062 — A command palette over the one search box

- **Status:** Accepted
- **Date:** 2026-08-10
- **Context:** Session 34, task B10 of `docs/menu-refinement-spec.md`
- **Amends:** [ADR-0055](0055-navigation-inside-a-section-and-a-keyboard-map.md) (the key map gains
  its first binding that holds a modifier)
- **Depends on:** [ADR-0023](0023-citations-parse-server-side-to-an-identifier.md) (unchanged — the form still
  posts to `/app/goto`), [ADR-0046](0046-per-route-javascript-byte-budget.md) (the cost is paid on
  every route)

## Context

`/` focuses the header's search box. That works while the box is on screen; below 64em it is inside
the hamburger (ADR-0058), so the key opens a menu in order to reach a control. And no single-letter
shortcut fires while focus is in a text field — the handler refuses them deliberately — so a reader
already typing somewhere has no keyboard route to the box at all.

Separately, several destinations this site serves are named in one place or in none. `docs/ia-map.md`
records `/app/settings` as reachable from no rendered page: `AuthNav` is its only linker and
`SiteHeader` does not render `AuthNav` while accounts are off (ADR-0034). `/app/diff` is three hops
from the text it compares — section, version history, pick two, diff — which is the gap task B5 owns
on the section header.

`docs/menu-refinement-spec.md` specifies a ⌘K palette as progressive enhancement of the one box,
with a citation group parsed client-side, a full-text row, and action rows.

## Decision

### 1. ⌘K opens a modal `<dialog>` carrying the same form

`CommandPalette.astro` renders a `<dialog>` holding a `role="search"` form with `method="get"` and
`action="/app/goto"` — the header box's action and the header box's field name. A closed `<dialog>`
is `display: none` by the UA stylesheet, so with scripting off it renders nothing and the site is
exactly what it was.

`showModal()` supplies the top layer, the focus trap, the inert background and `Escape` without any
of them being written here, which is why `ShortcutsDialog` is one too.

### 2. It parses no citations

The spec asked for a citation group parsed in the browser through `lib/cite.ts`. That is not
implementable as written: `cite.ts` is the *inverse* function — an identifier written out as a
citation — and `citeparse.py` is the only thing that decides what a citation is (ADR-0023). An
island is `<script is:inline>` and can import nothing, so a client-side parse would have been a
third copy of the parser, in the one place where disagreeing with the server means landing
somewhere else.

So the input submits to `/app/goto`, which is the router that already answers the question. The
palette gives the same result the header box gives because it is the same request.

The alternative considered and declined was a debounced fetch to `/api/v1/citation` to show the
parse before the reader commits. It keeps one parser and it costs a round trip per typing pause, an
unauthenticated fan-out this site does not currently have from the browser to `/api/v1`, and four
new failure states — for a preview of a destination that pressing Enter reaches anyway.

### 3. The rows are data, built on the server

`lib/palette.ts` has `siteCommands()` and `sectionCommands(identifier, releases, selected)`. Both
return `PaletteCommand[]`; `Base.astro` takes a `commands` prop and the section page fills it. Every
href goes through `url.ts` (architecture rule 5) and the module is unit-tested, which is the whole
reason it is a module: the island receives finished rows, the same way `KeyboardNav` receives its
three neighbour hrefs.

`sectionCommands` reads the previous release point out of the title's own release list, which the
section page already holds for the release switcher — so the B5 entry point costs no further API
call. That list is release points at which the *title* was published, not ones at which this section
changed, so the redline it opens can legitimately report no changes; the row names the release point
it will compare against, and `/app/diff` says `No changes` when the two texts match (ADR-0059).

There is no "add to My Provisions" row. Accounts are off in the reader (ADR-0034), so it would be a
command with nothing behind it.

### 4. `mod` is a field on the printed shortcut list, not a special case in the island

`Shortcut` gains `mod?: boolean`, and `keyMap()` writes those bindings as `Mod+k`. That prefix is
what keeps ⌘K and the plain `k` beside it — "next section" — two bindings rather than one
collision. `KeyboardNav` reads a held ⌘ or Ctrl only for a binding the list declares, and does so
*before* the text-field guard, because working while the reader is typing is the point of having
one.

The dialog prints both `⌘K` and `Ctrl K`. One cached document is served to every reader (ADR-0018),
so the page cannot know which modifier this keyboard has.

### 5. Rows are focused, not selected

`↑`/`↓` move real DOM focus between the rows rather than an `aria-activedescendant` around a
`role="listbox"`. The rows are links and one button, so `Enter` is the platform's: no handler
decides what activating a row means, and a row reached by Tab behaves like one reached by `↓`.

## Consequences

- **Every route pays 3,494 more bytes of inline script** — `CommandPalette` 2,568 and `KeyboardNav`
  926. The palette is in `Base`, so this is on the front page and the API docs page as much as on a
  section. It is the largest single island the chrome has added; the rationale that would ordinarily
  sit beside the code is in the component's frontmatter for that reason, which is where ADR-0055 put
  `KeyboardNav`'s. Ceilings raised in `docs/js-budgets.json` in the same commit.
- **⌘K is taken from the browser.** Chrome and Firefox both bind it to their own address-bar search.
  A reader who wanted that on this site no longer has it, and the only notice is the shortcut list.
- **`/app/settings` gains its first link from a rendered page**, which closes one line of
  `docs/ia-map.md`'s inbound-link table without any page having been changed.
- **The palette needs JavaScript**, and unlike the search box below it there is no no-script
  fallback for the command rows. Every one of them is a page linked from the header or the footer
  except the shortcut list, so nothing is only reachable this way.
- **`/app/design` renders it as a panel** (ADR-0053), which required the island's script to be
  conditional on `panel` — a second copy on that page would bind twice to the one real dialog and
  `↓` would skip a row.
- **A second `role="search"` landmark** exists on every page while the palette is open. Both carry
  `aria-labelledby`; `landmark-unique` is best-practice rather than WCAG and is not in the scan's
  tag set either way.
- The a11y matrix gains a `palette-open` state (`docs/a11y/routes.json`), scanned at 1280×900 in
  light, with no violation in the WCAG 2.1 AA tag set. `make shots` cannot cover the dialog — it is
  closed on every page that suite photographs — so the horizontal-overflow check WCAG 1.4.10 asks
  for is a test in `palette.spec.ts` at 320px instead.
