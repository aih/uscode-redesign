# ADR-0071 — Four orders from two controls, and a pager that numbers its pages

**Status:** accepted (2026-08-15)

**Task:** the classification flow's ordering and paging, and the pager everywhere else that pages.

**Amends:** ADR-0067 (the session page's two-value `?sort=`), ADR-0070 (the by-code views, which
had no order control at all).

**Related:** [ADR-0042](0042-contrast-computed-from-the-tokens.md) (a colour that is not a token),
[ADR-0049](0049-search-ranking-measured.md) (`?sort=` on search results),
[ADR-0053](0053-design-system-page.md) (the design page as the regression surface).

## Context

Three views on this site page a list, and all three paged it one page at a time. The classification
session page is the worst of them by an order of magnitude: the 104th Congress's whole-congress
table is 11,737 rows, which at 50 to a page is **235 pages**, and the only route to page 200 was
199 clicks on Next. The control also said nothing about size — a Next button is the same button on
page 2 of 3 and on page 2 of 235 — so a reader could not tell whether the thing they were looking
for was one turn away or two hundred.

Ordering was thinner still. A session page offered `pl` and `code` and neither could be reversed;
the by-code views — every row classified to one title, or to one section (ADR-0070) — offered
nothing, and `sort=code` for a title was already recorded as owed. "What has Congress done to title
42, section by section" was a question the data could answer and no URL could ask.

## Decision

### 1. One sort vocabulary, four values, two defaults

`storage.CLASSIFICATION_SORTS` is `pl`, `pl-desc`, `code`, `code-desc` — a key and a direction in
one value, so one view is still one URL and a sort is one query parameter rather than two. Every
listing route takes it and every response reports it.

The keys mean what they always meant. `pl` is public law order: inside one document that is the
source's own row order, because OLRC publishes a session table in public law order; across
documents it is the oldest law first. `code` is the Code's own order, `title_sort_key` then the
section number (gotcha 16).

What differs between views is which value is the **default**, and the difference is not an
inconsistency: a session page is a document as published, so `pl`; a by-code view is a history, so
`pl-desc`, newest law first. Each view omits its own default from the URL, so every URL that worked
before this change still names the same view.

### 2. A descending order is the ascending one reversed

Not a second comparator written the other way round. Two comparators can disagree about ties — and
these have ties, since 1,533 rows derive no `usc_identifier` and 2 no public law — and then a page
turned back is not the page it came from. `_code_ordered_page` sorts the keys once and reverses the
list; `_pl_order` is one function with a flag, and rows with a null Pub. L. cell sort **last in
both directions** rather than first, which is what a descending SQL sort does with a NULL left
alone.

### 3. The column heading is the same control as the sort bar

Two controls over one setting: the bar names the orders, and the heading of a column the server can
order by is a link that sorts by it. Selecting the order already in force reverses it; selecting
the other key starts it in its own ascending direction rather than carrying the current direction
across — a reader choosing "U.S. Code" is asking for the Code's order, not for the reverse of the
one they were in.

Only two of the five columns. Description, Sec. and Stat. page hold the source's own notation —
`nt [tbl]`, `2(6), (7)`, `1501A-594` — and an alphabetical order over any of them would be an order
over a notation rather than over anything a reader is looking for.

`aria-sort` goes on the header cell and names the direction in force; the link carries a
visually-hidden phrase saying what activating it does. The arrow is decoration — `▲`/`▼` for the
column in force, `↕` for one that could be — because a glyph is not a word, and neither is it the
accessible name.

The same rule governs the sort bar: the option in force is a **link**, not an inert
`aria-current` marker. Reversing the order is exactly what a reader wants from the option they are
already on.

### 4. The pager numbers its pages, and takes a page number

`Pager.astro` is one control for every paged list — search results, a session table, a title's or a
section's classification rows. It draws the page you are on and how many there are, Previous and
Next, the first page, the last page, and a window of two either side, with a gap marked wherever
the sequence skips. Where the numbers cannot reach every page it also renders a **Go to page**
form.

No script. Every control is a link or a GET submission, so the whole thing works with JavaScript
off and each page is an address that can be shared — the property the sort control and the filters
already had.

The jump form is why `?page=` exists beside `?offset=`. `?offset=` stays canonical — it is the
API's own parameter, every link writes it, and it survives a change of page size — and it wins
where both are present; `?page=` is 1-based, because a person typing a page number should not have
to multiply. `pageOffset` reads the pair, and an unreadable value is the first page, the rule
`readOffset` and `?sort=` already followed.

The arithmetic is `lib/pager.ts` rather than component frontmatter, and it is tested in Vitest at
the sizes the corpus has. The CI fixture corpus's largest classification table is 84 rows — two
pages — so the browser suite cannot exercise a window, a gap or a jump box at all; the design page
renders a 235-page specimen so that the axe matrix and `make shots` can.

### 5. `Previous` and `Next` stay in place when they cannot move

Rendered as inert `aria-disabled` spans at the two ends rather than removed. The row of controls
keeps its shape as a reader moves through it, and a control that vanishes at one end is a control
they have to look for at the other.

## What this does not do

- **The registry table and the ECCT are not sortable.** The registry is 33 rows in the order that
  answers the question it is there to answer — newest table first — and the ECCT is 21 rows across
  two documents. Both are small enough to read whole, and a sort control over either would be a
  control for a problem nobody has.
- **`/app/releases` and a section's version timeline are not paged.** 382 release points and a
  section's versions are lists a reader searches with their browser's own find; paging them would
  hide rows from it.
- **No sort by Description.** Grouping a table by what was done to each section is a real question —
  "what did this law repeal" — and the answer is a filter over `action`, not an order over
  `description_raw`. It is not built.

## Consequences

- `sort=code` on a by-code view sorts in Python over every matching row's key, as the session page
  already did. Bounded by the filter: 11,737 keys for the largest single document and **23,093 for
  the largest by-code view**, title 10 across every table. Two queries per page rather than one.
- The API's `ClassificationPageOut.sort` is now populated on every listing route, where it used to
  be the session route's alone. `tests/test_classification_api.py` asserts the route's `Literal` and
  `CLASSIFICATION_SORTS` are the same list, since the type has to be written out for OpenAPI to read
  it and two copies drift.
- Two colour defects, both ADR-0042's shape, found by rendering this and looking at it in the dark
  theme:
  - **`:root[data-theme="dark"] a` is 0-2-1** and `.sortbar__option--on` was 0-1-0, so the moment
    the option in force became a link its text took the dark link blue on a light blue fill and
    disappeared. Three classes now, the count ADR-0064's wordmark needed.
  - **USWDS paints `th[aria-sort]` in a fixed `#97d4ea`**, and applies it to `aria-sort="none"` as
    well as to the two real directions — so declaring the attribute turned two headings pale blue in
    the light theme and left them unchanged in the dark one, where the theme block repaints `th`. The
    cell keeps the header background it always had.
  A third, older and left alone: **`a { color: var(--link) }` is declared inside the dark block
  alone**, so an ordinary link in the light theme is the browser's `#0000EE` rather than the brand
  indigo, everywhere outside the statutory text. `.classtable__sortlink` sets the token explicitly;
  the site-wide version of that is not this task's.
