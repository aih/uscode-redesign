# ADR-0049 — The search ranking is measured, and the query can be scoped

- **Status:** Accepted
- **Date:** 2026-08-05
- **Context:** Session 29, workstream B task B4
- **Amends:** [ADR-0028](0028-keyword-search-opensearch-current-by-default.md) (the query and
  what a result reports, not the versioning rule), [ADR-0031](0031-search-matches-what-you-typed.md)
  (adds scopes in front of the parser; the parser is unchanged)

## Context

ADR-0031 made the search strict. It said nothing about *order*, and the order it left behind was
the one `multi_match` gives you for free:

```python
{"simple_query_string": {"query": q, "fields": ["heading^2", "xml_text"], …}}
```

Two things were wrong with that line, and neither was visible from reading it.

**The weighting was not the one written down.** The index mapping carried a deprecated index-time
`boost: 2.0` on `heading`. OpenSearch multiplies that into the query-time weight rather than
replacing it, so the effective heading weight was 4, not 2. Measured on the pre-B4 index: BM25's
`boost` factor for a heading term explains as 4.4 — 2.2 (`k1+1`) × 2.0 — and `heading^4` against a
boost-free mapping reproduces the old ranking *and its scores exactly*, on all ten queries tried,
where `heading^2` reproduces neither.

**Nothing said whether the order was any good.** "Ordered by relevance" was an assertion. The site
publishes its counts, its query plans and its accessibility scans as re-runnable commands, and its
ranking as an opinion.

Expressiveness was the second gap. A drafter can ask for a phrase, a truncation, a near-spelling,
a boolean and a grouping. They cannot ask for one title, one chapter, headings only, repealed
provisions only, or the text as it stood at a release point — except through `?release=`, which is
not something you can type into a box.

## Decision

### The ranking is chosen by nDCG@10 over a committed judgement set

`docs/verification/search-judgements.json` holds 37 queries with the provisions a drafter would
expect for each, graded 0–3. `scripts/search_eval.py` scores every profile in
`storage/searchquery.py` against it and writes `docs/verification/search-relevance.json`.

Candidates are **pooled before grading** — the union of the top 12 from every profile — so no
profile is scored against a set gathered only by another. Some entries were graded without
appearing in any pool, being the provision a drafter would name; those are what makes recall@10
mean anything.

Measured over the full local corpus (58 titles, 489,738 versions):

| profile | nDCG@10 | recall@10 |
|---|---|---|
| `deployed` — `heading^4`, `xml_text` | 0.6894 | 0.7672 |
| `heading-6` | 0.6995 | 0.7693 |
| `heading-10` | 0.7071 | 0.7688 |
| `heading-16` | 0.7086 | 0.7663 |
| **`phrase` — `heading^10`, `num.text^2`, `xml_text`, phrase boost 4 / heading phrase boost 8** | **0.7159** | **0.8016** |
| `all-versions` — the same, over every version, collapsed, current boosted 6 | 0.7192 | 0.8150 |

`phrase` ships. Thirteen queries improve against `deployed`, nine get worse, fifteen do not move.

The parameters around it were swept rather than picked: phrase boost at 2, 4, 8 and 16 (16 is
much worse, at 0.6519), slop at 0, 2 and 6, heading weight at 6, 10, 16 and 24, and `num.text` at
0, 2 and 8. The shipped combination is the best of them on recall and within 0.0004 of the best on
nDCG.

### The default still reads the text in force, and reports what it did not read

`all-versions` scores highest, and is declined. It wins by 0.0033 nDCG, and it changes what a
result *is*: a section whose current text no longer contains the words becomes a hit, which is a
different answer to the question the reader asked. Instead the default keeps ADR-0028's
`is_current` filter and a second, size-0 request counts how many superseded versions of the
sections *on the page* also match. A result then says "also matched in 4 earlier versions" and
links to the version history. The cost is bounded by the page, not by the result count.

### Scopes are lifted out of the query, not delegated to a second parser

`heading:`, `title:`, `chapter:`, `status:`, `release:` and `date:` are removed from the query
string by `parse_query` before what remains reaches the cluster. The alternative is
`query_string`, which understands `field:value` natively and **throws on malformed input** — the
exact trade ADR-0031 refused for an endpoint anyone can type into. A prefix this site does not
implement stays in the text and is searched for, so a reader's stray colon returns a search rather
than a 400.

`status:none` is the bucket for a section the source gives no `@status` at all, which is most of
the Code. It is a filter value rather than something the corpus contains, because `@status` is not
a closed set (gotcha 13).

### A filter is written into the query, not into a parameter beside it

Facet links edit `q`. `?q=water+title:16` is the whole search, so its URL carries the words, the
filters, the release point and the order together, and there is no second representation to
disagree with the first about which one won.

### One query builder, or the measurement measures the harness

`storage/searchquery.py` holds the parser, the profiles and the request body. `api/search.py`
calls it; `scripts/search_eval.py` calls it. Neither has a query of its own.

### Both counts were wrong, and are fixed here

`hits.total` stops at OpenSearch's default 10,000 and reports the cap as the answer, so every
broad search claimed exactly 10,000 results. And `hits.total` counts *documents* whether or not
the results were collapsed, so a point-in-time search reported its matching versions while listing
one row per section. `track_total_hits: true` fixes the first; a `cardinality` aggregation on
`identifier` fixes the second.

## Consequences

- **The mapping changed, so the index must be rebuilt** — `python -m ingest.reindex_search
  --recreate` (ADR-0028: OpenSearch will not add a field type to a live index). New fields:
  `title_num`, `chapter`, `sort_key`, `num.text`, `id_collision`.
- **Ranking by words cannot favour a provision whose heading does not carry them.** Every one of
  the six worst-scoring queries is this: FOIA is 5 U.S.C. § 552, *Public information; agency
  rules, opinions, orders, records, and proceedings*; the money-laundering offence is 18 U.S.C.
  § 1956, *Laundering of monetary instruments*; monopolization is 15 U.S.C. § 2, *Monopolizing
  trade a felony*. A heading weight of 10 helps when the heading names the subject and can do
  nothing when it does not. Closing that gap needs something other than term matching — the
  `embedding` field ADR-0028 declared is where that would go.
- **The judgement set is one person's reading**, from a heading and a snippet, not a panel's and
  not a reading of the whole section. It is committed line by line so a disagreement can be about
  a specific grade.
- **`num.text` is unmeasured by this set.** nDCG is identical at weight 0, 2 and 8, because none
  of the subject queries is a section-number lookup. Two number-bearing queries were added and it
  moves those; the field is kept on that evidence and no more.
- **A second request per default search.** The earlier-version count is `size: 0` over at most 20
  identifiers, and a failure leaves the counts at zero rather than failing the search.
- **`?sort=citation` puts every chapter and subchapter heading of a title ahead of every section
  of it**, rather than each immediately before the sections it contains. Structure nodes have no
  `seq_in_title`; deriving one means a join the reindex does not do. The sort control says so.
- **`cardinality` is approximate** above its precision threshold, which is set at 40,000 against a
  corpus of 65,938 sections. A count right to within a fraction of a percent on the widest search
  and exact on every ordinary one beats one pinned at 10,000.
- **The identifier-collision caveat is now visible** where it can bite. `reindex_search` flags the
  documents two versions share an `_id` for (ADR-0021) — measured at 160 (identifier, release)
  pairs across 49 identifiers in 14 titles — and the result row says the index holds one of two.
  An incremental load sets the same flag, since the second occurrence overwrites the first and
  they are one document.
- **`docs/verification/loadtest.json` is stale for `/api/v1/search` and `/app/search`**: the query
  is heavier (a phrase clause, two aggregations, an uncapped count) and there is a second request
  per search. Not re-measured here.
