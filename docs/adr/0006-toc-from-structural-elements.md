# ADR-0006: The TOC is read from structural elements, not from `<toc>`

**Status:** Accepted — 2026-07-27 (Session 3.5)
**Context:** PLAN.md Day 1 item 3a; CLAUDE.md architecture rule 2; supersedes nothing.

## Context

USLM files carry their table of contents twice over. There is an explicit `<toc>` element
listing children with their designators and headings, and there is the document's own
structural nesting — `<chapter><num/><heading/>…<subchapter>…<section>` — which contains
the same information as a by-product of containing the text.

We need a stored hierarchy: `sections` holds identifiers only, and nothing in the schema
held a chapter's *name*, so the §4 TOC routes and the reader's TOC page had no data source.
The question is which of the two representations to read it from.

## Decision

**Read the hierarchy from the structural elements.** `iter_structure()` walks
`title/subtitle/chapter/subchapter/part/subpart/…` elements that carry an `@identifier`,
capturing `<num>`, `<heading>`, `@status` and `@id` for each, and emits them in document
pre-order with a parent identifier and a sibling sequence. The `<toc>` element is not read
at all — by any parser, for any purpose.

## Why

1. **`<toc>` is one of the three things OLRC actually changed in USLM 2.x.** Their migration
   note lists tables of contents, tables, and the indent model as the substantive
   differences: 2.x replaces `<tocItem>`/`<column>` with `<referenceItem>`/`<designator>`/
   `<label>`/`<target>`. Structural markup barely moved. Reading `<toc>` would mean two
   incompatible implementations and a flag day when OLRC flips the corpus; reading structure
   means one pass. Measured, not assumed: the same pass yields 569 nodes for USLM 1.x
   Title 16 and 203 for USLM 2.x Title 49 (including 10 `subtitle`s, a level Title 16 never
   uses), with identifiers, headings and parents intact in both.
2. **The structure is the thing being described; the TOC is a description of it.** A
   generated TOC can be stale, truncated, or absent — the fixture in this repo has its
   `<toc>` bodies deliberately cut to 5 items while its structural headings are complete,
   and every unit test of the TOC pass runs against exactly that file. Anything derived from
   `<toc>` would pass those tests only by accident.
3. **It is the same traversal the section pass already does,** with the same guards: skip
   anything inside `<quotedContent>` (ADR-0005 — a quoted chapter in an amending act is not
   a chapter of the Code) and require an `@identifier`. In Title 16 all 569 structural
   elements with an `@identifier` sit outside `<toc>`, `<notes>` and `<quotedContent>`, and
   no structural element lacks one, so the two rules agree on every node in the file.
4. **Status is not section-only.** Title 16's single `@status="reserved"` sits on a
   `<subchapter>`. Before this table existed there was nowhere to put it (gotcha 13).

## How, and the one non-obvious constraint

Taking `iterparse` `end` events on `<chapter>` — the obvious reading of "parse the chapters"
— buffers an entire chapter of section text in memory before the first record is emitted,
which Title 42 does not forgive (gotcha 6). So the pass uses both events: identity and
document order are fixed at `start`, `<num>`/`<heading>` are captured at *their* `end` while
their parent frame is open, the frame closes at the structural element's `end`, and sections
are pruned as they go by. Peak RSS parsing the 32 MB Title 16 is 35 MB.

Records are emitted after the file is exhausted rather than streamed, because a node is not
complete until its heading arrives. That is bounded by the skeleton (569 nodes for all of
Title 16), never by the text.

## Consequences

- One TOC implementation serves both schema generations; `Uslm2Parser`'s remaining Day 7
  work is tables and the indent model, not the TOC.
- `structure_nodes` starts **unversioned** (PLAN §3: "start unversioned and measure"), with
  `first_release_id` and `last_release_id` per node. `first_release_id` is a real filter — a
  chapter added at a later release point must not appear in an earlier TOC.
  `last_release_id` is informational: with a handful of the 385 release points ingested,
  absence from the newest is not evidence of removal. If headings turn out to change across
  release points often enough to matter, that is when a `structure_versions` table earns
  its place.
- Structure guids join `guid_map`, so `?id=` resolves a chapter, not only a section.
- `section_versions.parent_identifier` links a section to its structure node. It is
  versioned with the content, which has one known hole: a section that is transferred
  between chapters *without a single character changing* dedupes into its existing version
  row and keeps that row's parent. Recorded rather than solved — the fix is hashing
  `(content, parent)`, and it should wait for a real occurrence in the backfill.
