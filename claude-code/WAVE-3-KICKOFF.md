# Wave 3 kickoff — classification tables, C3 (storage + API) and C4 (reader pages)

Paste the block below into a fresh Claude Code session on this repository, with Opus selected.
Everything it needs beyond `CLAUDE.md` is in `docs/classification-spec.md`.

---

Read `CLAUDE.md`, then `docs/classification-spec.md` in full — §4 (storage and API), §5 (frontend),
§6 (verification), § What Wave 1 measured, § What Wave 2 measured, and the C3 and C4 phase prompts.
Waves 1 and 2 are merged: the four tables, the parser, the loader, the poll and the two
`python -m ingest classification*` subcommands are in `main`, and 144,837 classification rows plus 21
ECCT rows are loaded on the dev box. Nothing reads any of it — there is no storage protocol, no API
route and no page.

Execute Wave 3 — two agents in parallel, decoupled by this spec's API contract. Dispatch both, do not
run either in this session:

- **Agent C — phase prompt C3** (storage protocol + API): `storage/classification.py`,
  `storage/postgres_classification.py`, `get_classification()` in `storage/session.py`, the exports,
  the fourth `..._agree` test in `tests/test_architecture.py`, `api/classification.py`'s seven
  routes, the schemas, and inclusion plus a `DESCRIPTION` paragraph in `main.py`. Merges first.
- **Agent D — phase prompt C4** (reader pages + lookup): the three Astro routes,
  `ClassificationLookup.astro`, the `lib/url.ts` helpers, the table markup, the sort control, the
  filter pills, paging, and the `js-budgets` / `a11y routes` / `screenshots.mjs` entries. Builds
  against the response shapes in §4–§5 in its own worktree, integration-verifies once C is merged,
  then merges. On drift, the spec is the arbiter: whichever side deviated fixes itself.

Each agent works in a worktree on a branch named for its phase, small commits, imperative messages,
`Co-Authored-By` trailer. C4 must not touch `SiteHeader`, `SiteFooter` or `lib/palette.ts` — C5 owns
the chrome. C3 must not touch `frontend/`.

Six things Waves 1 and 2 measured that §4 and §5 do not say — the § What Wave N measured sections are
the authority where they disagree:

1. **`usc_identifier` is spelled with an EN DASH** and `section_norm` with a plain hyphen. A route
   taking typed input normalizes to the hyphen and matches `section_norm`; a route taking an
   `@identifier` matches `usc_identifier` as the corpus spells it (gotcha 17). Both directions need a
   test, and §6 makes the en-dash variant mandatory.
2. **`session = 0` is the 104th's whole-congress file.** §5's URL vocabulary is `1|2|all`, so the
   page maps `all` ↔ 0 — the database never holds a NULL session.
3. **`classification_entries.stat_pages` is empty for 6,053 rows that do have a page**, because a
   page is not always a number: `110 Stat. 3009-587` and `113 Stat. 1501A-594` are single pages.
   `stat_page_labels` is the column to display, and a statviewer link is only buildable when
   `stat_volume` is set and the label is an integer.
4. **1,533 rows have no `usc_identifier`** — 1,531 of them appendix rows — **and 2 have no
   `pl_congress`/`pl_num`.** Appendix rows derive
   no identifier by rule (ADR-0067 decision 7), so a row's citation cell must render unlinked rather
   than 404 into the reader, and `pl_label` is derived and nullable.
5. **A `pl` row's `title_num` is a string** (`'5a'`), sorted only through
   `storage.postgres.title_sort_key` — which is what §4's `?sort=code` means (gotcha 16).
6. **The registry's freshness comes from `classification_source_checks`**, never `source_checks`:
   `last_source_check()` feeds `/api/v1/status` and interleaving the two would make the corpus
   answer flap between sources (ADR-0067 decision 4). Add `last_classification_check()` to the new
   protocol, not to `Repository`.

The 404-versus-empty-page distinction in route 3 is the one behaviour to get exactly right and it has
a test in §6: `covered_ranges` is gap-aware, so "no table covers Public Law 119-72" and "a table
covers it and it classified nothing" are different answers, and `ingest.classification.law_in_ranges`
already decides which.

Verify, and report each: `make test` green with `USC_REQUIRE_INTEGRATION=1`; `make test-web`,
`make test-e2e`, `make test-a11y` and `make shots` green after C4; manual spot checks of routes 2–6
against the loaded dev corpus; the three new routes rendering at 320 CSS px without sideways scroll.
A fresh-context reviewer reads the merged diff before the wave is called done.

End the session by updating `docs/classification-spec.md`'s status line, appending the BUILDLOG
entry, and writing `claude-code/WAVE-4-KICKOFF.md` for C5 (menus, guide chapter, `docs/ia-map.md`,
`/app/design` specimens, `deploy/update-corpus.sh` wiring, the backfill on the box). Stop before
Wave 4.
