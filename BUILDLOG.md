# Build Log

Session-by-session record of how this site was built. One entry per working session, written at the end of that session while context is fresh. Format:

```
## NNN — YYYY-MM-DD — <short title>
- Tool/model:
- Asked: <what the human directed>
- Decided: <key decisions; link ADRs>
- Produced: <commits / files>
- Verified: <what was checked, and how to re-check it>
```

---

## 001 — 2026-07-27 — Research & planning (pre-build)

- **Tool/model:** Claude (Cowork), Fable 5.
- **Asked:** Research USLM structure and uscode.house.gov release points; design a plan for a versioned US Code retrieval site (FastAPI + Postgres, later XCiteDB); specify agent/model orchestration, required accounts, and a documentation regime.
- **Decided:**
  - Sections are the storage atom; sub-section provisions extracted at request time (ADR-0001).
  - Schema-plural parser layer for USLM 1.x and 2.x (ADR-0002).
  - GUIDs treated as globally unique (provision, release point) pins; `@identifier` is the cross-release identity (ADR-0003).
  - Reuse dreamproit/loadusc-xcitedb for release-point download inventory and the future XCiteDB path.
  - Mine dreamproit/versions (older XCiteDB-based USC site) for the temporal diff algorithm and display insights (PLAN §1; GETTING-STARTED Session 1.5).
- **Produced:** PLAN.md, GETTING-STARTED.md, README.md, this file, docs/adr/0001–0003.
- **Verified:**
  - `id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd` ↔ `/us/usc/t16/s45f/c/5` confirmed by grep of usc16.xml.
  - Title 16 counts from source XML: 5,393 sections; 523 repealed / 102 omitted / 19 transferred / 1 reserved.
  - Current release point 119-102not101 and download URL scheme confirmed live at uscode.house.gov/download/download.shtml (2026-07-27).
  - ~324 prior release points, back to the 113th Congress, per priorreleasepoints.htm; compound skip labels observed (e.g. `277not255not268`).
  - USLM 2.x sample location confirmed: https://uscode.house.gov/currency/uscinuslmv2samples.zip.

## 002 — 2026-07-27 — CLAUDE.md, USLM fixtures, and Day 1 item 1 scaffold

- **Tool/model:** Claude Code, Opus 5 (CLAUDE.md authoring) then Sonnet 5 (fixture trimming, scaffold, permissions — per PLAN §7 model assignment).
- **Asked:** Execute GETTING-STARTED's sample-download step; write CLAUDE.md from PLAN.md so it's loaded into every future session; execute PLAN.md Day 1 item 1 (repo scaffold: `ingest/ api/ web/ db/`, uv, docker-compose + Postgres 16, Alembic, pytest, Makefile), committing in small steps; update project permissions for a more autopilot workflow.
- **Decided:**
  - Committed only 3 of the 57 USLM 2.x sample titles (usc16 for cross-schema parity, usc49 for heaviest table/layout markup, usc01 as a small fast fixture) instead of the full 594 MB zip — kept as a size/coverage tradeoff, not an ADR-level call; re-download `uscinuslmv2samples.zip` if another title is needed later.
  - `data/*` (with `!data/manifests/`) added to `.gitignore` so the CLAUDE.md claim "never commit `data/`" (PLAN §11.4 provenance manifests still committed) is actually true — verified with `git check-ignore` before committing.
  - DB URL is a single source of truth: `db/config.py` (`DATABASE_URL` env var, pydantic-settings) feeds both the app and Alembic's `env.py` (which also points `target_metadata` at `db.models.Base`) — no separate URL to drift.
  - Docker image sets `UV_PROJECT_ENVIRONMENT=/opt/venv` so the dev bind mount (`.:/app`) doesn't shadow the container's venv with the host's.
  - `make verify` is a stub that exits 1 with a message rather than silently succeeding — the real Day 7 full-corpus check (PLAN §11.5) doesn't exist yet.
  - `.claude/settings.json` now auto-allows `git commit`/`git push` in this repo and common package-manager installs (uv/pip/brew/npm/yarn/bun/apt); uninstall/remove variants of the same tools are routed to `permissions.ask` explicitly rather than left to default behavior.
- **Produced:** `samples/uslm1/usc16.xml`, `samples/uslm2/USLM2/{usc16,usc49,usc01}.xml`; `CLAUDE.md`; `pyproject.toml`/`uv.lock`, `ingest/ api/ web/ db/ tests/` packages; `db/config.py`, `db/base.py`, `db/models.py` (all 10 PLAN §3 tables); `api/main.py` (`/health`); `Dockerfile`, `docker-compose.yml`, `.env.example`; `alembic.ini`, `alembic/env.py`, initial migration `fce3a6c7a647_initial_schema.py`; `tests/test_health.py`, `tests/test_models.py`; `Makefile`; `.claude/settings.json`. 12 commits, `47744ec..d4eb0ae`.
- **Verified:**
  - `db.models.Base.metadata.tables.keys()` matches all 10 PLAN §3 tables exactly (`tests/test_models.py`, also spot-checked interactively via `uv run python`).
  - `GET /health` returns `{"status": "ok"}` via FastAPI `TestClient` (`tests/test_health.py`).
  - `docker compose up -d db` starts Postgres 16 cleanly; `alembic revision --autogenerate` detected all 10 tables with no drift; `alembic upgrade head` applied against the running container, confirmed via `psql \dt` (11 rows incl. `alembic_version`).
  - `uv run pytest` — 4 passed, 0 failed, no live DB required.
  - `make test` and `make verify` both run as expected (test passes; verify exits 1 with its stub message, by design).
  - `git check-ignore -v` confirmed `data/zips/*` is ignored while `data/manifests/*` is not, before trusting the CLAUDE.md claim.
  - Not yet done: `alembic downgrade base` round-trip untested (interrupted mid-session, not re-run); `docker compose up --build` (full containerized api service, as opposed to `make dev`'s locally-run API) untested end-to-end.

## 003 — 2026-07-27 — Session 1 review; plan tuned for speed (pre-Session-2)

- **Tool/model:** Claude (Cowork), Fable 5 — independent reviewer, fresh context.
- **Asked:** Review Session 1 progress; update the plan to improve quality and speed.
- **Findings:** Scaffold matches PLAN §3 faithfully (all 10 tables, correct constraints and keys); single-source DB config and the `UV_PROJECT_ENVIRONMENT` bind-mount fix are correct; BUILDLOG 002 debts confirmed as the only open items. Reviewer verification was **static (code review only)** — the review sandbox has no Python 3.12, so `uv run pytest` was not re-executed independently; Session 2 should not treat the test suite as independently confirmed until CI exists.
- **Decided (plan updates):**
  - Fixture-slice strategy: unit tests run against a small extracted `usc16_slice.xml`; the 32 MB file becomes a `@pytest.mark.slow` integration test asserting known-good counts. Default `make test` stays fast (PLAN Day 1 item 2; CLAUDE.md status).
  - Secondary indexes specified up front (guid_map(release_id, identifier); section_release_map(release_id); section_versions(section_id, first_release_id)) — added to PLAN §3, scheduled for the ingest-session migration, before guid_map grows to tens of millions of rows.
  - Session 3 rescoped from "schema + ingest" to "clear debts + indexes + ingest" (schema landed early).
  - Parallel tracks declared unblocked: parser / reader-UI-on-fixtures / downloader port are mutually independent (PLAN Progress note; GETTING-STARTED §10).
  - At Ari's request, `.claude/settings.json` rewritten for **autonomous sessions**: `defaultMode: acceptEdits`; allowlist covering the full build toolchain (uv/make/pytest/alembic upgrade/docker compose/git incl. push/curl/psql/file utils; WebFetch limited to uscode.house.gov, GitHub, core library docs); `ask` retained for `alembic downgrade`, `docker compose down`, volume removal, uninstalls; `deny` on sudo, out-of-repo `rm -rf`, force-push, `git reset --hard`, `git clean`, and reading `.env`. Safety rests on git recoverability + denied history-rewriting + repo-scoped blast radius (GETTING-STARTED §7a). Revisit `git push` auto-allow if/when the GitHub PR-review Action becomes the merge gate.
- **Produced:** Edits to PLAN.md (progress block, fixture strategy, index spec), GETTING-STARTED.md (Sessions 2/3 prompts, §10), CLAUDE.md (status + test-speed rule), this entry.
- **Verified:** Git history 47744ec..71ccaa8 reviewed commit-by-commit; models/tests/compose/Makefile read in full; `.claude/settings.json` audited. Re-check: `git log --oneline` and diff of this commit.

## 004 — 2026-07-27 — Day 1 item 2: the USLM parser layer

- **Tool/model:** Claude Code, Opus 5 (PLAN §7 assigns the parser to the main Opus session — USLM edge cases are the hardest code in the build).
- **Asked:** Execute PLAN.md Day 1 item 2 — `UslmParser` protocol, `detect_uslm_version()` (derive the rule from the samples, record it in an ADR), `Uslm1Parser` as a streaming `lxml.iterparse` implementation emitting normalized `SectionRecord`s, and a `Uslm2Parser` stub passing detection + basic section extraction. Script-extract `tests/fixtures/usc16_slice.xml` first and unit-test against it; the 32 MB file becomes a `@pytest.mark.slow` integration test. Default `make test` stays under a few seconds.
- **Decided:**
  - **Detection is by root namespace URI, nothing else** ([ADR-0004](docs/adr/0004-uslm-version-detection-by-namespace.md)): `http://xml.house.gov/schemas/uslm/1.0` → 1.x, `http://schemas.gpo.gov/xml/uslm` → 2.x. The namespace changed host *and* path across generations, so it is total and unambiguous. `xsi:schemaLocation` is read only to label the point version (`uslm-1.0.15`, `uslm-2.0.12`) — it is optional in XML, formatted differently in OLRC's own 2.x samples, and finer-grained than the parser boundary. An unknown namespace raises rather than guesses.
  - **`<section>` inside `<quotedContent>` is not a section** ([ADR-0005](docs/adr/0005-what-counts-as-a-section.md)) — and this **corrects the Title 16 counts carried since BUILDLOG 001**: 298 of the 5,393 `<section>` elements are statutory text quoted by amending acts, with no `@identifier` and no `@id`. Real code sections: **5,095**, with **522** repealed (one quoted section is marked repealed), 102 omitted, 19 transferred. The file's single `reserved` is on a **`<subchapter>`** (`/us/usc/t16/ch1/schXCVII`), not a section — section status counts total 643, never 644. Both the raw and emitted counts are now asserted, so the arithmetic between them is checked rather than assumed.
  - Skipped quoted sections are **not** cleared from the tree: their `end` event fires before the enclosing real section's, and the enclosing section's XML must be stored verbatim.
  - Shared streaming traversal (`StreamingSectionParser`) that **knows no element names of its own** — each parser supplies an `ElementNames` vocabulary and its own `<meta>` reader. This keeps CLAUDE.md architecture rule 2 true by construction while avoiding a duplicated `iterparse` prune loop; the documented 1.x→2.x differences (TOC, tables, indent model) are all outside section extraction and will land as `Uslm2Parser` overrides on Day 7.
  - **Every `@id` in a section is indexed, not just the section's own** (63,376 ids vs 5,095 sections in Title 16). Elements like `<p>` have an `@id` but no `@identifier`, so a `GuidRef` inherits the nearest enclosing identifier — `?id=` then resolves any guid in the corpus to a retrievable provision, which is what PLAN §3's global `guid_map` promises.
  - `@status` stays a free string, never an enum: USLM 2.x Title 49 carries `renumbered`, which Title 16 never shows. `@temporalId` is **absent from USLM 1.0.15 output entirely** (zero occurrences in 32 MB) — recorded, not worked around.
  - `SectionRecord` carries `ancestors` (level, identifier) beyond PLAN's field list, so the TOC/breadcrumb pass doesn't need a second traversal. Headings are deliberately not captured there: streaming prunes sibling `<num>`/`<heading>` nodes before later sections are reached.
  - Fixture is a **verbatim** slice — `scripts/extract_fixture.py` only drops unselected siblings and truncates `<toc>` bodies; every retained element is byte-identical to OLRC's output, so fixture-based assertions are assertions about real data.
- **Produced:** `ingest/{records,detect,base,uslm1,uslm2,parser,__init__}.py`; `scripts/extract_fixture.py` + `tests/fixtures/usc16_slice.xml` (878 KB); `tests/{conftest,test_uslm_detect,test_uslm1_parser,test_uslm2_parser,test_uslm_full_corpus}.py`; `docs/adr/0004`, `docs/adr/0005`; `slow` marker + `addopts` in `pyproject.toml`; `make test-slow` / `test-all` / `fixtures`; CLAUDE.md, PLAN.md, ADR-0002 updated with the locked detection rule and corrected counts.
- **Verified:**
  - `make test` — 35 passed in **0.87 s** (10 slow tests deselected). The default path parses only the 878 KB slice.
  - `make test-slow` — 10 passed in ~4 s: Title 16 emits 5,095 sections with contiguous `seq` and unique identifiers; status counts 522/102/19; raw-vs-emitted arithmetic (5,393 − 298 = 5,095; 523 raw repealed) checked directly against the source XML; every one of the 62,583 guids indexed exactly once.
  - Known-good assertion `id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd` ↔ `/us/usc/t16/s45f/c/5` holds against **both** the slice and the full 32 MB file, and the section's stored XML re-parses so the provision is XPath-extractable at request time (the ADR-0001 read path).
  - Streaming is memory-bounded, measured in a clean subprocess: **43 MB peak RSS** for the 32 MB file vs **274 MB** for `etree.parse()` of the same file; the test fails above 150 MB (gotcha 6 — Title 42 is multiples of this).
  - USLM 2.x samples parse: usc01 39 sections, usc16 5,028 (520/102/19), usc49 1,350 (43 repealed / 9 `renumbered`). Cross-schema parity on `/us/usc/t16/s45f`: same identifier, `num_value` and heading across 1.0.15 and 2.0.12; different guid, as ADR-0003 requires.
  - Re-check any of this: `make test-all`, and `uv run python scripts/extract_fixture.py` to confirm the committed fixture is reproducible from `samples/uslm1/usc16.xml`.
  - Not done (deliberate, Day 7): `Uslm2Parser` has no TOC, table, indent-model or MathML handling. Carried debts from BUILDLOG 002 (`alembic downgrade base`, `docker compose up --build`) remain untouched.

## 005 — 2026-07-28 — Day 1 item 3: ingest into Postgres, cleared debts

- **Tool/model:** Claude Code, Sonnet 5.
- **Asked:** Clear the BUILDLOG 002 debts (`alembic downgrade base && upgrade head`; `docker compose up --build` end-to-end), fixing anything broken; add PLAN §3's secondary indexes as a migration; implement `python -m ingest load <xmlfile> --release <label>` with content-hash dedupe, `guid_map` population, `seq_in_title`, and a PLAN §11.4 provenance manifest; load Title 16 @ 119-102not101 and verify counts.
- **Decided:**
  - Both carried debts turned out to be **not code bugs**: the alembic round-trip and the containerized stack both worked on the first try. The only failure was an unrelated host process (`python -m http.server 8000`, running since the day before) squatting on port 8000; killed with Ari's confirmation, then `docker compose up --build` succeeded end-to-end (build, healthcheck, api↔db connectivity, `/health`, `/docs`).
  - **Dedupe key is `(section_id, content_hash)`, looked up before insert.** If a section's content already has a `SectionVersion` row (any prior release), the new release only gets a `section_release_map` row pointing at the existing version — no new `section_versions` row, `first_release_id` untouched. Verified mechanically: re-ingesting the same file under the same release dedupes 100% (0 new / 158 deduped); ingesting identical content under a second release label also dedupes (0 new / 158 deduped) while adding the expected second set of `section_release_map` rows.
  - **`guid_map` is upserted (`ON CONFLICT (guid) DO UPDATE`), not inserted.** Guids are globally unique *by design* in real data (ADR-0003), so this only matters for idempotent re-runs of the same release — but makes reruns safe rather than assuming they never happen.
  - **Source USLM files carry no currency date at all** (confirmed: no date-shaped attribute anywhere in `usc16.xml`'s `<meta>` or root). `--currency-date` is a required CLI flag the *first* time a `--release` label is ingested (a `MissingCurrencyDateError` otherwise); later runs against the same release, or additional titles under it, don't need it. This is a stopgap until the Day 2 RP-inventory downloader (`uscreleasepoints.json`, PLAN §1) supplies real dates — noted as an open debt rather than solved here.
  - **`release_points.seq` is assigned sequentially on first sight of a label** (`max(seq)+1`), also a stopgap: correct within what this command has ingested so far, but not the true cross-RP ordering PLAN §3 specifies (RP labels don't sort lexically — gotcha 4). The real ordering needs the Day 2 RP inventory; scoped as future work, not silently declared done.
  - `count_section_elements` added to `StreamingSectionParser` (and the `UslmParser` protocol) as a second, cheap streaming pass — counts every `<section>` including quoted ones, for the manifest's raw-vs-real comparison. Kept separate from `iter_sections` rather than threading a side-channel counter through the generator, at the cost of parsing the file twice; acceptable at Title-16 scale (32 MB, ~28 s total including all DB writes) and revisit if a Title-42-sized file makes it worth avoiding.
  - Manifests are **one file per release, accumulating titles** (`data/manifests/{release}.json`, `titles.{num}` keyed) rather than one file per title, since a release is what a real ingest run is scoped to (PLAN's `titlesAffected` per RP) and PLAN §11.4 names the file per-release.
- **Produced:** `alembic/versions/aef3da4cc2e9_secondary_indexes_for_guid_map_section_.py`; `ingest/{release_label,load,manifest,__main__}.py`; `ingest/base.py` (`count_section_elements`); `tests/{test_release_label,test_ingest_manifest}.py` + a `count_section_elements` test in `test_uslm1_parser.py`; `data/manifests/119-102not101.json`; CLAUDE.md/PLAN.md status and Commands updates.
- **Verified:**
  - `uv run alembic downgrade base && uv run alembic upgrade head` — clean both directions, before and after the new index migration; confirmed with `psql \dt`/`\di` against the running `db` container.
  - `docker compose up --build` — full stack up (`db` healthy, `api` built and started); `GET /health` → `{"status":"ok"}`, `GET /docs` → 200, and the `api` container's own SQLAlchemy engine reaches `db` (`select 1`) — all via `docker compose exec`/`curl` against the running containers, not just log-reading.
  - `uv run pytest` — 46 passed in 0.84 s (still no live DB, still never touches the 32 MB sample).
  - `python -m ingest load samples/uslm1/usc16.xml --release 119-102not101 --currency-date 2026-07-12` — **5,095 sections stored, 0 deduped (first load); raw `<section>` elements: 5,393; status counts 522/102/19** — matches ADR-0005 exactly, not the uncorrected 5,393/523/102/19/1 in earlier framing (that count includes 298 quoted, non-section elements and a subchapter-level `reserved`, per CLAUDE.md's own gotcha 12/ADR-0005 — flagged to Ari rather than silently ingesting the wrong number). Cross-checked directly against Postgres: `sections`/`section_versions` row counts for title 16 both 5,095; known-good `id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd` ↔ `/us/usc/t16/s45f/c/5` present in `guid_map`; `release_points` row shows congress 119, law_num 102, excluded_laws `{101}`, currency_date 2026-07-12.
  - Re-check any of this: `uv run alembic downgrade base && uv run alembic upgrade head`; `docker compose up --build` then `curl localhost:8000/health`; `uv run python -m ingest load samples/uslm1/usc16.xml --release 119-102not101 --currency-date 2026-07-12` (idempotent — reruns dedupe to 0 new); `cat data/manifests/119-102not101.json`.
  - Not done: resolver/API routes (PLAN Day 1 item 4). `Uslm2Parser` TOC/table/indent parity remains Day 7.
- **Reviewed afterwards (same session, Opus 5), and the plans changed as a result.** Asked to review the session's output and update the plan for the next one. Checking what Sessions 4–5 *assume* against what now actually exists in the database turned up three gaps, none of them visible from the ingest work alone:
  1. **Only one release point is loaded.** PLAN Day 1 item 3 asks for two ("current RP + one prior RP") and the §10 demo needs two for the release picker to have anything to flip between; the session's prompt only asked for the current one, so item 3 is half done, not done. The prior RP's XML isn't in `samples/` — it must be downloaded. Sharper point: it should be chosen from the RP inventory's `titlesAffected`, because most RPs don't change most titles, so an arbitrary neighbour like 119-94 may be byte-identical for Title 16 — dedupe would behave correctly and the demo would show two identical texts.
  2. **Nothing stores the title's hierarchy** — new PLAN Day 1 item 3a and a `structure_nodes` table in §3. Ingest persists sections only and drops `SectionRecord.ancestors`; no table holds a chapter's name, so §4's TOC routes and the item-5 TOC page have no data source. Recommended (and checked against the fixture before recommending): read headings off **structural elements** (`<chapter><num>/<heading>`), not the `<toc>` element — structure markup is near-identical across USLM 1.x/2.x while `<toc>` is one of the three things OLRC actually changed in 2.x, and `tests/fixtures/usc16_slice.xml` keeps structure headings intact while truncating `<toc>` to 5 items, so the structural route is unit-testable today and the `<toc>` route is not. Streaming caveat noted: `end` events on `<chapter>` would buffer a whole chapter, violating gotcha 5.
  3. **`release_points.seq`/`currency_date` stopgaps block `?date=`.** Item 4's resolver rests on both, so RP-inventory seeding moves from Day 2 to a Day 1 prerequisite — which is also what supplies the `titlesAffected` that gap 1 needs. Session 1.5 (prior-art read) was never run and is a prerequisite for that port; neither reference repo is cloned.
- **Also corrected:** GETTING-STARTED's Session 2 and 3 prompts both carried the pre-ADR-0005 counts (5,393; 523/102/19/1). That is what sent this session looking for the wrong number in the first place, so the prompts are fixed in place with a note that ADR-0005 supersedes them, and §7a gained a line on what to do when a prompt contradicts the repo's own decisions.
- **Produced (review):** new Session 3.5 (RP inventory + TOC pass) and a revised Session 4 in GETTING-STARTED §7, plus updates to §7a/§10 and the Session 1.5/6 notes; PLAN §3 `structure_nodes`, Day 1 items 3/3a/4, §6 Day 2, and the progress block; CLAUDE.md status/debts. No code changed.

## 006 — 2026-07-27 — Sessions 3.5 + 4: RP inventory, hierarchy, the Repository, and the API

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Session 4 — "Implement the FastAPI app per PLAN.md §4: identifier routes with ?release/?date/?format, the guid lookup route, TOC, neighbors, versions, releases. Resolver algorithm per PLAN §3. Repository interface only — no SQL in handlers. Integration tests against the loaded Title 16."
- **Scope call, made before starting:** the repo's own docs (GETTING-STARTED §7, PLAN Day 1 items 3/3a) say Session 4 is blocked on Session 3.5 — no hierarchy storage means the TOC routes have no data source, and one release point means `?release`/`?date` can't be exercised. Ari chose "full 3.5 then Session 4", so this entry covers both.
- **Decided:**
  - **The dedupe shipped in BUILDLOG 005 deduped nothing, and only real data could show it (ADR-0007).** Hashing raw section XML is defeated by ADR-0003's own rule: guids are regenerated at every release point *by design*, so an untouched section's XML differs at every one of the ~324 of them. Measured across 119-99 and 119-102not101: **0 of 5,095** sections had identical raw XML; **5,093** were identical once `@id` was stripped; **2** had really been amended. The BUILDLOG 005 verification passed because it re-loaded the *same file* under a second label, where guids are identical by construction. Sections are now hashed over `SectionRecord.content_key` — the XML with `@id` removed — and `xml` is still stored verbatim. Cost, recorded rather than hidden: a deduped fragment carries the guids of the release point its text first appeared at; `guid_map` still resolves every guid of every release point, and responses say which release the bytes came from.
  - **Reading order and parenthood moved off `section_versions` onto `section_release_map` (ADR-0008).** Both are facts about (section, release point), not about the text: a section keeps its words while its neighbours are repealed, and a transferred section can change chapter without a character moving. On a content-deduped row they freeze at the release the text first appeared in — invisible with these two release points (nothing moved between them), silently wrong across a 324-release-point backfill.
  - **The TOC is read from structural elements, never from `<toc>` (ADR-0006).** `<toc>` is one of the three things OLRC actually changed in USLM 2.x; structural markup is near-identical. Verified rather than assumed: one pass yields 569 nodes for USLM 1.x Title 16 and 203 for USLM 2.x Title 49, including the `subtitle` level Title 16 has no instance of. Streaming detail (gotcha 6): frames open at `start`, fill from `<num>`/`<heading>` `end` events, close at `end` — waiting for a `<chapter>`'s own `end` would buffer a whole chapter.
  - **Release-point labels have a third form.** 17 of the 385 published release points carry a `u1` update suffix (`118-22u1`, `116-344not283u1`), and `118-22` exists separately, so `(congress, law_num, excluded_laws)` neither identifies nor orders a release point. `parse_label` returns `update_num`; `release_points` stores it.
  - **A request can name a release point that was never ingested, and the honest answer is not 404.** 119-100 is real, published, and changed only title 47 — Title 16's text there *is* its text at 119-99. Results therefore carry three release points: `release` (asked for), `served_from` (newest ingested at or before it carrying this title), `content_first_seen` (whose bytes are stored). Answering is right; answering silently would not be.
  - **`titles_affected` (what OLRC says a release point changed) is kept distinct from `ingested_titles` (what this database holds).** Conflating them would make an incomplete backfill look like a missing law.
  - `?date` accepts `07/12/2026` as well as `2026-07-12` — the first is what uscode.house.gov prints and what PLAN §10's demo URL uses.
  - Session ownership sits in `storage.get_repository`, so `api/` holds no database session at all. This was not the original design; the architecture test below caught the leak.
- **Produced:** 7 commits, `037225e..e71ac36`.
  - Ingest: `ingest/inventory.py` (the release-point inventory, in loadusc-xcitedb's `{name, date, titlesAffected, url}` shape), `ingest/download.py` (polite single-title download), `ingest/base.py` `iter_structure` + `_content_key`, `ingest/release_label.py` `u1` support, `python -m ingest {inventory,fetch,load}`.
  - Storage: `storage/{repository,postgres,session}.py` — the protocol, the only SQL in the project, and the FastAPI dependency.
  - API: `api/{routes,schemas,deps,render}.py`.
  - Schema: migrations `eab62d9362f4` (update_num), `1a045cde2094` (structure_nodes, parent_identifier), `9b1ce4ea7ddf` (per-release facts move, with data migration), `111ae2b5d127` (titles_affected).
  - Docs: ADR-0006, ADR-0007, ADR-0008; `make dev-data`.
  - Tests: `tests/test_{inventory,structure_pass,content_key,api,render,architecture}.py` — 125 passing, plus 13 slow.
- **Verified:**
  - `make test` — 125 passed in 1.6 s (35 of them API integration tests against the live database, skipping cleanly when it isn't loaded). `make test-slow` — 13 passed in 6 s.
  - Inventory: 382 release points seeded from uscode.house.gov, `113-21` (2013-07-18) through `119-102not101` (2026-07-12), each with a real `currency_date` and a global `seq` taken from page order — the page is strictly newest-first across all 385 `<li>` entries, which labels and dates are not. Re-check: `uv run python -m ingest inventory`, then `psql -c "select label,currency_date,seq,titles_affected from release_points order by seq desc limit 5"`.
  - Second release point chosen the way PLAN Day 1 item 3 insists — via `titlesAffected`, not by picking a neighbour: 119-99 is the newest prior release point that changed Title 16, and 119-100 sits between them changing only title 47. Downloaded `xml_usc16@119-99.zip` (5,386,575 bytes, sha256 `1449e230…1383`) at ~1 req/sec with a descriptive UA; hashes are in `data/manifests/119-99.json`.
  - Dedupe on real data: 119-99 → 5,095 new; 119-102not101 → **2 new, 5,093 deduped**, the two being `/us/usc/t16/s2201` and `/us/usc/t16/s2206` (Emergency Conservation Program and Emergency Forest Restoration Program). `section_versions` 32 MB → 16 MB. Re-loading either release point is idempotent (0 new, 5,095 deduped).
  - Database now holds: 382 release_points, 5,097 section_versions, 10,190 section_release_map rows, 569 structure_nodes, 125,410 guid_map rows.
  - Structure pass: 569 nodes for Title 16 (1 title / 153 chapters / 345 subchapters / 57 parts / 13 subparts), matching a raw `findall` count over the same file; peak RSS 35 MB on the 32 MB file.
  - PLAN §10's demo URL works end to end through the containerized stack: `curl "http://localhost:8000/us/usc/t16/s45f/c/5?date=07/12/2026"` returns §45f with `(c)(5)` extracted and anchored, `ETag` set to the content hash, and `X-Release-Point: 119-102not101` / `X-Served-From: 119-99` when asked for an un-ingested release point.
  - Architecture is tested, not trusted: `api/` imports no `db.models` and no SQLAlchemy, `storage/` never imports `api/`, the protocol and the Postgres implementation agree, and USLM element names stay out of extraction code outside the parsers. That last pair of tests both failed when first written and both were real — a stray session type annotation in `api/deps.py`, and `quotedContent` in the renderer's tag map (kept, narrowly and deliberately: presentation must know element names, and unknown ones degrade to a `<div>`, which has its own test).
  - Not done: the reader UI (Session 5) — `?format=html` renders a readable page and a TOC page, but it is the demo minimum, not the reader. Only Title 16 is loaded, at 2 of 382 release points. `Uslm2Parser` table/indent parity remains Day 7. `make verify` is still a stub.

## 007 — 2026-07-28 — Session 5: the reader

- **Tool/model:** Claude Code, Opus 5. (PLAN §7 assigns the reader UI to Sonnet 5; run on Opus because the session also carried the negotiation bug below, which is a semantics question, not UI iteration.)
- **Asked:** "Build the minimal reader per PLAN.md Day 1 item 5: TOC page, section page with provision anchor highlighting, prev/next, release picker, status badges. Server-rendered Jinja is fine. Make `/us/usc/t16/s45f/c/5?date=07/12/2026` demonstrable end to end." Mid-session: install the official FastAPI skill.
- **Decided:**
  - **The reader lives at the same URLs as the API, chosen by `Accept:`/`?format=` (ADR-0009).** The alternative — a `/read/…` prefix, or an SPA against the JSON API — would give `16 USC 45f(c)(5)` two web addresses, one for people and one for programs, in a project whose entire claim is that a citation *is* a URL. So `api/routes.py` negotiates and hands the HTML case to `web/reader.py`; `/api/v1/…` stays machine-only; `/` is the reader's own route.
  - **Server-rendered Jinja, one stylesheet, no build step.** The only JavaScript in the reader scrolls the highlighted provision into view; the release picker is a GET form, so it works with scripting off and leaves a URL you can paste. This also keeps `web/` on the `Repository` interface rather than on a second, JSON-shaped copy of it — the reader calls the same methods the API does, so the XCiteDB swap moves both at once.
  - **`api/render.py` → `web/uslm_html.py`.** Presentation is one layer now; the architecture test's "the renderer is the one place outside the parsers that may know USLM element names" exception moved with it, rather than being quietly widened.
  - **Links carry `?release=`, even when the request arrived as `?date=`.** The date is resolved once, to one release point; repeating the label thereafter keeps every link on the page unambiguous and pasteable, and stops a reader from drifting between release points while browsing.
  - **The release picker offers the release points a title is *ingested* at, not all 382.** `titles_affected` says where a title changed; `ingested_titles` says what this database holds. Offering the first would be offering 380 empty answers until the backfill (Session 6).
  - Three facts the pages must never drop, each of which a naive reader loses: the `not`-law caveat (gotcha 5), the served-from note when the requested release point was never ingested (gotcha 10), and status badges in TOCs and prev/next (gotcha 9). All three have tests that fail if they disappear.
- **Found, and it is the session's real finding: every browser was getting raw XML at the demo URL.** `negotiated_format` tested `"application/xml" in accept`, and Chrome sends `text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8` — so `?format=html` had been silently covering for a broken `Accept:` path since Session 4, in every test we had. It surfaced only from screenshotting the demo URL in a headless browser, which returned the XML tree view. The header now parses q-values (highest wins, ties to the client's order, unknown types fall back to JSON) with a test table built from the header Chrome actually sends. **Lesson worth carrying:** an `Accept:` header written by hand in a test is not the header a browser sends, and "it works with `?format=html`" is not evidence that content negotiation works.
- **Produced:** 5 commits, `1558bdb..` (this entry).
  - `web/reader.py` (repository results → pages), `web/templates/{base,section,toc,home,error}.html`, `web/static/reader.css`, `web/routes.py` (`/`), `web/uslm_html.py` (moved).
  - `api/deps.py` q-value negotiation; `api/routes.py` HTML delegation + `Vary: Accept`; `api/main.py` reader router, `app.frontend("/static", …)`, and an HTTP-exception handler that renders 404/409 as pages when HTML was asked for.
  - `docs/adr/0009-one-url-per-provision-negotiated-by-accept.md`; jinja2 dependency.
  - Tests: `tests/test_reader.py` (18 unit + 7 integration), `tests/test_negotiation.py` (13).
- **Verified:**
  - `make test` — **162 passed** in 2.1 s (was 125), 13 slow deselected. The reader's unit tests run against a stub `Repository` built from `storage`'s frozen dataclasses and touch no database: if one of them ever needs Postgres, the boundary has leaked.
  - PLAN §10's Day-1 demo, in a browser, through the containerized stack: `/us/usc/t16/s45f/c/5?date=07/12/2026` renders §45f with **(c)(5) highlighted and scrolled to**, breadcrumbs `Title 16 / CHAPTER 1 / SUBCHAPTER VI`, the caveat "Current through Public Law 119-102 (07/12/2026), except 119-101", the guid citation, prev/next to §45e and §45g, and a release picker holding 119-102not101 and 119-99. Screenshotted headlessly to confirm — the same command anyone can re-run:
    ```
    docker compose up -d --build
    open "http://localhost:8000/us/usc/t16/s45f/c/5?date=07/12/2026"
    ```
  - Release flip checked on `/us/usc/t16/s2201` — one of the two sections that actually differ between the two release points — and the pages differ, so the picker is switching content and not just labels.
  - `docker compose up --build` rebuilt after the jinja2 dependency was added; `/`, `/static/reader.css`, the demo URL and a 404 page all served from the container, not just from `TestClient`.
  - Not done: no keyboard navigation, no notes/sourceCredit toggles, no version timeline UI or diffs (all Day 4); dark mode is written but was not verified in a browser; USLM `<heading>` still renders as `<h2>` at every depth, so the heading outline is flat (accessibility pass, Day 7); breadcrumbs for a section cost an extra `get_toc` call on its parent (performance, Day 6). Still only Title 16, at 2 of 382 release points — Session 6.
- **Also:** installed the official FastAPI skill (`fastapi/fastapi@fastapi`) at Ari's request and applied it to this session's code — `Annotated` dependencies (already the case), `HTMLResponse` with `response_class` instead of hand-set media types, and `app.frontend()` in place of a manual `StaticFiles` mount.

## 008 — 2026-07-28 — Session 5 UI review; Session 7 (interface overhaul) specified

- **Tool/model:** Claude (Cowork), Fable 5 — independent reviewer, fresh context. Review of `web/` templates/CSS/renderer by reading, not rendering (review sandbox cannot run the stack).
- **Asked:** Review the post-Session-5 application with attention to interface and navigation; update Session 6+ tasks to add citation hover text, fix the section title, add a site navbar, put navigation top and bottom, and make the site mobile-first.
- **Findings:**
  - **Live bug: every section page ships broken links.** `web/uslm_html.py` copies `<ref href>` through verbatim, so source credits emit relative links to `/us/pl/111/24/tV/s512`, `/us/stat/123/1764` — paths this site does not serve. Also: internal `/us/usc/` refs drop the page's release context, and no ref anywhere has hover text.
  - Section `<h1>` splits `§ 45f.` into a small muted block label above the heading (`h1 .num { display: block }`) — not how the Code prints a section title; user asked for the fix directly.
  - No site menu exists; brand + breadcrumbs + release picker share one wrapping topbar row. Navigation appears only at the bottom (neighbors block); no footer.
  - CSS is desktop-default, not mobile-first: fixed `indent1–4` margins up to 6.4rem (a deep provision on a 360px phone keeps ~40% of the screen for text), `.toc .num` reserves 5.5rem, sub-16px form controls trigger iOS zoom. Viewport meta is present.
  - Worth keeping, explicitly: no build step, one stylesheet, single JS line, GET-form picker, badge/caveat/served-from tests, dark-mode variables (still unverified in a browser — noted in 007).
- **Decided:**
  - New **Session 7 — reader interface overhaul** (Sonnet, worktree), parallel to Session 6 — disjoint code (`web/` vs `ingest/`). Six-part spec in GETTING-STARTED §7 and PLAN Day 2–3: mobile-first restyle with an `--indent-step` variable; site navbar + contextual bar + skip link; one-line section title; top strip + bottom neighbors + footer; ref fix (internal refs get `?release=` + batched `title=` hover text, one repository query per page; `/us/pl/`+`/us/stat/` map to the govinfo link service or degrade to spans, never a local 404) with tests including "no rendered page contains a relative `/us/pl/` href".
  - Day 4 polish (keyboard nav, toggles, timeline, diffs) now explicitly builds on Session 7's layout, so Session 7 precedes it.
  - `.claude/settings.json`: govinfo.gov/congress.gov added to the WebFetch allowlist so Session 7 can verify link-service URL patterns before hard-coding them.
- **Produced:** Edits to PLAN.md (progress note; Day 2–3 parallel-track spec; Day 4 rebased), GETTING-STARTED.md (Session 7 prompt; §10 parallel tracks), CLAUDE.md (status), `.claude/settings.json`, this entry.
- **Verified:** Review grounded in file reads of `web/templates/*.html`, `web/static/reader.css`, `web/uslm_html.py`, `web/reader.py` at `6b1b0b5`; the `/us/pl/` claim re-checkable in one line: `grep -n 'href' web/uslm_html.py` (no scheme/host handling) plus any section page's source credit.

## 009 — 2026-07-28 — Reader/API separation (ADR-0010); frontend framework determination (ADR-0011)

- **Tool/model:** Claude (Cowork), Fable 5.
- **Asked:** (1) Separate the API and the reader, serving the application at something like `/app/us/usc`, for robustness. (2) Research UI frameworks and determine whether a TS/JS framework would ensure accessibility and allow flexible future feature-building.
- **Decided:**
  - **ADR-0010 (accepted — Ari's direction):** reader → `/app/us/usc/…` (always HTML), API → `/api/v1/us/usc/…` (machine-only, no Jinja under `api/`), and the bare citation URL `/us/usc/…` stays alive as a thin 307 redirector by `Accept:` (`?format=` wins, query preserved, `Vary: Accept`). This *amends* ADR-0009 rather than reversing it: "a citation is one URL" survives; the single-handler mechanism is what goes. The rejected alternative — bare URL serving JSON only — would dump JSON on anyone pasting a cited URL into a browser.
  - **ADR-0011 (proposed):** the `/app` frontend becomes **Astro 5 + TypeScript styled with USWDS**, consuming `/api/v1` only. Deciding factors (full comparison in `docs/research/2026-07-ui-framework.md`): Astro ships zero client JS by default, so statutory text stays server-rendered HTML — the founding principle survives the framework; islands hydrate only the components that need it (diff viewer, timeline, watchlist to come), and islands may be React or Svelte later without re-platforming; USWDS is the federal government's own WCAG 2.1 AA / Section 508 design system, framework-agnostic CSS, and the natural visual language for the US Code. Runner-up SvelteKit (compiler a11y warnings, but one component model for the whole page); Next.js only if the React ecosystem becomes necessary; htmx bridge rejected as a dead end before the planned features. **Consciously traded away:** the "no build step" principle, for `/app` only — a Node build/runtime joins the stack; the API keeps zero frontend dependencies.
  - Session 7 restructured into **Part A** (separation in the existing codebase — a complete, shippable checkpoint: negotiation tests become redirect tests; new architecture test that `api/` imports no Jinja) and **Part B** (Astro/USWDS reader implementing the BUILDLOG 008 spec as the parity bar; Jinja retires only when all six items pass). Opus plan first (new service topology), Sonnet implements.
- **Produced:** `docs/adr/0010-…`, `docs/adr/0011-…`, `docs/research/2026-07-ui-framework.md`; PLAN.md (progress note, §8 Node requirement), GETTING-STARTED.md (Session 7 two-part prompt), CLAUDE.md (architecture rule 5 rewritten to target state, marked *not yet implemented*), this entry.
- **Verified:** Nothing implemented this session — decisions only. Framework claims grounded in 2026 comparison guides and USWDS/Section 508 documentation (links in the research doc); USWDS's framework-agnostic HTML+CSS nature and `react-uswds`'s version-pinning caveat confirmed against its docs. Re-check: read the research doc's sources.

## 010 — 2026-07-28 — Prior art; Session 6: the resumable bulk downloader (ADR-0012)

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** (1) Read `../loadusc-xcitedb` and `../versions` and write `docs/prior-art.md` — what each does, what we reuse directly, what we deliberately do differently, citing specific files. (2) Session 6: port the release-point downloader into `ingest/` as a modern, resumable tool (Python 3.12, checksum cache, ~1 req/sec, descriptive User-Agent), building on the Session 3.5 inventory; drive it from `titlesAffected` per RP; use hash-dedupe as the verification step; record reused-vs-changed in an ADR.
- **Decided:**
  - **`docs/prior-art.md`** — both repos read at pinned commits (`loadusc-xcitedb` @ `d16f1ee`, `versions` @ `c937641`). Beyond the obvious reuse, three things there are worth more than they look: `data/document.conf` is the authority behind our `@identifier` short forms (`t`/`ch`/`sch`/`s`/`nt`, and **empty** for subsection and below, which is why `/us/usc/t16/s45f/c/5` has a bare `c/5`); `getxcite.py` is the de facto spec for the future XCiteDB `Repository` (including that identifiers are stored **en-dashed**, and that `versions()` needs two queries — `-match-start` for descendants plus `-match` for the node itself); and the `versions` demo's `Diff_Timeout: 0` is load-bearing, since diff-match-patch silently returns a *worse* diff on timeout.
  - **ADR-0012 — backfill driven by `titlesAffected`, verified by hash-dedupe.** Transport (`ingest/download.py`) split from orchestration (`ingest/backfill.py`). `fetch_zip` streams to a `.part` file, hashes on the way through, validates with `is_zipfile`, and **returns a result rather than raising** — "no such title at this RP" is an answer to record, not an error that aborts a 3,200-file run.
  - **Three outcomes, not two:** `ok` / `unavailable` (the server answered; there is no such file) / `failed` (transport, retries exhausted). Only `unavailable` says anything about what OLRC publishes; only `failed` is retried freely. Collapsing them either re-asks 3,000 settled questions per run or abandons a title over one reset connection.
  - **The ledger is a cache; the disk is the truth.** A zip on disk with no ledger entry is re-hashed and adopted, so a lost or corrupted ledger costs a hashing pass, not a re-download of tens of gigabytes.
  - **The oldest RP is fetched in full** as the baseline — `titlesAffected` is a delta and a delta needs something to apply to. This is exactly what makes gotcha 10's retrieval rule true. The original intended this but read `url`/`dir_name` from leftover loop variables pointing at different RPs, filing the oldest RP's files in the wrong directory.
  - **No silent `u1` fallback.** The original, failing on `…u1.zip`, retries without `u1` and stores another release point's content under the `u1` label. Both labels are separate inventory rows here, so the fallback isn't merely risky, it's wrong; we record `unavailable` and let the retrieval rule degrade. **TLS verification stays on** (the original disables it for this host globally).
  - **Hash-dedupe is verification, not storage.** These zips never collapse (guids regenerate, zip members carry timestamps). What identical bytes across two different `(release, title)` pairs prove: same title at two RPs = OLRC republished it unchanged (reported — also the `u1` substitution signature); two *different* titles sharing a zip = URL construction collapsed two addresses (**fails** the report).
- **Produced:** `docs/prior-art.md`; `docs/adr/0012-resumable-backfill-driven-by-titles-affected.md`; `ingest/backfill.py` (ledger, planner, runner, verification); `ingest/download.py` rewritten around `fetch_zip`; `python -m ingest backfill` and `verify-downloads`; `tests/test_backfill.py` (31 tests); CLAUDE.md (Commands, status), this entry.
- **Verified:**
  - `make test` — **193 passed** (was 162), 13 deselected. Nothing in the suite touches the network: `fetch_zip` takes an `opener`, and the tests serve zips built in-process, so the real streaming, hashing, validation, retry and backoff paths run against a fake transport rather than being mocked.
  - Plan against the real 382-RP inventory: **3,197 downloads vs 22,156** for a naive full crawl (85.6% less). Re-check: `uv run python -m ingest backfill --plan-only | head`. Baseline title set derives from the data as 58 — the 53 numbered titles that exist (no Title 53) plus the five appendices `05a`/`11a`/`18a`/`28a`/`50a` (gotcha 7).
  - **Live trial** against uscode.house.gov: 4 real Title 16 zips fetched (113-21, 113-31, 113-36, 113-44; ~4.7 MB each) at ~1 req/sec. Re-run skipped them with zero requests; `119-99/16`, downloaded in an earlier session and absent from the ledger, was **adopted** by re-hashing with zero requests.
  - `uv run python -m ingest verify-downloads --deep` — 5 entries, 5 ok, 5 distinct hashes, no duplicates, sound. (Also confirms gotcha 1 at the zip level: Title 16 at 5 different RPs is 5 distinct files.)
  - Resumability, ledger adoption, the 404/HTML-error-page/backoff paths, and both duplicate classes are each covered by a named test in `tests/test_backfill.py`.
  - **Not done:** the backfill has not been run to completion — that is an unattended multi-hour run, and loading what it fetches is Day 2-3.

## 011 — 2026-07-28 — Status sync; Session 8 (bulk load) specified

- **Tool/model:** Claude (Cowork), Fable 5.
- **Asked:** Check status, update PLAN.md and GETTING-STARTED.md, advise what to do next.
- **Status confirmed:** Sessions 1–6 done (BUILDLOG 010 verified against git `aa2eef2..2d0b336`, ledger on disk with 5 ok entries, 193 tests claimed by 010). Open: the backfill *run* (3,197 downloads, unattended), Session 7 A+B, loading the fetched corpus, `make verify`.
- **Decided:** The backfill run is operator work, not a Claude session — operator instructions (disk check, `caffeinate -i nohup … &`, resume semantics, `verify-downloads --deep` afterward) now live in GETTING-STARTED where Session 6's prompt was. **Session 8 — bulk load** specified: `ingest load-all` walking the ledger in inventory `seq` order (baseline first), idempotent and resumable, then `make verify` implemented for real (per-title-per-RP counts → `docs/verification/`, committed); headline metric is the dedupe ratio. Sessions 1.5/6 marked ✅ in GETTING-STARTED; PLAN progress note rewritten; §10 tracks now: backfill run ∥ Session 7 ∥ Session 8.
- **Produced:** PLAN.md, GETTING-STARTED.md edits; this entry. No code.
- **Verified:** Doc-level review only; repo state cross-checked via git log, ledger.json, and BUILDLOG 010's own verification section.

## 012 — 2026-07-28 — Session 6.5: the S3 mirror and the disposable download box (ADR-0013)

- **Tool/model:** Claude Code, Opus 5 → Fable 5 (mid-session switch).
- **Asked:** Start the backfill run locally; then design remote work from EC2 — budget-friendly, robust, mirrored, and never holding back local development — with a step-by-step guide and updated docs.
- **Decided:**
  - **The corpus was mis-sized and the constraint mis-identified.** Size-weighted projection from the live run: **~9 GB**, not 40–80 GB (that figure is what fetching *every* title at *every* RP would cost; `titlesAffected` is what collapses it — Title 42 alone is 3.1 GB of the 9). The real cost is **40–50 hours** of ~50 KB/s polite downloading. So the design protects download time, not disk: S3 is the corpus of record, EC2 is a disposable downloader, the laptop stays the dev machine (ADR-0013). Stale 40–80 GB claims corrected in PLAN, CLAUDE.md, GETTING-STARTED.
  - **`ingest mirror push/pull`**: transport delegated to `aws s3 sync` (its retries, its multipart, no new Python deps); **trust never delegated** — every pull re-hashes against the ledger's sha256s. Push uploads the ledger **last**, so the mirror can never advertise files it doesn't hold; a failed corpus sync leaves the previous ledger describing the previous complete state. One-writer rule: the ledger's writer is wherever the backfill runs.
  - **The ledger went machine-portable** — the mirror design surfaced a real bug: entries recorded the laptop's absolute paths, so a pulled ledger would have re-downloaded everything on EC2. Paths are now `{label}/{filename}` relative to the corpus dir, resolved against the ledger's own location; skip decisions check the *computed* local target, never the recorded string; old absolute paths normalize on load.
  - **The box runs itself**: `scripts/ec2-user-data.sh` (AL2023 arm64 `t4g.micro`, SSM-only — no key pairs, no inbound ports) writes two systemd units — pull → backfill → deep-verify → push → **power off** (billing stops), plus an hourly push timer bounding instance loss at ≤1 h of downloads. Run cost well under $1; mirror ~$0.25/mo.
  - Local dev explicitly unmoved: fixtures/samples/`make dev-data` stay the loop; `mirror pull --title N` fetches a verified slice on demand. Remote *compute* for the bulk load deferred to Session 8, to be decided against a measured database size.
- **Produced:** `ingest/mirror.py`; `ingest/backfill.py` portability fix; mirror CLI in `ingest/__main__.py`; `scripts/run-backfill-ec2.sh`, `scripts/ec2-user-data.sh`; `docs/remote-ops.md` (step-by-step: bucket, IAM, handoff, launch, monitor, pull, teardown, §7 Session 8 sizing); `docs/adr/0013`; `tests/test_mirror.py` (17) + 2 portability tests; PLAN/CLAUDE/GETTING-STARTED updates; this entry.
- **Verified:**
  - `make test` — **212 passed** (was 193). Mirror tests inject a recording runner (no aws CLI, no network); the push-ordering property, empty-mirror first-boot, corrupt-pull detection, and title∩release include-pattern product each have a named test. The moved-corpus test renames a downloaded corpus to a different machine-path and proves resume skips everything with zero requests and deep verification stays sound.
  - Live local run in progress meanwhile: ~90/3,197, zero failures; 8 legitimate `unavailable` (titles 34/52/54 predate their creation — 52 and 54 created 2014, 34 re-created 2017; and 113-36 lists 18A as affected while publishing no file for it, a recorded source inconsistency). Appendix URL naming validated by `113-44/11a` at 283 KB.
  - An accidental full-scale interrupt test: the first launch was killed mid-download (stdout buffering fix) — 16 ledger entries survived, zero `.part` files, relaunch resumed cleanly. Re-check any time: `pkill -f "ingest backfill"` then re-run.
  - **Not verified yet:** the mirror against real S3 (no bucket exists) — the aws-cli argv contract is tested, the first `mirror push` is the integration test, and remote-ops §2 makes it the first operator step.

## 013 — 2026-07-28 — Session 8: bulk load, a real `make verify`, and three bugs the scale exposed

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Restart the paused download and take on the next steps.
- **Decided:**
  - **ADR-0014 — bulk-load resume state lives in the database.** No second ledger to drift with the download ledger: `title_versions.sections_loaded` (new column) is stamped in the commit that ends a load, so NULL means "did not finish". The `title_versions` row is created *before* sections are read and `load_release` commits as it goes, so row presence proves nothing — only the count does. A crash leaves NULL and the pair is redone, which is safe because `load_release` is idempotent (content-hash dedupe + upserts). The column doubles as the verification datum, which is why it is a count, not a boolean.
  - Order is inventory `seq`, oldest first — the baseline must precede the deltas, and `first_release_id` must land on the earliest release carrying a text (ADR-0008). Each zip extracts to a temp dir and is deleted (the XML is several times the ~9 GB of zips); one session per title bounds memory; a title that won't parse is recorded and the walk continues.
  - **`make verify` is real** (PLAN §11.5): shallow compares recorded counts to `section_release_map` rows in seconds; `--deep` re-parses every source file for an *independent* recount — the only version that can catch a parser confirming its own bookkeeping. `ingest/verify.py` names no USLM elements, so architecture rule 2 holds (the architecture test caught a docstring that did).
- **Three bugs found, all by running at scale:**
  1. **Ledger paths hid 449 of 538 downloaded files.** Entries written relative *but including* the corpus prefix slipped past ADR-0013's absolute-path normalization and re-resolved to `data/releases/data/releases/…`. Paths now normalize to the `{label}/{filename}` contract however they were recorded; the parametrized test covers all three forms.
  2. **Resume would have reloaded titles 1–9 forever.** `Title.num` is the URL form from `<docNumber>` (`1`); the ledger uses OLRC's file-naming form (`01`). Compared raw, a single-digit title never matched its own completed load — and it failed in the *safe-looking* direction: extra work, reported as success.
  3. **An older load silently relabelled a current provision.** `structure_nodes` keeps one row per node; the descriptive fields were last-writer-wins, so loading Title 16 at 113-21 (2013) after 119-102not101 (2026) changed `/us/usc/t16/ch1/schXCVII` from `reserved` to `repealed` — wrong data served for the current release point. `first/last_release_id` were already gated on `seq`; the descriptive fields now are too, so the row means "newest loaded release's view" regardless of load order. Caught by `test_the_reserved_subchapter_is_retrievable_and_badged`, which is exactly the kind of specific fixture assertion that pays for itself.
  - Bugs 1 and 2 share a shape worth naming: **a string meaning different things in two layers, compared without conversion, failing silently toward extra work rather than an error.**
- **Produced:** `ingest/load_all.py`, `ingest/verify.py`, migration `4678d590a1a9` (`sections_loaded`, `raw_section_elements`), `load-all`/`verify` CLI, `make verify` + `verify-deep` + `load-all`, `tests/test_load_all.py` (13), ADR-0014, CLAUDE.md/BUILDLOG. Commits `f209c12`, `9245c18`.
- **Verified:**
  - `make test` — **227 passed** (was 212). Four API tests that asserted the database held *exactly* Title 16 were scoped to their fixture window, since a bulk load into the same database legitimately invalidates that.
  - Resume proven both ways: re-running an already-loaded `(release, title)` loads 0 and never opens the zip; `--limit` runs pick up where the last left off.
  - Dedupe confirmed at scale on the first repeat title: Title 16 at 119-99 re-loaded **5,095 sections, 0 new versions, 100% deduped**.
  - `make verify` sound on the partial corpus; the two pre-column Title 16 loads correctly read as `incomplete`.
  - **In flight at session end:** download ~660/3,197 and bulk load running concurrently (network-bound vs CPU-bound, so they compose). Neither is finished; the dedupe ratio over the whole corpus is the headline number still to come.

## 014 — 2026-07-28 — Session 7: reader/API separation (ADR-0010) and the Astro/USWDS reader (ADR-0011, ADR-0015)

- **Tool/model:** Claude Code, Opus 5. Worktree `uscode-web` on `feature/reader-overhaul`, sharing the Postgres of the main checkout while its bulk load ran.
- **Asked:** Run Session 7 from GETTING-STARTED §7 in full — Part A (separate the surfaces, commit the checkpoint), then Part B (Astro 5 + TypeScript + USWDS, with the BUILDLOG 008 acceptance spec as the parity bar). Plan mode first.
- **Decided:**
  - **Part A implements ADR-0010 as written.** Reader at `/app/us/usc/…` (always HTML), API at `/api/v1/us/usc/…` (machine formats only), bare `/us/usc/…` a 307 redirector — `?format=` wins, query string copied through verbatim, `Vary: Accept`. The negotiation tests became redirect tests: the same q-value table, asserted against `Location:`.
  - **The app's composition root moved out of `api/`** to a top-level `main.py`, with the shared HTTP helpers in `params.py` and the redirector in `citation.py`. Without that move, "nothing under `api/` imports Jinja" could not be true — `api/main.py` was importing `web.reader` to render HTML. Two architecture tests now hold both directions of the split.
  - **ADR-0015 records the two things Part B had to decide.** (1) **A proxy owns the origin:** Caddy on :8000 routes `/app/*` to the Astro service and everything else to FastAPI on :8001. Making FastAPI proxy `/app`, or Astro proxy the API, were both rejected — each re-couples what ADR-0010 separated, in one direction or the other. (2) **USLM → HTML renders in the frontend** (`frontend/src/lib/uslm.ts`), not as an `html` field on the API: a rendered-HTML field would put element names and anchor decisions back inside `api/`, and CLAUDE.md rule 5 already named the typed successor in the Astro app as presentation's home.
  - **One API addition, through the Repository:** `GET /api/v1/labels?identifier=…&identifier=…` and `Repository.labels()`, because ref hover text has to cost **one** request per page, not one per citation. Grouped by title before querying, since a page of Title 16 can cite Title 54 and the two need not be ingested at the same release point (gotcha 10). `/api/v1/releases` gained `?ingested_title=` so the picker offers release points that hold the title rather than all 382.
  - **Reference mapping verified against govinfo before being encoded** (ADR-0015 table): `/us/stat/{vol}/{page}` and `/us/pl/{congress}/{num}` map to the link service, but its public-law collection **starts at the 104th Congress** — `103/1` answers 400, `104/1` answers 302 — so older laws and pre-1957 `/us/act/` references degrade to plain text. Link to something that exists, or do not link.
  - **Jinja retired** (your call, taken up front): `web/` deleted, `jinja2` dropped from the dependency list. No Python module in this project now renders HTML or knows a USLM element name, so the architecture test that carved out `web/uslm_html.py` no longer needs an exception.
  - **Two USWDS defaults overridden, both because this reader ships no JavaScript:** the primary nav is hidden behind a menu button below the desktop breakpoint, and the mobile breadcrumb parks all but one crumb at `left: -999em`. A phone now gets a wrapped row of links and the whole trail — "where am I in the Code" is a question a versioned reader must answer at every width.
- **Three things that cost time, recorded so they cost less next time:**
  1. **Port 8000 was owned by the *other* checkout's `uscode-redesign-api-1` container.** This worktree's uvicorn bound 127.0.0.1:8000 alongside Docker's 0.0.0.0:8000 without error, and Docker won — so the new reader was calling the *pre-separation* API and every page 404ed. Moved to :8001, which is the compose topology anyway. Two checkouts, one machine: pick distinct ports before debugging anything.
  2. **Astro strips `base` before its dev proxy sees a URL.** A proxy entry for `/us/usc` therefore matched `/app/us/usc/…` and served JSON where a page belonged. The dev proxy deliberately no longer carries that path, with a comment saying why.
  3. **A test asserted Title 54 was *absent*.** True when written, false forty minutes later — the shared database was mid-bulk-load. Rewritten against identifiers that can never resolve (`/us/usc/t99/s1`), which is the only stable form for a "not found" assertion while a backfill is running.
- **Produced:** `main.py`, `params.py`, `citation.py`, `deploy/Caddyfile`, `frontend/` (Astro 5 + TS + USWDS: 4 pages, 8 components, `lib/{api,refs,uslm,url,types}.ts`, 27 Vitest tests, Playwright screenshot script), `docs/screenshots/` (375px and 1280px), ADR-0015, ADR-0011 → Accepted; `web/` and `api/{main,deps}.py` deleted. Commits `0141aac`, `c6b93ae`, `8829fd1`, `c3ac773`, `4ba8db8`, `99efb96`, `e205543`.
- **Verified:**
  - `make test` — **209 passed** (227 before; the Jinja reader's 35 tests retired and 17 new redirect/label/architecture tests landed). `make test-web` — **27 passed**.
  - Part A by hand against a live server: browser `Accept:` → `307 /app/…` with `Vary: Accept`; `curl` → `307 /api/v1/…`; `?format=` overrides both; the guid form redirects and lands on the highlighted provision; `/app` 404s render as pages and `/api/v1` 404s as JSON.
  - **All six acceptance items checked against the running stack**, not asserted: one-line section title, breadcrumbs + picker in a contextual bar, nav strip top and neighbours bottom, `--indent-step` at both widths, hover text from the batched lookup (`title="§ 45a–1. Addition of lands authorized"`), and zero relative `/us/pl/` or `/us/stat/` hrefs. The production build ships **one inline `<script>` and no JS bundle**.
  - The screenshot script fails the run if any page scrolls horizontally at 375px or 1280px; it passes at both.
  - Re-check: `make dev-all`, then `curl -sI 'localhost:8000/us/usc/t16/s45f/c/5?date=07/12/2026' -H 'accept: text/html'`, and `cd frontend && npm test`.

## 015 — 2026-07-29 — Status review across both checkouts; main synced

- **Tool/model:** Claude (Cowork), Fable 5 — independent reviewer.
- **Asked:** Review the status of `uscode-redesign` (main) and `uscode-web` (worktree), update documents, commit, and explain why there are two directories.
- **Status found:**
  - **Main:** Sessions through 8 built — backfill tool (ADR-0012), S3 mirror + EC2 remote-ops (ADR-0013, unexercised: no bucket yet), `load-all` + real `make verify` (ADR-0014), plus two post-013 fixes (structure repair `0c9d83f`, truncated-response retry `b86495e`). Backfill in flight locally: ledger 1,742 entries (1,698 ok / 44 unavailable), 5.1 GB in `data/releases/`; bulk load running concurrently. 22 provenance manifests from the in-flight runs were sitting uncommitted — now committed (`e844055`), per PLAN §11.4.
  - **Worktree `../uscode-web`, branch `feature/reader-overhaul`:** Session 7 complete (BUILDLOG 014, on the branch): ADR-0010 separation implemented with a top-level composition root; Astro 5 + TS + USWDS reader at `/app`; Caddy owns the origin (ADR-0015); USLM→HTML renders in `frontend/src/lib/uslm.ts`; batched `/api/v1/labels` for one-query hover text; Jinja retired with its 35 tests; branch claims 209 API + 27 web tests and commits 375/1280px screenshots. Branch is 1 commit behind main; touches PLAN/README/CLAUDE/BUILDLOG, so the merge will carry doc conflicts — append-shaped, trivial.
- **Why two directories:** one repo, two git worktrees — `uscode-redesign` (main: ingest/backfill/load work) and `uscode-web` (frontend branch) — created so Sessions 7 and 8 could run in parallel without colliding, per GETTING-STARTED §10. They share history and objects; `uscode-web` is disposable after merge (`git worktree remove ../uscode-web`).
- **Merge gate, per the repo's own rule:** not merged here — this reviewer cannot execute the suites. Merge steps: in `../uscode-web`, `git merge main` (pick up the 2 ingest fixes), run `make test` + `make test-web` + build, resolve the doc conflicts, then fast-forward main and `git worktree remove`.
- **Produced:** manifest commit `e844055`; PLAN.md progress note (Day 2–3 state, both checkouts); this entry.
- **Verified:** Branch review is textual (diff shape, BUILDLOG 014, ADR-0015) — test counts and screenshots are the branch's claims, to be re-run at merge. Ledger numbers re-checkable: `python3 -c "import json,collections;d=json.load(open('data/releases/ledger.json'));print(d['count'],collections.Counter(e['status'] for e in d['entries']))"`.

## 016 — 2026-07-28 — Merge session: `feature/reader-overhaul` → main; the worktree retired

- **Tool/model:** Claude Code, Opus 5. Run from the worktree `../uscode-web`, landing in the main checkout.
- **Asked:** Land the reader overhaul on main — merge, resolve the expected doc conflicts, re-run both suites and the build as the merge gate BUILDLOG 015 deferred, fast-forward, remove the worktree, and close the docs out.
- **Guard honoured:** a backfill (PID 58744) and a bulk load (69185) were running from the main checkout. Neither was killed, no docker service was restarted, no migration was run. The load-all finished **on its own at 16:25**, four minutes before the fast-forward touched the working tree — it completed its planned batch rather than being disturbed by it (`planned 791: 715 loaded, 76 skipped, 0 failed`). The backfill is still running.
- **What conflicted — two files, both append-shaped, exactly as predicted:**
  - **BUILDLOG.md** — main had appended 015, the branch 014, both after 013. **No renumbering was needed:** 013 (07-28), 014 (07-28), 015 (07-29) were already in chronological order, so both sides' entries were kept at their own numbers and no cross-reference had to move.
  - **PLAN.md** — the Day 2–3 progress note, rewritten by each side. Both sides' facts kept in one note: main's corpus numbers and ADR-0012/0013/0014, the branch's Session 7 completion. The caveats the merge falsified were dropped — main's "pending re-run of both suites and merge into main" and the branch's "Now: … Session 7", since the separation is now **implemented**.
- **No code file conflicted.** The two tracks were as disjoint as believed: the only code main carried in was the truncated-response retry (`ingest/download.py`, +5 tests), which the branch had never touched. This is the fact that made the merge cheap, and it is worth recording that the prediction held.
- **Stale claims the auto-merge left behind, fixed by hand** (a clean merge is not a correct document):
  - `README.md` did not conflict at all — main never touched it — so the branch's demo commands survived intact, but its Status section still knew nothing of the corpus. Added main's numbers: ~1,834/3,197 fetched (~57%), 5.3 GB of a measured ~9 GB, ADR-0012/0013/0014.
  - `CLAUDE.md` still said "Node 20+ required **once** the Astro frontend lands in Session 7" — it had landed.
  - `PLAN.md`'s Day-1 banner and Day-1 plan table still described `web/` and the shared-`Accept:` URL in the present tense. Marked superseded rather than rewritten: they are dated snapshots, and falsifying the record to keep it tidy would be the worse error.
- **Verified — the merge gate BUILDLOG 015 could not run, run here:**
  - `make test` — **214 passed, 13 deselected (slow), 0 skipped.** The 214 is 209 (branch) + 5 backfill tests from main. **Nothing was skipped:** the API integration tests need a loaded database and skip silently without one, so a skip here would have been a hole in the gate — the database was up and they ran.
  - `make test-web` — **27 passed** (2 files, 309 ms).
  - `npm run build` — **succeeds**, server built in 4.49 s. The USWDS `img/usa-icons/*.svg` warnings are pre-existing runtime-resolved assets, not build errors.
  - `docker compose config` — parses.
- **Produced:** merge commit `daaa5fb`, fast-forwarded to main and pushed (`0c9d83f..daaa5fb`); worktree `../uscode-web` removed and `feature/reader-overhaul` deleted; CLAUDE.md status line and this entry (`82b2a61`). Two commits, both pushed: `daaa5fb` (the merge, with the doc-conflict resolutions and the stale-claim fixes to README/CLAUDE/PLAN) and `82b2a61` (the close-out).
- **No new ADR.** This session made no architectural decision: it landed ones already recorded (ADR-0010 separation, ADR-0011 Astro/USWDS, ADR-0015 one-origin topology) and carried in main's ingest fix. The two judgement calls were documentation conventions, not architecture, and are recorded above rather than promoted to ADRs — keep the numbered series for decisions that constrain the code, or it stops being worth reading.
- **Corpus state at close (from `loadall.log`, not asserted):** **1,163,760 sections stored — 151,772 new versions, 1,011,988 deduped (87.0%)** over 715 title-releases, in 100.3 min. That is the first real reading of the dedupe ratio at scale, and it is the number ADR-0007 predicted the shape of; the authoritative one still wants `make verify-deep` over the finished corpus, which recounts from source XML instead of trusting the loader's own bookkeeping.
- **Next:** finish the backfill, re-run `make load-all` for the zips that landed after this pass, then `make verify-deep`; then Day 4 reader polish (keyboard nav, notes toggles, version timeline, diffs).

## 017 — 2026-07-29 — Status review (no changes needed beyond manifests)

- **Tool/model:** Claude (Cowork), Fable 5 — reviewer.
- **Found:** BUILDLOG 016's merge close-out left every document current; nothing to fix. Since 016: the backfill advanced to **2,188 ledger entries (2,144 ok / 44 unavailable, ~68% of 3,197; 6.4 GB)** and wrote 3 new provenance manifests, committed here. `docs/verification/database.json` on disk predates the 715-title load — regenerate with `make verify` after the next load pass rather than trusting it.
- **Next (unchanged from 016/CLAUDE.md):** finish the backfill → re-run `make load-all` → `make verify-deep` (corpus-wide dedupe ratio, independently recounted) → Day 4 reader polish on the Astro layout.

## 018 — 2026-07-29 — Session prompts written through Day 7 (Sessions 9–13)

- **Tool/model:** Claude (Cowork), Fable 5.
- **Asked:** Do prompts exist for the next steps including Day 4+? Add them if not.
- **Found/Done:** GETTING-STARTED §7 stopped at Session 8 (now marked ✅, BUILDLOG 013). Added paste-ready prompts: **9** corpus completion + `verify-deep` (mismatches classified, never averaged away; final numbers to README), **10** Day 4 reader polish (version timeline, diffs per prior-art's `Diff_Timeout: 0` finding, keyboard-nav island, notes toggles, heading-outline fix pulled forward from Day 7), **11** Day 5 auth + watchlist, **12** Day 6 perf + CI + deploy (CI closes the no-independent-test-runner gap; deploy choice becomes an ADR), **13** Day 7 hardening (`Uslm2Parser` parity, accessibility audit, the public "how this was built" page, debt sweep). 9 ∥ 10 are worktree-safe (ingest vs frontend).
- **Verified:** Prompts cross-checked against the open debts in CLAUDE.md's status line and BUILDLOG 013/014/016 — every recorded debt is owned by exactly one session.

## 019 — 2026-07-28 — Day 4: version timeline, diffs, keyboard nav, notes toggles — and the missing `lib/` found and fixed

- **Tool/model:** Claude Code, Sonnet 5.
- **Asked:** Build PLAN Day 4 on the Astro layout: a version-timeline page per section, diffs between any two versions (porting `../versions`' `Diff_Timeout: 0` per `docs/prior-art.md`), a keyboard-nav island, notes/`sourceCredit` as `<details>`, and the flat-`<h2>` heading-outline fix carried forward from Day 7 — plus tests, `make shots`, and this entry.
- **Found first, before any of that could be built: `frontend/src/lib/` did not exist.** `[...identifier].astro` imports `lib/{api,refs,uslm,url,types}.ts`, and BUILDLOG 014/016 both claim they exist (27 Vitest tests, `make test-web` green) — but the files were never in git, on any branch, at any commit, local or on `origin`. Traced to the actual cause, not just the symptom:
  - **A one-line root-`.gitignore` bug.** Line 17 was a bare `lib/` (Python-boilerplate, meant for a venv's `lib/site-packages`), and an unanchored gitignore pattern matches a directory of that name **anywhere in the tree** — including `frontend/src/lib/`. Every `git add` from Session 7 onward silently skipped the renderer, the API client, the URL helpers, the reference-resolution rules, and the whole Vitest suite testing them. The merge session (BUILDLOG 016) ran `make test-web` and reported 27 passing — genuinely true *of the worktree at that moment*, since untracked files still exist on disk and still run — but the fast-forward-then-`git worktree remove` sequence discarded everything the gitignore had kept out of every commit. Fixed: `/lib/` and `/lib64/`, anchored to root (`.gitignore`).
  - This is a durable lesson beyond this repo: **`make test` passing in a worktree is not evidence a commit is complete** — only `git show --name-status` on the actual commit is. BUILDLOG 016's own admission ("test counts and screenshots are the branch's claims, to be re-run at merge") was the closest anyone came to catching it, and even that re-run used the same untracked files rather than a clean checkout.
- **Decided:**
  - **Reconstruct `lib/` from the call sites, not from memory.** Every `.astro` page/component's imports (`fetchIdentifier`, `appHref`, `render`, `citedIdentifiers`, …) were read first, so the rebuilt modules match what BUILDLOG 014 and ADR-0015 already specified: `api.ts` resolves relative to `API_BASE_URL` and throws `ApiError` on non-2xx; `url.ts` is the one place `/app` and `/api/v1` are spelled out; `uslm.ts` walks the parsed USLM DOM with a small per-tag table (`LEVEL_TAGS`/`PARAGRAPH_TAGS`/`INLINE_TAGS`/`TABLE_TAGS`), copying `@class`/`@style` through per ADR-0015; `refs.ts` carries the ADR-0015 govinfo mapping table verbatim. Caught one bug the reconstruction itself introduced before it shipped: `API` as `/api/v1/us/usc` double-prefixed the identifier, since `SectionOut.identifier` already *is* the full `@identifier` path — fixed to `/api/v1` once call sites made the contract legible.
  - **Heading depth tracks USLM nesting**, not DOM nesting in general: a small `LEVEL_TAGS` set (section, subsection, paragraph, … item/subitem) increments a depth counter; `<heading>` renders `h{clamp(depth+1, 2, 6)}`. Section’s own (hidden) heading stays `h2`; a subsection heading is `h3`; deep enough nesting caps at `h6` rather than emitting an invalid tag.
  - **Notes/`sourceCredit` collapse via `<details>`, no JS — and the "open on desktop" half needed a second try.** The first CSS attempt (`.uslm-details > *:not(summary) { display: revert !important }`) looked right and even passed an isolated repro, but real Chromium (151) collapses closed `<details>` content through an internal `::details-content` box with its own `block-size`/`content-visibility`, not `display:none` on the light-DOM children — so overriding the children did nothing, confirmed by screenshotting the actual page (Source/Notes showed empty). Fixed with the pseudo-element the spec provides for exactly this: `@media (min-width:40em) { .uslm-details::details-content { content-visibility: visible !important; block-size: auto !important; } }` — verified via a headless probe that the rendered box height changed from 44px (closed) to 208px (open) at desktop width, and stayed 44px at 375px.
  - **Diff computes server-side through the Repository; presentation is the frontend's (ADR-0016).** `GET /api/v1/sections/{id}/diff?from=&to=` resolves both release points the normal way, fetches both `SectionResult`s, and diffs their verbatim XML with `diff-match-patch` (`Diff_Timeout = 0`, `diff_cleanupSemantic` — the exact setting `docs/prior-art.md` flagged as load-bearing), returning `{identifier, from, to, ops}`. This is a **generic text diff**, deliberately not structure-aware like `../versions`' `@emmetio/xml-diff` — doing that would require parsing USLM inside `api/`, which architecture rule 5 reserves for `frontend/src/lib/uslm.ts` alone. The frontend wraps `ops` in `<ins>`/`<del>` over the escaped raw XML — a source-level redline (like the existing "Source XML" link), not a diff of the rendered reading text; ADR-0016 names this simplification and its cost (a guid regenerating at every RP, per gotcha 1, is always the first thing a diff shows) directly.
  - **The version-history link lives next to the section title**, not the footer: `/app/versions/{identifier}` lists one entry per distinct text (from `Repository.versions()`, already built), oldest first, each linking to that release and to a diff against the previous entry, plus a from/to picker form (GET, no JS) for any pair.
  - **Keyboard nav is the one new client script, `is:inline`** (Astro would otherwise module-wrap it, and `document.currentScript` is `null` inside a module): ←/j previous, →/k next, u up, reading hrefs off `data-*` attributes the server already computed. Guards against modifier keys (⌘←/⌘→ browser history, etc.) and against firing while focus is in a form control — both verified with a headless keypress test, including the negative cases.
- **Produced:** `frontend/src/lib/{types,url,api,refs,uslm}.ts` (new), `frontend/vitest.config.ts` and `frontend/tests/{url,refs,uslm,fixture_corpus}.test.ts` (34 tests, replacing the lost 27), `frontend/src/components/KeyboardNav.astro`, `frontend/src/pages/versions/[...identifier].astro`, `frontend/src/pages/diff/[...identifier].astro`, edits to `[...identifier].astro` (version link, `KeyboardNav` mount) and `site.scss` (collapsibles, kbd hint, timeline, diff view); `api/diff.py`, `api/schemas.py`/`api/routes.py` (`DiffOut`/`/diff` route), `tests/test_diff.py` (8 tests); `docs/adr/0016-…`; `.gitignore` fix; refreshed `docs/screenshots/*`; this entry.
- **Verified:**
  - `make test` — **222 passed** (was 214; +8 for `api/diff.py`), 13 deselected. `make test-web` — **34 passed** (was claimed-27-but-actually-0; `npx astro check` — **0 errors**; `npm run build` — succeeds.
  - Against a live stack (local API on :8000 against the docker `db`, Astro dev on :4321): `/app/versions/us/usc/t16/s45f` lists all 9 real distinct-content versions from the loaded corpus (113-21 through 119-99), each a real link; `/app/diff/us/usc/t16/s2201?from=119-99&to=119-102not101` — the one section the fixture docstring in `tests/test_api.py` already names as changed between those two release points — shows both `<ins>` and `<del>` chunks; the unchanged-section case (`s45f` between the same two release points) is all-`equal`, `from.content_hash === to.content_hash`.
  - Headless keypress tests (Playwright) against the running dev server: `j`/`ArrowRight`/`u` each navigate to the correct prev/next/up URL; `⌘←` does not navigate (modifier trap check); pressing `j` while focused in the release-point `<select>` does not navigate either.
  - `make shots` — 8 screenshots at 375px/1280px, no horizontal scroll at either width, refreshed in `docs/screenshots/`.
  - Found and fixed in passing: the docker `api` container had been running a stale image whose reload target (`api.main:app`) predates the ADR-0010 split — every file save was crash-looping it silently (`Error loading ASGI app`). `docker compose up -d api` recreated it against the current `docker-compose.yml` (`main:app` on :8001, no host port — Caddy's job, ADR-0015); not otherwise touched.
- **No corpus work this session** — the backfill/verify-deep track from BUILDLOG 017/018's Session 9 is untouched; this was Session 10 only.

## 020 — 2026-07-28 — Day 5: auth + watchlists

- **Tool/model:** Claude Code, Sonnet 5.
- **Asked:** PLAN §4's auth + watchlists — email+password signup/login in `api/` (argon2,
  HTTP-only session cookies, CSRF on state-changing routes), watchlist CRUD (items =
  identifier + optional pinned release + note), a Watch button island, a My Provisions page
  with one-click open at current-or-pinned release, and status badges for a watched
  section that's since gone repealed/transferred — plus tests including the auth-required
  boundaries and the architecture suite.
- **Decided:** Full reasoning in ADR-0017. In short: sessions are server-side rows keyed by
  `sha256(token)` (revocable logout, not just a forgotten cookie); CSRF is a double-submit
  cookie pair (`usc_session` HttpOnly + `usc_csrf` readable), required on logout and every
  watchlist mutation but not on signup/login (no session yet to hijack, and the JSON-only +
  no-CORS combination already blocks a forged cross-site request from reaching either
  route); accounts get a second storage module (`storage/accounts.py` +
  `storage/postgres_accounts.py`, own `AccountsRepository` protocol and its own
  protocol/implementation contract test) rather than new methods bolted onto the
  version-resolution `Repository`, so `api/` still holds no SQL and no DB session either
  way; a watchlist item's status badge is a live `Repository.labels()` lookup grouped by
  resolved release, the same batched call a section page already makes for citation hover
  text — not a copy of the status recorded at add time.
  - **Reader-side choice, not in the ADR:** the reader gains three small `is:inline` islands
    (Watch button, login form, signup form) alongside Day 4's keyboard-nav island — auth
    genuinely needs client state (is this browser logged in, what does it currently watch)
    that a purely SSR page can't have without every page forwarding cookies, so this is a
    deliberate, small widening of "no JS by default," not an oversight. The **My Provisions
    page stays pure SSR** like every other reader page, by forwarding the browser's
    `Cookie` header to its own server-side API calls (`lib/api.ts`'s `fetchMe`/
    `fetchDefaultWatchlist`) — the one thing that makes it different from `releases.astro`.
  - A user's watchlists are lazily provisioned: no "create your first list" step — the
    reader's convenience endpoint (`GET /api/v1/watchlist`) auto-creates "My Provisions" on
    first use, and the general `/api/v1/watchlists` CRUD the schema supports (multiple named
    lists) exists underneath it for anyone who wants more than one.
- **Produced:** `db/models.py` (`AuthSession`), migration `c1f9a2b6d3e4`; `storage/accounts.py`,
  `storage/postgres_accounts.py`, `storage/session.py`/`storage/__init__.py` wiring;
  `api/auth.py` (signup/login/logout/me), `api/watchlists.py` (CRUD + the `/api/v1/watchlist`
  convenience singular), `api/schemas.py` additions; `main.py` router wiring;
  `tests/test_auth.py` (13 tests), `tests/test_watchlists.py` (13 tests), an accounts
  protocol-conformance test in `tests/test_architecture.py`, `tests/test_models.py` updated
  for `auth_sessions`, a `fresh_client` fixture in `tests/conftest.py` (function-scoped, so
  auth tests' cookies never leak into the session-scoped `client` other suites share);
  `frontend/src/lib/types.ts` (`User`/`Watchlist`/`WatchlistItem`), `frontend/src/lib/api.ts`
  (`fetchMe`/`fetchDefaultWatchlist`, cookie-forwarding), `frontend/src/lib/url.ts`
  (`provisionsHref`/`loginHref`/`signupHref` + 4 new Vitest cases);
  `frontend/src/components/{WatchButton,RemoveWatchItem}.astro`,
  `frontend/src/pages/{login,signup,provisions}.astro`, `SiteHeader.astro` nav link,
  `site.scss` additions; `docs/adr/0017-…`; this entry.
- **Verified:**
  - `make test` — **249 passed** (was 222; +27: 13 auth, 13 watchlist, 1 architecture), 13
    deselected. `make test-web` — **37 passed** (was 34; +3 URL-helper cases). `npx astro
    check` — 0 errors on the new files. `npm run build` — succeeds.
  - Against the real stack (API on :8123 against the docker `db`, Astro server build on
    :4321, `API_BASE_URL` pointed at the API): signup sets an `HttpOnly` session cookie and a
    non-`HttpOnly` CSRF cookie (checked via the raw `Set-Cookie` header, not just presence);
    a watchlist mutation without `X-CSRF-Token` is 403, with it 201/204; a bad-password login
    and an unknown-email login both return 401 with the same message; logout revokes the
    session (`/me` 401 immediately after); an end-to-end pass — sign up via the API, add
    `/us/usc/t16/s672` (known `omitted`, per `test_labels_carry_status_so_a_citation_can_be_badged`
    in `tests/test_api.py`) to the watchlist, then load `/app/provisions` on the *frontend*
    process with the browser's cookie forwarded by hand — rendered the heading, the `omitted`
    status badge, and the note text, proving the SSR cookie-forwarding path and the
    enrichment query both work together, not just in isolation.
  - `tests/test_architecture.py`'s existing suite still passes unmodified against the new
    files: no `db.*` import, no `sqlalchemy` import, and no template-engine import anywhere
    under `api/` — `api/auth.py` and `api/watchlists.py` go through `storage.accounts` only.
- **Open debt, named rather than silent:** no email verification, no password reset, no
  login-attempt rate limiting (PLAN's Day 5 description scopes email out of v1 entirely);
  the general `/api/v1/watchlists` CRUD has no frontend UI yet (only the default-list
  convenience endpoints the reader actually uses are wired to a page).

## 021 — 2026-07-29 — Code review of Days 4–5; GETTING-STARTED synced to reality

- **Tool/model:** Claude (Cowork), Fable 5 — reviewer, fresh context. Static review (this sandbox has no Python 3.12); test counts remain the sessions' claims until CI exists.
- **Asked:** Review the code, update GETTING-STARTED, say what to do next.
- **Reviewed:** `api/auth.py`, `api/watchlists.py`, `api/diff.py`, `storage/accounts.py`, `storage/postgres_accounts.py`, `frontend/src/{lib,components}`, and the Day 4/5 commits (`bcbe24b..cfd868b`).
- **Findings — the code is sound; four things worth naming:**
  - **Auth is well-built for its stated scope.** Argon2 with `check_needs_rehash` on login; sessions are server-side rows keyed by `sha256(token)`, so a database read never yields a usable cookie and logout revokes rather than merely forgetting; double-submit CSRF with `compare_digest`; identical error text for unknown-email and wrong-password. The docstring's argument for exempting login/signup from CSRF is correct and, more usefully, *written down* — the reasoning is auditable, which is the point of this repo.
  - **Ownership checks are consistent**, not sampled: every watchlist and item route resolves through `_owned_watchlist`/`_owned_item` before touching anything.
  - **`api/diff.py` respects architecture rule 5** — it diffs two opaque strings and names no USLM element; `Diff_Timeout = 0` is carried over from prior art with the reason in the docstring.
  - **One real risk for deploy, not for now:** `_set_session_cookies` derives `secure` from `request.url.scheme`, which behind Caddy is `http` unless proxy headers are trusted — the cookie would ship without `Secure` on the deployed site. Added to the Session 12 prompt (verify end-to-end, don't assume), along with `no-store` on authenticated responses so the caching work can't cache someone's My Provisions, and the BUILDLOG 020 auth scope cuts (rate-limiting; password reset decided either way) as pre-public-exposure gates.
- **Produced:** GETTING-STARTED §7 synced — Sessions 10 (Day 4) and 11 (Day 5) marked ✅ with their findings and scope cuts; **Session 9 marked UNBLOCKED** (ledger now 3,197 planned / 3,153 ok / 44 unavailable — the backfill is complete); Session 12 expanded per above. This entry.
- **Verified:** Ledger read directly (`data/releases/ledger.json`); commit range read from git log; code claims are from reading the files named above.

## 022 — 2026-07-29 — Day 6: caching, CI, the breadcrumb debt, auth hardening, and a load test that found things

- **Tool/model:** Claude Code, Opus 5 (plan mode first, then execution in one session).
- **Asked:** Session 12 from GETTING-STARTED §7 — (a) ETag + long `Cache-Control` on immutable responses with `no-store` on anything per-user, (b) fix the breadcrumb `get_toc` debt, (c) a load test with numbers here; CI running both suites; the ADR-0017 auth debts before public exposure, including verifying the `Secure` cookie end to end rather than assuming; and a deploy, plan-mode first. Deploy target chosen mid-session: **AWS**.
- **Decided:** [ADR-0018](docs/adr/0018-cache-immutably-only-when-the-release-point-is-pinned.md) (caching), [ADR-0019](docs/adr/0019-login-throttling-and-throwaway-accounts.md) (auth hardening; password reset deferred *by decision*), [ADR-0020](docs/adr/0020-deploy-one-ec2-box-compose-caddy.md) (deploy shape).
- **Three facts established before any code, two of which contradicted the status line:**
  - **The backfill is complete** — `data/releases/ledger.json` is 3,153 `ok` / 44 `unavailable` / 0 pending, 9.7 GB on disk. CLAUDE.md still said "~1,834/3,197 fetched".
  - **The mirror exists and is two-thirds empty.** An earlier probe with the wrong AWS profile said `NoSuchBucket`, which was wrong: `s3://uscode-mirror-dreamproit/` is reachable under the `uscode` profile and holds **1,122 of 3,153 zips (3.2 GB of 9.7 GB)** — an interrupted push. Correcting that mistake changed the deploy plan's first step from "create a bucket" to "finish a push".
  - **The database size is measured at last** — the input GETTING-STARTED made the deploy decision conditional on. **6,711 MB for 792 of 3,153 title-releases**, of which `guid_map` is 5,270 MB / 21.7 M rows and grows linearly. Full corpus projects to **25–35 GB**. Dedupe at this scale: 1,275,262 → 212,094, **83.4%**.
- **Caching (ADR-0018) — the rule is narrower than the plan's phrasing.** "A section at a release point is immutable" is true; "so mark section responses `immutable`" does not follow. A URL with no `?release=`, or with `?date=`, is answered from *newest ingested at or before* (gotcha 10), and that answer changes when a newer release point loads — caching it forever would pin superseded law into caches with no way to invalidate it. So immutability is a property of the *resolution*: `requested_label` and `is_exact` decide, and a bare `119-102` resolving to `119-102not101` is explicitly **not** pinned. `If-None-Match` now short-circuits to 304 with the full grammar (lists, `W/`, `*`). `no-store` sits on the auth and watchlist routers *and* is re-applied by path in the error handler — without the second half every 401 there was going out with no cache directives at all, because a raised `HTTPException` builds a fresh response the dependency never touched.
- **The breadcrumb debt (PLAN Day 6b).** `SectionResult.ancestors` now carries the title-root-to-parent chain, filled by the `_ancestors` walk `get_toc` already used. The reader's `Promise.all` drops from four calls to three. Measured: the removed call was the slowest of the four, so the fan-out's critical path falls **28.4 ms → 23.9 ms (−16%)**, and each section page transfers **9,794 fewer bytes** — it was fetching a chapter's whole table of contents (50 sections) to use 508 bytes of it. A test pins the equivalence rather than asserting it: the new breadcrumb is byte-for-byte what `[...toc(parent).ancestors, toc(parent).node]` returned.
- **Auth (ADR-0019).** Throttling is a delay, not a lockout — a lockout would let anyone lock anyone out by guessing badly at their address. 5 failures per email and 50 per address per 15 minutes, 429 with `Retry-After`, cleared on success, and unregistered addresses counted too or probing for valid emails would be free. The unknown-email path now runs argon2 against a dummy hash: **43.8 ms vs 41.9 ms (1.05×)**, where before it skipped key derivation entirely and was an enumeration oracle behind identically-worded errors.
- **The `Secure` cookie, checked end to end as instructed.** Confirmed with a request carrying `X-Forwarded-Proto: https` through `uvicorn --proxy-headers` inside the running stack: `usc_session=…; HttpOnly; Max-Age=1209600; Path=/; SameSite=lax; Secure`. Belt and braces anyway — `USC_COOKIE_SECURE=true` in production, so a proxy misconfiguration cannot silently downgrade it.
- **CI, finally.** `.github/workflows/ci.yml` runs `make test` against a Postgres 16 service container and `make test-web`, with `make test-slow` nightly. CI must not fetch from uscode.house.gov on every push (source etiquette; ADR-0013 says consumers pull from the mirror), and wiring CI to S3 for a 5 MB file is more machinery than it earns — so the fixture is committed and `make ci-data` loads both release points with **no network at all**, reproducing ADR-0005's 5,095 / 522 / 102 / 19 / 569. `USC_REQUIRE_INTEGRATION=1` turns the integration suite's self-skip into a failure, so a misconfigured job cannot go green having run nothing.
- **The load test found four things** (`docs/verification/loadtest.json`, `make loadtest`). Most routes are 130–300 rps at 30–70 ms. Then:
  1. **The diff endpoint does not scale and then fails.** ~0.45 rps at *every* concurrency from 1 to 10 — fully CPU-serialized — with latency growing linearly (2.2 s, 4.5 s, 11.9 s, 22.0 s) until past ~10 concurrent every request exceeds a 20 s client timeout. It is unauthenticated, so one client can saturate it. `Diff_Timeout=0` is ADR-0016's deliberate choice, so this is a known cost, but it needs a rate limit before the URL is advertised.
  2. **Half that cost is guid churn, not legal change.** `@id` regenerates at every release point by design (ADR-0003), so the two texts differ in every element. Diffing the guid-stripped text — what ADR-0007 already does for dedupe — took the same section from **2,220 ms / 51 ops to 1,172 ms / 20 ops**. The 31 extra ops are regenerated guids shown to the reader as amendments. Not changed here: it amends ADR-0016's source-level-redline decision, which deserves its own.
  3. **304s are not a latency win on loopback** — 183.7 rps against 159.1. What they save is the 28,348-byte body, which counts over a real network and not at all in this measurement. Recorded rather than dressed up.
  4. **HEAD is 405 on every `/api/v1` route** — FastAPI's `APIRouter` registers GET alone where Starlette's `Route` adds HEAD. This bit the load-test script itself: `curl -I` to read an ETag returned 405, so the revalidation row silently measured a plain 200 until it was caught.
- **Produced:** `ada0507` CI + offline fixtures · `a6ffe90` breadcrumbs on the section · `4643fa8` the caching policy · `675e618` auth hardening · `9eeb755` the load test and its findings · plus `docker-compose.prod.yml`, `docs/deploy.md`, ADRs 0018–0020 and this entry. **266 Python tests** (was 249) and **42 frontend tests** (was 37), both green.
- **Not done — the deploy itself.** Three blockers, none of them code: the mirror push was **denied by the sandbox permission classifier**, so the corpus is still only on this laptop and the mirror is still two-thirds empty; provisioning needs an IAM identity that can create EC2 and IAM resources, which the `uscode` profile cannot (it cannot even `s3:ListAllMyBuckets`); and Caddy needs a **domain name** to get a certificate. Everything that does not need those is built and committed — the production compose file, the HTTPS Caddyfile, the runbook with costed sizing, and the smoke tests to run against the URL once it exists.
- **Caveat on the load-test absolutes:** the run shared the laptop with a `ingest load-all` that was in progress throughout (it took the database from 792 to 1,160 title-releases and 6.7 GB to 9.7 GB during this session), so every throughput figure is depressed. The findings survive it: the diff result is about *scaling* — flat ~0.45 rps from concurrency 1 to 10 — not about absolute speed, and the 304-vs-200 and breadcrumb comparisons are between rows measured under the same conditions.
- **Verified:** `make test` 266 passed / 13 deselected; `make test-web` 42 passed; `npx astro check` 0 errors. Cache headers checked through the running Caddy stack at every layer — pinned section `immutable`, unpinned `max-age=300`, `/app/provisions` and `/app/login` `no-store` + `Vary: Cookie`, 401s from `/api/v1/auth/me` and `/api/v1/watchlist*` `no-store`. `Secure` cookie confirmed via a forwarded-proto request inside the stack. Load test re-runnable with `make dev-all` then `make loadtest`. Database and ledger figures come from `docker compose exec db psql` and `data/releases/ledger.json` directly; re-check with the queries in this entry.

## 023 — 2026-07-29 — Session 9: the corpus, finished and independently recounted

- **Tool/model:** Claude Code, Opus 5, run hands-off from a single prompt.
- **Asked:** Session 9 from GETTING-STARTED §7 in full — confirm the backfill is done, re-run `make load-all` for everything that landed since the last pass, push the final corpus to the mirror, run `make verify-deep` over the whole corpus and commit the artifact, classify every count mismatch rather than averaging it away, report the headline numbers, update README's Status, BUILDLOG and commit. Mid-session direction from Ari on the one question that came up: **where the source publishes more than one version of a section at one release point, serve them both with an explanatory note** rather than picking one.
- **Decided:** [ADR-0021](docs/adr/0021-repeated-identifiers-serve-every-occurrence.md) — repeated `@identifier`s serve every occurrence.

### The corpus

- **Backfill confirmed complete before loading anything:** 3,153 zips on disk exactly matching 3,153 `ok` ledger entries, 44 `unavailable`, 3,197 planned. `--plan-only` prints the whole plan rather than the remainder, so the file count against the ledger is the check that actually answers the question.
- **All 44 unavailable downloads classified**, since "unavailable" on its own is not a finding. Every one is an HTTP **200** that is not a zip: OLRC 302-redirects a missing file to `docnotfound.xhtml` and serves that with a 200, so the backfill's zip-magic check — not the status code — is what catches them.
  - **`113-21` ×8 — correct absence.** The baseline sweep asks for every title at the oldest release point; appendix titles `05a/11a/18a/28a/50a` and titles `34`, `52`, `54` did not exist in Aug 2013 (52 and 54 were enacted Sept 2014, 34 reestablished 2017).
  - **`113-36` ×1 — source inconsistency.** `titlesAffected` lists `18a`; OLRC published no such file.
  - **`114-219u1` ×35 — source inconsistency, whole release point.** The inventory gives it 35 affected titles and not one is downloadable. Not a URL-construction bug: 16 of the other 17 `u1` release points fetched fine.
- **`make load-all` over the full corpus:** 3,153 planned, **2,355 loaded, 798 already complete, 0 failed, 0 title mismatches**, 8h48m. Resume state is the database, as ADR-0014 intended, so the 798 were skipped without touching a zip. Rate fell from ~6/min to ~2.7/min as `guid_map` grew past 80 M rows, then recovered.
- **Mirror push finished and checked**, not assumed: 3,153 zips + ledger (9,697,559,134 bytes) and all 381 manifests on `s3://uscode-mirror-dreamproit/`, counted against the local corpus.

### Verification — the numbers, and the thing that nearly wasn't checked

`make verify-deep`, re-parsing every source file for a recount independent of the loader's own bookkeeping (`docs/verification/database.json`):

| | |
|---|---|
| Title-versions checked | 3,153 across 381 release points, 58 titles |
| **Independently recounted from source** | **3,153 of 3,153** |
| **Source mismatches** | **0** |
| Incomplete loads | 0 |
| Raw `<section>` element disagreements | 0 |
| Sections | 65,938 distinct |
| `section_versions` | 489,738 |
| `section_release_map` | 5,466,652 |
| `guid_map` | 96,185,732 |
| **Dedupe ratio** | **91.0%** |
| Database on disk | 27 GB |
| Deliberately unstored elements | 454,943 across 2,991 title-versions (ADR-0005) |

- **The first deep run silently checked only 84% of the corpus.** It recounted 2,649 of 3,153 title-versions and reported clean. The 504 it skipped were every single-digit title, Title 5 included: `_recount_from_source` keyed the ledger with `Title.num`, which is the URL form (`5`), while ledger keys use OLRC's file-naming form (`05`) — the same translation `load_all.completed_pairs` already had to make. The miss then `return`ed silently. Fixed both halves: the key goes through `_file_form`, and the function reports whether it actually recounted, so `source_unavailable` and a "recounted N of M" line make the coverage visible. **The silence was the worse bug** — a deep run that quietly recounts a subset is a weaker claim wearing the same words. Re-ran to full coverage; the result held.
- **`VerifyReport.guid_rows` was declared and never populated**, so every committed `database.json` had been claiming zero guids for a corpus with 96 M of them.

### Six count mismatches, and what was behind them

`sections_loaded` exceeded `section_release_map` rows on six title-releases: `113-296not287/54`, `114-329/10`, `115-8/10`, `117-80/19`, `117-110not103/19`, `117-111not103/19`.

- **Classification: source inconsistency.** OLRC publishes more than one `<section>` element under the same `@identifier` in one title at one release point. Title 19 at 117-80 has **three** for `/us/usc/t19/s2502` — two empty stubs headed "Purposes", then the real section headed "Congressional statement of purposes". Title 54 at 113-296not287 repeats `s200308`, `s300314`, `s300315`, whose occurrences carry the same operative text with differing notes and whose `@id` prefixes differ (`d303-11e4` vs `a8a5-11e4`), suggesting two generation runs merged into one file.
- **Not a parser gap:** these carry real `@identifier` and `@id`, so ADR-0005's quoted-statutory-text rule does not apply. **Not a loader bug:** ADR-0007's dedupe collapses byte-identical repeats into one `section_versions` row, which is exactly the arithmetic — the loader counts elements, the release map counts stored texts. The gap is **left reported**; suppressing it would weaken the check for a tidier artifact.
- **What it exposed was retrieval, and it was worse than the counting.**
  - `get_section` ended in an unordered `.first()`, so which occurrence a reader saw was whatever Postgres returned — for `/us/usc/t19/s2502`, a coin flip between a 360-byte empty stub and the 3,232-byte real section.
  - `neighbors` asked for the section's single place in reading order with `scalar_one_or_none`, which **raises** on multiple rows. The reader fetches neighbours on every section render, so **every affected section page was a live HTTP 500** — invisible until the corpus was loaded.
- **Decision (ADR-0021), per Ari's direction: serve every occurrence.** All occurrences come back in `seq_in_title` order; the reader prints a note at the top — "The official XML for this title at *RP* publishes *N* distinct texts under the identifier *X* … all *N* are shown below, in the order they appear in the source" — and renders each body under an "Occurrence *k* of *N*" caption. Neighbours bracket the group. Provision extraction searches across occurrences, so `/s2502/1` lands on text rather than on the stub that sorts first. The count is stated as **distinct texts**, not elements: Title 19's two identical stubs are stored once, so the page says two where the source has three, which is what the database can honestly claim.

### Produced

- `cdd8410` report guid_map rows in the verification artifact
- `c83192e` serve every occurrence when the source repeats an identifier (ADR-0021)
- `0b713ee` provenance manifests from the full-corpus load (271 files, PLAN §11.4)
- `cc0808c` recount every title in `verify --deep`, and name what it cannot
- `9c64fbb` the full-corpus deep verification artifact
- `bbcbfa0` README Status → the finished corpus
- `5e60107` CLAUDE.md status line

### Verified

- `make test` **273 passed** / 13 deselected; `make test-web` **42 passed**; `npx astro check` **0 errors**.
- Re-check the corpus: `uv run python -m ingest verify --deep` (~35 min) reproduces `docs/verification/database.json`; `python -m ingest verify` alone (seconds) reproduces the six mismatches.
- Re-check ADR-0021 end to end against the running stack: `curl -s "http://localhost:8000/app/us/usc/t19/s2502?release=117-80"` renders the note and **two** `section-body` articles; `/us/usc/t16/s45f` renders one and no note; `/api/v1/sections/us/usc/t19/s2502/neighbors?release=117-80` is 200 where it was 500.
- New tests: five in `tests/test_api.py` covering occurrences served, source order, stability across repeated requests, deep-link provision extraction, and neighbours bracketing the group; two in `tests/test_load_all.py` covering the ledger key form and `guid_rows`.
- **Two stale assertions corrected, both made wrong by the corpus rather than by code:** `test_ingested_titles_are_distinguished_from_affected_titles` asserted 119-100 had *no* ingested titles, which the full load made false (it now holds title 47, the one it affected) — rewritten as the absence it actually means. The architecture suite also caught a USLM element name in a docstring I had written in `storage/repository.py`, which is the rule working.

### Open after this session

- The six count mismatches stay in every `verify` run by design (ADR-0021).
- `DuplicateOccurrence.guid` repeats the section's guid: `guid_map` holds one row per (identifier, release) and cannot tell the occurrences apart. The source's ambiguity, not ours to invent around.
- Deploy is still the blocker for everything public (ADR-0020) — it needs an IAM identity that can create EC2/IAM, and a domain.

---

## 024 — 2026-07-29/30 — Session 10: the UI refresh before the deploy

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Review the repo before deploying to AWS and prepare a UI update. Evaluate **Appica**, a React component library the owner was leaning toward, plus reasonable alternatives that are mobile-first, accessible by default, and strong on text display. Then plan and build four things: (1) order the Titles numerically — the front page listed `1, 10, 11, … 2, 20`; (2) let a reader reach any provision by typing a citation (`11/523`, `11 usc 523`, `11 usc 523(1)(B)(ii)`), using parsing rules from the `versions` directory or GovTrack-style prior art; (3) a scrollable hover tooltip showing the text of any referenced provision, with testing planned so it is robust; (4) stop the menu, breadcrumbs, section number and navigation scrolling away.

- **Decided:**
  - **Keep USWDS; add no client framework (ADR-0022).** Appica was measured, not impressioned: `@appica/ui-react` is **v1.0.0, the only version ever published** (2026-07-09), its GitHub repo's last push was 61 minutes after its creation, and it gets **1,124 weekly downloads** against Base UI's 7.65M and USWDS's 68K. It requires React 19 + Tailwind 4 and pins pre-release deps inside a 1.0.0. Its components are genuinely apt — Preview Card is exactly requirement 3 — but the blocker is local: `lib/uslm.ts` renders statutory text to an **HTML string** consumed by `set:html`, so a React card cannot wrap a `<ref>` without rewriting the one module architecture rule 5 designates as the sole presentation layer. Its ideas were adopted and its code was not; the whole refresh cost one ~3 KB island. (Dark mode, the feature on the Appica page that prompted the evaluation, already existed in `site.scss`.)
  - **Titles order numerically, and the ordering is the Repository's contract (ADR-0025).** `Title.num` is a `String` and has to be — `5a` is a title and `5` is a different one — so `ORDER BY` collated it as text. Sorting moved to an explicit `title_sort_key`, and the guarantee is documented on the protocol so the XCiteDB port inherits it rather than rediscovering the bug.
  - **Citations parse server-side, in a pure module (ADR-0023).** `citeparse.py` imports no storage, db, fastapi or sqlalchemy — enforced by `test_architecture.py` — which is what lets its 84-case accepted-forms table run in `make test` with no corpus. `GET /api/v1/citation` adds existence via the batched `labels()` already built for hover text: no new `Repository` method. Three failures get three answers — 422 for "not a citation", 200 + `exists:false` for "names nothing here", and a specific `message` for what this site structurally cannot resolve. The reader's box is a plain GET form; an e2e test runs it with JavaScript disabled.
  - **Previews render server-side as HTML fragments (ADR-0024).** `/app/preview/…` is an Astro *endpoint* — a page would get a `<!DOCTYPE>` prepended — rendered by the same `lib/uslm.ts` as the section page, so **no USLM renderer reaches the browser**. The card is `popover` + CSS anchor positioning with a measured fallback for Safari 18.2–18.3. WCAG 2.1 SC 1.4.13's three clauses are three named mechanisms with three named tests. The card is `aria-hidden` (it duplicates the link's `title`; the rejected `aria-describedby` alternative is recorded). Touch navigates — the feature is gated on `(hover: hover) and (pointer: fine)`.
  - **The sticky stack is one `.topbar`**, whole on desktop and one 44px row on a phone, where the forced-open nav plus wrapping breadcrumbs would otherwise eat ~280px of a 660px viewport.

- **Produced:** `58c0f26` (title order), `d35f562` (sticky chrome), `4a3c957` (citation jump), `aeab9c5` (hover preview), plus this entry, ADR-0022/0023/0024/0025, a CI `e2e` job, and regenerated `docs/screenshots/`. New: `citeparse.py`, `frontend/src/lib/preview.ts`, `SectionBar.astro`, `CitationJump.astro`, `CitePreview.astro`, `pages/goto.astro`, `pages/preview/[...identifier].ts`, `frontend/tests/e2e/`. Deleted: `NavStrip.astro`, folded into `SectionBar`.

- **Verified:** `make test` **384** (was 273) · `make test-web` **60** (was 42) · `make test-e2e` **40** (new) · `astro check` 0 errors · `make shots` regenerated at 375px and 1280px.
  - Title order live: `curl -s localhost:8000/api/v1/titles | jq -r '.[].num'` → `1 2 3 4 5 5a 6 … 11 11a 12 … 50 50a 51 52 54`.
  - Sticky geometry measured at 375/700/1000/1280: the bar pins, and both a deep link and an in-page anchor jump land clear of it.
  - Citation box: `curl -sI 'localhost:8000/app/goto?q=16+USC+45f(c)(5)'` → 307 to `/app/us/usc/t16/s45f/c/5`.

### Seven bugs found by building it — four of them already live

1. **A typed hyphen matched nothing.** OLRC writes section numbers with an **EN DASH** — `/us/usc/t16/s45a–1`, U+2013 — and **5,697 of the 65,938 loaded sections contain one while not a single section contains a plain hyphen**. No keyboard has that key, so `42 USC 2000e-2` was unresolvable. The parse now carries dash variants and the batched lookup tries all of them for the price of one.
2. **A raw en dash in a `Location:` header is a crash**, not a wobble: a header value is a ByteString and Node throws. Both redirects in the app 500'd on those ~8.6% of sections — including the **pre-existing `?id=` guid lookup**, which had been broken for them since Session 7. Fixed in `url.ts`, so every href builder encodes.
3. **Every section page drew all three Watch buttons at once** — "Add", "Remove" and "Log in" together, for every visitor, since Day 5. USWDS's `.usa-button { display: inline-block }` is an author rule and beats the UA stylesheet's `[hidden] { display: none }`. The island had been correct all along.
4. **`title="§ § 688."`** on every citation's hover text: `num` arrives from the source as `§ 688.`, symbol included, and `refs.ts` added another. The same mistake appeared independently in the new section bar.
5. **`make shots` had silently stopped working.** Since the Day-5 islands landed the reader never goes network-idle, so `waitUntil: "networkidle"` timed out on every page — which is why `docs/screenshots/` still showed the pre-Day-5 layout.
6. `11 USC ch. 5` and `title 11` reported `exists: false` while sitting in the database: `labels()` answers about sections, so structure now goes to `get_toc`.
7. **Previews never scrolled.** The 1,400-character budget was smaller than the card's own 22rem, making the scroll area decoration and cutting every preview off mid-thought. Raised to 4,000.

`--sticky-h` drifted twice in one session — 224px → 280px when the citation box added a row — and each time the symptom was a deep-linked provision rendering *behind* the bar. It is now asserted against the measured stack in the e2e suite rather than trusted to memory.

### Open after this session

- **Appendix titles remain unreachable by citation.** `5 U.S.C. App. 3` parses to `/us/usc/t5a/s3` and OLRC publishes nothing there: **0 of 461 appendix sections** use the flat form — they are `/us/usc/t5a/pl/92/463/s1` (public law) or `/us/usc/t50a/act/1917-05-18/ch15/s212` (act by date). The API says so specifically rather than returning a bare "not found". Closing it needs a citation-to-enacting-instrument table this project does not have; inventing one silently would be worse than the gap.
- **The preview endpoint is unauthenticated and fans out per hovered citation.** Hover intent, a per-page cache and `AbortController` hold it down, and it is far cheaper than the diff — but the standing "rate-limit before advertising the URL" debt now covers two routes, not one.
- **A pre-existing rendering defect, untouched:** USLM `<date>` renders as a block, so "November 10, 1978" breaks onto its own line mid-sentence throughout the notes. One entry in `uslm.ts`'s inline-tag set, deliberately left out of a scoped refresh.
- `docs/ui-improvements-plan-unapproved.md` is untracked and not this session's work.
- Deploy is still the blocker for everything public (ADR-0020) — it needs an IAM identity that can create EC2/IAM, and a domain.

## 025 — 2026-07-30 — Session 11: light by default, a readable redline, and what a release point changed

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Three things, in the order they arrived: (1) *why is the app in dark mode?* — make light the default and let the reader toggle to dark; (2) render diffs in XML/HTML, don't show the markup; (3) on the Release Points page, list the titles affected in a column, and drop "Titles held here" as redundant with "Titles changed".

- **Decided:**
  - **Light at every OS setting; dark is a control, not a media query (ADR-0027).** The palette was gated on `prefers-color-scheme`, and most laptops say dark — so most visitors got the United States Code light-on-black without asking, with no way out. Dark now hangs off `<html data-theme="dark">`, set by a ~700-byte island and remembered in `localStorage`. **Not a cookie:** every reader response is cached (ADR-0018) and identical for everyone; a theme cookie would put `Vary: Cookie` on the whole site to record a colour preference. A blocking inline `<head>` script stamps the attribute before first paint, so a dark reader never sees a white flash — and light, the default, pays for no script at all.
  - **The reader's diff shows the reading text; the API keeps the XML (ADR-0026, amending ADR-0016).** The old page printed the source redline, which for two release points of an *untouched* section is hundreds of struck-and-reinserted `@id`s — guids regenerate at every RP by design (gotcha 1). Now both versions are turned into lines a reader reads (`uslm.readingBlocks`) and those are diffed (`lib/diffdoc.ts`): lines aligned first (each distinct line encoded as one character), then a deleted line paired with an inserted one and diffed **word by word**, because a character diff of `$5,000,000` → `$7,500,000` strikes `5,0` and inserts `7,5`. A pair that shares less than 40% of the longer line is *not* merged — showing an edit that never happened is worse than showing both texts. It is computed in the frontend because deciding where a line of statutory text ends is a USLM question, and `lib/uslm.ts` is the only module outside the parsers allowed to ask one (architecture rule 5).
  - **"Titles changed" names the titles and links each one** to that title *at that release point* — the question the page exists to answer. The old second column counted `ingested_titles`, which mattered while the backfill ran and became a second copy of the same number when it finished (3,153 of 3,153). The distinction it protected is kept where it still bites: a title OLRC republished that this database does not hold is marked per row (grey, `†`), instead of being inferred by comparing two totals.
  - **The toggle shares a flex row with the citation box** (`.navtools`), which is geometry rather than taste: a second block in the navbar adds ~44px to the sticky stack between 40em and 64em, and `--sticky-h` is what `scroll-margin-top` spends. Measured before and after at 700px: top bar 280px, token 288px, unchanged.

- **Produced:** ADR-0026, ADR-0027, this entry. New: `frontend/src/lib/diffdoc.ts`, `frontend/src/components/ThemeToggle.astro`, `frontend/tests/diffdoc.test.ts`, `frontend/tests/e2e/theme.spec.ts`. Changed: `site.scss` (light default + a dark block that covers what USWDS actually paints), `uslm.ts` (`readingBlocks`), `url.ts` (`unpadTitle`, `compareTitles`, `apiDiffHref`), `Base.astro`, `SiteHeader.astro`, `pages/diff/[...identifier].astro`, `pages/releases.astro`. One dependency: `diff-match-patch` (npm), server-side only — the same algorithm as the Python side, so the two redlines stay comparable.

- **Verified:** `make test` **384**, unchanged (nothing Python moved) · `make test-web` **78** (was 60) · `make test-e2e` **44** (was 40) · `astro check` 0 errors.
  - The headline diff case, live against the loaded corpus: `/app/diff/us/usc/t16/s45f?from=119-99&to=119-102not101` → *"The text of this section is identical at both release points."* The same URL previously rendered a wall of guid churn.
  - A real amendment reads as one: `/app/diff/us/usc/t16/s1531?from=117-327not263&to=119-99` → "2 lines changed", one of them `…note under section ~~14~~1013 of ~~the Federal Advisory Committee Act in the Appendix to~~ Title 5`.
  - Theme, in a browser with the OS set to dark for every assertion: body background `rgb(255,255,255)` on first load; the toggle goes both ways; the choice survives a navigation and is stamped by the head script; the top bar still fits inside `--sticky-h`.
  - Screenshots taken at 375/700/1280 in both themes before and after each fix.

### Found while building it

1. **The dark palette only ever coloured four things.** `body`, the header, the footer element and links — while USWDS paints its inputs, selects, tables and summary boxes white *explicitly*, and puts the footer's colour on `.usa-footer__primary-section`/`__secondary-section` rather than on `.usa-footer`. So dark mode had a white slab for a footer and a glowing citation box. The `<select>` chevron is a background SVG drawn in ink: on a dark field it was a dark arrow on a dark background, so it is repainted rather than hidden.
2. **A note can be an entire Executive Order**, and USLM marks its paragraphs with `<p>` — which was not in the line-breaking set, so E.O. 13648 came out as *one* line and a three-word amendment inside it redlined as a wall of text. Fixed and tested.
3. **The source is free to put no whitespace between `<num>` and its `<chapeau>`**, which turned `(a)` + `Whoever—` into `(a)Whoever—`. Text extraction now joins block-level children with a space and inline ones (`<i>`, `<ref>`, `<sup>`) without, so `10<sup>3</sup>` stays one token.
4. **The citation box wrapped its own "Go" button onto a second line** once the toggle joined its row at 1280px — the navbar silently grew a row, which in the sticky band is `--sticky-h` drifting again. Held to one line at ≥64em.

### Open after this session

- **The rendered redline drops `<ref>` links**, so a changed cross-reference is text rather than a link with a hover preview. The section pages either side of the diff still have both.
- **A whitespace-only change is now invisible** in the reader's diff, because the text is normalized before diffing. Between two release points of a statute that is the right trade; it is still a deliberate blind spot.
- **The API's diff endpoint is still unauthenticated and CPU-bound** (`docs/verification/loadtest.json`) and still must be rate-limited before the URL is advertised. The reader no longer calls it, which moves the reader's cost off it but changes nothing about the endpoint.
- **`docs/verification/loadtest.json` is now stale for `/app/diff`**, which does two section fetches and a text diff instead of one API call. Worth re-running before deploy.
- The `<date>`-renders-as-a-block defect from Session 10 is still open, still one line in `uslm.ts`'s inline set.

## 026 — 2026-07-30 — Session 12: search, made to run and made to know about versions

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** *The app is not showing. Another agent made changes to add search. Please review the deployment status and get the app running locally.* Then, once it ran: hold off on a full index; make partial indexing happen as the database is updated; fix the ADR number collision; fix search's versioning so the **current** text of a provision is what a search returns by default; commit and rebase onto the frontend branch.

- **Why nothing was showing.** Three independent breakages in one commit, only the last of which was about search:
  - `main.py` imports `api.search` → `storage.search` → `opensearchpy`. The dependency was in `pyproject.toml` and `uv.lock` but not in the built image, so **uvicorn died at import before binding a port**. Every route that wasn't `/app/*` returned nothing — the site was down, not search.
  - The `opensearch` service was added to compose and **never started**; started, it **exited 1 at every boot**. OpenSearch's security plugin rejects `Uscode_Search_Admin_123!` as *"Password is similar to user name"* because it contains "admin". The single line saying so was in a container log.
  - The frontend image predated `search.astro`, so `/app/search` was a 404.

- **Decided:**
  - **The index unit is the deduped section version, and the default search returns only the text in force (ADR-0028).** A section amended four times has four documents, all matching the same query; the first cut had nothing to tell them apart, so a search for "conservation" returned the same provision several times over, ranked against itself. Every document now carries `is_current` and the default filters on it. `?release=`/`?date=` swap that for `first_release_seq <= seq` plus a `collapse` on `identifier` — the newest text at or before the release asked for, which is the rule the Repository already applies to a release point that was never ingested (gotcha 10). Labels resolve through `Repository.resolve_release`, so `119-102` disambiguates here exactly as on a section page, and no SQL entered a handler.
  - **Ordering is `release_points.seq`, never a row id.** The draft filtered on `release_id`, a primary key — insertion order, which orders nothing, and release labels do not sort lexically either (gotcha 4).
  - **The index is maintained incrementally.** A new version is indexed current; the section's previous versions are retired with a partial update that does not resend the text; **text a release republished unchanged writes nothing at all** — 91% of the corpus (ADR-0007). So a release point costs an index write per section it actually changed, not per section in the title. Writes happen *after* the transaction commits, so a rollback cannot leave the index advertising a section the database has not got, and current-ness is decided against the newest **completed** load of that title — the same `seq` gate `structure_nodes` uses, so loading an old release point after a newer one does not relabel superseded text as in force.
  - **Renumbered to ADR-0028, not "0018a".** A letter suffix reads as an amendment to the ADR it hangs off, and search amends nothing about cache policy. 0022–0027 went to the UI refresh while this was in flight, so it landed at 0028.

- **Two bugs the draft would have shipped:**
  - `reindex_search` read `SectionVersion.section` behind a `hasattr` guard, but **`db/models.py` declares no ORM relationships at all** — so the guard was always false, every section would have indexed as `identifier="unknown"`, and since `_id` was `f"{identifier}_{release_id}"` they would have collapsed into **one document per release**. It also called `.all()` over 490k rows and 3.5 GB of XML before indexing anything. Both passes now stream.
  - Every search result linked to `/us/usc/${identifier}` — but the identifier already *is* `/us/usc/…`, so every link on the page pointed at `/us/usc//us/usc/t16/s3831`. **The test fixture is why this passed CI:** it asserted an identifier of `"t16/s1"`, a shape the index never holds.

- **Produced:** ADR-0028, this entry, and commits `7235afe` (opensearch boots), `ce6268a` (versioned index, current by default), `365de5c` (result links + release context in the page), `87a01a7` (renumber). New: `tests/test_search_sync.py`. Rebased onto `feature/ui-refresh-title-order`; the one conflict was `SiteHeader.astro`, where search's new nav block met Session 11's `.navtools` row — resolved **into** that row, because a second block in the nav is ~44px on `--sticky-h` and that token is what `scroll-margin-top` spends.

- **Verified:** `make test` 401 passed (384 + 17 new), `make test-web` 78 passed, full stack up under `docker compose` with all five services healthy. Search checked end to end at both surfaces: default reports *"searching the law currently in force"*, `?release=119-99` reports the release and marks each result *"unchanged since"*, an unknown label is 404, an unreachable cluster is 503.

- **Open, and deliberately so:**
  - **The index is a 4,000-document smoke slice**, not the corpus — a full build was explicitly deferred. `python -m ingest.reindex_search --recreate` builds the 66k current-text index the default query reads; `--all-versions` adds the 490k superseded ones that `?release=` needs to reach back. Until that runs, a point-in-time search answers from current text alone. The response names the release it searched, so this is visible rather than silent.
  - **The search endpoint is unauthenticated and unthrottled**, now the third such route alongside `/diff` and `/preview`.
  - **A section the source publishes twice under one identifier at one release (ADR-0021) shares a `_id`**, so the index keeps one of the two. Six title-releases are affected.
  - `docs/adr/0018-keyword-and-vector-search.md`'s original text claimed a `release_id` filter that never worked; it is superseded rather than deleted, and ADR-0028 says why.

## 027 — 2026-07-30 — Session 13: paying the security debt, then fixing the chrome

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Continue the cleanup plan (`docs/cleanup-plan.md`) from where Session 12 left it — Phase 0 and S1 were committed, Phase 1's S2/S4/S5 were half-written in the working tree. Then, mid-session, four things about the reader: note where ids or other metadata changed when a diff reports "identical"; make the search bars larger and visible at all screen sizes and merge the citation box into one control, with a `cites` prefix reserved for reverse citation lookup (and a plan document for it); show the verbatim-XML redline inside the app as legible HTML; lay the footer out horizontally.
- **Decided:**
  - **ADR-0029 — request identity and rate limits**, one ADR because they are one subject: a limiter keyed on a value the caller chooses is not a limiter. Token buckets in `params.py` for `/api/v1` and a new `frontend/src/middleware.ts` for `/app/preview` and `/app/diff`, which the API cannot see or attribute. Budgets are split by *who calls the route*: the reader's server-side calls all arrive from one container address, so `/labels`, `/search` and `/citation` are sized for a server and bound fan-out, while signup and diff are sized for a person. Two costs recorded rather than discovered later: the state is per process, and a shared NAT is one bucket.
  - **The S1 finding was real but its stated mechanism was wrong, and the correction is the interesting part.** "Caddy appends, so a forged `X-Forwarded-For` lands leftmost and wins" is only true from a peer inside `private_ranges`, because Caddy preserves an inbound value *only from a trusted proxy* — and the global block trusts private ranges for `X-Forwarded-Proto`'s sake. So the dev stack was exposed and ADR-0020's internet-facing EC2 shape was not; what was actually latent is the deployment most likely to come next, with a CDN or load balancer in front (ADR-0018 anticipates exactly that). Measured in a container rather than argued: `docs/verification/xff.md`.
  - **ADR-0030 — browser security headers.** `frame-ancestors 'none'` and `X-Frame-Options: DENY`; a CSP that is a *description* of a site with no CDN, no web font and no analytics, which is what makes it safe to enforce; `includeSubDomains` taken deliberately as a commitment. `script-src` carries `'unsafe-inline'` and the ADR says so plainly — eight `<script is:inline>` islands, and the theme toggle must run before first paint (ADR-0027). Nonces are the named follow-up and now have somewhere to live, since ADR-0029 added the middleware.
  - **`safeNext()` is an allowlist, not a denylist** — `//evil`, `/\evil`, `java\tscript:` and percent-encoded schemes are an open-ended set; "a path under `/app/`, no scheme, no authority" is checkable. Validated server-side so the island only ever receives a vetted value.
  - **OpenSearch stops being configured by accident:** no default password (raise `SearchNotConfigured`), TLS verified unless told otherwise, hostname assertion follows `verify_certs` rather than being a separate knob, and the service finally exists in `docker-compose.prod.yml`. `verify_certs=false` is accepted *in that file for that deployment*, with the reason, rather than hardcoded for every environment forever.
  - **One search box, not two** (`SiteSearch`), with `/app/goto` promoted to a router: citation → provision, `cites …` → a marked keyword search, anything else → a plain one. Whether something *is* a citation stays `citeparse`'s decision (ADR-0023); `lib/query.ts` decides only the prefix, the one thing decidable without the API. The interim `cites` answer is labelled on the results page so it cannot be mistaken for the real feature.
  - **The reader gets the source XML redline in the page** (`lib/xmlredline.ts`), computed locally rather than from `/api/v1/…/diff`: both fragments are already fetched for the reading diff, and calling the endpoint would compute it twice while spending ADR-0029's tightest budget. Opt-in behind `?source=1` because *not* computing it is the saving. Diffed over raw bytes, never a pretty-printed form — whitespace is precisely what this view exists to be able to show (ADR-0026's named cost).
  - **An empty redline now says which of three things it found** — byte-identical, guid-only, or beyond guids — and names the guids, which differ per release even when the stored fragment is shared, because ADR-0007's dedupe makes one row serve both and it carries the guids of the release the text first appeared at.
- **Produced:** commits `6233124` (OpenSearch credential/TLS/prod service), `8291ad6` (rate limits, input bounds, the error-detail leak, ADR-0029, `docs/verification/xff.md`, and — untidily, sharing a commit — the Caddyfile's CSP block and the `CitationJump` deletion), `a964732` (`safeNext`, ADR-0030), `3eedc0e` (the four reader changes, `docs/citation-index-plan.md`). New: `docs/adr/0029`, `docs/adr/0030`, `docs/verification/xff.md`, `docs/citation-index-plan.md`, `frontend/src/middleware.ts`, `frontend/src/lib/{ratelimit,query,xmlredline}.ts`, `frontend/src/components/SiteSearch.astro`.
- **Verified:**
  - `make test` **413** (was 401), `make test-web` **119** (was 78). `npx astro build` clean; `caddy validate --config deploy/Caddyfile` reports valid.
  - The X-Forwarded-For matrix measured against `caddy:2` with an echo upstream — forged value survives as leftmost in exactly one of six configurations, and `header_up X-Forwarded-For {remote_host}` closes it in all of them. Reproduction script in `docs/verification/xff.md`.
  - Header geometry measured in a browser at six widths rather than eyeballed: search input 116px → **172px** at 1280, and **234/426/686px** at 375/640/900 where it had been a sliver. An intermediate attempt let the nav links shrink and put the box on top of "API docs"; caught by measuring the gap, fixed with `flex: 0 0 auto`. The nav-link padding rule needed USWDS-beating specificity — a plain `.usa-nav__primary > li > a` silently did nothing, which only showed up by reading *computed* padding rather than trusting cascade order.
  - Footer nav 4 stacked rows → **1 row, 59px** at 1280; still wraps on a phone.
  - The source redline checked on a pair that really changed (`t16/s45f`, 113-21 → 119-99): 91 insertions, 52 deletions, guid churn struck through and a real `class` change visible beside it.
  - The `<ref>` measurement behind the citation plan, over `samples/uslm1/usc16.xml`: 55,659 refs, mean 10.9/section, of which **only 21.3% point into the USC** — the rest are public laws and Statutes at Large in the notes apparatus. The plan's first draft claimed ingest already extracts cross references; it does not (`guid_refs` is the `?id=` lookup's index, and `ref` is in no parser's vocabulary), and the draft was corrected.
  - **Not verified here:** `make test-e2e`. The specs were updated for the merged box and the new routing, but running them needs the compose stack rebuilt, which now requires `SEARCH_PASSWORD` in `.env` — see below.
- **Continued the same day, after the `.env` was supplied:** the stack was recreated and all three suites finally run together — **413 / 119 / 45**.
  - The recreate surfaced two things worth recording. `OPENSEARCH_INITIAL_ADMIN_PASSWORD` is honoured **only on first boot**, so a password changed in `.env` leaves the security index in the volume holding the old one and every search 401s; resolved by keeping the documented dev literal rather than wiping the volume. And the healthcheck this session wrote used `curl -sk`, which **exits 0 on an HTTP 401** — so the cluster reported *healthy* while rejecting the credential, and `depends_on` cheerfully started the API against it. `-f` added to both compose files.
  - Verified live against `make dev-all`: CSP, `X-Frame-Options: DENY` and HSTS with `includeSubDomains` present on `/app/` (they were absent at first — the proxy container was still running the old Caddyfile and needed recreating, which is itself worth knowing); the diff limiter shedding `200 200 200 200 200 429 429 429` with `Retry-After: 5`; and `HEAD` returning 405 on `/api/v1`, confirming the standing U7 debt from the other side.
  - Then the header layout, asked for after the first pass: the search box moved to **its own row from 64em up**, 116px → **467px**. Sharing the navbar's row was never going to work — `.usa-nav-container` is USWDS's 1024px grid container, so the header is 1024px wide at any window size, and the box only ever got what the 238px logo and ~380px of links left. The row costs `--sticky-h`, and measuring it corrected **two** bands: ≥64em from 13rem to 19rem (287px occupied), and 40–64em from 18rem to 22rem (337px occupied) — the second already wrong before this session. The measurement only works *after scrolling*; a first attempt read unscrolled positions and reported 467px of sticky chrome for a phone whose band is one 45px row.
  - The single e2e failure was the suite being right rather than a regression: `.usa-alert--warning a` now resolves to two links, because a citation naming nothing offers the text search alongside the title.
- **Note for the next session:** `docker compose` will not start until `SEARCH_PASSWORD` is set in `.env` (copy the line from `.env.example`). That is this session's change working as designed — the alternative was a password published in this repository — but it means the running dev stack must be recreated, and the currently-running API container predates `SEARCH_VERIFY_CERTS` and so now fails TLS verification against the dev cluster's self-signed certificate. Recreating it with the updated compose file fixes both.

---

## 028 — 2026-07-30 — Session 14: a search that means it, and chrome that stays on the site

- **Tool/model:** Claude Code, Opus 5 (main session); Sonnet 5 subagent for the settings backend; Haiku/Sonnet Explore agents for the code map.
- **Asked:** Six things, on a new branch. (1) The search returns `Company` and `Compact` for `Compare` — make it strict unless the reader uses OpenSearch syntax to loosen it, and add a syntax guide. (2) Fold the API docs into the site chrome instead of a separate page. (3) Drop the "Log in to track this section" button from section pages; put a login control in the navbar. (4) Show the diff XML inline as text. (5) Open links in a new tab, with the choice as an option for logged-in users. (6) Mid-session: remove the duplicate search box on the search page.
- **Decided:**
  - **Search is strict by default (ADR-0031).** The cause was not stemming — there is no analyzer configured anywhere in this project, so both text fields use the `standard` analyzer, which does not stem. It was `fuzziness: "AUTO"`, which spends two character edits on any term of six letters or more: `compact` and `company` are each *exactly* two edits from `compare`, and a fuzzy hit is a full match clause rather than a near miss. Now `simple_query_string` with `default_operator: and`. `simple_query_string` and not `query_string` because the latter throws on an unbalanced quote — on a public endpoint that turns a typo into a 400.
  - **The flags are named, not `ALL`,** so the syntax guide can be *checked* against them rather than trusted. `tests/test_search_syntax.py` reads `api.search.QUERY_SYNTAX_FLAGS` and the operator list the guide renders (`frontend/src/lib/searchsyntax.ts`) and fails on drift in either direction — the only link between the Python suite and the frontend one.
  - **`WHITESPACE` is not the flag it looks like.** It was left out first, on the reasoning that a search box cannot produce a tab. Wrong: it is what makes the parser split on spaces at all, and without it `water -pollution` parses to `+water +pollution` — the exclusion becomes a requirement. Valid query, opposite meaning, no error. Recorded in ADR-0031 because the failure generalises: a missing parser flag does not fail, it changes what the query means.
  - **The API reference is server-rendered from `/openapi.json`** into the site's own layout (`/app/docs`). Both obvious alternatives were already closed off by earlier decisions: the CSP names no CDN, so a Swagger bundle cannot load, and ADR-0030's `X-Frame-Options: DENY` blocks framing `/docs` even same-origin. Deriving it from the schema also means no second description of the API to drift. FastAPI's `/docs` and `/redoc` stay mounted and are linked — Swagger UI can send a request, and losing that would be a subtraction.
  - **Sign-in is site state, so it lives in the site chrome.** An island, not SSR, for the same reason the theme toggle is `localStorage` (ADR-0027): rendering "logged in as …" on the server would put `Vary: Cookie` on every page carrying the header, which is all of them.
  - **New-tab is the default, and the preference is applied client-side.** A per-user setting cannot be rendered into a page held in a shared cache, so `user_settings` is the record and `localStorage` is what the page reads, with `AuthNav` joining the two. New-tab is therefore what a reader with scripting off gets — the right default to fail to. Scope: cross references and search results, not breadcrumbs/prev-next/TOC, which *are* the reading rather than a departure from it.
  - **The diff XML needed no work** — Session 13 had already moved it in-page (`?source=1`, monospace, syntax-coloured). Confirmed with the user rather than assumed; the behaviour being described was the older one that opened the XML in a browser window.
- **Produced:** branch `feature/search-strictness-and-chrome`, five commits — 7898715 (strict search + guide + ADR-0031), 9792fb1 (one search box), f28358f (API reference in chrome), 52a7a8e (navbar auth), 5d44282 (new tab + `user_settings`). New: `docs/adr/0031`, `api/settings.py`, `frontend/src/{components/AuthNav.astro,lib/openapi.ts,lib/searchsyntax.ts,pages/docs.astro,pages/settings.astro,pages/search/syntax.astro}`, migration `a2f0edc8f5e2`, `tests/test_{search_syntax,settings}.py`, `frontend/tests/{openapi,searchsyntax}.test.ts`, `frontend/tests/e2e/chrome.spec.ts`.
- **Verified:**
  - All three suites green against the running compose stack: **`make test` 439** (was 413), **`make test-web` 149** (was 119), **`make test-e2e` 53** (was 45).
  - Operators checked against the live cluster, not documentation: `Compare` 139 → 2 results; `compare~2` 139 (the old behaviour, on request); `"national park"` 1,253 vs `national park` 1,521; `water -pollution` excludes, `water +pollution` 29 requires; `park | forest` 2,190; `compar*` 65. The `-` bug was found with `_validate/query?explain=true` — re-check with that, since both parses are valid.
  - `/api/v1/settings` exercised live end to end: default `true` on a fresh account with no row written, PUT → GET round trip, 403 without CSRF, 401 anonymous, and `private, no-store` + `Vary: Cookie` on **all four** including the 401.
  - The e2e sticky-height assertions still pass with a third control in `.navtools`, which was the real risk of putting auth in the navbar — `--sticky-h` is unchanged.
- **Corrected during the session:** `params.PRIVATE_PREFIXES` did not list `/api/v1/settings`, so the 401 was cacheable — every settings test passed anyway, because they all checked a 200. Test added for the error path. Two e2e specs failed correctly on the new-tab change (they asserted the current page navigates) and were rewritten to assert the popup.
- **Open, unchanged by this session:** the `heading` field carries both a deprecated index-time `boost: 2.0` and a query-time `heading^2`; `total` is the uncollapsed hit count, so the pager over-counts on `?release=` queries; the search index still holds Session 12's 4,000-document smoke slice, so the absolute result counts above are smaller than they will be after `python -m ingest.reindex_search --recreate`.

---

## 029 — 2026-07-30 — Session 14b: looking at the pages

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Pull the merged `main` and fix whatever I identify in the UI.
- **Decided / found:** Six defects, none of which was visible in the code — all six came from rendering the pages at 375px and 1280px and reading them.
  - **An empty 72px band on every section page**, and a regression from this session's own work: removing "Log in to track this section" left `.watch-widget` holding nothing, but it reserves `min-height: 2.5rem` plus 1rem of margin either side so that swapping Add for Remove does not shift the page. The island now hides the container.
  - **The API reference printed its own Markdown.** OpenAPI descriptions are Markdown by specification, and `main.py`'s is a bulleted list full of `code` spans — shown as text it was literal backticks and asterisks with every bullet collapsed into one run-on paragraph. `renderMarkdown` in `lib/openapi.ts` covers the four constructs the docstrings here actually use; deliberately not a dependency, since the input is our own prose and the output goes through `set:html`.
  - **"9 endpoint s"** — the plural `s` was a second JSX expression on its own line, so a newline landed between the noun and its suffix.
  - **The contents list read as eight rows for four groups** (`.toc li` gives every item a rule and a block layout), with FastAPI's lowercase route tags (`api`, `auth`) as the labels.
  - **The syntax table was wrong at both ends, and the first fix made it worse.** It overflowed a phone by 135px; making the table its own scroll container fixed that and broke the desktop, because `display: block` takes the cells out of table layout and the last column was clipped at 1280px with room to spare either side. Four columns of which one is prose does not fit a 700px reading measure, so the operators are a list of blocks now. The API parameter tables keep their table and get a scrolling *wrapper*, which is the version that works in both directions.
  - **Astro preserves whitespace inside an element**, unlike React JSX, so `<a>\n  <code>x</code>\n</a>` renders a link with underlined spaces hanging off it. Confirmed in the emitted HTML rather than assumed, then fixed in four places.
  - Not a defect but a clear improvement while there: search snippets were OpenSearch's defaults — five fragments of 100 characters *per field*, so one result could carry ten disconnected shards cut mid-clause. Now two fragments of 220, with the heading highlight used *as* the result title rather than repeated beneath it.
- **Produced:** branch `fix/ui-followups`, commit 4abf952, plus this entry.
- **Verified:**
  - `make test` **441**, `make test-web` **159**, `make test-e2e` **53** — all green.
  - **`make shots` now covers `/app/search`, `/app/search/syntax` and `/app/docs`** at both widths. That script asserts no horizontal overflow, and it is what caught the 135px table; the docs page earns its place there because it renders a parameter table per endpoint, which is the thing most likely to push a phone sideways. Re-check with `make shots` — it exits non-zero on overflow.
  - Dark mode checked on the new pages by driving the header toggle.
- **Method note worth keeping:** every one of these was invisible to the test suites, which were green throughout, and invisible to `astro check`, which reported 0 errors throughout. Rendering the page and looking at it is a distinct verification step from running the tests, and this session is the argument for doing it before saying a UI is done.

## 030 — 2026-07-31 — Session 14c: making CI able to pass at all

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** CI on GitHub is failing — `make test-web` is green, `make test-e2e` exits 1 and `make test` exits 2. Fix it.
- **Found:** Four faults, all of them the job's rather than the code's. Every run in the repository's history had failed, back to the first one — CI has never been green, and BUILDLOG 022's claim that "the standing 'test counts are the sessions' own claims' gap is closed" was therefore true only of the Python and Vitest suites once, and never of the browser suite at all.
  - **`test_titles_are_listed_in_the_codes_own_order` asserted the fixture, not the ordering.** One line after a docstring promising "a property rather than a fixed list, because which titles are loaded changes as the corpus grows", it asserted `nums[0] == "1"`. `make ci-data` loads Title 16 alone, so CI answered `'16' == '1'` — failing since Session 10 wrote the assertion, and green locally the whole time because the dev database holds the whole corpus. Now guarded like the `"2"` comparison directly below it, which had the same problem and had already been guarded.
  - **`docker compose up -d db` failed on a service it was not starting.** Compose interpolates the whole file before deciding which service to bring up, so OpenSearch's `${SEARCH_PASSWORD:?}` — added in Session 13, on purpose, to stop the password being a committed literal — stopped `up -d db` as surely as `up -d`. CI now generates one per run and writes it to `.env`, rather than putting the credential back in the repository under another name. This had blocked the e2e job at its third step since Session 13, which is why none of the faults below had ever been reached.
  - **`up -d db` returns on *started*, not *ready*.** The next step ran `alembic upgrade` into the middle of initdb: "server closed the connection unexpectedly". The service has carried a healthcheck all along; `--wait` is what makes anything read it.
  - **Nothing had ever indexed the fixture corpus.** `make ci-data` runs before the cluster exists and ingest is allowed to run without one, so the OpenSearch index did not exist — and a missing index is a 404 that the reader renders as a *failure* panel, while `chrome.spec.ts` asserts on the *zero-results* panel. The job now builds it (`ingest.reindex_search --recreate`, Title 16, seconds).
  - Also: the actions bumped off the deprecated Node 20 (checkout/setup-node@v5, upload-artifact@v5, setup-uv@v6), and `if-no-files-found: ignore` on the trace upload so a job that fails before Playwright runs stops adding a second, misleading annotation beside the real one.
- **Produced:** branch `fix/ci-green`, commits `Make CI able to pass at all` and `Wait for Postgres to finish starting before loading into it`, plus this entry.
- **Verified:** run 30640486770 — **`make test` 441 passed, `make test-web` green, `make test-e2e` 53 passed**, all three on the runner rather than on this laptop. Re-check with `gh run list --branch fix/ci-green`. The 53 browser tests were also run locally against `make dev-all` before the first push, which is what established that the specs themselves were sound and the failures were environmental.
- **Worth keeping:** two of the four faults were latent behind the one in front of them, so each push revealed the next. A CI job that has never been green is not one bug; it is a stack of them, and the only way to find the second is to fix the first and run it again. Also: a test asserting something its own docstring disclaims is a test that will pass wherever it was written and nowhere else.

## 031 — 2026-07-31 — Session 14d: the unchanged-diff message, and the link under it

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Two fixes to the diff page's "nothing readable changed" case. (1) Reword *"This view diffs what the section says, so it cannot show what that was: the source-level redline shows it."* (2) That link opened the API's JSON; it should open the source redline **in the page** — the same destination the link at the foot of the page already has — and scroll to it, with a loading indicator if the render takes time.
- **Decided / found:**
  - The wording is now *"This view diffs the displayed text only. The source-level redline shows the changed metadata as well."* — the third `UNCHANGED_NOTE` case plus the sentence carrying the link.
  - The link's `href` moved from `apiDiffHref(...)` to `${sourceToggleHref(true)}#source`, so both offers of the source redline now lead to the same in-page panel (Session 13 had moved the redline into the page but left this one link pointing at JSON). When `?source=1` is already on, it is a bare `#source` jump instead of a reload. The API's JSON is still one link away, at the foot of the rendered panel.
  - **`#source` had no `scroll-margin-top`.** The heading is an anchor target like any provision and pays the same `--sticky-h` toll; without it the panel lands behind the reading chrome. `.sourcepanel > h2` now spends the token, like `.section-body [id]` does.
  - The indicator is a small inline island, not a spinner component: rendering the source redline is a *server* round trip over the expensive diff, so there is nothing to show but a line beside the link that was clicked. It is inserted after the paragraph rather than after the anchor (a spinner mid-clause), carries `role="status"` so the wait is announced and not merely drawn, and honours `prefers-reduced-motion`. Modified clicks (new tab/window) get no indicator, because the wait is not happening on this page. Both source links carry `data-source-render`; without script they still work, which is the whole no-JS contract.
  - Two whitespace defects of the kind BUILDLOG 029 catalogued, in the markup touched here: Astro keeps the newlines inside an element, so the anchors rendered as ` available as a source redline ` — an underlined space either side — and the sentence after one read "redline ." Both fixed by closing the tag against its text.
- **Produced:** `frontend/src/pages/diff/[...identifier].astro`, `frontend/src/styles/site.scss`, and a new `frontend/tests/e2e/diffsource.spec.ts`.
- **Verified:**
  - `make test` **441**, `make test-web` **159**, `make test-e2e` **56** (53 + the three new) — all green against the compose stack.
  - The three new e2e tests are the ones only a browser can answer: the link lands on the same page with `.diff-view--source` rendered (not on the API), `#source` is *painted* at its own top edge rather than behind the chrome (`elementFromPoint`), and the indicator exists at click time. That last one needed the click dispatched and the DOM read in the **same task** — any Playwright query races the navigation the click starts, and the document it would query is already gone, which is why the first version of the test failed against working code.
  - The `beyond-guids` branch is not reachable from the dev corpus (Title 16 + 5 at two release points give `identical` or a real text change), so the reworded sentence was rendered by forcing `delta` to `beyond-guids` in a temporary patch, screenshotted at 1280px, and the patch reverted — confirmed with `diff` against a pre-patch copy.
  - The indicator was looked at in both themes at 1280px, following BUILDLOG 029's method note: the first placement put the spinner in the middle of a sentence, which no test would have failed.

## 032 — 2026-07-31 — Session 15: the chrome a public site needs

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Pull `main` and deploy; then nine things — (1) Swagger UI and ReDoc are not rendering, review and fix; (2) an SVG favicon reading "USC", legible at every tab size; (3) an About menu item leading to the footer's "A conceptual redesign…" text; (4) disable Login and Sign Up, with text explaining that a future version will offer accounts — alerts on provisions and titles, favourites — and put that text on My Provisions too; (5) a disabled Downloads control explaining that bulk downloads could be part of the API later, refreshed from OLRC; (6) a search guide covering both the citation forms and the OpenSearch grammar we support, with tests that the documentation is accurate; (7) the search bar's right edge is obscured by the Go button; (8) a Congress.gov-style copy widget, but more elegant — text / citation / citation + text / link, chosen by a key combination or a toggle at the top of the column; (9) mid-session: the footer menu's links are underlined and the top menu's are not, make them consistent.
- **Decided / found:**
  - **Deploy** is the local compose stack, agreed with the user before starting. The AWS path (ADR-0020) is still blocked on the two things no code can supply: an IAM identity that can create EC2/IAM, and a domain for Caddy's certificate.
  - **The docs pages were a 200 with a blank body (ADR-0032).** FastAPI loads Swagger UI and ReDoc from `cdn.jsdelivr.net`, its favicon from `fastapi.tiangolo.com`, and ReDoc's typefaces from Google — six requests, every one refused by ADR-0030's `default-src 'self'`. Nothing on the server said so; `curl` returned perfect markup. Both bundles are now vendored under `static/apidocs/` with a URL and a sha256 per file, verified by `scripts/vendor_apidocs.py --check` from the test suite. `tests/test_apidocs.py` asserts what the CSP was asserting silently: **no `src` or `href` in either page names another origin**, and every same-origin asset each page names answers 200.
  - **One CSP directive was added and it was earned rather than assumed:** `worker-src 'self' blob:`. ReDoc builds its search index in a Blob worker; with no `worker-src` the browser falls back to `script-src`, which has no `blob:`, so `/redoc` rendered *in full* and its search box returned nothing for every query. Measured before and after — 0 hits, then 8. Naming the directive is what keeps the widening narrow: it changes nothing about what may execute in the page.
  - **The favicon is one file** (`static/favicon.svg`) served at the root by the API, because `/favicon.svg` is not under `/app`. Drawn for 16px and allowed to look plain at 64: full bleed, `textLength` with `lengthAdjust` so the word fits whatever font a renderer has, and its own dark-scheme rule so a navy square does not vanish into a dark tab strip. Rasterized at 16/24/32/64 and looked at, twice — the first version was a **blank tab**, because an SVG comment must not contain a double hyphen and the explanation in it contained an em dash. That parse error is silent; `tests/test_apidocs.py` now parses the file as XML.
  - **About is a page, not an anchor to the footer (ADR-0034 context).** The disclaimer is the most important sentence on the site for anyone arriving from a search engine and it was eight-point grey type below the fold. An anchor would scroll them to the same small print; the page has room for the thing they need next, which is how to check the text.
  - **Accounts and Downloads are built-and-off, and say so (ADR-0034).** One constant each in `lib/features.ts`, one copy of the wording, four places that render it. The control is an ordinary **enabled** button: `disabled` hides the explanation from keyboard and screen-reader users, and `aria-disabled="true"` — the fix for that — is a falsehood, since the button does have an action and always performs it. Playwright caught that by refusing to click it, which is the correct refusal. `popover` + `title` gives the pop-up and the hover text with no JavaScript.
  - **The search guide now documents both halves of the one box, and both halves are tested.** `lib/citationforms.ts` lists 14 accepted citation shapes and the identifier each resolves to, plus two documented limits; `tests/test_citation_forms.py` runs every example through `citeparse.parse_citation` and fails if any disagrees — including the limits, because a limit that quietly starts working is as much a documentation bug as a form that quietly stops.
  - **The search bar's right edge was USWDS's, not ours.** `[type="search"]` is shipped **unscoped** by the search package: `border-right: none`, both right radii to 0, `float: left`. Right inside `.usa-search`, where the submit button supplies the edge; wrong for a box with a gap and a separate button. Measured before touching anything — `border-width` computed to `1px 0 1px 1px`. Restored, plus `padding-right` so the browser's own clear button stops sitting on the text.
  - **The copy widget (ADR-0033)** puts a control beside every identified provision, a four-mode toggle above them, and Shift/Alt/Ctrl as a per-click override. Link mode writes a `text/html` flavour as well as plain text, so it pastes as a real hyperlink labelled with the citation. **Every citation and URL is computed on the server** (`lib/cite.ts`, the inverse of `citeparse.py`) and shipped as JSON, so the formatting is unit-tested and the island is left with only DOM work and the clipboard.
  - **The footer's links now match the navbar's** — no underline at rest, underline on hover and focus. Of the two treatments the navbar's is right: underlining every item in a row of navigation turns a menu back into a paragraph.
- **Produced:** `docs/adr/0032`, `0033`, `0034`; `static/` (favicon + vendored bundles + manifest); `scripts/vendor_apidocs.py`; `tests/test_apidocs.py`, `tests/test_citation_forms.py`; `frontend/src/lib/{features,cite,citationforms}.ts`; `frontend/src/components/{ComingSoon,AccountsOff,CopyColumn}.astro`; `frontend/src/pages/about.astro`; `frontend/tests/{cite.test.ts,e2e/copy.spec.ts}`; and edits across `main.py`, `deploy/Caddyfile`, the header, footer, section page, syntax guide, the four account pages and `site.scss`.
- **Verified:**
  - `make test` **474**, `make test-web` **185**, `make test-e2e` **74** — all green against the rebuilt compose stack.
  - **Both docs pages driven in a real browser**, console watched: Swagger UI renders with zero errors; ReDoc renders and its search returns 8 hits for `release` where it returned 0 before the `worker-src` change. The one remaining console message is Redocly's own logo from their CDN, which stays blocked and degrades to text.
  - **All four copy modes read back off the clipboard** in Playwright, plus the modifier override, the toggle's persistence across a navigation, and that a modifier does *not* rewrite the stored mode.
  - **`--sticky-h` re-measured at eight widths after the nav grew.** Two new items pushed the wrapping nav in the 40–64em band to another row: **386px against a 352px token**, so every anchor jump in that band was landing 34px behind the chrome. Corrected to 25rem (400px, 14px headroom); 640–800px now measure 386, 900–1000 measure 342, 1024+ measure 289. Re-check with the anchor-jump assertions in `sticky.spec.ts`.
  - `make shots` regenerated, now including `/app/about`; phone (375px) checked for horizontal overflow and dark mode checked with the coming-soon panel open — which is how the last defect of the session was found, and it is BUILDLOG 029's method note earning its keep again.
- **Two bugs worth keeping, both invisible to every test that was passing at the time:**
  - **The copy island shipped doing nothing, for one build.** It is rendered *above* the statutory text, so an inline script runs before `.section-body` exists: `querySelector` returned null, the guard returned cleanly, no error, no console output, no failing assertion. It now waits for `DOMContentLoaded`, and `copy.spec.ts` exists mostly to catch that class of failure.
  - **The coming-soon panel's prose did not wrap.** `.authnav` is `white-space: nowrap` so the account control can never wrap the chrome's row — and a `popover` is in the top layer but is still a *descendant* for inheritance, so three paragraphs rendered as three very long lines clipped at the panel's edge. Only visible by opening it and looking.

## 033 — 2026-07-31 — Session 16: an "i" beside the search box, then saying things plainly

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Five things, each arriving while the previous one was still running — (1) a branch adding an information "i" after "Search or go to a citation", noting that the keyword search uses OpenSearch and OpenSearch syntax and linking to the syntax guide; (2) pull `main` and open a PR for it; (3) review the README for accuracy and fluidity, with no choppy or pedantic-sounding phrases; (4) the guide says a search covers the law in force "unless you name a release point" — say *how* to name one, and if release points are not indexed yet, say that it is a future feature; (5) review all of the text on the site and make it more natural: the explanatory phrases sound stilted and self-congratulatory.
- **Decided / found:**
  - **The "i" is a `popover` and ships no JavaScript.** Same platform feature as `ComingSoon` and the citation preview (ADR-0024) — top layer, `Escape`, light dismiss. The search box is a plain GET form that works with scripting off (ADR-0023), so explaining it must not be the thing that needs a script. It sits **outside the `<label>`**, because a control nested in a label has the label's click stolen from it: the "i" would focus the input and never open.
  - **It cost the sticky chrome 5px, measured rather than assumed.** The circle is 18px and the label's line box is 13px, so the label row grew at every width from 640px up — and `--sticky-h` is what `scroll-margin-top` spends, a token that has now drifted three times. A negative block margin takes the difference back out of the *outer* height: 0px at all eight widths after. `sticky.spec.ts` asserts the **delta** — measure, remove the button from the layout on the same page, re-measure — rather than an absolute number that would drift with every other change to the chrome.
  - **18px is not a touch target,** so `::after` grows the pointer target to ~44px without growing the box. Growing the button would have put the chrome back into the measurement it had just passed. The test clicks 8px outside the visible circle.
  - **The README had been describing Session 6.** 271 Python and 42 frontend tests against **474 / 187 / 74**, with the third suite unmentioned though CI has required it since Session 10. **Four ADR links were broken**, including the dedupe ADR the headline 91% figure cites — `0007-content-dedupe-on-guid-stripped-content-key.md` has never existed. Watchlists were advertised as a live reader feature (ADR-0034 switched them off); search was missing entirely; `?release=119-102` was not a published label; `make verify --deep` is spelled `make verify-deep`; and the corpus table read "58 titles × 381 release points", which multiplies to 22,098 rather than 3,153. The quickstart also never mentioned that `docker compose` has refused to start without `SEARCH_PASSWORD` since Session 13, so a fresh clone following it failed on the first command.
  - **The guide promised a point-in-time search and never said how to ask for one.** There is no control in the box, so the answer is `&release=` or `&date=` on the results URL — now a section of its own with worked examples, linked from the top of the page and from the sentence that used to end the subject.
  - **The limit is stated rather than left to be discovered.** The index holds one document per section as it reads *today*, so a search at a release point finds provisions whose current text was already in force then and misses text that has since been replaced: a section amended in 2024 is not searchable as it read in 2019, even though the reader will show you that version. That is a missing index and not a missing feature — `ingest.reindex_search --all-versions` writes the ~490k superseded documents against the 66k the default search reads, and has not been run here. A search that quietly under-reports is worse in a legal corpus than one that refuses.
  - **Documenting `&date=` found a matching gap in the pager.** It rebuilds its href through `searchHref`, which took `release` and not `date`, so **page two of a dated search reverted to the law in force** — same query, same result count in the heading, different text underneath. Both are carried now, with the vitest case that would have caught it.
  - **The explanatory copy kept complimenting the design instead of stating the fact.** "Which is what makes the whole history fit", "that is the check worth knowing about", "because that is the reading itself rather than a departure from it", "it is computed on request because it is the expensive one", "so it says so rather than inventing one". The pattern behind all of them is the "X rather than Y" construction and the appositive stacked between em dashes, so most of the fix is splitting one clever sentence into two plain ones and deleting the clause that admired the decision. **No fact changed**: where a sentence carried a caveat — the reader's redline covers the displayed text only, a stored fragment carries the guids of the release its text first appeared at, an appendix citation parses and then finds nothing — the caveat is still there and said more directly.
  - **Two strings were leaking the repo into the reader's view.** The version-history page printed a literal "(CLAUDE.md gotcha 10)", and the search guide explained that a space "is why a plain two-word search is narrower than it used to be" — a comparison to a version of the site nobody outside this repository has ever seen.
  - **One correction to the brief, and it mattered.** The example rewrite supplied read "stored once, avoiding deduplication"; storing text once *is* deduplication, so the sentence shipped as "avoiding duplication". The 91% is also the share of stored text that is a republication rather than the share of release points, and the published sentence says so.
- **Produced:** two branches, opened as PRs against `main`. `feature/search-info-button` (`2047c55`) — `SiteSearch.astro`, `site.scss`, and eight new browser tests across `chrome.spec.ts` and `sticky.spec.ts`. `docs/accuracy-pass` (`4ac5913`, `c53e355`, `710a9f1`) — `README.md`; the release-point section of `frontend/src/pages/search/syntax.astro` with `searchHref`'s `date` option and the pager fix in `search.astro`; and the copy pass across about, index, goto, search, syntax, releases, settings, versions, diff, docs, 404, `AccountsOff.astro` and the copy constants in `lib/{features,citationforms,searchsyntax}.ts`.
- **Verified:**
  - `make test` **474**, `make test-web` **185 → 187**, `make test-e2e` **74 → 82** on the info-button branch, all green against the rebuilt compose stack; `astro check` 0 errors.
  - **The "i" costs 0px of sticky chrome at 375, 414, 640, 700, 800, 900, 1024 and 1280px**, measured by hiding the button and re-measuring the same page. Before the negative margin: 5px at 640–900 and 6px at 1024–1280.
  - **Every relative link in the README resolves**, checked by walking the Markdown link targets against the filesystem — which is how the four broken ADR paths were found, one of them present since the file was written.
  - `make shots` regenerated at 375px and 1280px, which also re-asserts that no page scrolls sideways at either width.
  - Point-in-time search checked against the live API before documenting it: `?q=conservation` returns 738 results and `&release=119-99` returns 611, naming the release it searched.
- **Note on method:** four of the five requests arrived mid-turn, while work on the previous one was still running. Each was finished and committed on its own branch before the next was started, which is why the session produced two reviewable PRs rather than one branch holding an unrelated pile.

## 034 — 2026-07-31 — Session 17: a red CI that was the test's fault, and a 500 with the answer in memory

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Three things, each arriving as the previous one finished — (1) the checks don't pass on the server, fix them; (2) where did the "i" go on the search bar; (3) `/app/us/usc/t3/s301?release=114-139` doesn't work.
- **Decided / found:**
  - **The failing check was the test racing the browser, not the widget.** `copy.spec.ts › each mode copies what it says it copies` had failed every CI run since the copy column landed (BUILDLOG 032, ADR-0033) and passed locally every time. The trace artifact settled it rather than reasoning did: the page snapshot taken at the moment of the assertion shows the status line reading **"Link copied"**, with the clipboard still holding the previous mode's text. The write worked; the read was early. `click()` returns once the click is dispatched, and the island writes the clipboard in a promise nothing on the test's side awaits — and **link mode is the one that loses that race**, because a `ClipboardItem` carrying a text/plain and a text/html blob resolves measurably slower than `writeText`. CI's single worker on a slower machine lost it every run.
  - **The fix waits for the page's own signal, not for a duration.** Every clipboard read now goes through `copyWith()`, which clicks, waits for the announcement that mode makes, then reads. The four modes are worded differently, so this is an exact event rather than a sleep — which matters in a suite whose config says in as many words that a flaky assertion about timing is a bug in the assertion and that retries would hide the thing it exists to measure. Four other tests in the file were winning the same race by luck and go through it too.
  - **The "i" was never missing.** No code change: the local frontend container had been built at 22:27 UTC and `feature/search-info-button` merged at 22:33, so the running reader was one merge behind its own repository. Recorded because the failure mode is worth knowing — `make dev-all` does not rebuild, so after a merge the reader can silently serve the previous build, and the symptom is a feature that "disappeared" rather than an error.
  - **A 500 whose answer was already in memory.** 3 U.S.C. § 301 carries **242 distinct cross references**; `/api/v1/labels` bounds one call at 100 identifiers, because the list fans into one `IN (...)` (ADR-0029); the reader asked for all 242 at once; the API answered 422; `Promise.all` rejected; and the route handler discarded a section it had already fetched in full.
  - **The bound's stated justification was an estimate, and it was wrong.** The comment read *"the densest section in the corpus carries a few dozen cross references; 100 is well clear of that"*. Measured over all 489,738 stored section versions: the densest carries **1,011**, and **4,221 of them carry more than 100**. So this was not one bad URL — roughly 0.9% of stored versions were an unconditional 500 in the reader, and had been since the bound landed in Session 13. The comment now carries the measurement instead of the guess.
  - **Two faults, so two fixes.** `fetchLabels` batches at 100 and caps a page at 1,200 identifiers — the input is a *document*, and letting one decide how many requests the reader makes is the thing ADR-0029 exists to stop; the measured worst case of 1,011 fits under it. Separately, **the labels call is now allowed to fail**: it is hover text over citations that are already links, and the section's words are in hand before it runs, so losing it should cost a tooltip rather than the statute. The preview endpoint had the same fault in a smaller frame — its existing `catch` was replacing the provision with an error note — and got the same treatment.
  - **The batch size and the bound are one number in two languages,** which is the pair that drifts silently: raising `max_length` costs nothing visible and lowering it puts the 500 back. `tests/test_rate_limit.py` now reads `LABELS_PER_REQUEST` out of `frontend/src/lib/api.ts` and asserts both against the value FastAPI actually enforces — the second link between the two suites, after `test_search_syntax.py`, and for the same reason.
  - **No new ADR.** Both changes implement bounds ADR-0029 already decided rather than deciding anything new; the one arguably novel rule — *enrichment may fail, the document may not* — is recorded here and in the code comments rather than promoted, which is a judgement a later session is free to overturn.
  - **The rich-clipboard write still has no plain-text fallback,** and that is now a decision rather than an oversight: if `ClipboardItem` genuinely throws (older Firefox, a page served over plain HTTP on a non-localhost host), the reader is told "Could not copy" and gets nothing, where a bare URL would do. Raised, and explicitly left unchanged this session.
- **Produced:** two branches, both merged. `fix/copy-clipboard-race` (`0cfc785`, PR #9) — `frontend/tests/e2e/copy.spec.ts`. `fix/labels-dense-sections` (`59cdca3`, PR #10) — `frontend/src/lib/api.ts`, `frontend/src/pages/us/usc/[...identifier].astro`, `frontend/src/pages/preview/[...identifier].ts`, `api/routes.py`, `tests/test_rate_limit.py`, and a new `frontend/tests/labels.test.ts`.
- **Verified:**
  - `make test` **474 → 475**, `make test-web` **187 → 194**, `make test-e2e` **82**, all green locally against the rebuilt compose stack, and **all three green on CI for both PRs** — which is the point, since CI is what was red.
  - The reported URL answers **200** and renders **244 distinct citations in three batched requests**, labelling the 131 the database can resolve. The other 113 return `{}` when asked individually too — repealed sections and subsection-level refs the endpoint does not resolve — so they are the API's answer, not batching losses.
  - The corpus measurements above are reproducible from the loaded database: count `href="/us/usc/` occurrences per `section_versions.xml` row.
  - **No e2e test for the labels fix, deliberately.** The densest section in CI's fixture corpus is 16 U.S.C. § 1801 at 75 references — under the bound — so an end-to-end assertion would pass with or without the fix, which is worse than no test. Real cover would mean a fixture title carrying a section over 100 references in `make ci-data`. The batching is covered directly in Vitest with a stubbed `fetch`, where what is under test is the *shape* of the request.
- **Note on method:** the CI failure was diagnosed from the uploaded trace rather than by re-running the suite until it broke. The suite is configured `retries: 0` and had failed four consecutive runs, so the artifact was the cheaper and the more honest evidence — and it named the cause outright, which repetition would not have.

## 035 — 2026-08-01 — Session 18: the doctor pass, and a CLAUDE.md that had become a second build log

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** `claude doctor`, then `/doctor` — a full health check of the Claude Code setup, with the findings applied.
- **Decided / found:**
  - **The installation was clean and needed nothing.** One native install at 2.1.220 (`~/.local/bin/claude`), matching `installMethod`; no npm-global copy and no `~/.claude/local` leftover; `~/.local/bin` on `$PATH`; all four config files parsing; no hooks anywhere; no agent-definition files, so no collisions. 2.1.220 is also the latest on the `latest` channel, so the update attempt `claude doctor` reports as failed had left nothing behind — there was nothing to fetch.
  - **`CLAUDE.md` had grown into a second build log, and was being paid for every session.** At 46,298 bytes (~11.6k est. tokens) it tripped Claude Code's large-memory-file warning, and **over half of it was one 25,307-character paragraph** — a session-by-session narrative of Sessions 10–15 and Days 4–6 that `BUILDLOG.md` (179 KB, one entry per session) and the 34 ADRs already hold in full, cited by number in the very same sentences. A file that restates the build log is a file that goes stale against it.
  - **The rule applied was derivability, not length.** Cut what a session could reconstruct by reading the repo; keep what it could not. So the narrative went and the **"Open debts:" list stayed** — that aggregation exists nowhere else — as did the Gotchas, Identifier semantics, the Architecture rules, the Fixtures counts, Documentation duties, and External source etiquette. The `Stack:` paragraph lost its dependency list (that is `pyproject.toml`) and kept the two things the manifests cannot say: why `UV_PROJECT_ENVIRONMENT=/opt/venv` is set, and how `db/config.py` and Alembic's `env.py` share one `DATABASE_URL`.
  - **The kept passages were lifted programmatically, not retyped.** The "Open debts" list, the "Test speed rule", and the `**Next:**` line were sliced out of the original paragraph by string index and re-inserted byte-for-byte — the one way a 25k-character edit does not quietly reword a debt it was supposed to preserve.
  - **The `python -m ingest …` reference became a skill** (`.claude/skills/ingest-cli/SKILL.md`) rather than being deleted: it is a command reference needed when ingest runs and at no other time, so only its one-line description stays resident. The `make` targets stayed in `CLAUDE.md` — they are the everyday entry points. `## Model assignment` became a pointer to **PLAN §7**, which was verified to hold the same table with an extra Rationale column.
  - **Result: 46,298 → 23,954 bytes, ~11.6k → ~6.0k est. tokens in every session,** and under the warning threshold.
  - **One unused MCP server disabled for this project** (`MCP_DOCKER`, zero invocations across 31 transcripts / 5 days). Its tools are deferred, so this bought no context — it is decluttering, and recorded as such rather than dressed up as a saving.
  - **No permission allow-rules were added, which was the finding.** All 13 denials in the window were either this repo's own `Read(./.env)` deny rule doing its job or genuinely write-capable commands (`alembic downgrade`, `python3` heredocs, `git reset --hard`). Auto mode became the default permission mode in user settings; that is a machine setting and touches nothing in this repo.
- **Produced:** branch `chore/trim-claude-md` — `CLAUDE.md` (trimmed), `.claude/skills/ingest-cli/SKILL.md` (new), this entry. Machine-local changes outside the repo: `permissions.defaultMode: "auto"` in `~/.claude/settings.json`, `MCP_DOCKER` added to this project's `disabledMcpServers` in `~/.claude.json` (backup at `~/.claude.json.doctor-backup`).
- **Verified:**
  - `CLAUDE.md` byte count 46,298 → 23,954, checked against `git show HEAD:CLAUDE.md | wc -c`.
  - Every kept section still present after the splice: 17 Gotchas, 5 Architecture rules, 5 Documentation duties (27 numbered bold items total), both fence delimiters balanced, `Open debts:` / `Test speed rule` / `purge_login_failures` / `HEAD is 405` all still matched by grep.
  - The whole edit is reversible with `git checkout CLAUDE.md`; nothing was committed before review.
  - **Re-check the context claim with `/context`** — the figures here are disk-based estimates at characters/4, not a live measurement.

## 036 — 2026-08-02 — Session 19: the site went up, and four things that looked like something else

- **Tool/model:** Claude Code, Fable 5.
- **Asked:** Plan and execute the AWS deployment — the app, the preprocessing, and the search index, with GitHub Actions deploying pushes to main automatically. Containerize everything, keep the images in the cloud, keep it cheap, and parallelise the work across agents on the cheapest models that would do it reliably. Goal: a high-performance demo for a few hundred people, meant to convince an LRC-familiar audience.
- **Decided:**
  - **Followed ADR-0020's shape unchanged** (one EC2 box, compose, Caddy, data on a separate volume) and added what it left open in **[ADR-0035](docs/adr/0035-images-from-ecr-deploys-from-actions.md)**: images built by Actions on native arm64 runners and pushed to ECR, deploys by SSM running a repo-versioned script, a `pg_restore` fast path beside `load-all`, and the weekly corpus update — which **moves ADR-0013's one-writer role onto the site box**, the backfill machine having finished its job.
  - **`t4g.large`, not `t4g.medium`.** ADR-0020 never reconciled OpenSearch's 2 GB heap with a 4 GB box; 8 GB is that arithmetic actually adding up. ~$60–65/month all in.
  - **Three file-disjoint tracks in parallel worktrees on Sonnet** (images/compose, workflows/scripts, docs), reviewed and merged here. Provisioning and every judgement call stayed on the orchestrator.
  - **The repo went public** rather than putting a deploy key on the box — checked first that neither the tree nor any of the 206 commits carried a credential.
- **Produced:** PRs #14–#18. `.github/workflows/deploy.yml`, `update-corpus.yml`; `deploy/` gained `admin-grant.sh`, `admin-grant-bootstrap-policy.json`, `provision.sh`, `bootstrap-box.sh`, `deploy-on-box.sh`, `update-corpus.sh`, `alarms.sh`; multi-stage `frontend/Dockerfile`, `aws` CLI in the API image, ECR image refs and real healthchecks in `docker-compose.prod.yml`, `/app/healthz`, a compose-lint CI job; ADR-0035; a rewritten `docs/deploy.md`; and `docs/deploy-status.md` as the live picture.
- **Found — four failures that each named the wrong thing:**
  - **`docker compose` was never installed.** AL2023's `docker` package is engine, CLI and buildx only, and the distro ships no compose package at all — so `docker compose -f …` failed with `unknown shorthand flag: 'f' in -f`, because docker had never heard of `compose` and read the `-f` as its own.
  - **A tag-targeted SSM command cannot be polled.** `Commands[].InstanceIds` is empty for one *permanently*, not briefly, so the workflow reported "Could not resolve the target instance" while the box was running the deploy perfectly well. Both workflows now resolve the instance by tag and send by id.
  - **GitHub's OIDC `sub` carries immutable numeric ids** — `repo:aih@217356/uscode-redesign@1314203308:ref:refs/heads/main`, not the documented `repo:OWNER/REPO:ref:…` — so every assume was denied against a trust policy that read as correct. Diagnosed by having a throwaway workflow print the token's claims instead of guessing a fifth time.
  - **`iam:PassRole` is required by `AddRoleToInstanceProfile` without appearing in it.** The bootstrap policy was derived by reading the script's `aws iam` calls, which is exactly how that one gets missed; the run died with the group, role and profile already made.
  - Also caught before it bit: `--image-id resolve:ssm:…` makes `RunInstances` call `ssm:GetParameters`, and fails with an error naming SSM rather than the AMI.
  - **The seed dump would have shipped 1,301 test accounts and 1,343 sessions to production.** ADR-0034 turned accounts off in the reader and deliberately not in the API, so those were live credentials behind a working signup route. Re-dumped with `--exclude-table-data` for the six auth tables; the nightly backup deliberately keeps them.
- **Verified:**
  - Instance `i-06b433caacd78fd96` at `52.1.30.78`; all five services healthy, migrations applied, images pulled from ECR.
  - The whole Actions path proven as far as it can be: OIDC assume, both arm64 builds, ECR push, SSM dispatch. The box-side deploy then ran to completion.
  - Seed dump verified before upload — nine corpus tables carry data, zero auth tables do — and its TOC read back with `pg_restore -l`.
  - `make test-slow`'s CI failure investigated rather than accepted: **not** a streaming regression. On aarch64 Linux peak RSS is flat against file size (0.3 MB → 19 MB, 23 MB → 31 MB, 33 MB → 33 MB), `MALLOC_ARENA_MAX` changes nothing, macOS gives 48 MB, and only GitHub's x86_64 runners report 551 MB. The box is arm64, so `load-all` is memory-safe there.
  - A mono-font "fix" was **reverted** after checking what it actually touched: the rules belong to `.usa-input` and friends, which the search box puts on every page, so it would have changed how form controls render for a cosmetic reason no test could catch.
- **Left for the morning:** the DNS A record (the one blocker for TLS), confirming the SNS subscription, merging #17 and #18, and the search index — see `docs/deploy-status.md`.
- **Postscript, the search index.** The 490k superseded-version pass exposed a real bug — `session.execute(stmt).yield_per(n)` calls `yield_per` on the *Result*, by which point psycopg has buffered every row, so selecting `SectionVersion.xml` across 489,738 rows costs ~3.5 GB and was OOM-killed twice. Passing it as an execution option on the statement is what opens a server-side cursor: measured on the full corpus, 1,020 MB and climbing at 60k rows before, a flat 283 MB after. **Every failure *after* that fix was this repository's own deploy pipeline**: each docs push to `main` went green, fired `deploy.yml` on `workflow_run`, and `deploy-on-box.sh` ran `compose up -d`, recreating the `api` container and killing the `exec` inside it — three deploys, three deaths, timestamps matching, with `systemd-oomd` inactive, `dmesg` silent, cgroup `oom_kill 0` and dockerd logging `hasBeenManuallyStopped=true`. That is [ADR-0035](docs/adr/0035-images-from-ecr-deploys-from-actions.md)'s named cost met in the wild. Two of my own errors are recorded in `docs/deploy-status.md` rather than smoothed away: a `MemoryMax` backstop that constrained the wrong cgroup and was then wrongly blamed, and running the pass as `--recreate --all-versions` so that a mid-run failure left no search at all instead of a partial index.

## 037 — 2026-08-02 — Session 20: nobody was getting the alarms, and nothing recorded that we were still looking

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Review the deployed site, finish the remaining deployment to-dos, work out why the email alerts never arrived, and review the update mechanism — the app should poll uscode.house.gov periodically, download and process what is new, and record when it last looked (no more often than daily, no less often than weekly).
- **Decided:**
  - **[ADR-0036](docs/adr/0036-record-every-check-of-the-source.md): poll daily, record every check, and say so on the page.** A new `source_checks` table takes a row on every poll — *including the ones that fail*, which is the point: a corpus that has stopped being updated is indistinguishable from a corpus with nothing to update, from the outside and from the inside. `python -m ingest check` fetches the page, records the attempt, and signals through its exit code (0 nothing new, 10 new release points, 1 the check failed) so the shell that decides whether to run the expensive chain cannot fail open on a mis-parsed answer.
  - **Daily on the box, weekly `--force` from Actions.** Daily is the ceiling as well as the floor — the source publishes a few dozen times a year, so polling a static page harder would be rude for no gain — and the weekly sweep becomes the backstop that repairs a half-finished load rather than the thing that notices new law. The two schedules fail independently, which matters because GitHub disables scheduled workflows on a repository quiet for 60 days.
  - **`GET /api/v1/status` reports two facts and refuses to collapse them:** what is loaded here, and when this deployment last confirmed that is everything published. `behind_by` is `null` rather than `0` when the last check failed — "we don't know" is not "nothing". `/app/releases` says it in one sentence, as a quiet line when the answer is reassuring and a warning alert when it is not.
  - **A stopped checker is now an alarm.** `USCode/SourceCheckStale`, with `treat-missing-data breaching` — the only alarm here that does that, because a checker that has stopped publishes nothing at all and an alarm that went quiet with its metric would be silent for exactly the reason it exists.
  - **The box's schedule became a file.** `deploy/install-crons.sh` writes `/etc/cron.d/uscode` whole and `bootstrap-box.sh` calls it; the three jobs that were there had been typed in by hand and existed nowhere else, so a rebuilt box would have come up looking healthy except that it had quietly stopped checking for new law.
- **Found — why no alarm mail ever arrived:** the `uscode-alerts` topic reads `SubscriptionsConfirmed: 0, SubscriptionsPending: 1, SubscriptionsDeleted: 1`. **Nobody has ever received an alarm.** The `Deleted: 1` is the first confirmation link expiring — AWS drops an unconfirmed subscription after three days — so "click it later" silently became "you need a new one". The five alarms were healthy and correctly wired the whole time, which is the trap: a topic with no confirmed subscriber looks exactly like a working one. Two further things fell out of diagnosing it:
  - **The deploy policy denied the call that would have shown this.** `sns:ListTopics` and `sns:ListSubscriptions` are account-wide and do not support resource-level permissions, so scoping them to `uscode-*` denied them outright — an `AccessDenied` for a permission the policy appeared to grant. Split into a second statement on `Resource: "*"`, with `ListSubscriptionsByTopic` and `GetSubscriptionAttributes` added.
  - **`deploy/alerts-status.sh` now answers "is anyone receiving these?"** in one command, and exits non-zero when the answer is no.
- **Produced:** ADR-0036; migration `b7d41c9e05aa` and `db.models.SourceCheck`; `ingest.inventory.poll_source` / `record_source_check` and `python -m ingest check`; `Repository.last_source_check` + `SourceCheckInfo` (with `SOURCE_URL` and `SOURCE_CHECK_STALE_AFTER` living in `storage.repository`, so the API can name the source without importing the ingest layer); `GET /api/v1/status`; `frontend/src/lib/currency.ts` + `SourceCurrency.astro` on `/app/releases`; `deploy/alerts-status.sh`, `deploy/install-crons.sh`, a rewritten `deploy/update-corpus.sh` with `--check-only`/`--force`, the `uscode-source-check-stale` alarm, `--force` on `update-corpus.yml`; `tests/test_source_check.py` (10) and `frontend/tests/currency.test.ts` (11).
- **Verified:**
  - `make test` 485, `make test-web` 205, `make test-e2e` 82 — all green.
  - `python -m ingest check` run against the live page: 382 release points, newest `119-102not101` (2026-07-12), `nothing new since the last check`, exit 0. `/api/v1/status` then reported `stale: false`, `behind_by: 0`, and `/app/releases` rendered "Checked uscode.house.gov for new release points in the last hour."
  - The failure paths are the tested ones: a poll that cannot reach the page, and a page whose markup no longer parses, both record a check with `ok: false` and `release_points_seen: null` — not zero, which would be a different lie.
  - A fresh SNS confirmation was sent to the alarm address at 16:00 UTC; `deploy/alerts-status.sh` still reports 0 confirmed until someone clicks it, and says so with a non-zero exit.
- **Left for the box:** `sudo bash deploy/install-crons.sh` once (deploys do not touch `/etc/cron.d`), `deploy/alarms.sh` once for the new alarm, and `deploy/admin-grant.sh` under an admin profile for the SNS policy — all three in `docs/deploy-status.md`.

## 038 — 2026-08-03 — Session 21: the site was being read, just not by people

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Continue where the last session left off — the deployment's open items.
- **Found first, because it changed what the session was about:** the two items `docs/deploy-status.md` listed as outstanding had both resolved themselves. `deploy/alerts-status.sh` reports `confirmed: 1, pending: 0, deleted: 0` — somebody will receive an alarm from this site for the first time — and the fact that the script *runs at all* proves the admin re-run of `admin-grant.sh` happened, since it needs the `Resource: "*"` SNS grant that re-run added. What was left was the thing nobody had looked at.
- **Found — the box was pinned, and the alarm that said so had been read backwards.** `uscode-cpu-credits-low` was still in `ALARM`, and `deploy-status.md` had already written down what that would mean after a quiet day: *the instance is undersized for what is being asked of it*. Half right. The box sat at load average 2.06 on 2 vCPUs, `api` burning 132% CPU, with **nobody reading it**. One hour of proxy log:

  | | |
  |---|---|
  | requests | **43,068** (~12/s sustained) |
  | ClaudeBot | 33,937 (79%) |
  | GPTBot | 9,079 (21%) |
  | everything from a human browser | **~48** |
  | carrying `?release=` | 36,465 (**85%**) |
  | requests for `/robots.txt` | 5, **all 404** |

  The 85% is the whole diagnosis: the crawlers had found the version dimension. Behind it are 65,938 sections × 382 release points ≈ 25 million reader pages, plus 96,185,732 `?id=` guids, every one returning real law with a real 200. No crawl budget finishes that, so the load had no natural end. The site had never served a `robots.txt` — not a permissive one, none — so this was not a crawler misbehaving. It was a site that had never said anything, being taken at its word. On a `t4g` in unlimited mode the surplus credits are billed, so it was also the one part of the deployment quietly costing more than the estimate.
- **Decided — [ADR-0037](docs/adr/0037-disallow-the-crawl-while-the-demo-is-a-demo.md): `Disallow: /`, from the Caddyfile, for now.** Served by the proxy rather than by either surface because `robots.txt` belongs to the *host*, and under ADR-0015 one Caddy owns the host — that is what makes one answer true for `/app` and `/api/v1` alike, and what stops the policy drifting between a `frontend/public/` file and a FastAPI route. The blunt setting was Ari's call and is recorded as a choice rather than a default: the site is a demo, discoverability is worth nothing yet, and blunt is what is correct on the least information. The shaped version — index the ~66k canonical current-text sections, refuse the permutation space — is written into the ADR so returning to it is a decision and not a rediscovery. ADR-0029's rate limits were never going to catch this: they bound the expensive *routes* (57 diff requests in that hour, throttled and fine), and the section reader is cheap per request and correctly unthrottled. The problem was never per-request cost.
- **Found — two live deployment bugs, both surfaced by trying to ship one file.**
  - **Nothing in the deploy had ever restarted the proxy.** `deploy/Caddyfile` is a bind mount, and `compose up -d` recreates a container when its *service definition* changes; a mounted file's bytes are not that, and Caddy reads its config once at start. So every Caddyfile change since the box was built would have reached it via `git checkout --force` and then sat there unserved, under a green deploy.
  - **`caddy reload` is the obvious fix and is wrong** — which I found by writing it, shipping it into the local stack, and watching it fail. A single-file bind mount binds an **inode**, not a path, and `git checkout` replaces the file rather than rewriting it, so the new bytes land where nothing in the container is looking. Measured: `docker inspect` still lists the mount while `/etc/caddy/Caddyfile` is *gone* inside the container and `/etc/caddy` is empty. Reload would have reloaded a file that is not the one in the repository and exited 0 having done it — the same silent failure with a reassuring log line over it. `deploy-on-box.sh` now force-recreates the proxy, then greps the served `robots.txt` over `--resolve` against the real hostname, because a deploy script whose failure mode is *looking successful* should assert what it is serving.
- **Produced:** ADR-0037; the `handle /robots.txt` block in `deploy/Caddyfile`; proxy recreate + served-config check in `deploy/deploy-on-box.sh`; `caddy validate` in CI beside the compose parse (the Caddyfile is a bind mount, so a syntax error in it is caught by no image build and no compose parse, and would take both surfaces down *after* the deploy replaced the running config); `frontend/tests/e2e/robots.spec.ts` (2). Commits `770798d`, `fb4b3cc`, `440c238`, plus docs.
- **Verified:**
  - `make test` 486, `make test-web` 205, `make test-e2e` **84** (was 82) — all green.
  - `caddy validate` against the real `caddy:2-alpine` before committing; the served body is exactly `User-agent: *\nDisallow: /` by `od -c`, so the heredoc's newlines are real. The e2e test asserts the line *shape*, not just the substrings, because a heredoc that lost its newlines would pass the substring check and parse as one meaningless line.
  - Live on the box after deploy: `curl https://uscode.linkedlegislation.org/robots.txt`.
- **Verified — ADR-0036's daily check ran unattended**, which is the claim it actually makes and one that could not be made on 2026-08-02, when every check so far had been typed by a human. `source_checks` holds a row at **06:41:04 UTC from the box's own cron**, `nothing new since the last check`, start to finish in **6 seconds** — one HTTP request and one row, the cheap path the ADR designed for the ~360 days a year when OLRC publishes nothing. The weekly Actions sweep also ran green **on its own schedule** for the first time (10m30s), having previously only been proven by `workflow_dispatch`. The two `source_checks` rows 88 seconds apart at 10:52 are ADR-0036's named cost — two checks on a day the full chain runs — here caused by the `--force` sweep rather than by new law.
- **Left owed:** the nightly `pg_dump` to `s3://uscode-mirror-dreamproit/usc/db/` has **no expiry** — 2.2 GB a night, ~66 GB a month, growing linearly, against a cost estimate that does not include it. The deploy user cannot even read the current lifecycle setting, so it needs an admin profile. Alarm *delivery* was listed here as unproven and is not: Ari confirmed the AWS mail arrives, which closes a chain this deployment has been checking a link at a time — the alarms exist, they point at the topic, the topic has a confirmed subscriber, and a human receives what it sends. That last link is the one that had been silently broken since the box was built.
- **Then, on Ari's correction — "there is no need for a nightly `pg_dump`: the US Code data changes infrequently."** Right, and a better fix than the S3 lifecycle rule I had written down as owed: the cheapest backup is the one never taken. The nightly cron wrote 2.2 GB every night at 04:17 UTC, ~360 near-identical copies a year of a corpus OLRC republishes a few dozen times a year. It now runs at the end of `update-corpus.sh` **gated on `load-all` having actually written something** — not on the mode the script was called in, because the weekly `--force` sweep reaches that point having loaded nothing on most weeks (last Monday: `planned 3153: 0 loaded, 3153 skipped`), and that run should not produce a backup. It is taken *after* the `verify` gate, since a dump taken before it could preserve exactly the corruption the gate exists to catch and would be the copy someone restores from. **A latent bug went with it:** the cron ran under `bash` with no `pipefail`, and `pg_dump | aws s3 cp -` with a `pg_dump` that dies half way is an `aws` that uploads what it got and exits 0 — a truncated dump, named like a backup, logged as a success. `update-corpus.sh` sets `pipefail`, and a failed dump now exits non-zero. Retention still needs an admin profile, and deliberately so: the instance role has `s3:PutObject` on `usc/*` and **no `s3:DeleteObject`**, so the one writer of the corpus of record cannot delete it. Commit `25d9a0f`; `sudo bash deploy/install-crons.sh` re-run on the box, since deploys do not touch `/etc/cron.d`.
- **Verified, three hours on:** the crawl stopped. Both bots fetched the new `robots.txt` within minutes and went away — 16 requests in 30 minutes against ~718/min before, load average 2.06 → **0.12**, `api` 132% CPU → **0.12%**. The new cron is installed on the box (`pg_dump` no longer appears in `/etc/cron.d/uscode`) and `update-corpus.sh --check-only` runs green there against the live source. One thing left open rather than closed: `uscode-cpu-credits-low` is still in `ALARM`, unchanged since 2026-08-02, because the balance must climb back over 60 and a `t4g` in unlimited mode repays accrued surplus before rebuilding it. It should clear on its own now the box is idle; if it has not after a quiet day, the undersizing reading is the one left standing.
- **Then: the retention rule, as `deploy/mirror-lifecycle.sh`.** The dangerous version of this is the one-liner, because `put-bucket-lifecycle-configuration` **replaces** a bucket's whole configuration rather than merging, and this bucket holds the corpus of record (ADR-0013) beside the dumps — an unscoped expiry rule would delete the 9.7 GB of release-point zips and would look like a working retention policy right up until it did. Every rule is scoped to `usc/db/`; the script refuses to overwrite a configuration it did not write, and refuses when it cannot *read* one. **That second refusal exists because the first draft had the bug:** `get-bucket-lifecycle-configuration || true` collapses `NoSuchLifecycleConfiguration` and `AccessDenied` into the same empty string, so run with the deploy profile — which cannot read a lifecycle configuration — it announced "none — this will be the first" and would have replaced whatever was there. Found by running it rather than by reading it. Also expires noncurrent versions (the bucket is versioned, so expiring a current object only writes a delete marker and goes on billing the version behind it) and aborts incomplete multipart uploads (the dump is streamed with `pg_dump | aws s3 cp -`, so a dump that dies half way leaves billed parts that `aws s3 ls` does not show — one per failed dump, forever, in exactly the case nobody inspects). Commit `7940639`; still needs an admin profile to actually run.
- **Closed out:** Ari confirmed the AWS alarm mail arrives (so the alarm chain is proven end to end, not merely wired), and created the two `usc/db/` lifecycle rules through the S3 console. Two rules rather than one because S3 rejects `ExpiredObjectDeleteMarker` alongside a day-based expiration in the same rule — the console enforces it by disabling the checkbox. **The permission question was the interesting part:** `deploy/mirror-lifecycle.sh` refused under `AWS_PROFILE=uscode-admin`, and the reason is that **`uscode-admin` is not an admin** — it is the profile name for the IAM user `linkedlegislation-deploy`, which `docs/deploy-status.md` has said in its box table since the box was built and which still caught us. The `uscode` profile is `uscode-mirror-dreamproit-user` and is denied the same call; both are object-level identities, so *no credential on this machine can set or read a bucket lifecycle*. Added `deploy/mirror-lifecycle-bootstrap-policy.json` for the attach/run/detach path, and made the script's refusal name the confusion rather than telling someone to "use an admin profile" when they believe they did. **Recorded as a limitation rather than smoothed over:** the rules are *reported*, not measured — `s3:GetLifecycleConfiguration` is denied to everything here, so it is the one claim in `deploy-status.md` that rests on a console rather than on a command anyone can re-run, and it says so.

## 039 — 2026-08-03 — Session 22: a user guide that runs

- **Tool/model:** Claude Code, Fable 5 (planning) then Opus 5 (execution).
- **Asked:** A detailed markdown → HTML user guide, updated as the application develops, serving as the basis for regression testing and an automatically-generated demo video with captions highlighting the functionality.
- **Found first, and it decided the design:** `/app/search/syntax` carried a summary box headed "Not the whole picture yet", telling readers the search index held current text alone and that a point-in-time search therefore answered from the present. True when written; false since 2026-08-02, when the superseded pass finished on the box (489,578 documents, 423,649 of them superseded — `docs/deploy-status.md`). The site had been advertising a limitation it no longer had, for a fortnight, and nothing was ever going to notice. A user guide is that failure mode at ten times the surface area, so the question was not how to write one but how to write one that cannot rot.
- **Decided ([ADR-0038](docs/adr/0038-the-user-guide-is-executable.md)): the guide is executable.** Three parts, one source. Chapters are `.md` pages in `frontend/src/pages/guide/`, rendered by Astro against a `GuideLayout` named in their frontmatter — no markdown dependency, no build step, the site's own chrome and theme, and still plain markdown on GitHub. Each behavioural claim carries a ` ```scenario ` fence beside the prose it supports, and that block is simultaneously the walkthrough a reader follows, a Playwright test, and — when flagged `demo: true` — a captioned scene of the demo video. `scripts/scenarios.mjs` is the single reader of them; `scripts/remark-scenario.mjs` renders them as the "How this is verified" box.
- **And a ratchet, which is the part that makes "kept up to date" true.** `frontend/tests/guide.test.ts` fails when a route under `src/pages/` is in no chapter's `covers.routes`, or an ADR is in neither a chapter's `covers.adrs` nor an explicit infrastructure exemption list. Adding a reader page or a decision now turns `make test-web` red until the guide accounts for it. The exemption list keeps that to one line for work with no reader-visible surface; 14 of 38 ADRs are on it, and each entry says why.
- **Produced:** nine chapters (~1,400 lines of prose) covering what the site is, reading, reading at a point in time, version history and redlines, search and citations, working with the text, accounts, the API, and how to check the site; 25 scenarios, 13 of them demo scenes; `make demo-video` → a 158-second captioned mp4. Commits `2ca0c85` (chapters served), `e81766f` (runner + ratchet + the remaining chapters), and this one. The stale search box is rewritten against what `deploy-status.md` records, including the 160-document ADR-0021 shared-`_id` gap it had never mentioned.
- **Verified:** `make test` 486 green, `make test-web` 213 (was 205: +8 ratchet), `make test-e2e` 109 (was 84: +25 scenarios, 2 skipping without the full corpus). The runner was checked by sabotage — changing one scenario's expected text to `45zzz` failed that test and only that test. The ratchet was checked the same way: it was red on arrival, listing all 13 undocumented routes and 17 unclassified ADRs, and went green as the chapters claimed them. `make shots` passes its no-horizontal-scroll assertion on the new pages at 375px and 1280px. `make demo-video` produces 13 scenes, 32 caption cues, and frames extracted from the mp4 show the caption bar rendering over the real site.
- **Two things the first build got wrong, both fixed rather than worked around.** Globbing the chapters at module scope read a chapter's frontmatter from inside its own import cycle (chapter → layout → glob → chapter) and 500'd every guide route; the read is deferred to render time, where the cycle has unwound. And a sticky contents column honouring `--sticky-h` as its `top` offset started 320px down the page, because that token is a scroll-margin budget rather than a measurement of the chrome — the column is not sticky.
- **Named costs, in the ADR:** the step vocabulary is nine verbs and deliberately cannot express what `preview.spec.ts` and `sticky.spec.ts` assert, so the guide suite proves the documented path works and not that the feature is correct; CI runs scenarios against Title 16 at two release points, so a `data: corpus` scenario is a weaker claim than a default one; and the mp4 is gitignored and regenerated by hand, so nothing enforces that the current video matches the current guide — `scenes.json` and the `.vtt` are committed so at least its content is reviewable in a diff.
- **Left owed:** the video has no title card and no cursor visualisation, both considered and cut; `make demo-video` is not in CI and should not be, but nothing yet reminds anyone to re-run it before showing the site.

## 040 — 2026-08-03 — Session 22b: the video that was uploaded, fetched, and never written

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** The guide merged and is live, but `/app/demo` shows no video.
- **Found:** the page was fine and all three assets 404'd. On the box, `/var/lib/uscode/demo` existed, was **owned by root**, and was empty. `deploy-on-box.sh` runs `compose run api` for the migration *before* the demo fetch, and that instantiates the api service including its volumes — so Docker created the bind-mount directory as root. The fetch runs as `ec2-user`: `mkdir -p` succeeded because the directory was already there, and every `aws s3 cp` failed with `EACCES`. Nothing was wrong with S3, the credentials, the mount, the CSP or the player.
- **What made it slow to see, and the more interesting bug:** the fetch loop treated *every* failure as `"${asset} is not published yet — skipping"`. So the deploy log said, reassuringly, that nobody had recorded a demo — while the truth was that it had found the video and could not write it. A permission error reported as an absence. That is the same failure shape this repository has hit twice before (BUILDLOG 038's `get-bucket-lifecycle-configuration || true` collapsing `AccessDenied` into `NoSuchLifecycleConfiguration`; the `pg_dump | aws s3 cp` pipeline exiting 0 on a truncated dump), and it is worth naming as a pattern: **an error path that cannot tell "absent" from "denied" will always report the reassuring one.**
- **Fixed, in two places.** On the box, `chown ec2-user:ec2-user /var/lib/uscode/demo` and re-ran the fetch — the video has been live since. In the code, `deploy/publish-demo.sh --fetch` now takes ownership when the destination is not writable (rather than depending on running before whichever compose command creates it — the order is not a guarantee, since any command touching the api service creates that directory), and distinguishes a missing object via `s3api head-object` from a failed write, which is now an `ERROR` line and a non-zero exit. `deploy-on-box.sh` still swallows that exit deliberately: no demo video should ever fail a deploy.
- **Also fixed, and my error:** the "next steps" `publish-demo.sh` printed after a successful upload were wrong three ways and failed with `UnrecognizedClientException` when Ari ran them — no `AWS_PROFILE` (so `default`, whose credentials on that workstation are invalid, rather than `uscode-admin`), `--targets Key=tag:` (which reports an empty invocation list and looks like it did nothing — `deploy.yml` resolves `--instance-ids` first for exactly that reason), and `cd /opt/uscode` (the checkout is `~ec2-user/uscode-redesign`, reached with `sudo -iu ec2-user`, since SSM runs as root). Worse, suggesting the command at all: the box cannot fetch anything until it has the script and the volume mount, and both arrive with the code, so the first publish is a merge. That commit missed PR #19 and is cherry-picked here.
- **Verified:** against the live host, not locally. `poster.png` 200 `image/png`, `uscode-demo.vtt` 200 `text/vtt`, `uscode-demo.mp4` 206 `video/mp4` for a range request (so seeking works). In a real browser on `https://uscode.linkedlegislation.org/app/demo`: `duration` 160 s, `readyState` 4, `paused` false with `currentTime` advancing, `videoWidth` 1280, and one text track `showing` with **32 cues**.
- **Left owed:** nothing new. The video remains the one manually-published artifact in the project (ADR-0038's named cost) — re-recording it and re-publishing is still a human step, and nothing checks that the deployed mp4 matches the current guide.

## 041 — 2026-08-03 — Session 23: something that measures the accessibility claim

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Workstream A task A1 — build an accessibility harness and make it a CI gate, before any of the workstream's fix tasks, "because every later task cites findings by rule id, and without the harness you will be guessing at which of them are real on your build." The in-flight user-guide edits on this branch were stopped on instruction and left uncommitted.
- **Found first, and it justified the ordering.** A throwaway probe at 1280px showed the reader completely clean and every violation on the API documentation pages — which, had it been the whole scan, would have been a comfortable and wrong answer. The full matrix says otherwise: **the USWDS mobile nav is unreadable in dark mode** (`#565c65` on `#1c1d1f`, **2.5:1** against a required 4.5:1) on every reader page at 320px and 375px, and clean at 1280px, which is exactly why nobody had seen it. The copy column keeps the USWDS primary blue in dark (2.71:1). Guide chapter 08's code blocks render a syntax token at **1.11:1** — in light, in dark, and under forced-colors. And **the citation preview carries `aria-hidden="true"` and `tabindex="0"` at the same time**, so while it is open it is in the tab order and hidden from assistive technology at once. That last one is invisible to any scanner that only loads URLs, which is the argument for the interactive states being in the matrix rather than a later nicety.
- **Decided ([ADR-0039](docs/adr/0039-accessibility-is-a-ratchet-in-the-browser-suite.md)): axe-core runs inside the existing Playwright suite, over a declared route matrix, and fails the build on anything not recorded as known.** `docs/a11y/routes.json` declares 26 route entries — one expanding to every guide chapter on disk, so a tenth chapter is scanned the day it lands — three viewports, both themes, a `forced-colors: active` pass and six interactive states. `frontend/tests/e2e/a11y.spec.ts` scans against `wcag2a`/`wcag2aa`/`wcag21a`/`wcag21aa`. `docs/a11y/known-violations.json` is the ratchet, and every entry carries the task that owns the fix.
- **Why axe-in-Playwright rather than pa11y-ci or a Lighthouse budget:** one browser suite, one set of fixtures, and the states are reachable. Both alternatives take a list of URLs; neither can open a hover preview by keyboard focus, click a copy button and scan what the page announced, or toggle a theme and scan what changed. The spec reuses `preview.spec.ts`'s and `copy.spec.ts`'s own selectors rather than a second, drifting description of the same widgets. A fourth test runner was ruled out by the session rules anyway.
- **Produced:** `frontend/tests/e2e/a11y.spec.ts`, `a11y-report.ts` (the shard format and merge), `frontend/scripts/a11y-setup.ts` / `a11y-teardown.ts`, `docs/a11y/routes.json`, `docs/a11y/known-violations.json`, `docs/verification/a11y.json`, ADR-0039, `make test-a11y`, the 320px and 1280px-at-200%-zoom rows in `make shots`, and the guide's accessibility section in chapter 09.
- **Verified:** `make test` 486 green; `make test-web` 213 green; `make test-e2e` **355** (was 109; +245 a11y, 2 skipped without the full corpus), **1m45s**. The scan itself is **244 scans in ~1m20s**, producing 41 route/rule pairs over 2,251 nodes: 1 critical, 40 serious, 0 moderate, 0 minor. Re-check with `make test-a11y` against `make dev-all`; the artifact is `docs/verification/a11y.json`. **The ratchet was checked by sabotage in both directions** — deleting the `aria-hidden-focus` entry failed exactly the `preview-focus` state with "not in docs/a11y/known-violations.json", and downgrading ReDoc's `select-name` waiver from `critical` to `moderate` failed all seven of its scans with the severity mismatch named. `make shots` passes, and its new 320px row found a real 3px horizontal overflow on `/app/docs`, now recorded with an owner.
- **Named costs, in the ADR.** **The gate is weaker than the task specified**, and this is the one deliberate deviation: A1 asked that serious and critical violations fail regardless of the known-violations file. Every serious and critical violation on this build already exists and each is owned by a later task in the same workstream, so a literal gate lands the harness red and fixing them here would be five other tasks in one commit. `waiveSeverity` is the compromise — a serious regression still defaults to a red build, and each exception is a dated, owner-signed line that must name the exact impact it waives, so a moderate that becomes critical still fails. **axe adds ~1m20s to every push**, and a new guide chapter adds seven scans by itself. **Listing routes explicitly taxes new pages**: the dark-nav entry names 25 routes rather than using a wildcard, so a new page inherits no waiver. **`make shots` now commits 48 PNGs (2.6 MB) rather than 24 (2.2 MB).**
- **Two calibrations against the standard rather than the instruction.** A1 asked for captures at "320px and 1280px at 200% zoom"; 320 at 200% lays out in **160 CSS px**, and WCAG 2.1 AA asks for reflow down to 320 and no further, so asserting there fails the build on something the standard does not require — measured, the demo URL scrolls sideways by 86px. The rows that ship are 320 CSS px (1.4.10's floor, which 1280 also reaches at 400%) and 640 (1280 at 200%, which is 1.4.4). The seed matrix's "429 rate-limited response" is also not scanned: forcing one means hammering ADR-0029's budget from inside the suite that shares it, which makes every other test in the run flaky — A6 and A8 assert that degradation behaviourally instead.
- **One Playwright trap, worth the line.** A `globalSetup` inside `testDir` is loaded as part of the *config*, and every spec under that directory is then loaded in the config's context — where `test.describe()` throws "did not expect test.describe() to be called here" and the whole suite collects as **zero tests**, silently, with a "No tests found" that reads like a bad `--grep`. The hooks live in `frontend/scripts/` for that reason.
- **Carried along, not mine:** `CLAUDE.md`'s documentation-duty 7 (guide prose describes behaviour, not rationale) arrived uncommitted from the previous session and is included in this one's `CLAUDE.md` commit.
- **Candidate tasks found, not fixed (scope discipline).** `/app/us/usc` answers **400** and `/app/us/usc/t5a/s3` answers **404** in the reader, so neither is in the scan matrix — the appendix case is the known citation gap, but a reader 404 where the API explains is its own defect. `html-has-lang` on `/docs` and `/redoc` is ours rather than the vendor's: those shells come from `get_swagger_ui_html` and `get_redoc_html` in `main.py`, and it is a one-line fix that A4 now owns. And `docs/verification/a11y.json` is regenerated by any full `make test-e2e`, so it will show up in `git status` after an unrelated run.
- **Left owed:** A2 through A10. `docs/a11y/manual-protocol.md` (A9) does not exist, so the half of WCAG 2.1 AA axe cannot see is unmeasured, and no conformance statement is published (A10) — `/app/accessibility` is named in the matrix's exclusions with the instruction to add it in the same commit that adds the page.

## 042 — 2026-08-04 — Session 24: the inline set was written from memory

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Workstream A task A2 — add `date` to the inline element set in `frontend/src/lib/uslm.ts`, then audit the whole inline/block partition against the USLM vocabulary rather than fixing one entry, with a table-driven Vitest case per element so the next omission is a one-line addition.
- **Measured rather than guessed, and that is the whole of it.** `scripts/inline_elements.py` counts, for every element across the four committed USLM 1.x and 2.x samples, how often it sits beside a non-whitespace text node — the empirical form of "occurs in running prose", and the same question the renderer has to answer. 18 elements do. `docs/verification/inline-elements.json` is the artifact; re-run with `uv run python scripts/inline_elements.py`.
- **`<date>`: 20,513 occurrences in running prose and zero anywhere else.** It was in neither the inline set nor anyone's memory of it, so it fell through to the `<div>` at the bottom of `renderElement` — a block in the middle of every sentence in every editorial note. CLAUDE.md had carried it as a formatting nuisance; it is WCAG 1.3.2, because a block reorders the sequence a screen reader announces mid-sentence in the one part of the page a drafter reads for amendment history. `<footnote>` is the same shape: 1,051 inline, 0 isolated.
- **Decided ([ADR-0040](docs/adr/0040-inline-or-block-is-decided-per-occurrence.md)): a name is not always enough, so elements the source uses both ways are decided per occurrence.** `<note>` is an editorial note 30,981 times and a footnote marker inside a sentence 883 times ("…the Act of March 1, 1872, *1 See References in Text note below.* reserving lands…"); `<quotedContent>` is a block quotation 875 times and a quoted phrase 2,701 times. Classified by name, whichever way it goes, thousands of occurrences are wrong. `CONTEXTUAL_TAGS` + `inRunningProse(el)` asks the markup instead, and marks the inline case `.uslm-inlined`.
- **The same bug was in the redline.** `collectBlocks` (ADR-0026) has `note` in `LINE_BREAK_TAGS`, so an inline footnote marker flushed and one sentence redlined as three blocks. Same test, same fix.
- **Where the line is drawn, with the ratios:** `<p>` 50 of 58,865, `<table>` 26 of 822, `<list>` 8 of 36, `<heading>` 3 of 87,190, `<proviso>` 2 of 5 also appear beside text and stay blocks — under 1% is the source being odd, and a `<heading>` as a `<span>` would cost the document outline that task A4 depends on more than three sentences are worth. Each is listed in the test with its ratio, so the exception is a diff rather than an omission.
- **Produced:** `scripts/inline_elements.py`, `docs/verification/inline-elements.json`, the `INLINE_TAGS`/`CONTEXTUAL_TAGS` changes and `inRunningProse` in `uslm.ts`, `.uslm-inlined` in `site.scss`, 14 new Vitest cases driven by the artifact, ADR-0040, and a `dates-read-inline` scenario in guide chapter 02.
- **Verified:** `make test` 486 green; `make test-web` **227** (was 213: +14); `make test-e2e` **356** (was 355: +1 scenario). `make shots` passes and its diff is real — the demo, section-provision and guide-chapter frames all changed. On the fixture section the page went from **12 `<div class="uslm-date">` to 12 `<span class="uslm-date">`**, and the note now reads "The Act of August 25, 1916 (39 Stat. 535…" as one sentence. **Checked by sabotage:** deleting `date: "span"` from `INLINE_TAGS` failed exactly three tests — the element's own case, the explicit `<date>` case, and the catch-all that walks the artifact — and nothing else.
- **Named costs, in the ADR.** An element's rendering now depends on its siblings, so two `<note>`s with identical content can render differently; `.uslm-inlined` is what makes that visible in the output. A `<quotedContent>` in prose whose quoted material has internal structure produces a `<span>` wrapping a `<div>` — browsers render it, validators will not like it, and the alternative is 2,701 broken sentences. **The measurement is four files, not 58 titles**, so an element that only appears in prose in some unsampled title is still classified by the `<div>` fallback; widening the sample is one command.
- **`term` and `quote` do not exist.** A2 named both as elements to check. Neither appears in any sample, in either schema, in any position. Recorded in the ADR so the next person does not go looking.
- **Side effect, worth knowing:** `CopyColumn` decides line breaks by whether a node is a block, so a date inside a note used to break the copied line and no longer does (ADR-0033).
- **Candidate tasks found, not fixed (scope discipline).** `docs/screenshots/demo-video-*.png` churn on every `make shots` run regardless of code changes — the `<video>` frame is nondeterministic, so those four files show as modified in every session that regenerates shots. Worth either pinning the poster frame or excluding that page from the shot set.
- **Left owed:** A3 through A10.

## 043 — 2026-08-04 — Session 25: the preview was focusable and hidden at the same time

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Workstream A task A6 — close the gap between hover and keyboard/touch on the citation preview (ADR-0024): focus opens what hover opens, Escape dismisses without moving the reading position, the card is reachable in the tab order and returns focus to the trigger, a tap on touch opens the target, and a 429 degrades to a message rather than a silent empty box.
- **The defect A1 found, fixed.** The card carried `aria-hidden="true"` **and** `tabindex="0"`. That is axe `aria-hidden-focus` and it is the one combination with no defensible reading: a keyboard user can put focus somewhere their screen reader will not describe. Invisible to any scanner that only loads URLs; ADR-0039's open-state scan found it on its first run, which is the argument for the interactive states being in that matrix.
- **ADR-0024's reasoning did not survive the mechanism.** It justified `aria-hidden` by saying a forty-reference section would otherwise announce forty paragraphs of statutory text. Removing it announces nothing: nothing moves focus on open and there is no live region, so the card is silent until a reader goes to it deliberately. The alternative ADR-0024 actually rejected — `aria-describedby` at the live card — *would* have announced, and rejecting it was right; `aria-hidden` was applied as though it were the same decision.
- **Decided ([ADR-0041](docs/adr/0041-the-preview-card-is-reachable-and-says-when-it-fails.md), amending ADR-0024 decision 4): the card is a non-modal dialog the reader can reach and leave.** `role="dialog"` with an `aria-label` set per reference, so focus arriving announces the provision rather than "dialog". `tabindex="0"` **stays** — the body scrolls, and a scrollable region with no focusable children is unreachable by keyboard without it (`scrollable-region-focusable`), so removing it would have traded one axe violation for another. Tab from the trigger moves into the card; Escape closes it and returns focus to the reference without scrolling; tabbing past either end does the same.
- **The non-obvious part: a dismissal has to latch.** Escape returns focus to the trigger, which is a `focusin` on the trigger, which is what opens the card — so the card the reader just dismissed reopened 300 ms later and Escape did nothing. `dismissed` holds the reference until attention moves elsewhere, cleared on mouseout and on focus moving to another reference. `a dismissed card does not immediately reopen itself` is the test.
- **A failure is now shown rather than swallowed.** The old behaviour — `catch { return; }` — was recorded nowhere but a code comment, which is part of why it lasted: a user-visible behaviour nobody signed. A card that silently declines to open is indistinguishable from a broken feature, from a citation with nothing behind it, and from a page that has stopped responding. It now renders "Preview unavailable" and a link to the citation; a 429 says "too many previews just now" by name, which matters because ADR-0029 rate-limits this endpoint at 60/min burst 5 and a reader moving down a dense section meets it in normal use. An `AbortError` stays silent — that is the island superseding its own request.
- **Touch needed nothing.** The feature is gated on `(hover: hover) and (pointer: fine)`, and `preview.spec.ts` already asserted that a tap opens the citation and no card ever appears. Verified, not rewritten.
- **Produced:** the rework of `CitePreview.astro`, ADR-0041, the superseded-decision marker in ADR-0024, six new/rewritten cases in `preview.spec.ts`, a `preview-keyboard` scenario and the keyboard/failure prose in guide chapter 06, and **the first entry removed from `docs/a11y/known-violations.json`** — the ratchet is one notch tighter.
- **Verified:** `make test` 486 green; `make test-web` 227 green; `make test-e2e` **362** (was 356: +6). `preview.spec.ts` is 16 tests, all green. The scan independently agrees the defect is gone: with the `aria-hidden-focus` entry deleted from the known-violations file, `make test-a11y` passes and the artifact went from **41 route/rule pairs over 2,251 nodes to 40 over 2,250**. Re-check with `make test-a11y` against `make dev-all`.
- **Named costs, in the ADR.** The dismissal latch is state, and a reference the reader dismissed behaves differently from one they have not until they look elsewhere. A failure message costs a card where there used to be none, so a reader on a failing network now gets a small box on every citation they touch — louder than silence, deliberately. The 429 message names a cause the reader cannot act on; the useful part is the link beneath it, and `Retry-After` is not surfaced. And **`role="dialog"` on something non-modal** sets an expectation of modality this does not meet — no focus trap, the page behind stays live — but it is the closest role the ARIA Authoring Practices offer.
- **One thing worth knowing for the rest of the workstream:** `make test-e2e` runs against `:8000`, which is the **docker-built** frontend, while `astro dev` on `:4321` hot-reloads. A source change is invisible to the browser suite until `docker compose up -d --build frontend`. Two runs were spent discovering that in session 24.
- **Left owed:** A3, A4, A5, A7, A8, A9, A10. Ten entries remain in `docs/a11y/known-violations.json`.

## 044 — 2026-08-04 — Session 26: the scan and the tokens miss opposite things

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Workstream A task A7 — audit contrast in both themes against every token the design defines and every one it inherits from USWDS; stop status badges encoding status by colour alone; support `forced-colors: active` and `prefers-reduced-motion`; honour `prefers-color-scheme` on first visit; commit the computed table to `docs/verification/contrast.json`, generated by a script that reads the token file rather than measured by hand.
- **Why this is not just more of A1.** ADR-0039's axe scan and a token audit miss *opposite* things, and both misses were live. The scan only sees pairs a scanned route actually renders — **no route in the matrix carried a status badge**, so nothing had ever measured one, and dark's was white on a pale red at **2.25:1**. A token audit only sees colours that are tokens — **USWDS's own `.usa-nav__link` kept its light-theme grey inside a dark panel, `#565c65` on `#1c1d1f`, 2.5:1, on every reader page**, and no token file contains either value. Neither tool alone would have found both.
- **Decided ([ADR-0042](docs/adr/0042-contrast-is-computed-from-the-tokens.md)): `scripts/contrast.py` reads the token block out of `site.scss` and computes every declared pair in both themes**, exiting non-zero on a failure so it is a check as well as a generator. 17 pairs, 34 checks, in `docs/verification/contrast.json`. The token *values* come from the stylesheet; the list of *pairs* is declared in the script, because which colour is painted on which is a fact about the design rather than about the file.
- **`--rule` is split, and that is the judgement call in this task.** SC 1.4.11 asks 3:1 of "visual information required to identify user interface components" — a field's edge, not a divider between two paragraphs. Holding both to 3:1 puts every hairline on the site at `#949494` or darker: a visibly heavier reader bought for no conformance gain. So **`--edge`** is the half that carries meaning and is held to the ratio (4.71:1 at its worst, on a dark form field), and `--rule` stays decorative — still measured, still reported at **1.15–1.89:1**, flagged `"decorative": true` so the number is on the record and the judgement is arguable rather than hidden.
- **Status badges keep their word and gain a shape.** The text was always the information — "repealed" and "omitted" are different words, printed verbatim (gotcha 13: the set is not closed). What colour adds is emphasis, and emphasis is what monochrome loses. Each known status now differs in border style; unknown ones keep the plain pill and their word. A **border rather than an icon**, because CSS `content` is announced by some screen readers and "× repealed" would be noise read to exactly the readers who needed no help.
- **Two bugs rather than choices, and both are the same underlying error — a token used for a role it was not defined for.** `.usa-alert`'s background is on `__body`, not on the outer element, so overriding `.usa-alert` left the pale slab exactly where the text was; that is the identical shape to ADR-0027's footer note, made a second time. And `.endpoint__method` took its *text* colour from `--panel`, which inverts between themes, while its background was a fixed saturated colour — near-black on dark green in dark mode. The guide's code blocks were a third: Shiki paints the `<pre>` dark and USWDS paints every `<code>` pale, and the `<code>` is *inside* the `<pre>`, so the light syntax colours landed at **1.11:1**.
- **Produced:** `scripts/contrast.py`, `docs/verification/contrast.json`, the `--edge` / `--danger-ink` tokens and the dark overrides for nav, outline buttons and alerts, the badge border treatments, a `forced-colors: active` block and a global `prefers-reduced-motion` block (including `scroll-behavior`, so a deep link is not a smooth scroll nobody asked for), ADR-0042, the guide's colour paragraphs, and `/app/us/usc/t16/s688` added to the scan matrix.
- **Verified:** `make test` 486 green; `make test-web` 227 green; `make test-e2e` **369** (was 362; +7 scans, not new tests). `make shots` passes. `uv run python scripts/contrast.py` exits 0 with **34 checks, 0 failures**. The scan agrees independently: **`docs/verification/a11y.json` went from 41 route/rule pairs over 2,251 nodes to 8 over 1,780**, and **five entries came out of `docs/a11y/known-violations.json`**, which is now down to five — all A4 or A10, none of them the reader's own markup.
- **One clause declined, and confirmed rather than assumed.** A7 asked to "honour `prefers-color-scheme` on first visit **while keeping ADR-0027's light default explicit**". Those halves contradict each other: honouring the OS on a first visit *is* not defaulting to light. ADR-0027 decision 1 removed exactly that behaviour after a reader asked why the site was in dark mode, and `theme.spec.ts` carries a test named for it. Asked the maintainer; **light default stands**. WCAG 2.1 AA requires neither direction — 1.4.3 and 1.4.11 are about the contrast of what is shown, not which palette is chosen first — so nothing in the workstream's own target depended on it. Recorded in ADR-0042 under "What was declined".
- **Named costs, in the ADR.** The pair list is hand-declared: a changed hex is caught because the values are read from the stylesheet, but **a new token painted on a new surface is a pair nobody added**, and the script does not know to look — the axe scan is the backstop, and only on routes the matrix covers. Four badge colours are now **hard-coded** rather than tokenised, deliberately (they must not move with the theme) and therefore outside `contrast.py`'s reach. `--rule` failing 1.4.11 on paper is a judgement a reviewer can argue with, and the numbers to argue with are in the artifact. **`forced-color-adjust: none` is used twice**, on the badge and the highlighted provision — both override a reader's chosen palette, which is what the property is for and is still an override.
- **Candidate task found, not fixed (scope discipline).** The scan matrix had no route carrying a status badge for the whole of A1 and A6. Adding `/app/us/usc/t16/s688` fixed that one case, but nothing systematically checks that the matrix *exercises every component the reader can render* — a component-level inventory against the matrix would be the real fix, and would have caught this without a token audit.
- **Left owed:** A3, A4, A5, A8, A9, A10. Five entries in `docs/a11y/known-violations.json`, all vendored bundles or A4's two.

## 045 — 2026-08-04 — Session 27: the chrome was on one page out of seven

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Workstream B (`claude-code/prompts/B-navigation-ia.md`) — navigation, information
  architecture, retrieval. Scope agreed at the start of the session: **B1 and B2 together**, because
  B1's breadcrumb bullet is literally "with the release context pinned to its right", which is B2's
  requirement, and splitting them means editing the same components twice. TOC rail agreed as a left
  rail from 64em with a disclosure below. B3–B6 deferred.
- **Decided:**
  - **ADR-0043 — one navigation chrome.** `docs/ia-map.md` first, derived from the guide ratchet's
    own `readerRoutes()` rather than from memory, with every inbound link recorded as file:line.
    From it: the breadcrumb ends at the provision on screen (`usa-current`, `aria-current="page"`);
    `SectionBar`'s steps name their neighbour from 40em up; a new `ChapterRail` shows the parent
    subdivision's sections in reading order with status badges in place; `/app/versions` and
    `/app/diff` get the trail they never had.
  - **ADR-0044 — release context in the chrome.** `ReleaseContext` replaces `Provenance` and adds the
    fact it never stated: whether the release point being read is the newest. `ReleasePicker` becomes
    two GET forms offering all three ways to ask — newest, a date, a named release point — and posts
    to the *requested* identifier, so the provision survives the switch.
  - **The switcher left the sticky stack, and that is measured, not assumed.** Before: 19px of
    headroom under `--sticky-h` at 700px, 55px at 1280px; the date field costs about eighty.
    `--sticky-h` is what `scroll-margin-top` spends and `docs/backlog.md` already flags that band for
    carrying 19rem of chrome, so the control moved down to the facts it changes and the release point
    stayed pinned as text. After: 89px and 85px, asserted in `sticky.spec.ts`.
  - **`/app/versions` and `/app/diff` get no release band** — the first spans every release point, the
    second is about two. A narrower reading of B2's "every reader page" than asked for, taken
    deliberately and recorded in ADR-0044.
  - **B1 asked for deletions and there were none to make.** `/app/goto` vs `/app/search`, the three
    prev/next affordances and the two from/to pickers were each checked and are each one path;
    recorded in the map so the question is not re-opened. The real defect was the opposite —
    `/app/settings` reachable from no rendered page, `/app/diff` two hops from the text it compares.
  - **The guide's scenario DSL gained a `select` verb.** `fill` cannot drive a `<select>`, and
    "switching release keeps the provision you were reading" is the claim that most needed executing.
- **Produced:** `docs/ia-map.md`; `docs/adr/0043`, `docs/adr/0044`;
  `frontend/src/components/{ChapterRail,ReleaseContext}.astro`; `Provenance.astro` deleted;
  `Breadcrumbs`, `SectionBar`, `ReleasePicker`, `Base.astro`, `middleware.ts`, `site.scss`, the
  section/versions/diff pages; guide chapters 02 and 03; `scripts/scenarios.mjs` +
  `tests/e2e/guide.spec.ts` (`select`); `tests/e2e/sticky.spec.ts`;
  `claude-code/WORKSTREAM-B-STATE.md`. Branch `workstream-b-navigation-ia`, 6 commits from `387ff3a`.
- **Verified:**
  - `make test` — 486 passed. `make test-web` — 227 passed, including the ADR-0038 ratchet, which is
    what forced chapters 02 and 03 to claim ADR-0043 and ADR-0044.
  - `make test-e2e` — 373 passed, 251 of them the a11y scan. `docs/verification/a11y.json` is **8
    route/rule pairs over 1,780 nodes**, the same as the ADR-0039 baseline, and everything in it is
    still `docs/a11y/known-violations.json`'s.
  - `make shots` — no horizontal overflow at 320 CSS px or 1280 at 200% zoom, apart from the known
    3px on `/app/docs` that A4 owns.
  - The switcher, end to end against `make dev-all`, from `/app/us/usc/t16/s45f/c/5?release=119-99`:
    picking a release gives `/app/us/usc/t16/s45f/c/5?release=119-102not101`; picking a date gives
    `…/c/5?date=06/12/2026`; picking Newest gives `…/c/5` with no parameter. The
    `switch-keeps-provision` scenario in guide chapter 03 is the standing version of that check.
  - **One real bug the scan caught, not me:** the unlinked breadcrumb item was the first non-link
    text ever put in that bar, so it inherited USWDS's own breadcrumb ink — derived from
    `$theme-breadcrumb-background-color`, which assumes a light page — and failed `color-contrast`
    in dark theme on **every reader page**. Same shape as ADR-0042's `.usa-nav__link`. Fixed to
    `--ink` on `--panel`, a pair `scripts/contrast.py` already measures.
- **Candidate tasks found, deliberately not done:**
  - **`/app/settings` has no inbound link from any rendered page.** `AuthNav:49` is its only linker
    and `SiteHeader` does not render `AuthNav` while `ACCOUNTS_ENABLED` is false (ADR-0034). Guide
    chapter 06 links it in prose; that is the only way in.
  - **`previewHref` in `lib/url.ts` has no caller.** `CitePreview.astro:176` builds
    `` `/app/preview${identifier}` `` inline in browser JavaScript — a reader href built outside
    `url.ts`, against architecture rule 5, and the exact inlining `previewHref`'s docstring says it
    exists to replace.
  - **`us/usc/index.astro:22` calls `fetch` with its own `process.env.API_BASE_URL`** instead of
    going through `lib/api`.
  - **The release menu carries every release point for the title** — 115 options against the local
    corpus, 381 corpus-wide, in the markup of every section page.
  - **The deployed box returned one transient 502** on `/app/` while checking B3's prerequisites,
    then 200 on every subsequent request. Worth a look when B3 measures it.
  - `docs/verification/loadtest.json` is now stale for a fourth reason — ADR-0043's extra API call
    per section view — on top of ADR-0029, ADR-0026 and ADR-0037. B3 owns it.

## 046 — 2026-08-04 — Session 28: B3 phase 1, and the wait is not the server's

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Workstream B task B3 — navigation speed. Explicitly the **measure half only**: regenerate
  `docs/verification/loadtest.json` against the deployed box, add a navigation profile distinct from
  the load profile, report the numbers and a recommendation, and stop before any fix. Three problems
  in the task were handed over to be resolved rather than papered over: the rate limiters would shape
  the results, "the five journeys in the test plan" is a forward reference to a document that does not
  exist, and per-surface attribution needs something that does not exist either.
- **Decided:**
  - **Every load-test row names the limiter that governs it, and whether it was held inside that
    budget or driven past it.** B3's `-n 500 -c 20` against ADR-0029's budgets does not measure the
    site, it measures ADR-0029 — and badly, because 429s are produced in microseconds and read as a
    throughput *improvement* on whichever route shed the most. A limited route now gets two rows:
    `hey -q` holds a "within" row under the bucket's refill rate so the row describes the route, and
    an "over" row exceeds it on purpose so the row describes the shedding. Unlimited routes carry a
    null limiter and are the only ones whose throughput describes a route.
  - **The five journeys are derived from `docs/ia-map.md`'s "Exits to" column**, and each carries its
    derivation string into the artifact rather than citing a test plan this repository does not have:
    spine, citation, search, read-along, compare.
  - **Per-surface attribution is measured, not inferred.** The box is SSM-only, so `navprofile.py`
    ships itself there and times the *same path* at four nested vantages — the internet, Caddy over
    loopback via `--resolve` (same host, same TLS, same virtual host), the Astro container, the
    FastAPI container. Every subtraction is between two measurements that differ by one layer.
  - **No SQL is written into the query profile.** `spine_explain.py` attaches a
    `before_cursor_execute` listener, runs `PostgresRepository`'s own spine calls, and re-runs each
    captured statement under `EXPLAIN (ANALYZE, BUFFERS)` with the same parameters. What is explained
    is what was executed, by construction — the property ADR-0040 gives the USLM partition.
  - **A journey is timed on one connection**, because a browser reuses one; the first step of each
    journey pays the TLS handshake and `connects` is recorded so a slow first step is not read as a
    slow page.
  - **Recommendation carried to the human, not acted on.** The numbers reorder B3's list: fixes 1, 2
    and 4 all target the API/Postgres side, which is 37 ms of a 78 ms origin inside an 823 ms journey.
    Proposed doing fix 4 (one index), fix 3 (the byte budget), and the measured half of fix 2 (drop
    `/api/v1/releases?title=` from the per-view fan-out); proposed **not** building a Caddy cache
    layer for fix 1, because the headers are already correct for a shared cache and what is missing is
    a shared cache to read them, which is a deployment decision rather than a code one.
- **Produced:** `scripts/navprofile.py`, `scripts/spine_explain.py`, `scripts/spine_explain.sh`;
  `make navprofile` and `make spine-explain`; a rewritten `scripts/loadtest.sh`;
  `docs/verification/{loadtest,navprofile,spine-explain}.json`. Branch
  `workstream-b-navigation-ia`, 3 commits on top of session 27's seven.
- **Verified:**
  - `make test` — 486 passed. `make test-web` — 227 passed. `make test-e2e` was **not** run: this
    session changed no application source, only scripts and artifacts. It runs before B3's fix half is
    called done.
  - **A reader's four clicks down the spine cost 823 ms, of which 221 ms is the origin and 601 ms
    (73%) is the network.** Re-check: `jq '.attribution'` over `navprofile.json`.
  - **Section page, warm p50, by layer:** 117 ms internet and TLS, **41 ms Astro's own render**, 37 ms
    for the five API calls' critical path, ~3 ms of that in Postgres, and Caddy the remainder.
    **Caddy's own share is at the resolution limit of this method and cannot be stated more precisely
    than "small":** across the twelve warm steps it ranges 0.3–11.1 ms, and the section page measured
    twice — once as the spine's fourth step, once as read-along's first — gives 0.4 ms and 11.1 ms for
    the same page. It is not the bottleneck; that is all these numbers support.
  - **ADR-0043's fourth call is free in wall clock.** The parent TOC costs 16 ms and runs in the same
    `Promise.all` as `/api/v1/releases?title=` at 20 ms, so the page's API cost is unchanged by it. It
    is also the fastest API row under load: 61.9 rps, 116.9 ms p50, 2,168 wire bytes. The question
    session 27 left open is answered.
  - **The transient 502 did not recur** — 813 timed nav-profile requests across four vantages, every
    one a 200, plus a full load test.
  - **The reader page is the origin's limit, not the API.** 195 ms for one reader; 702 ms p50 and
    11.0 rps at 8 concurrent on 2 vCPUs. The TOC page: 526 ms, 14.4 rps. The JSON routes hold up.
  - **`/api/v1/releases?title=N` is the slowest unlimited API route** — 247 ms p50, 30.6 rps — and it
    is fetched on every section page *and* every TOC page to fill a picker with 381 options.
  - **The API diff costs 5.1 s per request** on the box. The limiter sheds correctly (23 × 429 at
    C=10) but the requests it *admits* still exceed a 20 s client timeout.
  - **`structure_nodes` has no index on `identifier` alone.** Its unique constraint is
    `(title_id, identifier)`, which a lookup by identifier cannot use, so it seq-scans 9,916 rows at
    1.3 ms — 80% of `get_section`'s database time, and it recurs in both `get_toc` paths and
    `resolve_id`. Everything else is fine: no repository call exceeds 2 ms in Postgres, and the
    96,204,776-row `guid_map` answers in 0.035 ms through `ix_guid_map_release_id_identifier`.
  - **Cache headers confirmed live**, by the script rather than by assertion: `immutable` when pinned,
    `max-age=300` unpinned, `max-age=300` on a TOC even when pinned (ADR-0043). `HEAD` is still 405
    where `GET` is 200.
- **Two methodology errors found and paid for, both recorded in the scripts:**
  - **Neither script asked for compression.** curl sends no `Accept-Encoding` unless told, and Caddy
    only compresses what asks — so the first pass timed every reader page at 76,021 bytes against the
    21,246 a browser receives, attributing transfer time to the network that no reader spends. Both
    runs were discarded and redone with `--compressed`, under which `%{size_download}` reports wire
    bytes.
  - **`curl -X HEAD` only changes the method.** curl still waited for a body the 405 never sent, exited
    18, and `set -e` discarded a completed 35-minute run with every row measured and nothing written.
    `-I` is curl's own HEAD; every probe in the checks block is now non-fatal for the same reason.
- **One thing the artifact records as empty on purpose:** `checks.diff_retry_after_header`. The probe
  asks sequentially, and the diff bucket refills one token every five seconds while the endpoint takes
  about five seconds to answer — so a caller making one diff at a time is never shed. The 429 and its
  `Retry-After` are observed in the over-budget row, where concurrency is what exceeds the bucket.
- **Candidate tasks found, deliberately not done:**
  - **Astro's own render is the largest single component of the origin cost** — 41 ms against 37 ms
    for all five API calls' critical path — and the reader page, not the API, is what collapses under
    concurrency. Profiling inside the Node process is a task of its own, and it is not on B3's list.
  - **The box's own throughput ceiling is unmeasured.** At C=8 over a ~120 ms round trip the ceiling
    is 8 ÷ 0.12 ≈ 65 rps as arithmetic, and the fast rows all sit just under it, so they describe the
    link rather than the box. Measuring the box needs a load generator running on it, which is not
    something to install on production during a measurement session.
  - **The load test speaks HTTP/1.1 while the nav profile speaks h2.** `hey` has an `-h2` flag and
    `scripts/loadtest.sh` does not pass it; curl negotiates h2 by default. So the two artifacts'
    latencies are not directly comparable, and the load test measures a protocol no browser uses
    against this host. One flag.

## 047 — 2026-08-04 — Session 28b: B3 phase 2, three fixes and one declined

- **Tool/model:** Claude Code, Opus 5. Same session as BUILDLOG 046, after the phase-1 report was
  approved.
- **Asked:** Take B3's fix 4 (the `structure_nodes.identifier` index), fix 3 (the byte budget,
  counting inline `<script>` bytes since there are no client JS bundles) and the measured half of
  fix 2 (drop `/api/v1/releases` from the per-view fan-out), and write an ADR declining fix 1 rather
  than building a Caddy cache layer the measurements do not justify.
- **Decided:**
  - **ADR-0045 — one release list per title, held five minutes.** Entries hold the *in-flight
    promise*, not the value, so N concurrent misses make one request; a rejected fetch is evicted
    rather than cached, guarded on the entry still being current so a slow failure cannot delete its
    replacement. Five minutes is not a free parameter — it is ADR-0018's own `max-age` for an
    unpinned answer, so the reader is never staler than what it tells browsers.
  - **ADR-0046 — the byte budget is counted from source, and validated against a page.** There is no
    bundle to weigh, so the count walks each page's transitive `.astro` import graph. Counting from
    source is also what lets it run in Vitest with no server and no build, which is the requirement:
    a budget needing a running stack is a budget nobody runs, and B3 forbids a fourth runner.
  - **ADR-0047 — fix 1 declined, with the audit it asked for.** ADR-0018's policy is already correct
    on the deployed host, re-verified by the load test on every run. What is missing is a shared cache
    to read those headers; a cache on the box addresses the 27% of a reader's wait that is the origin,
    not the 73% that is the network. A CDN moves the 73%, and that is ADR-0020's territory.
  - **The guide states the cost of ADR-0045 rather than hiding it.** Chapter 03 says the release menu
    is rebuilt at most every five minutes, that `?release=` reaches a new release point immediately,
    and that the release point a page is *reading* is always read fresh. ADR-0046 and ADR-0047 are
    infrastructure in the ratchet — a test harness and a deployment decision.
- **Produced:** migration `d5c81f27a930`; `db/models.py`; `frontend/src/lib/releasecache.ts` +
  `frontend/tests/releasecache.test.ts`; `frontend/tests/jsbudget.test.ts` + `docs/js-budgets.json` +
  `docs/verification/js-bytes.json`; `docs/adr/0045`, `0046`, `0047`; guide chapter 03;
  `docs/verification/b3-fixes.md`. Six commits on `workstream-b-navigation-ia`.
- **Verified:**
  - `make test` — 486 passed. `make test-web` — **253** passed, up from 227: 7 for the release cache
    and 19 for the byte budget. `make test-e2e` — 373 passed, 2 skipped, against a rebuilt frontend
    container. `docs/verification/a11y.json` unchanged at 8 route/rule pairs over 1,780 nodes.
  - **The index changes the plan, at production row count.** Local `structure_nodes` holds 9,916
    rows, the same as the deployed corpus, because the table is the newest loaded release's view
    rather than something that grows per release point (ADR-0006). Seq Scan 1.497 ms with 9,915 rows
    removed by filter → Index Scan 0.135 ms on three buffers. Command in
    `docs/verification/b3-fixes.md`.
  - **The release call is gone from the fan-out**, counted from the API's own access log rather than
    from the reader's intentions: eight *concurrent* views on a cold cache produce **one**
    `/api/v1/releases`, a warm cache produces **none**, and it was eight. That the single-flight
    promise is what does it is visible in the concurrent case specifically.
  - **The byte budget bites.** 600 bytes injected into a component on every route's graph failed 16
    routes, each message naming that route's islands; removing the bytes passes again.
  - **The static byte count is validated against a live page**, not assumed: source says 32,150 bytes
    for `/app/us/usc`, the rendered page carries 25,474, and the 6,676-byte difference is exactly
    `AuthNav` (3,239) plus `WatchButton` (3,437) — both behind `ACCOUNTS_ENABLED` (ADR-0034). The
    page also carries **zero `<script src>`**, which is the fact the whole approach rests on.
- **A measurement error in BUILDLOG 046, found while implementing and corrected:** the reader calls
  `/api/v1/releases?**ingested_title**=16`, and both measurement scripts asked for `?title=16`. Those
  are different work — `?title=` filters in the repository, `?ingested_title=` fetches all 382 release
  points and filters in Python — and different costs: **27.0 ms against 20.1 ms** at the API
  container. So the release list was a *worse* offender than reported, and the section page's API
  critical path was 42.8 ms rather than the 36.6 ms recorded. Both scripts now ask for what the reader
  asks for. The committed artifacts still carry the old figure and are superseded on the next run;
  that is why `b3-fixes.md` says the deployed re-measurement is still owed.
- **Still owed:** the deployed re-measurement. `make navprofile`, `BASE=… make loadtest` and
  `make spine-explain` all measure the box, and the fixes are not on the box — the branch is not
  merged and not deployed. The three artifacts in `docs/verification/` remain the *before* picture.
- **Candidate tasks found, deliberately not done:**
  - **`?ingested_title=` should be a repository filter, not a Python one.** `api/routes.py` asks
    `list_releases(title_num=None)` for all 382 release points and filters the list afterwards, so the
    work does not shrink when the answer does. ADR-0045 caches around it rather than fixing it.
  - **`CopyColumn`'s JSON data island is measured nowhere.** 4,278 bytes on `/app/us/usc/t16/s45f`,
    varying per section, excluded from the byte budget because a static ceiling over it would be a
    ceiling on the statute. Measuring it needs a running server.
  - **Inline scripts ship their comments.** 25,474 bytes of inline script on a section page, much of
    it explanatory prose that only the browser downloads and nobody reads. Minifying inline islands at
    build time is a real saving and a real loss of the thing that makes them readable in `view-source`.

## 048 — 2026-08-05 — Session 28c: the deployed re-measurement

- **Tool/model:** Claude Code, Opus 5. Continues BUILDLOG 046 and 047.
- **Asked:** Open a PR and deploy. Merging turned out to *be* the deploy, which was reported before
  anything was pushed; the human merged, and this entry is the re-measurement that B3 still owed.
- **Decided:**
  - **`api_cost_ms` counts only the calls a page makes per view.** ADR-0045 stopped the release list
    being fetched per view, and the attribution arithmetic did not know: it credited a table of
    contents page with 41.2 ms of API time when the whole page took 22.1 ms, and printed a **negative**
    figure for Astro's own share on two rows. `FANOUT` entries now carry a `cached` list — still timed,
    still reported, with `per_view: false` — excluded from the critical path. The corrected
    attribution was **re-derived from the same stored measurements** rather than re-measured, and the
    artifact says so.
- **Produced:** regenerated `docs/verification/{navprofile,loadtest,spine-explain}.json`;
  `docs/verification/b3-fixes.md` gained a "Before and after" section; `scripts/navprofile.py`.
  Commits `9c35538` and this entry, on `main`.
- **Verified:**
  - **The deploy landed.** Alembic head on the box is `d5c81f27a930`, `ix_structure_nodes_identifier`
    exists, and the plan there is an Index Scan at 0.057 ms.
  - **The release cache works in production**, counted from the API's own access log on the box:
    eight concurrent section views produce **one** `/api/v1/releases`.
  - **The spine's plans, which is the one result attributable to B3 alone** — nothing else in the
    deploy touches Postgres. `get_section` 1.649 → **0.348 ms**, `get_toc` chapter rail 1.769 →
    **0.446 ms**, `resolve_id` over the 96 M-row `guid_map` 1.388 → **0.119 ms**, and
    `seq_scans_on_large_tables` is empty for all thirteen calls. Calls that never touched
    `structure_nodes` are flat: `neighbors` 0.291 → 0.308 ms.
  - **Under load, 8 concurrent:** reader TOC page 14.4 → **35.0 rps** and 525.5 → **183.7 ms** p50;
    reader section page 11.0 → **15.6 rps** and 702.4 → **480.0 ms**. The TOC page gains most, which
    is what the fan-out predicts — it made two calls and the release list was the slower one.
  - **One reader, no contention:** four clicks down the spine 823 → 801 ms at the edge, of which the
    **origin is 221 → 159 ms**. The network share is unchanged and still dominates, which is
    ADR-0047's argument restated by its own re-measurement.
- **Two reasons this is not a clean A/B, both recorded in `b3-fixes.md`:**
  - **The previous deploy was `387ff3a`** — the commit this branch was cut from — so the *before* box
    was running main with **none of B1, B2 or B3**. The after box's section page carries a
    `ChapterRail`, a `ReleaseContext` band and a `ReleasePicker` it did not have, and makes **five**
    API calls where it made four. The reader-page rows are "workstream B, all of it". That the page
    got faster while doing more is the honest reading, and a stronger one than a like-for-like would
    have been.
  - **The twelve untouched routes drifted to a median 1.073× their before p50** (range 0.995–1.123),
    same laptop and link at a different hour. The gains above are understated by about that much.
  - Related: `releases the picker can offer` reads 30.6 → 23.1 rps, but that row **changed URL** — it
    now measures `?ingested_title=`, the parameter the reader uses, rather than the cheaper `?title=`.
    The endpoint did not get slower; the measurement got correct.
- **Found, not caused, and not fixed here:** **the nightly `make test-slow` has failed every night
  since at least 2026-07-31** — `test_parsing_32_mb_stays_memory_bounded`, peak RSS 552 MB against a
  150 MB bound. It is not run by `make test`, so no session's own suite catches it. This branch
  touches nothing under `ingest/` or `storage/`, and the failure predates it by five days. Owed to
  whoever picks up the parser next.

## 049 — 2026-08-05 — Session 29: B4, search relevance measured and the query scoped

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Workstream B task B4. Propose and *measure* a scoring model rather than shipping a
  hunch — field weighting, phrase proximity, current-release boost, collapse of superseded
  versions — against a committed relevance judgement set scored by nDCG@10 before and after. Add
  explicit sort control. Note the ADR-0021 identifier-collision caveat in the results UI where it
  can bite. Audit the operator set against what a drafter asks for and document each with an
  executable scenario. Add facets, reflected in the URL so a search is citable. Mid-session: pin
  the section page's chapter rail so it does not scroll with the text.
- **Decided:**
  - **[ADR-0049](docs/adr/0049-search-relevance-measured-and-scoped.md)** — the ranking is chosen
    by measured nDCG@10 over `docs/verification/search-judgements.json`, and the query gains six
    `field:value` scopes lifted out before the cluster sees them, so ADR-0031's choice of the
    parser that never throws stands. Facets edit the query rather than adding a parameter beside
    it. One query builder (`storage/searchquery.py`) serves both the API and the harness.
  - **[ADR-0050](docs/adr/0050-the-chapter-rail-is-pinned.md)** — the rail is pinned from 64em with
    a bounded height and its own scrollbar, reversing ADR-0043's standing decision. The height is
    the half the first attempt was missing: `top` alone pins the rail and lets it run past the
    bottom of the viewport.
  - **`all-versions` measured and declined.** It scores highest (0.7192 against 0.7159) and changes
    what a result *is* — a section whose current text no longer carries the words becomes a hit.
    The default keeps ADR-0028's `is_current` filter and reports the rest as "also matched in N
    earlier versions", counted by a second size-0 request bounded by the page.
- **Produced:** commits `3f79851`, `36978d5`, `c1d4a12`, `e3dab92`, `9188bc2` on
  `workstream-b-search-relevance`. New: `storage/searchquery.py`, `scripts/search_eval.py`,
  `frontend/src/lib/searchscope.ts`, `frontend/src/components/SearchFacets.astro`,
  `tests/test_searchquery.py`, `frontend/tests/searchscope.test.ts`,
  `docs/verification/search-judgements.json`, `docs/verification/search-relevance.json`,
  ADR-0049, ADR-0050.
- **Verified:**
  - **The old heading weight was not the one written down.** The mapping carried a deprecated
    index-time `boost: 2.0` on `heading` *and* the query said `heading^2`; OpenSearch multiplies
    them. Explained on the pre-B4 index as a BM25 `boost` factor of 4.4 = 2.2 (`k1+1`) × 2.0, and
    `heading^4` against a boost-free mapping reproduces the old ranking **and its scores exactly**
    on all ten queries tried, where `heading^2` reproduces neither. That is why the baseline
    profile is `heading^4`.
  - **nDCG@10 over 37 queries and 529 graded documents (312 of them graded relevant)**, pooled from every candidate profile
    before grading: deployed **0.6894** → shipping **0.7159**; recall@10 **0.7672** → **0.8016**.
    Thirteen queries improve, nine get worse, fifteen do not move. Re-check:
    `uv run python scripts/search_eval.py score`.
  - **The parameters were swept, not picked**: phrase boost 2/4/8/16 (16 is much worse at 0.6519),
    slop 0/2/6, heading weight 6/10/16/24, `num.text` 0/2/8.
  - **Two counting defects found and fixed.** `hits.total` stopped at OpenSearch's default 10,000
    and reported the cap as the answer, so `q=land` claimed 10,000 and now reports 4,593; and under
    collapse it counted versions while the page listed sections, so `q=conservation&release=119-99`
    claimed 10,000 and now reports 2,963.
  - **A parser bug in both languages.** The tokenizer only recognised a quoted run at the *start*
    of a token, so `heading:"wild horses"` matched `heading:"wild` then `horses"` — a valid query
    meaning something else. Caught by `frontend/tests/searchscope.test.ts`, fixed in
    `storage/searchquery.py` and `frontend/src/lib/searchscope.ts`.
  - **The ADR-0021 collision count is now a number**: 160 (identifier, first-release) pairs across
    **49 identifiers in 14 titles**, from `_colliding_doc_ids`. Flagged on the document and shown
    on the result row.
  - **Suites:** `make test` **527** passed (was 486), `make test-web` **271** (was 253),
    `make test-e2e` **386** passed / 2 skipped (was 373). `make shots` reflow-clean at 320 CSS px
    and 1280@200% apart from A4's known 3px on `/app/docs`. `make test-a11y` **258 scans, 8
    violation/route pairs over 1,794 nodes** — unchanged from the ADR-0039 baseline, with a
    filtered-and-sorted search added to the matrix so the filled facet and sort pills are scanned
    at all. `uv run python scripts/contrast.py` — 18 pairs, 36 checks, the new
    `--danger-ink` on `--link` at 6.72:1 light and 8.13:1 dark.
  - **The local index was rebuilt** with `--all-versions`: 489,738 section versions and 9,916
    structure nodes, which is what made the `all-versions` profile measurable rather than
    hypothetical. The cluster holds **489,578** documents for those 489,738 versions, and the
    difference is exactly the 160 collisions — an independent confirmation of the ADR-0021 count,
    arrived at from the other end.
  - **A number to correct:** commit `c1d4a12`'s message says "573 graded documents". The artifact
    says **529**, of which 312 are graded relevant. The prose in this entry, `CLAUDE.md` and
    `WORKSTREAM-B-STATE.md` is right; the commit message is not, and the branch was already past it.

### Owed before this deploys

- **The deployed OpenSearch index must be rebuilt.** The mapping is not additive (ADR-0028), so
  `python -m ingest.reindex_search --recreate` has to run on the box or `title:`, `chapter:`,
  `status:`, `?sort=citation` and the collision flag are all silently empty. The deploy does not do
  this on its own.
- `docs/verification/loadtest.json` is now stale for `/api/v1/search` and `/app/search` as well as
  for the reasons already listed: the query carries a phrase clause, two aggregations and an
  uncapped count, and there is a second request per default search.

### Candidate tasks found and deliberately not done

- **`/app/search/syntax` has a heading reading "Two things that will catch you out"**, which is
  both a teaser heading and a presumption about the reader — two of the prose rules in
  `~/.claude/CLAUDE.md`. Pre-existing, on a page this session edited, left alone under scope
  discipline.
- **`?sort=citation` puts every chapter and subchapter heading of a title ahead of every section of
  it.** Structure nodes have no `seq_in_title`, so they all take position `000000`. A true position
  means deriving one from the first section beneath each node — a join `reindex_search` does not do.
  Named in the guide and in ADR-0049 rather than hidden.
- **`num.text` is unmeasured by the subject queries.** nDCG is identical at weight 0, 2 and 8. Two
  number-bearing queries were added and it moves those; a judgement set that exercised
  section-number lookup properly would be a task of its own.
- **The relevance ceiling is heading-shaped.** Every one of the six worst queries is a provision
  whose heading does not contain the words searched for — FOIA is *Public information; agency
  rules…*, § 1956 is *Laundering of monetary instruments*, § 2 is *Monopolizing trade a felony*.
  Term matching cannot close that; the `embedding` field ADR-0028 declared is where it would go.
- **The earlier-version count is only as good as what is indexed.** CI builds a current-only index,
  so no scenario can assert "also matched in N earlier versions" without `data: corpus`.

## 050 — 2026-08-05 — Session 29b: the search index rebuilds itself

- **Tool/model:** Claude Code, Opus 5.
- **Asked:** Open a PR for B4, and either write instructions for the reindex it needs or — better —
  trigger it automatically.
- **Decided:**
  - **[ADR-0051](docs/adr/0051-the-search-index-rebuilds-itself.md)** — the mapping carries a
    fingerprint, the index names become aliases over a physical index named for that fingerprint,
    and `reindex_search --if-changed` rebuilds only what drifted, **beside the live index rather
    than over it**. `deploy/deploy-on-box.sh` runs it.
  - **Automatic rather than a runbook line, because the failure is silent.** A field the new code
    queries and the old index lacks is *absent, not broken*: `title:16` filters on a field that does
    not exist and matches nothing, which is what a title with nothing in it looks like. Nothing
    raises, nothing alerts, the deploy is green.
  - **`--recreate` on every deploy was rejected as worse than the problem** — it deletes the live
    index and rebuilds 66k documents with the site up, so search answers 503 for the length of every
    deploy whether or not anything changed.
  - **A failed rebuild is not a failed deploy.** The step is `|| echo`, which is safe *because*
    nothing is promoted until everything is built: a failure part-way leaves the alias where it was,
    so the site keeps the index it had.
- **Produced:** [PR #25](https://github.com/aih/uscode-redesign/pull/25), and commits on
  `workstream-b-search-relevance`. New: `tests/test_search_mapping.py`, ADR-0051.
- **Verified:**
  - **The migration was run for real against the local cluster**, from exactly the state the box is
    in: `uscode_sections` a *concrete* index with no fingerprint. `stale_aliases` reported both
    indices stale, and the rebuild swapped them.
  - **Search answered normally throughout.** Probed mid-rebuild at 15,000 documents indexed:
    `q=conservation` returned its usual 2,937 totals and the same first result, because the alias
    still pointed at the old index. The declared fingerprints are `b8be98476068` (sections) and
    `68fa86c5cf0b` (structure).
  - **`--if-changed` is a no-op the second time** — the check is two requests.
  - **18 tests in `tests/test_search_mapping.py`**, driven against a fake cluster that records the
    call sequence: a moved field does not change the fingerprint, a changed field *type* does, an
    index with no fingerprint counts as stale, the alias moves in one call, the old index is deleted
    *after* the alias moves, and a concrete index of the alias name is deleted *before*.
  - `_every_index_for` checked against the live cluster: it finds both the old concrete index and
    the new physical one, and a wildcard matching nothing returns an empty list rather than raising.

### Owed

- **A rebuild concurrent with a corpus load is unguarded.** An incremental load during a rebuild
  writes through the alias to the outgoing index, and those writes are lost at promotion. The poll
  is daily and a deploy is minutes. The fix is a lock, and it is not written.
- **Disk left by a failed rebuild is not collected.** The half-built index keeps its name and the
  next `--if-changed` reuses it, which is correct — documents overwrite by `_id` — but a generation
  abandoned by a mapping that changed twice is only removed by `--recreate`.
