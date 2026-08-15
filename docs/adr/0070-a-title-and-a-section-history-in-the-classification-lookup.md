# ADR-0070 — A title, and a section's public laws, in the classification lookup

**Status:** accepted (2026-08-14)

**Task:** classification tables — the two questions the lookup could not answer.

**Amends:** ADR-0067 (the lookup's query vocabulary), ADR-0068 (the table scope).

## Context

The lookup read three things: a public law, a provision of one, and a US Code citation naming a
section. Two questions a reader arrives with were not among them.

**A title with no section.** `15 usc` and `title 15` parse in `citeparse` — `kind="title"` — and
the suggest endpoint dropped them on the floor, because `_citation_suggestions` returned early for
anything that was not a section. "What has Congress done to title 15" had no answer on this site
short of paging a session table with a hand-edited `?title=15`, one table at a time.

**A section's public laws, when the tables hold none.** A citation offered the section's notes
always and the classification rows only when a row existed, so the choice between the two readings
appeared or vanished depending on data the reader cannot see in advance. The tables begin at the
104th Congress; a section last amended in 1994 has no rows, and the empty answer — with the notes
named as the place that does go back that far — is the useful one.

## Decision

### 1. A title citation is a lookup answer

`_title_suggestions` handles `parsed.kind == "title"`:

- **`title-classifications`** — every row classified to that title, across every table,
  `/app/classification?title=15`.
- **`title-in-table`**, first and only under ADR-0068's scope — the rows that one table classified
  to the title, `/app/classification/118/2?title=15`. The same shape `section-in-table` has, and
  counted the same way, by `entries_for_file`.

A title no table has ever classified anything to gets neither, which is ADR-0067's rule for a
public law nothing is held about.

### 2. `/app/classification?title=` alone is a view

The by-section view becomes a by-code view: a title, and a section within it when one was named. A
section number still names nothing without its title, so the pair is ordered rather than symmetric
— dismissing the section pill leaves the title view, dismissing the title pill drops both.

It is served by a new route, `GET /api/v1/classifications/code/{title_num}`, over a new
`ClassificationRepository.entries_for_title`. Not a nullable `section` on the by-section route: the
sets are different sizes and are counted and paged independently — title 10 carries 23,093 of the
144,837 loaded rows and title 42 19,476, where the longest single section history is
`/us/usc/t10/s113`'s 412.

### 3. The choice between the notes and the rows is offered every time

`section-classifications` is emitted whenever the section resolves in the corpus **or** a row
exists, rather than only for the second. Its label says what it leads to — "Public laws that
affected 16 U.S.C. § 201" — and its detail carries the count, or names the coverage limit when the
count is zero.

### 4. The view says what it cannot show, and links what can

Both by-code views state that the tables begin at the 104th Congress (1996). The section view names
the section's notes in the reader as the place OLRC's own classification history goes back further,
and links them at `#section-notes` (ADR-0055's anchor).

The link is resolved through `/api/v1/citation` rather than assembled from the title and section in
hand. Two reasons, both measurable: the corpus spells a section number with an EN DASH where the
tables write a plain hyphen (gotcha 17), so an assembled path 404s for 3,398 of the identifiers the
tables name; and a section that is not in the Code as it now stands should be offered no link at
all, which only a lookup can decide.

## Consequences

- The by-section view costs one extra API call — the citation lookup — and gains the section's
  heading with it. The title view costs none.
- A title view is a large answer: 4,495 rows for title 15, 23,093 for title 10. It is paged at 50
  like every other listing here, ordered newest public law first, and the ordering is done in
  Postgres over `pl_congress`/`pl_num` rather than over a title key, so `sort=code` is not offered
  on it.
- Six suggestion kinds now exist. `classificationSuggestionHref` builds each one's URL from the
  structured pieces (architecture rule 5), asserted against `_app_path`'s output in `url.test.ts`.
- A citation for a section with no rows now returns two suggestions where it returned one, so the
  listbox is never a single row for a resolvable section.

## What was declined

- **A title's table of contents as a second suggestion.** The mirror of the section case would be
  "the title in the reader" beside "the title's classification rows". The lookup on this page is
  about the tables; the site search box already reaches a title, and `/app/classification?title=15`
  links the title in the reader from the view itself.
- **A `sort` control on the title view.** `sort=code` on a session page orders by
  `title_sort_key`, which within one title would order by section number alone — worth having, and
  not worth a second paging path before anyone has asked for it.
- **Rendering classification rows on section pages.** Still ADR-0067's decision: the link runs one
  way, and the section page now has a route to link back to when that is revisited.
