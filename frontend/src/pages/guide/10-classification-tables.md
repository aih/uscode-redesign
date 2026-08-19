---
layout: ../../layouts/GuideLayout.astro
title: Classification tables
order: 10
summary: Which provision of which public law became which section of the Code, from the 104th Congress onward, with a lookup for a law, a title or a citation.
covers:
  routes:
    ["/app/classification", "/app/classification/[congress]", "/app/classification/ecct"]
  adrs: [67, 68, 70, 71, 72]
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

## Looking up a law, a title or a section

The box at the top of the page takes four kinds of query:

| Type | Example | Where it goes |
|---|---|---|
| A public law | `118-42` | Its rows in the table for that congress and session |
| A provision of one | `118-42 421` | The same table, narrowed to that provision |
| A Code citation | `16 usc 3831` | Two answers: the section's notes in the reader, and every public law the tables record against it |
| A title, with no section | `15 usc`, `title 15` | Every row classified to that title, across every table |

A citation offers both answers whether or not the tables hold a row for the section. The notes on a
section page are where the OLRC prints that provision's own classification history, in its own
words, and they reach back past the 104th Congress; the classification rows are this site's index
of the tables, and they do not.

Capitalisation and spacing do not matter: `TITLE 15`, `15 U.S.C.` and `15 usc` are one query.

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

**Or go to one table**, under the box, loads a table. Anything typed in the box goes with it and is
answered there: choosing the 118th Congress's second session with `16 usc` in the box lands on that
table, filtered to title 16.

```scenario
id: classification-scoped-lookup
title: Choose a table, and arrive on it filtered
steps:
  - goto: /app/classification
  - fill: { selector: "#classlookup-q", value: "16 usc" }
  - select: { selector: "#classlookup-scope", value: "118-2" }
  - expect: { url: "classification/118/2?title=16" }
  - expect: { selector: ".filterpills", contains: "16" }
```

## Reading one table

A table is one congress and one session — [the 118th's second
session](/app/classification/118/2) is `/app/classification/118/2`. The 104th's is a single file
covering the whole congress, at `/app/classification/104/all`.

Five columns, in the source's own order:

- **U.S. Code** — the citation the provision was classified to, linked to the section in the reader
  where the table gives enough to address one. Hovering one shows the section's text in a card, the
  same preview a cross reference in the statute gives; clicking opens the section.
- **Description** — what was done. A blank cell means the section or note was amended, and is shown
  as *Amended*; every other value is the source's own token. `tr to 42/290ee-10` names the other
  end of a transfer, `ed chg` and `nt ed chg` point at the editorial table below, and a quoted
  string in the **Sec.** column — `3 "50506"` — is a new section the law adds to the underlying act.
  The set of tokens is not fixed, and one this site has not seen prints as the source wrote it.
- **Pub. L.** — linked to the law on govinfo.
- **Sec.** — the law's own section designator.
- **Stat. page** — linked to the OLRC's statviewer where the volume and the page are both known.

### Ordering a table

**Order**, above the table, switches between public law order — the source's own — and U.S. Code
order, which sorts by title and then by section number. The order in force carries an arrow and the
direction in words; selecting it again reverses it, so there are four orders in all.

The headings of the **U.S. Code** and **Pub. L.** columns do the same thing: selecting one orders
by that column, and selecting it again turns it round. The other three columns hold the source's own
notation and are not ordered by.

```scenario
id: classification-sort
title: Read one table in Code order instead of public law order
steps:
  - goto: /app/classification/118/2
  - click: '[data-sort="code"]'
  - expect: { url: "sort=code" }
  - expect: { selector: ".classtable", contains: "U.S.C." }
```

```scenario
id: classification-sort-reverse
title: Turn an order round from the column heading
steps:
  - goto: /app/classification/118/2?sort=code
  - click: '[data-sort-column="code"]'
  - expect: { url: "sort=code-desc" }
  - expect: { selector: '.classtable th[aria-sort="descending"]', contains: "U.S. Code" }
```

### Moving through a table

Rows come 50 at a time. Under them is the page you are on, how many pages there are, **Previous**
and **Next**, and the page numbers either side of you with the first and the last always among
them. The 104th Congress's table is 235 pages, so where the numbers cannot reach every page a
**Go to page** box takes one directly.

Filters are shown as pills above the table and each one can be dismissed on its own. The address
bar holds the filters, the order and the page, so a view is citable by its URL, and changing the
order starts again at the first page.

```scenario
id: classification-pager
title: Move through a table by page number
steps:
  - goto: /app/classification/118/2
  - expect: { selector: ".pager__status", contains: "Page 1 of" }
  - click: .pager__list a[rel="next"]
  - expect: { url: "offset=50" }
  - expect: { selector: ".pager__page--on", contains: "2" }
```

The lookup box is on the table's page as well, scoped to that table, and what it finds there is
applied to the table as a filter. A bare law number — `35`, or `35 101` for one of its provisions —
means a law of that congress; `16 usc` filters to the rows classified to title 16; `42 usc 254c-2`
to the rows for one section. A query the table cannot be filtered by — a section's notes in the
reader, or every row classified to a section across every table — is listed under the box instead.

```scenario
id: classification-table-lookup
title: Find a row in a table without paging through it
steps:
  - goto: /app/classification/118/2
  - fill: { selector: "#classlookup-q", value: "35" }
  - click: .classlookup__go
  - expect: { url: "pl=118-35" }
  - expect: { selector: ".filterpills", contains: "118-35" }
```

```scenario
id: classification-table-preview
title: Read a classified section without leaving the table
steps:
  - goto: /app/classification/118/2
  - hover: .classtable__cite a
  - expect: { selector: "#cite-preview", visible: true }
```

## Every row for one section, and for one title

A Code citation in the lookup box leads to every row ever classified to that section, across every
table, newest public law first. **Order** turns that round to oldest first. The two filters are
shown as pills, and the view is paged like any other.

```scenario
id: classification-by-section
title: One section's whole classification history
steps:
  - goto: /app/classification?title=18&section=3551
  - expect: { selector: "#classsection-heading", contains: "18 U.S.C." }
  - expect: { selector: ".classtable", contains: "118-35" }
```

The same view without a section — `/app/classification?title=42` — is every row classified anywhere
in that title. Dismissing the section pill leaves the title one in place and shows it. A title's
rows can also be read in U.S. Code order, section by section; a single section's cannot, since every
row of that view carries the same citation.

```scenario
id: classification-by-title
title: Every row classified to one title
steps:
  - goto: /app/classification?title=42
  - expect: { selector: "#classsection-heading", contains: "Title 42" }
  - expect: { selector: ".classtable", contains: "42 U.S.C." }
```

```scenario
id: classification-title-code-order
title: Read a title's rows in U.S. Code order
steps:
  - goto: /app/classification?title=42
  - click: '[data-sort="code"]'
  - expect: { url: "sort=code" }
  - expect: { selector: '.classtable th[aria-sort="ascending"]', contains: "U.S. Code" }
```

Both views name where the tables stop. A section that is in the Code carries a link to its notes in
the reader, which reach back past the 104th Congress; a section with no rows at all carries the
same link, and that is the answer for a provision last amended before 1996.

```scenario
id: classification-notes-link
title: A section with no rows still says where its history is
steps:
  - goto: /app/classification?title=16&section=201
  - expect: { selector: "#classsection-heading", contains: "Nothing was classified" }
  - expect: { selector: ".classsection__notes a", contains: "read them in the reader" }
```

Section pages in the reader do not carry these rows. The link runs one way, from a classification
row to the provision.

## Editorial changes

A row marked `ed chg` or `nt ed chg` moved because the OLRC reorganised the Code, not because a law
moved it. The [Editorial Classification Change Table](/app/classification/ecct) records those moves:
the former classification, the new one, the provision affected, and the provision that prompted the
change.

The table lists changes in classification of earlier laws made in the course of classifying new
laws from the 119th Congress. Its rows combine OLRC's
[Session 1](https://uscode.house.gov/classification/ecct_119-1.html) and
[Session 2](https://uscode.house.gov/classification/ecct.html) files, and the page quotes OLRC's
own description, which also says where other classification changes are accounted for (Table III,
on completion of a main edition or supplement) and what a prompting provision is.

This table is separate from the
[editorial reclassification projects](https://uscode.house.gov/editorialreclassification/reclassification.html)
the OLRC undertakes to reorganize areas of the Code.

No cell in that table links into the reader. A former classification is by definition an address the
provision has left, and the table supplies no identifier to link to.

```scenario
id: classification-ecct
title: The editorial table says where a provision moved from and to
steps:
  - goto: /app/classification/ecct
  - expect: { selector: ".classtable", contains: "Former classification" }
  - expect: { selector: ".olrc-quote", contains: "Table III" }
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
last looked and how many tables had changed at that check. Before the first poll runs, the
last-checked date shown is the date the tables were loaded from uscode.house.gov; each poll after
that updates it.

Two states get a warning instead: the last check failed, or the last check succeeded longer ago
than the daily schedule intends. The tables shown are the ones this site holds; a warning means
OLRC may have published a newer one since anybody asked.

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
