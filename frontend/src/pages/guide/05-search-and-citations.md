---
layout: ../../layouts/GuideLayout.astro
title: Search and citations
order: 5
summary: One box that takes a citation or a phrase, works out which you meant, searches strictly unless you ask it not to, and lets you scope, filter and order what comes back.
covers:
  routes: ["/app/goto", "/app/search", "/app/search/syntax"]
  adrs: [23, 28, 31, 49]
---

There is one box in the header and it answers two kinds of question. Type a citation and it goes
straight there; type anything else and it searches the text. You do not have to tell it which you
meant.

```scenario
id: citation-box
title: Type a citation and land on the provision
demo: true
demoOrder: 90
steps:
  - goto: /app/
    caption: One box takes a citation or a phrase — you do not have to say which.
  - fill: { selector: ".navtools .sitesearch__input", value: "16 usc 45f" }
    caption: Type a citation in more or less any written form.
  - click: .navtools .sitesearch__go
    caption: And it goes straight to the provision.
  - expect: { selector: ".doc-title", contains: "45f" }
    caption: 16 U.S.C. § 45f — no need to know the URL scheme at all.
```

## Going to a citation

Fourteen written forms are accepted — `16 U.S.C. § 45f`, `16 usc 45f`, `16 USC 45f(c)(5)`,
`/us/usc/t16/s45f` and the rest. The [search and citation guide](/app/search/syntax#citations)
lists every one of them with a worked example, and each example there prints the identifier it
resolves to. That list is generated from the parser's own table, so it cannot describe a form the
site does not accept.

Two things to look out for: a bare section number with no title
(`523`) is searched rather than resolved, because it is not a citation; and an appendix citation
like `5 U.S.C. App. 3` parses but resolves to nothing, because the OLRC publishes nothing at that
flat address.

```scenario
id: citation-forms-listed
title: Every accepted citation form is listed, with what it resolves to
steps:
  - goto: /app/search/syntax
  - expect: { selector: "#citations", visible: true }
  - expect: { selector: ".syntaxop__result", contains: "/us/usc/t" }
```

## Searching the text

The search **matches the words you typed** without applying fuzzy matching or stemming by default.

If you want more flexibility, use search operators: `conservtion~1` allows one character change. The other operators — `"exact phrase"`,
`-exclude`, `either | or`, `truncat*`, and parentheses for grouping — are listed with examples on
the [syntax guide](/app/search/syntax#operators).

### Scoping a search

Six prefixes narrow a search without changing the words in it. They can be combined, and they can
be mixed with the operators above.

| Prefix | Example | What it does |
|---|---|---|
| `heading:` | `heading:conservation` | The word in a section's heading rather than anywhere in its text |
| `title:` | `conservation title:16` | One title of the Code. `title:t16` works too |
| `chapter:` | `conservation title:16 chapter:1` | One chapter number |
| `status:` | `conservation status:repealed` | Provisions carrying that status. `status:none` is the rest |
| `release:` | `conservation release:119-99` | The text as it stood at that release point |
| `date:` | `conservation date:05/08/2026` | The text in force on that date |

A value with a space in it goes in quotes: `heading:"wild horses"`.

Repeating a prefix widens it — `title:16 title:33` searches both. Using two different prefixes
narrows — `title:16 status:repealed` is repealed provisions of Title 16 alone.

```scenario
id: search-scope-title
title: Restrict a search to one title
demo: true
demoOrder: 102
steps:
  - goto: /app/search?q=conservation+title%3A16
    caption: title:16 searches Title 16 and nothing else.
  - expect: { selector: ".searchresult__meta", contains: "/us/usc/t16" }
    caption: Every result is in the title you asked for.
```

```scenario
id: search-scope-heading
title: Search headings rather than the whole text
steps:
  - goto: /app/search?q=heading%3Aconservation
  - expect: { selector: ".searchresult__title em", visible: true }
```

```scenario
id: search-scope-status
title: Search only repealed provisions
steps:
  - goto: /app/search?q=conservation+status%3Arepealed
  - expect: { selector: ".searchresult__meta", contains: "repealed" }
```

```scenario
id: search-scope-chapter
title: Restrict a search to one chapter
steps:
  - goto: /app/search?q=conservation+title%3A16+chapter%3A1
  - expect: { selector: ".searchresult", visible: true }
```

```scenario
id: search-scope-release
title: Name a release point inside the query
steps:
  - goto: /app/search?q=conservation+release%3A119-99
    caption: "release: does in the box what ?release= does in the URL."
  - expect: { selector: ".doc-meta", contains: "119-99" }
    caption: The page names the release point it searched.
```

```scenario
id: search-exact-phrase
title: Search for an exact phrase
steps:
  - goto: /app/search?q=%22national+park%22
  - expect: { selector: ".searchresult", visible: true }
```

### Narrowing what you got back

Above the results are the titles and statuses the matches fall into, each with a count. Selecting
one adds it to the query rather than to a separate control, so the address bar always holds the
whole search — the words, the filters, the release point and the order. A search you paste into a
brief or a ticket arrives as the search you ran.

```scenario
id: search-facet-goes-in-the-url
title: A filter you click is part of the search's address
demo: true
demoOrder: 104
steps:
  - goto: /app/search?q=conservation
    caption: The counts say which titles and statuses the matches fall into.
  - click: .facets__value--status
    caption: Selecting one narrows the search.
  - expect: { url: "status" }
    caption: The filter is written into the query, so the URL is the whole search.
```

### Ordering the results

Results come back by relevance. Two other orders are available:

- **Citation order** — the Code's own order, title by title. Chapter and subchapter headings sort
  ahead of every section of their title rather than immediately before the sections they contain.
- **Recently amended** — newest text first, by the release point at which each provision's current
  text first appeared.

```scenario
id: search-sort-citation
title: Read results in the Code's own order
steps:
  - goto: /app/search?q=conservation+title%3A16
  - click: .sortbar__list a
  - expect: { url: "sort=" }
```

### How relevance is decided

A match in a section's heading counts for more than one in its body, and a section whose text
carries the words together counts for more than one that merely contains all of them somewhere.

The ordering is measured rather than asserted. `docs/verification/search-judgements.json` holds 37
queries with the provisions a drafter would expect for each, and
`uv run python scripts/search_eval.py score` scores the ranking against them. The result is in
`docs/verification/search-relevance.json`.

Ranking by words has a limit worth knowing: it cannot favour a provision whose heading does not
contain the words you searched for. The Freedom of Information Act is 5 U.S.C. § 552, headed
*Public information; agency rules, opinions, orders, records, and proceedings*, and a search for
`freedom of information` does not put it first.

```scenario
id: keyword-search
title: Search the text of the Code
demo: true
demoOrder: 100
steps:
  - goto: /app/search?q=conservation
    caption: Anything that is not a citation searches the text of the Code.
  - expect: { selector: "main", contains: "conservation" }
    caption: Matches are highlighted, and each result says where it sits in the Code.
```

A search that finds nothing offers you the loosened version of your own query rather than a blank
page, and links to the syntax guide.

### Searching at a release point

Add `&release=` or `&date=` to a search and it runs against the text as it stood then, and
`release:` and `date:` in the box do the same. The results page always says which it did — *“In the
text as of release point …”* or *“Searching the law currently in force.”* — so you can tell from
the answer which question was asked. When both a parameter and a prefix name a release point, the
parameter wins.

A search of the text in force also reports where the words used to be. A result reading *“also
matched in 4 earlier versions”* is a provision whose current text no longer contains what you
searched for; the link goes to its version history.

Where the source publishes more than one provision under a single identifier at one release point,
the index holds one of them and the result says so. The section page shows every occurrence. This
affects 49 identifiers across 14 titles.

### Asking what cites a provision

Prefixing a query with `cites` — `cites 26 usc 501` — searches for the text of that citation. Note that this is a keyword search rather than a structured reverse-citation index.

```scenario
id: cites-is-honest
title: The "cites" prefix says what it actually is
steps:
  - goto: /app/search?q=cites+16+usc+45f&cites=1
  - expect: { selector: "main", contains: "keyword search" }
```
