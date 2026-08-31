# Version-change semantics — implementation spec for aih/uscode-redesign

**Status:** spec written 2026-08-30, from a measurement session against the full local corpus
(session 62, BUILDLOG). Wave 1 (V1) is implemented (session 63, ADR-0074); V4 — the full-corpus
backfill, `docs/verification/version-changes.json` and the `update-corpus.sh` wiring — is done
(session 65). Implementing sessions update this line and the [§ Status](#status) table as waves
land.

The version timeline groups a section's history by `content_hash` — the XML with `@id` stripped
(ADR-0007). Everything else in the fragment still participates in the hash, so the timeline
records a new version whenever the XML changed at all: attribute drift from the 2013–2015
converter (gotcha 8), whitespace at element boundaries, `@style`/`@class` churn, a note edited,
a source credit extended. Measured on the loaded corpus (§ What was measured), **72.7% of
recorded version transitions change no text and no notes; only 8.4% change the statutory reading
text**. The timeline presents all of them identically, and its lede calls each one "a release
point where the text changed", which is false for most of them.

This spec adds a stored classification of every version transition — text change, notes change,
or structure-only — and, for text changes, an attribution to the Public Law(s) that drove them,
confirmed against the OLRC classification tables (ADR-0067). The reader's version history then
defaults to statutory changes with law attributions, with the full recorded history one click
away. The dedupe key itself does not change: ADR-0007's hash still decides what is stored once,
and this layer annotates the transitions between stored versions. (ADR-0007 reserved any
widening of "the same content" for its own ADR; this is deliberately not that — nothing about
storage identity moves.)

Scope, from the user's request (2026-08-30):

- Database design first: kind of change per transition, correlated with the classification
  tables. Then the UI.
- The reader defaults to text-affecting versions only; the full history (XML/metadata changes
  included) is a user choice, reachable from the default view without taking much space there.
- A per-account default-view preference comes later, once accounts carry settings for it; this
  spec records the mechanism but does not build it.

## What was measured

All numbers from a 600-section random sample (seed 42) of the 61,252 sections with more than one
version, 3,881 transitions, run against the full local corpus (489,738 `section_versions`,
144,837 `classification_entries`). Method: consecutive version pairs ordered by the earliest
release each version is mapped to in `section_release_map` (never `first_release_id` — ADR-0066);
reading text extracted by walking the fragment excluding `notes`/`note`/`sourceCredit`/`toc`
by local name; comparison with all whitespace removed.

| transition kind | share | matched a classification row for a law newly incorporated in the window |
|---|---|---|
| structure-only (no text, no notes change) | 72.7% (2,822) | 0.0% (1 note row in 2,822) |
| notes-only | 18.9% (732) | 7.4% (54: 37 note rows, 17 text rows) |
| text | 8.4% (327) | 50.5% (165) |

Findings that shape the design:

1. **The window must be the delta of incorporated-law sets, honoring `excluded_laws`.** Labels
   do not describe what a release point contains: the text change between `116-344not283u1` and
   `116-344` is Pub. L. 116-283 entering, a law *below* both labels. A law L = (congress, num)
   is in a transition's window iff L is incorporated at the arriving release and not at the
   departing one, where incorporated(RP, L) = L ≤ (RP.congress, RP.law_num) and L is not in
   RP.excluded_laws. Naive `(from_label, to_label]` interval matching misses every `not`-law
   incorporation.
2. **The classification match and the source credit agree exactly.** For every transition where
   a classification row's law fell in the window, the same citation was newly added to the
   section's `source_credit`; no transition had a new credit citation without a classification
   row. The credit is a confirming second signal, not an independent source.
3. **Whitespace sensitivity is converter noise.** With whitespace-sensitive comparison the text
   share is 11.4%; the extra transitions are almost all element-boundary whitespace from the
   2013–2015 converter (`"In general In"` vs `"In generalIn"`). Comparison is
   whitespace-insensitive. The recorded cost: a genuine whitespace-only statutory change
   classifies as structure-only, which is also how the reader's redline already treats it
   (ADR-0026).
4. **Half the text changes name no statute**, and the sample says why: footnote-marker
   insertions, editorial reference trimming (`"II of this chapter," → "II,"`,
   `"of this section" → ""`), renumbering notices (`[§ 2313a. Renumbered 3847]`), and some
   genuine amendments the tables record under a law the window arithmetic or the tables
   themselves miss. The design stores "text changed, no classifying statute recorded" as an
   honest state, never infers a law.
5. **Structure-only transitions match classification rows at 0%**, which validates the
   correlation: when the tables say a law touched a section, the text (or its notes) actually
   moved.
6. **The CI fixture corpus can exercise attribution end to end.** Its two release points are
   119-99 and 119-102not101; the only two sections whose content differs between them are
   t16 s2201 and s2206 (ADR-0007's measurement), and the real 119-2 classification table
   classifies Pub. L. 119-102 to exactly those: s2201 amended + a new note, s2206 amended.
   A committed `tbl119pl_2nd_slice.htm` fixture (which does not exist yet) makes the whole
   chain testable offline.

Probe scripts are not committed; `python -m ingest version-changes --report` (Phase V1)
reproduces the numbers corpus-wide into `docs/verification/version-changes.json`.

## Design

### Terminology

- **Version group** — one `section_versions` row: a distinct stored content for one section.
- **Transition** — an ordered pair of consecutive version groups for one section. Order is by
  the earliest release each group is mapped to (`min(release_points.seq)` over
  `section_release_map`), tie-broken by version id. Never by `first_release_id` (ADR-0066:
  an incremental load attaches earlier releases without lowering it).
- **Window** — the releases a transition spans: from the last release mapped to the departing
  group to the first release mapped to the arriving group.
- **Change kind** — `text` | `notes` | `structure`, decided in that priority order;
  the earliest group of a section is `initial`.
- **Attribution** — the laws newly incorporated in the window that the classification tables
  classify to this section.

### Schema (migration, Phase V1)

Two columns on `section_versions`, both nullable so the migration is trivial and old rows are
back-fillable:

- `text_hash BYTEA` — sha256 of the parser's `plain_text()` for the fragment with all
  whitespace removed.
- `notes_hash BYTEA` — sha256 of a stable serialization of `notes_text()` (each note's
  topic/role/heading/text joined with separators), all whitespace removed.

These are facts about the content, so they belong on the content-deduped row (gotcha 15 cuts
the other way for placement: they cannot change while the text does not).

New table `section_version_changes` — one row per version group, describing its arrival:

| column | type | meaning |
|---|---|---|
| `id` | Integer PK | |
| `section_id` | FK `sections.id`, not null | denormalized for the per-section query |
| `to_version_id` | FK `section_versions.id`, not null, **unique** | the arriving group |
| `from_version_id` | FK `section_versions.id`, nullable | the departing group; NULL = the section's first group |
| `window_from_release_id` | FK `release_points.id`, nullable | last release mapped to the departing group (NULL with `from_version_id`) |
| `window_to_release_id` | FK `release_points.id`, not null | first release mapped to the arriving group |
| `change_kind` | String, not null | `initial` / `text` / `notes` / `structure` — a string, not an enum, per project convention |
| `text_changed` | Boolean, not null | reading text differs (whitespace-insensitive) |
| `notes_changed` | Boolean, not null | notes/sourceCredit text differs |
| `heading_changed` | Boolean, not null | `heading` differs (whitespace-collapsed); informational — a heading change is already a text change |
| `status_changed` | Boolean, not null | `status` differs (e.g. → repealed) |
| `concurrent` | Boolean, not null, default false | the two groups' release ranges overlap (ADR-0021's several-elements-per-identifier sections; 160 (identifier, release) pairs corpus-wide) — window arithmetic is unreliable here and the UI says so |
| `attribution` | String, not null | `classified` (≥1 non-note classification row in window) / `none` — a string, not an enum |
| `computed_at` | DateTime(tz), not null | |

Index on `section_id`. The unique on `to_version_id` is the idempotency key: recompute is
delete-and-reinsert per section.

New table `section_version_change_laws` — the attributed laws, one row per (transition, law):

| column | type | meaning |
|---|---|---|
| `id` | Integer PK | |
| `change_id` | FK `section_version_changes.id`, **ON DELETE CASCADE**, not null | |
| `pl_congress` | Integer, not null | |
| `pl_num` | Integer, not null | |
| `in_classification` | Boolean, not null | a classification row for this law names this section |
| `is_note_classification` | Boolean, not null | only note rows name it (a note-only classification against a text transition is worth showing as such) |
| `in_source_credit` | Boolean, not null | the citation newly appears in `source_credit` across the transition |
| `classification_actions` | ARRAY(String), not null, default `{}` | distinct `action` values of the matching rows (`''` = amended, `new`, `repealed`, `tr to`, …) — display vocabulary for the UI |

Unique on `(change_id, pl_congress, pl_num)`.

Deliberately **no foreign key into `classification_entries`** — those rows are deleted and
re-inserted wholesale when a file changes (`db/models.py` documents that nothing may FK into
the table). These are derived facts, re-derivable at any time by `--reattribute`.

### Computation (Phase V1)

New module `ingest/version_changes.py`, plus a CLI subcommand:

```
python -m ingest version-changes [--title T] [--recompute] [--reattribute] [--report]
```

- **Hashes.** `SectionRecord` gains `text_hash`/`notes_hash`, computed in `_build_record`
  where the element is already in hand (beside `content_key`, before the streaming parser
  clears the element — gotcha 6). The loader writes them on new `section_versions` rows.
  The backfill computes them for existing rows via `parser_for_fragment(xml)` +
  `plain_text()`/`notes_text()` — the extraction the schema-plural parsers already own
  (`ingest/base.py`); no USLM element names appear in this module (architecture rule 2).
- **Change rows.** Per section: order groups as defined above; compare hashes pairwise; write
  one `section_version_changes` row per group (the first gets `initial`). `heading_changed`/
  `status_changed` from the version rows' own columns. `concurrent` when the departing group's
  last mapped seq exceeds the arriving group's first mapped seq.
- **Attribution.** For each transition: laws L with incorporated(window_to, L) and not
  incorporated(window_from, L) (finding 1), intersected with the classification rows for the
  section's identifier — `usc_identifier IN identifier_variants(identifier)`
  (`storage/classification.py`; the corpus spells 5,697 sections with an EN DASH, gotcha 17).
  Non-note rows in the window ⇒ `attribution = 'classified'`. Independently, diff the two
  `source_credit` strings for newly appearing `Pub. L. C-N` citations and set
  `in_source_credit` per law (finding 2 says the two agree; recording both keeps that
  checkable). For `initial` rows whose section appears mid-corpus (the title was loaded at an
  earlier release without this section), the window runs from that earlier release, so a `new`
  classification row attributes the section's creation; if that proves awkward in V1, record
  it as a named cost in ADR-0074 and leave `initial` unattributed.
- **Incremental.** The `load_title` path computes change rows for version groups it creates,
  after the release map upsert. The classification poll path (`python -m ingest
  classification`) triggers `--reattribute` for the congress of any file it changed —
  attribution-only recompute (child rows + `attribution` column), never touching the content
  flags. `deploy/update-corpus.sh` wiring is Phase V4.
- **Resumability and cost.** ~423,800 transitions; each version parsed once for its hashes.
  The measurement session parsed at ~12 ms/fragment → roughly 1.5–2 h single-process for the
  full backfill; per-title batches with commits, skip sections whose newest group already has
  a change row unless `--recompute`. One fragment in memory at a time.
- **`--report`** writes `docs/verification/version-changes.json`: corpus totals by
  `change_kind`, attribution rates, per-title breakdown, `concurrent` count, compute
  timestamp. Documentation duty 5's artifact; the § What was measured table is its sampled
  prediction.

### Repository and API (Phase V2)

`SectionVersionInfo` (`storage/repository.py`) gains optional fields, `None` when no change row
exists (a corpus loaded but not back-filled):

```python
change_kind: str | None          # 'initial' | 'text' | 'notes' | 'structure'
text_changed: bool | None
notes_changed: bool | None
status_changed: bool | None
concurrent: bool | None
attribution: str | None          # 'classified' | 'none'
laws: tuple[VersionLawRef, ...]  # pl_congress, pl_num, in_classification,
                                 # is_note_classification, in_source_credit,
                                 # classification_actions
```

`PostgresRepository.versions()` joins the two new tables (one extra query, assembled in
Python — same shape as the existing two-query build). While there, fix the group ordering to
the earliest *mapped* release (`min` over the map) instead of `first_release_id`'s seq —
the ADR-0066 finding, now load-bearing since transitions depend on order. `first_seen` stays
in the payload for compatibility; `releases[0]` is authoritative and the UI switches to it.

API: `VersionOut` gains the same fields additively (`laws` as a list of a new `VersionLawOut`);
`VersionsOut` is otherwise unchanged; no new routes, no new params — the response is small and
filtering is presentation. No raw SQL outside `storage/postgres.py`; `tests/test_architecture.py`
already enforces the boundary.

### Reader (Phase V3)

**`/app/versions/[...identifier]` — two views, one document shape, zero script.**

- The page renders **every** entry, each `<li>` carrying `data-change-kind` (and its law chips,
  badges, releases). The list root carries `data-view="text"` (default) or `data-view="all"`
  from the `?view=all` query param — server-rendered, cacheable per URL (ADR-0018), no JS
  (`/app/versions`' budget is 18,500 bytes and stays there). CSS scoped on `[data-view="text"]`
  hides `structure`/`notes` entries. The query param adds no route, so the guide ratchet asks
  only for the ADR and prose.
- In the text view, an entry's "Unchanged through" run must extend through the hidden groups
  that follow it. `frontend/src/lib/versions.ts` (new, Vitest-tested) computes effective runs
  and counts; each entry renders both its own-run line and its effective-run line, CSS picking
  one per view.
- The view switch sits under the lede in the sortbar vocabulary (ADR-0071 —
  `.sortbar__option`, the option in force marked, the other a link): **"Amendments (N)"** |
  **"All recorded versions (M)"**. One line; this is the whole footprint the full history costs
  the default view.
- Entry annotations: a text entry attributed `classified` shows its law chips —
  "Pub. L. 119–102" linking through `classificationHref` (`lib/url.ts`) to the session table
  filtered to that law, with the action word when it is not a plain amendment (`repealed`,
  `new`, `tr to`); an unattributed text entry says "no classifying statute recorded"; in the
  all view, notes entries say "Notes updated" and structure entries "XML/metadata only".
  `concurrent` entries carry the ADR-0021 note. The lede sentence is rewritten — the current
  one ("Each entry is a release point where the text changed") is what this feature falsifies.
- **Unknown state degrades visibly:** when `change_kind` is null on any entry (no backfill),
  the page renders the all view with a sentence saying change kinds are not computed for this
  corpus, and no view switch.
- `first_seen.label` display switches to `releases[0]` (ADR-0066; V2 fixed the ordering).

**Section page.** `previousChangedRelease` (`lib/compare.ts`) becomes
previous-*text*-changed-release: walk annotated entries past notes/structure groups; fall back
to current behavior when annotations are null. `CompareWith`'s hint says "the last release
point holding different statutory text" (and its stale docstring referencing
`content_first_seen` gets fixed). The doc-meta line above it becomes
"Version history — amended N times over M release points" from the already-fetched timeline.

**Diff page.** When the reading redline reports "No changes", it already reports whether the
source XML differs (`sourceDelta`); with annotations it can now say which kind of change the
interval held. Small, optional.

**Design page** (ADR-0053): the `Timeline` specimen's fixture entries gain all three kinds and
a law chip, in both views, so `make shots` and the axe matrix see the badges without a corpus —
this is also the only place the metadata-only *display* is exercisable by CI, since the fixture
corpus's two RPs produce only text transitions (finding 6).

**Guide** (duty 6): chapter 04 rewritten around the default/all views; scenarios: the s2201
timeline shows "Pub. L. 119–102" (EN DASH in the assertion text); the view switch to
"All recorded versions"; the unattributed state needs no scenario (not constructible from the
fixture corpus — Vitest covers the lib, the design page covers the rendering). New a11y route
entry for `?view=all` in `docs/a11y/routes.json`.

**Account preference (deferred, designed now).** localStorage key `usc-versions-view`
(`text` / `all`), stamped as `data-versions-view` by `Base.astro`'s pre-paint bootstrap next to
`usc-theme`/`usc-density`; a settings row over `GET/PUT /api/v1/settings` on the
`open_links_in_new_tab` pattern; the stamp flips the default the CSS reads when no `?view=` is
present. Nothing in V1–V4 builds this; the CSS in V3 should key on the list root's `data-view`
so the stamp can later override the absent-param default without markup changes.

### ADRs

- **ADR-0074** (V1): version transitions classified and attributed. Records: the dedupe key is
  untouched; whitespace-insensitivity and its cost; the incorporated-set window; no FK into
  classification tables; the `concurrent` escape hatch; the measured table above.
- **ADR-0075** (V3): version history defaults to statutory changes. Amends ADR-0066's default
  ("last release holding different *text*" becomes annotation-driven) and chapter 04. Records:
  all-entries-in-DOM with CSS filtering and why (one cacheable document per URL, account
  preference later); the unknown-state fallback.

### Costs and risks, named

- The backfill is a one-time ~2 h local compute and the same on the deployed box after its next
  `pg_restore`-free deploy; migration + backfill on the box is owed work recorded in
  `docs/deploy-status.md` (V4).
- Attribution is honest, not complete: ~half of text transitions carry no law (finding 4). The
  UI wording never claims "editorial" — it says no classifying statute is recorded.
- A section renumbered away (gotcha 3) ends its identifier's timeline; the transfer is a `tr to`
  action chip at best. Cross-identifier continuity stays future work (the declined redirects
  table, ADR-0065).
- ECCT rows (21, editorial moves) are not consulted; a moved provision's text change stays
  unattributed. Named in ADR-0074.
- `compare.spec.ts` re-derives the compare default from the live API and hard-codes current
  grouping semantics; V3 must update it in the same session as `compare.ts`.

## Phases

Each phase is one worktree agent session on the model-assignment rhythm (PLAN §7): read this
spec, implement, tests green, guide/ADR duties in-session, BUILDLOG entry, small commits. Every
prompt below is self-contained for an agent starting cold in the repo.

### V1 — schema, hashes, computation, backfill (Python only)

**Prompt:**

> Read `docs/version-semantics-spec.md` (§ Design: Schema, Computation; § What was measured)
> and ADR-0007, ADR-0021, ADR-0066, ADR-0067. Implement Phase V1:
> `text_hash`/`notes_hash` columns on `section_versions` and the
> `section_version_changes` + `section_version_change_laws` tables (one Alembic migration);
> `SectionRecord.text_hash`/`notes_hash` computed in `_build_record`;
> `ingest/version_changes.py` with the ordering, window, and attribution rules exactly as
> specified (incorporated-law-set delta honoring `excluded_laws`; identifier matching through
> `storage.classification.identifier_variants`); the
> `python -m ingest version-changes [--title|--recompute|--reattribute|--report]` subcommand;
> the `load_title` incremental hook; and a committed CI fixture
> `tests/fixtures/tbl119pl_2nd_slice.htm` (slice the real 119-2 table to its Title 16 rows —
> it classifies Pub. L. 119-102 to t16 s2201 and s2206) wired into `make ci-data`'s
> classification step. Write ADR-0074 per the spec's ADR section. Tests: unit tests on the
> fixture slice corpus (the two-RP CI corpus must yield: s2201/s2206 transitions
> `change_kind='text'`, `attribution='classified'`, law 119-102 with `in_classification` and
> `in_source_credit` true; unchanged sections one `initial` row), a `@pytest.mark.slow`
> full-sample test, and migration round-trip. Run the backfill over Title 16 locally and sanity-check
> `--report` output. Update `.claude/skills/ingest-cli/SKILL.md` and this spec's Status table.
> Do NOT touch `storage/repository.py`, `storage/postgres.py`, `api/`, or `frontend/`.
> `make test` green before finishing; BUILDLOG entry.

**May touch:** `db/models.py`, `alembic/versions/`, `ingest/`, `tests/`, `tests/fixtures/`,
`Makefile` (ci-data wiring only), `docs/adr/0074-*.md`, `.claude/skills/ingest-cli/SKILL.md`,
`docs/version-semantics-spec.md`, `BUILDLOG.md`.

### V2 — repository and API (depends on V1 merged)

**Prompt:**

> Read `docs/version-semantics-spec.md` (§ Design: Repository and API) and ADR-0066. Implement
> Phase V2: extend `SectionVersionInfo` and `PostgresRepository.versions()` with the change
> annotations and laws (fields exactly as the spec lists; `None`s when no change row exists);
> fix `versions()` ordering to the earliest mapped release; extend `VersionOut`/new
> `VersionLawOut` additively in `api/schemas.py`. No new routes or params; no raw SQL outside
> `storage/postgres.py`. Tests: repository tests against the dev corpus (skip without
> `make dev-data`, as the existing API integration tests do), API response-shape tests
> including the all-`None` degradation, and the ordering fix (a version group whose
> `first_release_id` is later than its earliest mapped release must sort by the latter).
> Update this spec's Status table; BUILDLOG entry. Do NOT touch `ingest/`, `frontend/`, or
> `db/models.py`. `make test` green.

**May touch:** `storage/repository.py`, `storage/postgres.py`, `api/schemas.py`,
`api/routes.py`, `tests/`, `docs/version-semantics-spec.md`, `BUILDLOG.md`.

### V3 — reader (depends on V2 merged)

**Prompt:**

> Read `docs/version-semantics-spec.md` (§ Design: Reader, ADRs, Costs) and ADR-0053,
> ADR-0056, ADR-0066, ADR-0071. Implement Phase V3: the two-view `/app/versions` page
> (all entries in DOM, `data-view` from `?view=all`, CSS filtering, sortbar-vocabulary view
> switch, law chips through `classificationHref`, effective "unchanged through" runs from a
> new Vitest-tested `frontend/src/lib/versions.ts`, the unknown-state fallback, `releases[0]`
> as the displayed start); `previousChangedRelease` → previous-text-changed with null
> fallback and the `CompareWith` hint + stale docstring fix; the section page's
> "amended N times" doc-meta line; the `Timeline` specimens on `/app/design` covering all
> three kinds and both views; guide chapter 04 rewritten with the scenarios the spec names
> (mind the EN DASH in "Pub. L. 119–102"); ADR-0075; `?view=all` entry in
> `docs/a11y/routes.json`. Update `compare.test.ts`, `compare.spec.ts` (it re-derives the
> default from the live API), `url.test.ts` if `versionsHref` gains a param. JS budget for
> `/app/versions` must not grow. Do NOT touch Python. `make test-web` green; run
> `make test-e2e` and `make test-a11y` against `make dev-all`. Update this spec's Status
> table; BUILDLOG entry.

**May touch:** `frontend/`, `docs/adr/0075-*.md`, `docs/a11y/routes.json`, `docs/ia-map.md`,
`docs/version-semantics-spec.md`, `BUILDLOG.md`.

### V4 — corpus backfill, verification artifact, deploy wiring (depends on V1 merged; parallel with V2/V3)

**Prompt:**

> Read `docs/version-semantics-spec.md` (§ Computation, § Costs). Phase V4: run
> `python -m ingest version-changes` over the full local corpus (resumable; expect ~2 h — run
> per-title with `--title` if interrupted), then `--report` and commit
> `docs/verification/version-changes.json`; compare its corpus-wide shares against the spec's
> sampled table and record any surprise in the spec's Status table. Wire
> `deploy/update-corpus.sh`: version-changes after a load that loaded something, and
> `--reattribute` after a classification poll that changed a file. Add the owed deploy work
> (migration + one-time backfill on the box) to `docs/deploy-status.md`. Update the CLAUDE.md
> status section's version paragraph and this spec's Status table; BUILDLOG entry. Do NOT
> touch `storage/`, `api/`, or `frontend/`.

**May touch:** `deploy/update-corpus.sh`, `docs/verification/version-changes.json`,
`docs/deploy-status.md`, `CLAUDE.md`, `docs/version-semantics-spec.md`, `BUILDLOG.md`.

## Wave plan

| wave | phases | parallel? | notes |
|---|---|---|---|
| 1 | V1 | alone | schema first (merge order: schema → ingest → API → web) |
| 2 | V2 ∥ V4 | yes — disjoint files (V2: storage/api; V4: deploy/docs + a long local compute) | both branch from main after V1 merges |
| 3 | V3 | alone | needs V2's API fields |

Worktree agents per phase; each merges via PR with a fresh-context review of the diff before
the next wave starts. File-boundary lists above are the non-interference contract.

## Status

| phase | state | branch/PR | notes |
|---|---|---|---|
| V1 schema + computation | implemented | `c5-version-changes-v1` / PR #61 | ADR-0074. Migration `b6e1f0a2c9d4`; `ingest/version_changes.py`; `version-changes` subcommand; `load_release` hook; `tbl119pl_2nd_slice.htm` in `make ci-data`. Mid-corpus `initial` groups **are** attributed (departure re-derived from `title_versions`, stored column stays NULL). Title 16 back-filled locally (184 s, 40,073 rows): 79.5% structure / 14.2% notes / 6.3% text, text 29.8% classified — a structure-heavier, less-classified title than the corpus-wide sample predicts (V4 compares corpus-wide). **Surprise:** `concurrent` fired on 3,016 transitions, not ADR-0021 duplicates but recurring content (converter flip-flops/reverts) — recorded in ADR-0074's costs. |
| V2 repository + API | not started | — | |
| V3 reader | not started | — | |
| V4 backfill + deploy wiring | done | `c5-version-changes-v4` | Full corpus back-filled locally: 489,738 change rows over 423,800 transitions (the spec's own estimate exactly), 30,250 law rows — **7m50s wall**, not the ~2 h estimated, mostly V1's post-review streaming path. Corpus-wide shares **75.1% structure / 17.1% notes / 7.8% text, text 49.2% classified** — every share within 2.5 points of the sampled table above, so the sample held. **Surprise:** `concurrent` is **39,645** corpus-wide (9.4% of transitions) — V1's Title 16 finding (recurring content, not ADR-0021 duplicates) scaled with the corpus rather than staying near the predicted ~160. `update-corpus.sh` runs `version-changes` after a load that loaded something and `--reattribute` after a classification change; the box's owed migration + one-time backfill is in `docs/deploy-status.md`. |
