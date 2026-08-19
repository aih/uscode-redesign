# ADR-0072 — Choosing a table loads it, and the box on a table filters it

**Status:** accepted (2026-08-18)

**Task:** classification tables — the lookup as a way into a table rather than a way around it.

**Amends:** ADR-0068 (the table scope on the lookup, and the `<select>` that offered it).

## Context

ADR-0068 made the index page's `<select>` a *scope*: choosing the 118th Congress's second session
narrowed what the lookup would suggest, and the reader stayed on the index. Reaching the rows still
meant typing a query and picking a suggestion. Choosing a table and typing nothing did nothing at
all.

The box on a session page had the same shape: a query submitted there rendered a list of links
above the table it was submitted from, one of which filtered that table. The filter was two steps
from the query, and the first step's answer was a list of one on most queries.

Two smaller things were measured on the way:

- The `<select>`'s longest option, `104th Congress, whole congress`, measures 287px. Sharing a row
  with the field and the button, it was capped at 256px — clipped — and the field beside it was
  198px at 700px wide, where the placeholder is 340. The field's text ran to the edge of its own
  padding box with the button 8px beyond it.
- A GET form posts its own fields and nothing else, so `?sort=code` did not survive a submission
  from the box on a table.

## Decision

### 1. The select chooses a table, and choosing one loads it

`?scope=118-2` on `/app/classification` is now a 302 to `/app/classification/118/2`. Whatever is in
the field rides along as `?q=`, so a query begun before the table was chosen is answered on the
table's own page against the box that is already scoped to it — which is where ADR-0068's scoped
suggest lives. The index therefore asks for no scoped suggestions of its own, and `?scope=` no
longer round-trips into a selected option.

The island submits the form on `change` rather than navigating, so the pointer path and the
no-script path are one request to one page, and the URL is written by the page (`url.ts`,
architecture rule 5).

**Only for a pointer.** A native `<select>` fires `change` on every arrow key in Firefox, so a
keyboard stepping through 32 options would load each table it stepped past. The island tracks
whether the interaction began with a `keydown` and submits only when it did not; a keyboard commits
with `Enter`, which submits the form it is in, or with the **Look up** button.

### 2. A query submitted on a table is applied to it

The session page reads the suggestions it already fetched and, when one of them names rows inside a
session table, redirects to that filtered view instead of rendering a list. `16 usc` on the 118th's
second session is that table's title-16 rows; `118-42` is that law's rows; `42 usc 254c-2` is one
section's. The filters arrive as the pills the page already draws, and the URL is the citable one it
already had.

`classificationTableFilterHref` (`lib/url.ts`) is the mapping: `pl`, `section-in-table` and
`title-in-table` are the three kinds that name rows in a table, and the other three — the section's
notes in the reader, and the two corpus-wide by-code views — answer `null`. What answers `null` is
still listed under the box, because a list is the only answer there is for it.

The order the reader is in is a hidden field on the form and is carried into the redirect.

### 3. The U.S. Code column previews

A citation in that column with a `usc_identifier` behind it gets `data-cite` and `data-preview`, and
both pages that render a classification table render `CitePreview`. So a row's section can be read
without leaving the table, on the same terms as a cross reference in the statute (ADR-0024,
ADR-0041): 300 ms to open, hoverable, `Escape` to dismiss, touch navigates instead. Clicking still
opens the section.

### 4. The select moves under the field

It is a chooser rather than part of the query, and it is 287px wide. On its own row it stops
competing with the field, which now holds its placeholder at every width from 375px up: 198px →
459px at 700, 448px → 747px at 1280. The row's gap goes 0.5rem → 0.75rem, which is the buffer
between the field and the button that the shared row had 8px of.

The suggestion list moves with it. It was absolutely positioned against the panel — `top: 100%` —
so a row added at the bottom of the panel would have opened the list below the select rather than
below the field. The field, the button and the list are now one positioned box, and the list opens
4px under the field on every page.

## Consequences

- Both classification pages ship `CitePreview`'s island: `docs/js-budgets.json` raises
  `/app/classification` and `/app/classification/[congress]` 24,000 → 36,000. That is 11.4 KB of
  inline script on two routes that carried none of it, for a card that only a pointer with hover
  ever opens.
- The index no longer answers a scoped query, so `parseClassificationScope` is read for a redirect
  target rather than for a fetch. The `scopeValue` prop and the round trip it served are gone.
- A submitted query that the table can be filtered by never renders `ClassificationMatches`. The
  component is still what the index uses, and still what a table uses for the answers it cannot
  apply.
- The select is one control with two commit paths, which is a keyboard rule the markup does not
  state. `classification.spec.ts` asserts that an arrow press does not navigate.
- `/app/design` renders the live component, so the select there navigates off the design page. The
  page's no-data property is about what it fetches on render and is unchanged.

## What was declined

- **Applying the query on the index too.** There is no table to filter there; the two by-code views
  are what a citation leads to and they are a list of two, not a destination of one.
- **Redirecting when the scoped answer is empty.** The API offers `title-in-table` only when the
  table holds rows, so `14 usc` on a table with no title-14 rows falls through to the list, where
  "Title 14 — every classification row, 2,210 rows across every table" is the useful answer. An
  empty filtered table would have been the literal one.
- **Navigating on `change` unconditionally.** See decision 1; the Firefox behaviour is the reason
  the guard exists rather than a preference about jump menus.
