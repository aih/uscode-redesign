# ADR-0021 — When the source repeats an identifier, serve every occurrence

- **Status:** Accepted
- **Date:** 2026-07-29
- **Context:** Session 9 (corpus completion + deep verification), BUILDLOG 023

## Context

Loading the whole corpus (3,153 title-releases) and verifying it turned up six
title-releases where `sections_loaded` exceeded the rows in
`section_release_map`:

```
113-296not287/54: recorded 332, section_release_map has 330
114-329/10:       recorded 3572, section_release_map has 3571
115-8/10:         recorded 3572, section_release_map has 3571
117-80/19:        recorded 1113, section_release_map has 1112
117-110not103/19: recorded 1113, section_release_map has 1112
117-111not103/19: recorded 1113, section_release_map has 1112
```

The cause is in the published XML, not in our code: **OLRC sometimes publishes
more than one `<section>` element under the same `@identifier` in the same
title at the same release point.**

* Title 19 at 117-80 carries **three** elements for `/us/usc/t19/s2502` — two
  empty stubs headed "Purposes", then the real section headed "Congressional
  statement of purposes" with the operative text.
* Title 54 at 113-296not287 repeats `s200308`, `s300314` and `s300315`, where
  the occurrences carry the same operative text with differing amounts of notes,
  and their `@id` guid prefixes differ (`d303-11e4` vs `a8a5-11e4`), suggesting
  two generation runs merged into one file.

These are **not** the quoted statutory text an amending act carries, which the
parser deliberately drops (gotcha 12, ADR-0005): they hold real `@identifier`
and `@id` values. The parser is right to emit them and storage right to keep
them. The count gap is ADR-0007's dedupe working correctly on top: where two
repeated elements are byte-identical, they collapse to one `section_versions`
row, so the loader counts two parsed elements where the release map holds one
row.

The real problem the mismatch exposed was in **retrieval**. `get_section` ended
its query with an unordered `.first()`, so which occurrence a reader saw was
whatever Postgres happened to return — for `/us/usc/t19/s2502` a coin flip
between a 360-byte empty stub and the 3,232-byte real section. Worse,
`neighbors` asked for the section's single place in reading order with
`scalar_one_or_none`, which **raises** on multiple rows: every affected section
page was a 500, because the reader fetches neighbours on every section render.

## Decision

**Serve every occurrence, and say so.** No rule picks a winner honestly — the
source gives nothing to distinguish them by — so the reader shows all of them
rather than choosing one silently.

1. `Repository.get_section` returns all occurrences at the release point,
   ordered by `seq_in_title`: the first as the `SectionResult`, the rest as
   `SectionResult.duplicates` (`DuplicateOccurrence`). Ordering is now explicit,
   so the same URL always answers the same way.
2. The API serializes them as `SectionOut.duplicates` — an empty list in the
   overwhelmingly common case.
3. The reader renders an explanatory note at the top of the page ("The official
   XML for this title at *RP* publishes *N* distinct texts under the identifier
   *X* … all *N* are shown below, in the order they appear in the source") and
   then every body, each captioned "Occurrence *k* of *N*". The extra bodies
   join the page's single batched label lookup, so a repeated section still
   costs one `/api/v1/labels` call, not one per occurrence.
4. `neighbors` takes all of the section's positions and brackets the group:
   what precedes the first occurrence, what follows the last.
5. Sub-provision extraction searches the occurrences in order and keeps the
   first hit, so a deep link like `/s2502/1` lands on text rather than on the
   empty stub that happens to sort first.

The count is stated as **distinct texts**, not elements: two byte-identical
stubs are stored once, so Title 19's three elements are two distinct texts. The
page says two, and that is what the database can honestly claim.

## Consequences

* The reader tells the truth about a source oddity instead of hiding it behind
  an arbitrary pick. This is the same principle as `served_from` (gotcha 10):
  answer, but never silently.
* Retrieval is deterministic. The previous behaviour was not, which is a poor
  foundation for "any provision, at any release point".
* Six title-releases keep a `sections_loaded` / `section_release_map` gap, and
  `make verify` keeps reporting them as count mismatches. That is deliberate —
  they are real findings with a real explanation, and suppressing them would
  make the check weaker for the sake of a clean report.
* `DuplicateOccurrence.guid` repeats the section's guid, because `guid_map`
  holds one row per (identifier, release) and cannot tell the occurrences apart.
  The ambiguity is the source's; inventing a distinction here would be worse.
* Affected pages went from HTTP 500 to rendering. That failure was live before
  this session and invisible only because the corpus had not been loaded.
