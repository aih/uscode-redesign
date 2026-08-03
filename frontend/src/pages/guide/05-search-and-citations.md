---
layout: ../../layouts/GuideLayout.astro
title: Search and citations
order: 5
summary: One box that takes a citation or a phrase, works out which you meant, and searches strictly unless you ask it not to.
covers:
  routes: ["/app/goto", "/app/search", "/app/search/syntax"]
  adrs: [23, 28, 31]
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

Two things will catch you out, and both are on that page: a bare section number with no title
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

The search **matches the words you typed**. It does not quietly spend two character edits looking
for something near them — in a legal corpus a different word is a different rule, and a search for
`compare` returning `compact` and `company` is a search that has answered a question nobody asked.

If you do want that, ask: `conservtion~1` allows one edit. The other operators — `"exact phrase"`,
`-exclude`, `either | or`, `truncat*`, and parentheses for grouping — are listed with examples on
the [syntax guide](/app/search/syntax#operators).

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

Add `&release=` or `&date=` to a search and it runs against the text as it stood then. The results
page always says which it did — *“In the text as of release point …”* or *“Searching the law
currently in force.”* — so you can tell from the answer which question was asked.

### Asking what cites a provision

Prefixing a query with `cites` — `cites 26 usc 501` — searches for the text of that citation. It is
a keyword search, not a citation index, and the results page says so plainly rather than implying a
completeness it does not have. A real reverse-citation index is designed and not built.

```scenario
id: cites-is-honest
title: The "cites" prefix says what it actually is
steps:
  - goto: /app/search?q=cites+16+usc+45f&cites=1
  - expect: { selector: "main", contains: "keyword search" }
```
