# Plan: a citation index, and the reverse lookup it enables

*Written 2026-07-30 (Opus 5). **Status: proposed, not built.** The `cites …`
prefix ships now and answers with a keyword search over the cited provision's
text, saying on the page that that is what it did. This document is the design
for making it real. Nothing here has been implemented; every measurement below
is labelled as either measured or estimated.*

## What is being asked for

> "Which provisions cite this one?"

Today the site answers the forward question — what does § 45f cite? — implicitly,
because `lib/uslm.ts` renders every `<ref>` in a section as a link and
`CitePreview` will show you the target on hover. The backward question has no
answer at all, and it is the more useful one: the provisions that cite a section
are how you find the machinery around a right, the definitions that reach it,
the penalties that enforce it, and every place Congress cross-wired it.

It is also the question a keyword search answers worst. Searching for
`26 usc 501` finds sections that spell the citation out in prose and misses
every one that encodes it as a `<ref>`, which — in USLM — is most of them. The
interim answer is honest but weak, and the gap is exactly what an index closes.

## What the source gives us

USLM marks cross references explicitly, as `<ref href="…">`.

**The ingest layer does not extract them.** This is worth stating plainly
because it is easy to assume otherwise: `SectionRecord` has a `guid_refs` field,
and it is *not* this — it collects the `@id` guids found inside a section and
maps each to its containing provision, which is what makes `GET /us/usc/?id=`
resolvable (ADR-0003). `ref` appears nowhere in `ElementNames`
(`ingest/base.py:32`), so no parser has a vocabulary entry for it and nothing in
the pipeline has ever looked at one.

That makes this a slightly larger job than it first appears: it needs a parser
change (a `ref` entry in `ElementNames`, supplied by both `Uslm1Parser` and
`Uslm2Parser` per architecture rule 2 — **never a hard-coded element path
outside a parser**) as well as a schema and a backfill.

### Measured, not estimated

Over `samples/uslm1/usc16.xml` (Title 16 at 119-102not101, 5,095 real sections):

| | |
|---|---|
| `<ref>` elements total | **55,659** |
| Mean per section | **10.9** (median 6, max 500) |
| …that point into the USC | **11,848 — 21.3%** |
| …to public laws (`/us/pl/…`) | 21,601 — 38.8% |
| …to the Statutes at Large (`/us/stat/…`) | 17,235 — 31.0% |
| …to acts (`/us/act/…`) | 4,013 — 7.2% |
| …with no `@href` at all | 962 — 1.7% |

**Most `<ref>`s are not USC cross references.** Nearly 70% point at public laws
and the Statutes at Large, because they live in the source-credit and notes
apparatus, which is mostly amendment history. The USC-internal share is about
**2.3 per section**, not 10.9 — and that is the number the reverse lookup is
built on.

Of the 11,848 USC refs, 9,230 (78%) name a whole section and 2,618 (22%) name
something below it, up to four levels deep (`/us/usc/t54/s100101/b`). 7,828 of
them are Title 16 citing itself; the rest reach 30-odd other titles.

Two consequences for the design:

1. **`@href` is an `@identifier`-shaped path, not a guid.** That is the right
   key: `@identifier` is cross-release identity and `@id` is explicitly not
   (ADR-0003). An index keyed on guids would be a different graph at every
   release point and would answer no question anyone has.
2. **`kind` has to be recorded, not assumed**, and the reverse lookup answers
   over the USC-internal ones. Storing the others costs little and makes "what
   cites Public Law 92-463" answerable later; a `<ref>` with no `@href` is
   recorded as unresolvable rather than dropped.

One title is not the corpus — Title 16 is conservation, unusually dense in
cross-title references to Title 54 — so phase 1 still re-runs this over
everything. But the design no longer rests on a guess.

## The temporal problem, which is the whole difficulty

"What cites § 501" is not one question. Its answer changes at every release
point, and the site's entire premise is that it can answer as of any of 382 of
them (PLAN §1).

The corpus is deduped: 5,466,652 (section, release) pairs are stored as 489,738
`section_versions`, 91.0% collapsed (CLAUDE.md). The citation index has to ride
on that dedupe rather than fight it, and it can, because **a citation is a
property of a version's text**. If the text did not change, its outgoing
citations did not change. So:

> The index unit is the **section version**, exactly as it is for search
> (ADR-0028). One row per (citing version, cited identifier).

That gives a table sized by versions, not by (section × release) pairs — the
same 11x saving the corpus already gets — and it makes the temporal query the
same shape as the search one, which is a shape this project has now built twice
and understands.

### The size

489,738 versions × 10.9 refs ≈ **5.3 million rows** if every kind is stored,
of which ≈ **1.1 million** are the USC edges the reverse lookup reads. Both
numbers extrapolate Title 16's measured density to the whole corpus, which
phase 1 corrects.

Postgres holds either comfortably. The index on the cited side is what matters,
and 1.1M edges over 65,938 distinct sections is an average fan-in of ~17 — with
a long tail: a definitions section or `26 usc 501` will have thousands, which is
why phase 5 puts the reader's "Cited by" behind a link rather than rendering it
inline.

## Schema

```sql
CREATE TABLE citation_edges (
    -- The citing side: a version, so this rides the dedupe.
    from_version_id   BIGINT NOT NULL REFERENCES section_versions(id) ON DELETE CASCADE,
    -- The cited side: an identifier, because that is cross-release identity.
    -- Deliberately NOT a foreign key: the Code cites provisions that this
    -- database does not hold and that sometimes do not exist (a repealed
    -- section, a citation to a title we have not loaded, a typo in the source).
    -- A dangling edge is data, not corruption.
    to_identifier     TEXT   NOT NULL,
    -- The section the target sits in, so "what cites § 501" and "what cites
    -- § 501(c)(3)" are both answerable without parsing at query time.
    to_section        TEXT   NOT NULL,
    -- 'usc' | 'statute' | 'publaw' | 'other'. Never an enum in the model, for
    -- gotcha 13's reason: the source's vocabulary is not a closed set.
    kind              TEXT   NOT NULL,
    -- Where in the citing text, for rendering a snippet without re-parsing.
    context           TEXT
);

CREATE INDEX ix_citation_edges_to_section ON citation_edges (to_section);
CREATE INDEX ix_citation_edges_from ON citation_edges (from_version_id);
```

`to_section` is the column the reverse lookup reads, and it is why subdivision
citations do not fragment the index: `/us/usc/t26/s501/c/3` and
`/us/usc/t26/s501` both carry `to_section = '/us/usc/t26/s501'`.

## The query

"What cites `X` at release `R`" is a join from the cited identifier back through
the versions in force at `R`:

```sql
SELECT DISTINCT s.identifier, v.num, v.heading
FROM citation_edges e
JOIN section_versions v ON v.id = e.from_version_id
JOIN section_release_map m ON m.version_id = v.id
JOIN sections s ON s.id = m.section_id
WHERE e.to_section = :cited
  AND e.kind = 'usc'
  AND m.release_id = :release
ORDER BY s.identifier;
```

The release join is `section_release_map`, which is already the table that
answers "which version was in force at this release" and already carries the
per-release facts that must not live on the deduped row (ADR-0008). Default with
no release: the text in force, matching search's default (ADR-0028).

**This stays behind `Repository`** (architecture rule 1) as something like
`citing(identifier, release) -> list[Entry]`. No SQL in a handler, and XCiteDB
gets to implement it differently — which matters here more than usual, because a
citation graph is exactly the kind of thing a graph-shaped store does better.

## Ingest

The edges are written where the text is written, in the same transaction, for
the same reason `search_sync` publishes after commit and gated on the title's
newest completed load (ADR-0028):

- **New version stored** → extract refs, insert edges.
- **Text republished unchanged** → the version already exists, its edges already
  exist, write nothing. This is 91% of the corpus and it must stay free.
- **Backfill** → `python -m ingest.reindex_citations`, streaming over
  `section_versions` in `seq` order, resumable the way `load-all` is: the
  presence of edges for a version is its own resume state, so a crash costs a
  scan rather than a restart.

Backfilling 489,738 versions is the expensive part — **estimated** at a few
hours, dominated by lxml parsing of stored fragments rather than by inserts.
It parallelises by title.

## Phases

1. **Measure over the whole corpus** (half a day). The table above is one title;
   redo it across all 58, and add the two counts it does not answer: how many
   USC refs **dangle** (name an identifier no release holds), and how many use
   `et seq.`. Write `docs/verification/citations.json`. **If the corpus-wide
   numbers disagree with Title 16's, the design gets revisited before phase 2.**
2. **Parser vocabulary + schema + repository method** (a day and a half). A
   `ref` entry in `ElementNames` supplied by both parsers, `RefEdge` on
   `SectionRecord` beside `guid_refs`, the migration, `Repository.citing(...)`,
   the Postgres implementation, and tests against the fixture slice.
3. **Ingest wiring + backfill** (a day, plus runtime). Edge extraction on load,
   `reindex_citations`, run it over the corpus. The backfill parses the stored
   `section_versions.xml` rather than re-reading the source zips, so it is a
   database pass and not a second corpus load.
4. **The API** (half a day). `GET /api/v1/sections/{identifier}/citing`, with
   `?release=`/`?date=` resolved through `Repository.resolve_release` like every
   other temporal route, paginated, and rate-limited under ADR-0029 — it is a
   fan-out query on an unauthenticated route, which is precisely the shape that
   ADR's limits exist for.
5. **The reader** (half a day). `cites …` stops being a keyword search and
   becomes this. A "Cited by (N)" section on the section page, lazy behind a
   link for the same reason the source redline is: a heavily-cited section like
   `26 usc 501` will have thousands.

## Decisions this defers rather than hides

- **Renumbering breaks edges.** Gotcha 3: an `@identifier` can change or vanish
  without the provision being repealed. An edge to `/us/usc/t42/s1234` stays
  pointing there after a transfer, so the reverse lookup will under-report for
  renumbered targets. The redirects table gotcha 3 already contemplates is the
  fix, and it is out of scope here — but the index must not be built in a way
  that makes it impossible, which is why `to_identifier` is a plain column and
  not a foreign key.
- **Notes cite too.** A `<ref>` inside a note is a real citation and a weaker
  one. `kind` has room for the distinction; whether the reader shows them
  together is a UI question for phase 5.
- **`et seq.` is a range, not a point.** `26 U.S.C. 501 et seq.` cites a span.
  Phase 1's measurement decides whether that is common enough to model or rare
  enough to record as a point citation with a flag.
- **The appendix titles** are unreachable by citation today (CLAUDE.md's open
  debts), and citations *into* them will dangle. Consistent with the existing
  behaviour, and worth counting in phase 1.

## Why not OpenSearch

The obvious shortcut is to index outgoing citations as a keyword field on the
existing search documents and query `refs:"/us/usc/t26/s501"`. It would work,
and it is rejected for two reasons: the answer is a **join against release
state**, which is Postgres's job and not the index's, and it would put a second
temporal-resolution rule in a second system — the thing ADR-0028 was careful to
avoid by resolving releases through `Repository` rather than by querying. The
citation graph is relational data; the keyword index is for words.
