---
layout: ../../layouts/GuideLayout.astro
title: Classification tables
order: 10
summary: Which provision of which public law became which section of the Code, from the 104th Congress onward, with a lookup for a law or a citation.
covers:
  routes:
    ["/app/classification", "/app/classification/[congress]", "/app/classification/ecct"]
  adrs: [67, 68]
---

A public law is not written in the Code's numbering. The Office of the Law Revision Counsel decides
which section each of its provisions becomes, and publishes that decision as a table: one row per
provision, naming the Code section, what was done to it, the public law, the law's own section
designator, and the page of the Statutes at Large.

[/app/classification](/app/classification) holds those tables — one per congress per session, from
the 104th Congress onward.

```scenario
id: classification-index
title: Every table the site holds is listed on one page
steps:
  - goto: /app/classification
  - expect: { selector: ".classindex", contains: "Congress" }
```

## Looking up a law or a section

The box at the top of the page takes three kinds of query:

| Type | Example | Where it goes |
|---|---|---|
| A public law | `118-42` | Its rows in the table for that congress and session |
| A provision of one | `118-42 421` | The same table, narrowed to that provision |
| A Code citation | `16 usc 3831` | Two answers: the section's notes in the reader, and every classification row for it |

The notes on a section page are where the OLRC prints that provision's own classification history,
in its own words. The classification rows are this site's index of the tables.

Suggestions appear as you type. <kbd>↓</kbd> and <kbd>↑</kbd> move through them, <kbd>Enter</kbd>
opens the one you are on, and <kbd>Esc</kbd> closes the list without moving the keyboard. With
JavaScript switched off the box is a form, and **Look up** reaches the same answers by the same
parse.

```scenario
id: classification-lookup
title: A public law leads to its rows
steps:
  - goto: /app/classification
  - fill: { selector: "#classlookup-q", value: "118-42" }
  - expect: { selector: ".classlookup__option", visible: true }
  - click: .classlookup__option
  - expect: { url: "pl=118-42" }
```

**Every table**, beside the box, is a scope. Choosing one table narrows the lookup to it: a bare
law number — `35` — then means that law of the chosen congress, and a citation gains a first
answer counting the rows classified to that section in that table.

```scenario
id: classification-scoped-lookup
title: Narrow the lookup to one table
steps:
  - goto: /app/classification
  - select: { selector: "#classlookup-scope", value: "118-2" }
  - fill: { selector: "#classlookup-q", value: "42 usc 254c-2" }
  - expect: { selector: ".classlookup__option", contains: "rows in this table" }
  - click: .classlookup__option
  - expect: { url: "classification/118/2?title=42" }
```

## Reading one table

A table is one congress and one session — [the 118th's second
session](/app/classification/118/2) is `/app/classification/118/2`. The 104th's is a single file
covering the whole congress, at `/app/classification/104/all`.

Five columns, in the source's own order:

- **U.S. Code** — the citation the provision was classified to, linked to the section in the reader
  where the table gives enough to address one.
- **Description** — what was done. A blank cell means the section or note was amended, and is shown
  as *Amended*; every other value is the source's own token. `tr to 42/290ee-10` names the other
  end of a transfer, `ed chg` and `nt ed chg` point at the editorial table below, and a quoted
  string in the **Sec.** column — `3 "50506"` — is a new section the law adds to the underlying act.
  The set of tokens is not fixed, and one this site has not seen prints as the source wrote it.
- **Pub. L.** — linked to the law on govinfo.
- **Sec.** — the law's own section designator.
- **Stat. page** — linked to the OLRC's statviewer where the volume and the page are both known.

**Order** switches between public law order, which is the source's, and U.S. Code order, which sorts
by title and section. Rows come 50 at a time. Filters are shown as pills above the table and each
one can be dismissed on its own. The address bar holds the filters, the order and the page, so a
view is citable by its URL.

The lookup box is on the table's page as well, scoped to that table. A bare law number — `35`, or
`35 101` for one of its provisions — means a law of that congress, and choosing a match filters the
table to it instead of paging.

```scenario
id: classification-table-lookup
title: Find a row in a table without paging through it
steps:
  - goto: /app/classification/118/2
  - fill: { selector: "#classlookup-q", value: "35" }
  - expect: { selector: ".classlookup__option", visible: true }
  - click: .classlookup__option
  - expect: { url: "pl=118-35" }
```

```scenario
id: classification-sort
title: Read one table in Code order instead of public law order
steps:
  - goto: /app/classification/118/2
  - click: .sortbar__list a
  - expect: { url: "sort=code" }
  - expect: { selector: ".classtable", contains: "U.S.C." }
```

## Every row for one section

A Code citation in the lookup box leads to every row ever classified to that section, across every
table, newest public law first. The two filters are shown as pills, and the view is paged like any
other.

```scenario
id: classification-by-section
title: One section's whole classification history
steps:
  - goto: /app/classification?title=18&section=3551
  - expect: { selector: "#classsection-heading", contains: "18 U.S.C." }
  - expect: { selector: ".classtable", contains: "118-35" }
```

Section pages in the reader do not carry these rows. The link runs one way, from a classification
row to the provision.

## Editorial changes

A row marked `ed chg` or `nt ed chg` moved because the OLRC reorganised the Code, not because a law
moved it. The [Editorial Classification Change Table](/app/classification/ecct) records those moves:
the former classification, the new one, the provision affected, and the provision that prompted the
change.

No cell in that table links into the reader. A former classification is by definition an address the
provision has left, and the table supplies no identifier to link to.

```scenario
id: classification-ecct
title: The editorial table says where a provision moved from and to
steps:
  - goto: /app/classification/ecct
  - expect: { selector: ".classtable", contains: "Former classification" }
```

## A law with no rows, and a law with no table

Three answers, meaning three different things.

- **A law a table covers that classified nothing.** Public Law 119-2 is inside the 119th Congress's
  first-session table and has no rows in it. The lookup leads to that table filtered to the law, and
  the table says it classified nothing matching the filter. That is an answer, not a gap.
- **A law past the range any table covers.** The 119th is classified through 119-102, so `119-103`
  matches nothing in the lookup, and `/api/v1/classifications/pl/119/103` answers 404 naming the
  law.
- **A congress and session with no published table.** `/app/classification/104/1` is a 404: the
  104th's rows are in one whole-congress file, at `/app/classification/104/all`.

## How current this is

The classification tables are polled separately from the Code's text: they are a different source
page on the same site, republished as new laws are classified. The index page says when this site
last looked and how many tables had changed at that check.

Three states get a warning instead: no check has ever run here, the last check failed, or the last
check succeeded longer ago than the daily schedule intends. The tables shown are the ones this site
holds; a warning means OLRC may have published a newer one since anybody asked.

## Limitations

- **The tables begin at the 104th Congress.** A section last touched before 1996 has no rows here.
- **Appendix rows do not link to a provision.** An appendix section's address in the Code is a form
  such as `/us/usc/t5a/pl/92/463/s1`, which the table's `5A / 101` cannot produce, so the citation
  is printed as text.
- **127 rows show no Statutes at Large page, and 2 show no public law.** Their columns ran together
  in the source and could not be separated. Every row keeps the source's own line, which the API
  returns as `raw_line`.
- **A change to the Editorial Classification Change Table alone is not visible to the poll**, which
  compares the covered-law sentence the index page carries for each public law table.
