# ADR-0095 — A release point assembled section by section from the classification tables

**Status:** accepted (2026-10-27)

**Related:** ADR-0007 (content-hash dedupe), ADR-0012 (the backfill), ADR-0067 (the classification
tables), ADR-0074 (version transitions and their laws), ADR-0082 (an unfinished load is inert),
ADR-0094 (source formats).

## Context

The release-point path loads a title at a release point from that title's zip: `check` and
`inventory` learn of the release point, `backfill` downloads the zips of the titles it lists as
changed, `load-all` loads them. On 2026-10-27 the source was reported to show the current Code
only, with no history of release points and no download of only the changed titles. This
session's network does not reach uscode.house.gov, so that report is not confirmed here; the
newest committed captures (2026-10-23, ADR-0094) still list 22 prior release points and a zip per
title.

The classification tables already say, law by law, which sections a public law was classified to
(144,837 rows, ADR-0067), and ADR-0074 already decides which laws are new at a release point:
`law_in_window(base, target, law)`. Measured on the CI corpus, 119-99 → 119-102not101 adds Pub. L.
119-100 and 119-102; the 119-2 table classifies 119-102 to §§ 2201 and 2206 of Title 16; and those
are the only two of 5,095 sections whose guid-stripped content differs between the two files.

## Decision

1. **A second path, `python -m ingest sections-update`.** For a release point in `release_points`
   and each title, the base is the title's newest completed load before it. The laws in the
   window are looked up in `classification_entries` and the ECCT; a row naming a section of the
   title for one of them sends that section to be fetched, with a `tr to` row's counterpart
   fetched too. Only those sections are fetched.
2. **Coverage is required.** A law in the window that no loaded Public Law table covers
   (`classification_files.covered_ranges`) stops the update, exit 3. A table that has not reached
   a law cannot say which sections it changed. A covered law that classifies nothing is reported
   and does not stop it.
3. **The title is assembled, not patched.** Fetched sections are stored through the loader's own
   `VersionStore`, so dedupe, search sync and retirement are the release-point path's. Every other
   section is mapped to its base version in the base's reading order; a new section goes after the
   base section with the greatest section number below it, with that neighbour's parent unless the
   fetched document carries ancestors. `title_versions` gains `load_method` (`release-point` |
   `sections`) and `base_release_id`; `sections_loaded` is stamped last (ADR-0082). Every fetch
   happens before the first write, and a planned section the source does not have fails the title
   with nothing written (`--allow-not-found` carries its base text instead and records it).
4. **Each law's effect is recorded.** `section_update_items` holds a row per (release point,
   section, law): the basis (`classification` | `ecct`), the row's action and note flag, and the
   outcome (`new-version`, `unchanged`, `new-section`, `not-found`) with the version mapped. The
   version timeline's existing law attribution (ADR-0074) covers the same transitions.
5. **The title's file wins.** A load of the title's file at the same release point unmaps the
   assembled placements and loads over them, and `load-all` does not count an assembled load as
   done.
6. **Sources are pluggable.** `--section-url` (or `USC_SECTION_URL`) is a template with
   `{identifier}`, `{title}`, `{title_padded}` and `{section}`, fetched one GET per section through
   the download throttle and cached under `data/sections/{release}/`; `--from-dir` reads saved
   documents; `--title-file` reads the planned sections out of a title XML or zip, including the
   all-titles zip. A response must be USLM; anything else is an error naming its first bytes.
7. **The answer says so.** On an assembled title `SectionResult` carries `assembled_from` and
   `fetched_for`, and `served_note` writes one of two sentences: fetched for the laws named, or
   carried from the base release point. A carried section's guid is the base's.
8. **The daily run calls it.** `deploy/update-corpus.sh` runs `sections-update --expected-only`
   after `load-all`, limited to the titles the release point lists as changed (all titles when it
   lists none), and again when a classification table changes on a day with no new release point.
   Exit 3 is logged; exit 2 (sections to fetch and no source) and a failed title make the run red.

## Consequences

- `scripts/section_update_check.py` assembles Title 16 at 119-102not101 from 119-99 and the
  committed table slices, reading only §§ 2201 and 2206 from the 119-102not101 file: all 5,095
  sections match that file by content hash (`docs/verification/section-update-check.json`).
- The source's current Code is one point in time. The update assembles the newest release point
  only; a release point between the base and it stays answered from the base (gotcha 10), and
  text fetched after OLRC has moved past the target release point would carry the later law.
- Correctness depends on the tables. A change OLRC makes without a classification row, such as an
  editorial correction, a change to a note no row names, or a structural move, is not fetched,
  and the carried text is stale until the title's file loads.
- `structure_nodes` is not updated: a new chapter has no node, and a new section's parent is
  inferred.
- Carried sections get no guid rows at the assembled release point.
- **No per-section address is configured.** The page that serves one section's USLM on the
  relaunched site has not been captured; until it is, `USC_SECTION_URL` is unset and the daily run
  reports exit 2 whenever there are sections to fetch.
