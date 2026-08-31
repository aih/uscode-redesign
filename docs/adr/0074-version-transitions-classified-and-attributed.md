# ADR-0074 — Version transitions classified and attributed to Public Laws

- **Status:** Accepted
- **Date:** 2026-08-31
- **Context:** `docs/version-semantics-spec.md` (Phase V1, session 62's design);
  ADR-0007 (dedupe on guid-stripped content), ADR-0021 (several elements per
  identifier), ADR-0066 (`content_first_seen` does not mean what it is called),
  ADR-0067 (the classification tables). Session 63; amended in session 89
  after a fresh-context review of the merged V1 diff — decisions 7 and 9 and
  four costs.

- **Owed:** `docs/verification/version-changes.json` predates decision 7's
  second clause and reports `concurrent: 39,645` where the code now computes
  **77,596**. Every other number in it is unchanged. Regenerate with
  `python -m ingest version-changes --recompute --report` (3 minutes over the
  full local corpus, hashes already stored).

## Context

The version timeline groups a section's history by ADR-0007's content hash —
the XML with `@id` stripped, everything else participating. It therefore
records a new version whenever the XML changed at all: converter attribute
drift (gotcha 8), element-boundary whitespace, `@style`/`@class` churn, a note
edited, a source credit extended. Measured on the loaded corpus (600-section
sample, 3,881 transitions — the spec's § What was measured):

| transition kind | share | matched a classification row in the window |
|---|---|---|
| structure-only (no text, no notes change) | 72.7% | 0.0% |
| notes-only | 18.9% | 7.4% |
| text | 8.4% | 50.5% |

The timeline presents all of these identically. This ADR adds a stored
classification of every transition and, for text changes, an attribution to
the Public Laws the OLRC classification tables record — so the reader (Phase
V3) can default to statutory changes with the full history one click away.

## Decision

1. **The dedupe key is untouched.** ADR-0007's hash still decides what is
   stored once; this layer annotates the transitions between stored versions.
   ADR-0007 reserved any widening of "the same content" for its own ADR.

2. **Two content hashes on `section_versions`** (`text_hash`, `notes_hash`,
   nullable, back-fillable): sha256 of the parser's `plain_text()` with all
   whitespace removed, and of a field-separated serialization of
   `notes_text()`. They are facts about the content, so they sit on the
   content-deduped row — gotcha 15's placement rule cut the other way.
   Computed in `_build_record` while the element is in hand; the backfill
   recovers them from stored fragments via `parser_for_fragment`, so no USLM
   element name appears outside a parser (architecture rule 2).

   **Whitespace-insensitive, and that has a cost:** with whitespace-sensitive
   comparison the text share is 11.4% instead of 8.4%, and the extra
   transitions are almost all element-boundary whitespace from the 2013–2015
   converter. The recorded cost is that a genuine whitespace-only statutory
   change classifies as structure-only — which is also how the reader's
   redline treats it (ADR-0026).

3. **One `section_version_changes` row per version group**, describing its
   arrival: `change_kind` (`text` / `notes` / `structure`, decided in that
   priority; the earliest group is `initial`), the individual flags, the
   release window, `concurrent`, `attribution`. Groups are ordered by the
   earliest release each is mapped to in `section_release_map`, tie-broken by
   version id — never by `first_release_id`, which an incremental load
   attaches earlier releases to without lowering (ADR-0066's finding, now
   load-bearing). `notes_changed` covers the source credit as well as the
   notes, compared from the version rows' own columns. Both `change_kind` and
   `attribution` are strings, not enums.

   **Every textual comparison here is whitespace-removed** — the reading
   text, the notes, the source credit, and the heading. The spec wrote
   "whitespace-collapsed" for the heading; that would flip `heading_changed`
   on the same converter element-boundary whitespace the module suppresses
   everywhere else, so the heading follows the rule the others use.

4. **The window is the delta of incorporated-law sets, honoring
   `excluded_laws`.** A law L = (congress, num) is in a transition's window
   iff L is incorporated at the arriving release and not at the departing one,
   where incorporated(RP, L) = L ≤ (RP.congress, RP.law_num) and L is not in
   RP.excluded_laws. Labels do not describe what a release point contains: the
   text change between `116-344not283u1` and `116-344` is Pub. L. 116-283
   entering, a law *below* both labels, and naive `(from_label, to_label]`
   interval matching misses every such `not`-law incorporation. Classification
   rows are matched by `usc_identifier IN identifier_variants(identifier)`
   (`storage/classification.py`), because the corpus spells 5,697 sections
   with an EN DASH (gotcha 17).

5. **Attribution records both signals and requires only one.**
   `attribution = 'classified'` needs at least one non-note classification row
   in the window; each attributed law's row records `in_classification`,
   `is_note_classification` (only note rows name it), `in_source_credit` (the
   citation newly appears across the transition's `source_credit` diff), and
   the distinct `action` vocabulary for display. The measurement found the two
   signals agree exactly (156/156); recording both keeps that checkable. A
   transition whose text changed with no law recorded stays
   `attribution = 'none'` rather than carrying an inferred law.

6. **No foreign key into `classification_entries`.** Its rows are deleted and
   re-inserted wholesale when a source file changes (`db/models.py` documents
   that nothing may FK into it). The law rows are derived facts, re-derivable
   at any time by `version-changes --reattribute`, which redoes attribution
   and the law rows without touching the content flags and parses no XML.

7. **`concurrent` says the window arithmetic is unreliable here.** Two shapes
   set it. The departing group is still mapped at or after the arriving
   group's first release — at equality, the ADR-0021 case, where the source
   published several elements under one identifier at one release point (160
   (identifier, release) pairs corpus-wide). Or some *third* group is mapped
   inside the window, which is what content that recurs produces: a later run
   of releases maps back to an earlier group, so the interval between a
   departure and an arrival can cover releases a third group held. The second
   clause is the hardening session's amendment; without it only the first
   transition of such a pair was flagged and its successor's window ran
   silently across the revert era.

8. **A mid-corpus `initial` group is attributed from the title's previous
   loaded release.** A section absent from the previous loaded release of its
   title and present now was created in between, so a `new` classification row
   in that window attributes the creation. The stored `window_from_release_id`
   stays NULL (the schema ties it to `from_version_id`); the departure is
   re-derived from `title_versions` on every compute, `--reattribute`
   included. A section present at the title's earliest loaded release gets no
   window and no attribution — an unbounded window would attribute everything
   ever enacted.

9. **Incremental.** `load_release` recomputes change rows for the sections a
   load can have moved, in committed batches. The first implementation took
   that to be every section whose release map gained a row, which on a release
   the corpus has not seen before is every section of the title — a
   whole-title pass per load, 27.0s for Title 42, over 3,153 title-releases in
   a `load-all`. `sections_needing_recompute` names the four cases instead: a
   new version group; a version no change row covers (an interrupted earlier
   load, or a corpus loaded before this ADR); a group the title's previous
   completed load did not map this section to; and a group that departs into a
   successor, where extending its range moves that successor's window
   (decision 7's recurrence, which is most of the set — 1,122 of Title 16's
   1,124). A load that is **not** the title's newest returns every section of
   the title: inserting a release below the top can lower a group's first
   mapped release, and it joins the load history a mid-corpus `initial` window
   departs from, for sections the load never touched. Measured: Title 42 8,465
   sections → 1,590 and 27.0s → 17.4s, Title 16 5,095 → 1,124.

   The hook runs after the load has committed. A failure warns loudly without
   failing the load — the load is complete at that point and the rows are
   re-derivable by `--recompute`, while failing would mark a committed load as
   failed in `load-all`'s ledger — and then **deletes the change rows it was
   recomputing**, because the resume skip is a count equality that can see a
   missing row and not a stale one. `load-all --defer-version-changes` skips
   the hook for a bulk run that will follow with one `version-changes` pass,
   which computes each section once rather than once per release point that
   touched it. The unique constraint on `to_version_id` is the idempotency key
   — recompute is delete-and-reinsert per section. Wiring the classification
   poll to `--reattribute` on the deployed box is Phase V4
   (`deploy/update-corpus.sh`).

## Costs and limits, named

- **The backfill parses every stored fragment once** (~423,800 transitions
  corpus-wide; Title 16's 40,073 versions took about 3 minutes locally), and
  `_build_record` now walks each section twice more at load time for the two
  hashes. The full-corpus run and its committed artifact
  (`docs/verification/version-changes.json`, via `--report`) are Phase V4.
- **Attribution is honest, not complete:** roughly half of text transitions
  name no statute — footnote-marker insertions, editorial reference trimming,
  renumbering notices, and amendments the tables or the window arithmetic
  miss. The UI wording (V3) says no classifying statute is recorded, never
  "editorial".
- **ECCT rows are not consulted** (21 editorial moves); a moved provision's
  text change stays unattributed.
- **The resume skip is a count equality** — a section is skipped when its
  change rows number its version groups — rather than "the newest group has a
  row". A new group breaks the equality either way; what the approximation
  cannot see is a corpus whose *membership* of groups changed at equal count,
  which only a manual deletion produces, and `--recompute` covers.
- **A section computed before the classification tables were loaded is one of
  the skipped**, and its attribution is `none`, which reads exactly like a text
  change no statute is recorded for. `run_compute` says so on stderr when
  `classification_entries` is empty; the repair is `--reattribute`, which
  parses no XML.
- **The digests carry no normalization version.** `text_hash` is sha256 of
  `plain_text()` with whitespace removed; a change to what `plain_text()`
  renders — Day 7's table handling is the live candidate — redefines what every
  stored hash means, silently, since old and new rows are the same 32 bytes.
  The repair is `version-changes --recompute`, which rebuilds every hash from
  the stored fragments, and nothing detects the need for it.
- **The incremental hook cannot see the out-of-order case it does not touch.**
  Loading a release *below* a title's newest changes the departing release of
  every mid-corpus `initial` window above it, including for sections that
  release never carried. `sections_needing_recompute` answers by returning the
  whole title for such a load, which is correct and is the expensive branch;
  `load-all` walks seq ascending, so the bulk path never takes it.
- **A section renumbered away (gotcha 3) ends its identifier's timeline**; the
  transfer is a `tr to` action chip at best. Cross-identifier continuity stays
  future work (the declined redirects table, ADR-0065).
- **`concurrent` fires far beyond ADR-0021's duplicates.** The spec expected it
  to flag the 160 several-elements-per-identifier pairs; the corpus-wide
  backfill flagged **39,645 of 423,800 transitions** under the first rule and
  **77,596 (18.3%)** under decision 7's second clause, none of them on a
  section with a same-release duplicate. The cause is content that *recurs*: a
  mid-era converter serialization variant (or a genuine revert) maps a handful
  of releases to a group whose neighbour spans releases on both sides, so the
  ranges overlap and the model — one row per stored group, which cannot
  represent a third era of a twice-used content — reports a window running
  backwards (`119-102not101 → 114-139`). Flagging these unreliable is the
  design working as defined. Representing recurrence properly (a row per era
  rather than per group) would be its own ADR; nothing else in the artifact
  moved when the second clause landed — every other count, share and per-title
  breakdown is identical.
