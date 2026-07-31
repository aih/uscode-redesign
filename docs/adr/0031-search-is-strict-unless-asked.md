# ADR-0031: The search matches what you typed, and loosens only when asked

**Status:** Accepted
**Date:** 2026-07-30
**Supersedes in part:** [ADR-0028](0028-keyword-search-opensearch-current-by-default.md) (the
query construction, not the versioning rule)

## Context

Session 12 shipped keyword search over OpenSearch. The query it built was:

```python
{"multi_match": {"query": q, "fields": ["heading^2", "xml_text"], "fuzziness": "AUTO"}}
```

Two defaults in that line were never chosen; they are simply what happens when you leave
`multi_match` alone.

**`fuzziness: "AUTO"`** applies an edit distance to every term: 2 for terms of six characters
or more, 1 for three to five. So a reader searching for `compare` was also searching for every
word within two single-character edits of it. Measured against the live index:

| query | results |
|---|---|
| `Compare` (before) | 139, led by *Implementation of **Compact*** and *PUBLIC **COMPANY** ACCOUNTING OVERSIGHT BOARD* |
| `Compare` (after) | 2, both containing the word "compare" |

`compact` and `company` are each exactly two edits from `compare`. This is not a near-miss the
ranking buries — a fuzzy hit is a full match clause, so the wrong words scored as well as the
right ones.

**No `operator`** means `OR`. A two-word search matched provisions containing either word, so
the documents matching both competed with the ones matching one.

Neither is defensible in a body of law, where a different word is a different rule. The user
reported it as: *"search returns matches for 'Company' and other words with different endings
when I search for 'Compare'."*

Worth recording that the reported diagnosis — different *endings*, i.e. stemming — was not the
cause. There is no analyzer configured anywhere in this project; both text fields use
OpenSearch's default `standard` analyzer, which lowercases and tokenizes and does not stem. The
fuzziness was doing a bad impression of a stemmer, which is why the symptom looked like one.

## Decision

Match the terms as typed. Give the reader operators to loosen it deliberately, and document
them.

```python
QUERY_SYNTAX_FLAGS = "AND|OR|NOT|PHRASE|PRECEDENCE|PREFIX|FUZZY|SLOP|ESCAPE|WHITESPACE"

{"simple_query_string": {
    "query": q,
    "fields": ["heading^2", "xml_text"],
    "default_operator": "and",
    "flags": QUERY_SYNTAX_FLAGS,
    "analyze_wildcard": True,
}}
```

### Why `simple_query_string` and not `query_string`

`query_string` is the more capable parser — field-scoped terms, regex — and it **throws on
malformed input**: an unbalanced quote or paren is a parse error. On an unauthenticated public
endpoint that turns a reader's typo into a 400. `simple_query_string` never throws; it treats
the stray character as text and answers. For a box anyone can type into, not failing is worth
more than regex support.

### Why the flags are named rather than `ALL`

`ALL` would work and would need no maintenance. Naming the set is what makes the syntax guide
*checkable*: `tests/test_search_syntax.py` reads `QUERY_SYNTAX_FLAGS` and the operator list the
guide page renders (`frontend/src/lib/searchsyntax.ts`) and fails if they disagree in either
direction. A guide that documents an operator the cluster does not honour is worse than no
guide, because the reader cannot distinguish it from a query that legitimately found nothing.

### `WHITESPACE` is not optional, and this is why the ADR says so

The flag list was first written *without* `WHITESPACE`, on the reasoning that it makes newlines
and tabs into operators and no search box can produce those. That reasoning is wrong, and the
way it is wrong is the interesting part.

`WHITESPACE` is what makes the parser split on spaces at all. Without it, `-` and `+` are never
recognised as leading operators, because the parser never sees a term boundary in front of
them. `water -pollution` parsed to:

```
+(heading:water) +(heading:pollution)      # -pollution became a REQUIREMENT
```

The exclusion silently became a requirement — the exact opposite of the request — and the query
was *valid* either way, returned a plausible-looking result set, and produced no error. It was
visible only through `_validate/query?explain=true`. With the flag:

```
+(heading:water) +(-(heading:pollution) *:*)
```

This is recorded because the failure mode generalises: a query parser flag that is missing does
not fail, it changes the meaning of the query. Every operator this project claims to support is
therefore verified against a running cluster, not read off documentation.

## Consequences

**A reader who was relying on the looseness loses it silently unless told.** This is the real
cost, and it is paid by a syntax guide at `/app/search/syntax`, linked from the results page and
— most importantly — from the zero-results panel, which is exactly where someone who mistyped
ends up. The page leads with `~1`, and the zero-results panel offers the reader's own query
re-written with `~1` on each term (`fuzzify`, which appends per *word*: appending to the query
would fuzz only the last one, and the mistyped word is usually not the last one).

**Multi-word searches return fewer results.** Intended. `national park` went from 1,521 to
1,253 hits when quoted as a phrase, and the AND default means both words must now appear at
all.

**Operators verified against the live cluster** at the time of the change: `"national park"`
(phrase, narrower than the bare terms), `compare~2` (139 results — the old behaviour, on
request), `compar*` (65), `water -pollution` (excludes), `water +pollution` (29, requires),
`park | forest` (2,190).

**Two pre-existing problems are untouched and remain open.** The `heading` field carries both a
deprecated index-time `"boost": 2.0` in its mapping and a query-time `heading^2`, so the intent
is expressed twice and at most one takes effect. And `total` is the uncollapsed hit count, so on
a `?release=` query — the only one that collapses — the pager over-counts, because it is
counting versions rather than sections. Neither is caused by this change and neither is fixed by
it.

**No reindex is required.** This changes only how the query is parsed; the mapping and the
documents are untouched. (The index still holds Session 12's 4,000-document smoke slice — a full
build remains outstanding, and is what makes the absolute result counts above smaller than they
will be.)
