# ADR-0008: Reading order and parenthood belong to (section, release point)

**Status:** Accepted — 2026-07-27 (Session 4)
**Context:** PLAN.md §3; ADR-0001 (sections are the storage atom); ADR-0007 (dedupe on
guid-stripped content). Amends the `section_versions` shape PLAN §3 sketched.

## Context

`section_versions` is deduped on content: one row per distinct text, reused by every
release point that publishes it (ADR-0007 — 5,093 of Title 16's 5,095 sections share a row
across 119-99 and 119-102not101). PLAN §3 put `seq_in_title` on that row, and Session 3.5
added `parent_identifier` beside it for the TOC.

Both are wrong there, for the same reason. Neither is a property of the text:

- **Reading order.** A section keeps its words while sections around it are added,
  repealed or renumbered. Its `seq_in_title` changes; its content does not. Stored on the
  version, prev/next at a later release point would be computed from the ordering of an
  earlier one.
- **Parenthood.** A transferred section can move to another chapter with no textual change
  at all (`status="transferred"` — gotcha 3 — is exactly this event). Stored on the
  version, the TOC would keep listing it under its old parent forever.

Neither bug is visible in the two release points loaded today: no section was added,
removed or moved between 119-99 and 119-102not101, so both values happen to agree. They
would surface silently during the ~324-release-point backfill, as wrong prev/next links and
sections filed under the wrong chapter, with nothing to make them look like errors.

## Decision

**`section_release_map` carries `seq_in_title` and `parent_identifier`.** That table is
already the (section version, release point) join — the natural home for facts that are
true of a section *at* a release point rather than of its text. `section_versions` keeps
only what the content itself determines: `num`, `heading`, `status`, `source_credit`, the
XML, and the hash.

Indexes follow the queries: `(release_id, seq_in_title)` for prev/next and "everything at
this release point", `(release_id, parent_identifier, seq_in_title)` for listing a TOC
node's sections in reading order.

Ingest upserts the placement on every load, so re-ingesting a release point corrects it,
and the migration moves existing data across rather than requiring a re-ingest.

## Consequences

- `Repository.neighbors` and `get_toc` are release-correct by construction; neither needs
  to know that dedupe exists.
- The caveat ADR-0006 recorded — "a section that moves without a character changing keeps
  its old parent" — is now closed rather than merely documented.
- PLAN §3's schema block is updated to match. The remaining per-release fact still stored
  on the version is the fragment's `@id` guids, which ADR-0007 covers.
- General rule for later tables: if a fact can change while the text does not, it does not
  belong on a content-deduped row.
