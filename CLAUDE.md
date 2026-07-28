# CLAUDE.md — uscode-redesign

Versioned US Code retrieval site: any provision, at any release point (RP), via a URL scheme
mirroring the USLM `@identifier`. FastAPI + Postgres v1, XCiteDB later behind a repository
interface. Full context in [PLAN.md](PLAN.md); decisions in `docs/adr/`.

**Status:** Day 1 item 3 complete (BUILDLOG 005) — `alembic downgrade base`/`docker compose up --build` verified end-to-end; secondary indexes migrated (PLAN §3); `python -m ingest load` ingests a USLM file into Postgres with content-hash dedupe, `guid_map`, `seq_in_title`, and a `data/manifests/{release}.json` provenance manifest. Title 16 @ 119-102not101 loaded and verified: 5,095 sections (522/102/19 repealed/omitted/transferred), 5,393 raw `<section>` elements per ADR-0005. **Next: PLAN Day 1 items 3/3a (second release point + hierarchy storage), which the API session depends on** — see GETTING-STARTED §7 Session 3.5. Open debts: **only one release point is loaded** (a prior RP must be downloaded, chosen via `titlesAffected`); **no hierarchy/TOC is stored at all** — ingest persists sections only and drops `SectionRecord.ancestors`, so nothing holds a chapter's heading and the §4 TOC routes have no data source yet; `release_points.seq`/`currency_date` are per-ingest stopgaps (sequential counter / required `--currency-date`) until the RP inventory is seeded; `Uslm2Parser` has no TOC/table/indent handling (Day 7). **Test speed rule:** default `make test` never parses the 32 MB usc16.xml — unit tests use `tests/fixtures/usc16_slice.xml` (regenerate with `make fixtures`); full-sample tests are `@pytest.mark.slow`, run by `make test-slow`.

## Architecture rules (PLAN §2)

1. **API and UI talk only to the `Repository` interface** — `get_section(identifier, release)`,
   `get_toc(...)`, `resolve_id(...)`, `neighbors(...)`. Postgres is implementation v1; XCiteDB
   becomes a second implementation with no API/UI changes. **No raw SQL in API handlers**, and
   nothing version-resolution-related outside the Repository.
2. **The ingest layer is schema-plural.** A `UslmParser` protocol with `Uslm1Parser` and
   `Uslm2Parser`, selected by `detect_uslm_version(file)` — **the root namespace URI decides**
   (`xml.house.gov/schemas/uslm/1.0` → 1.x, `schemas.gpo.gov/xml/uslm` → 2.x); `xsi:schemaLocation`
   only labels the point version (ADR-0004). Both emit the same normalized `SectionRecord`
   (identifier, guid, temporalId, num, heading, status, seq, raw XML fragment, source credit,
   notes, guid_refs, ancestors). **Never hard-code USLM element paths outside a parser
   implementation** — `StreamingSectionParser` shares the traversal but knows no element names of
   its own; each parser supplies an `ElementNames` vocabulary. Downstream layers are
   schema-agnostic; `schema_version` rides along so original XML is always returnable verbatim.
3. **Sections are the storage atom** (ADR-0001). Sub-section provisions (`/c/5`) are extracted from
   the section XML at request time via lxml XPath on `@identifier`, returning the whole section with
   the target anchored/highlighted — the reader always keeps context.
4. **Layout:** `ingest/` (fetch RPs, parse USLM, split into sections) → `storage/` (Postgres +
   repository interface) ← `api/` (FastAPI resolver, auth, watchlist) ← `web/` (reader, watchlist).

## Identifier semantics (PLAN §1, ADR-0003) — the thing most likely to be gotten wrong

| Attribute | Meaning | Use for |
|---|---|---|
| `@identifier` | Logical path `/us/usc/t16/s45f/c/5`. **Cross-release identity.** Stable across RPs *unless renumbered*. | Primary key for the URL scheme; joining a provision to itself over time |
| `@id` (guid) | `id0b32dff7-810c-11f1-…`. **Pins (provision, release point)** — regenerated at every RP *by design*, and that pair is globally unique. | Global `guid_map` index; `?id=` lookup needs no release param; stable "this exact text at this exact time" citation |
| `@temporalId` | `s1201_a_1_A`. **Not guaranteed unique.** | Display only — never a key |
| `@status` | `repealed` / `omitted` / `transferred` / `reserved` | Must stay retrievable and badged in UI |

A guid is never a cross-release identity — that is `@identifier`'s job, and only its job.

## Gotchas (PLAN §9) — encoded here because each one has already bitten someone

1. **Guids regenerate per RP by design.** Version pin, never cross-release identity.
2. **Dual schemas** — no USLM 1.x paths outside `Uslm1Parser` (see architecture rule 2).
3. **Renumbering/transfers break `@identifier` continuity.** Track `status="transferred"`; consider a
   redirects table. An identifier can vanish at an RP *without* being repealed.
4. **RP labels do not sort lexically.** Parse into (congress, law_num, excluded_laws[]) plus a global
   `seq`. Skip labels compound: `277not255not268`.
5. **"not" laws vs `?date`.** At RP `119-102not101` the text is *not* fully current through
   07/12/2026. The UI must surface the exception, not just the date.
6. **Title 42 is huge** (multiples of Title 16). Parsers must stream — `iterparse` + element
   clearing, never whole trees. Batch DB writes.
7. **Appendix titles** (`05a`, `11a`, `18a`, `28a`, `50a`) are separate files with looser structure —
   treat as distinct titles.
8. **Early RPs (2013–2015)** came from an older USLM 1.0 converter; expect attribute drift. Validate
   ingest counts per title per RP.
9. **Repealed/omitted sections keep their place in reading order** — present in prev/next, badged.
10. **Every RP republishes all titles** but few changed — dedupe by content hash or storage explodes
    (~300 RPs × ~1 GB). `titlesAffected` from the RP inventory drives ingest; hashing verifies.
11. **XCiteDB is the near future,** not "someday" — respect rule 1 strictly.
12. **`<section>` inside `<quotedContent>` is not a section** — it is statutory text quoted by an
    amending act, carries no `@identifier`/`@id`, and must never be stored or counted (ADR-0005).
    Counting `<section>` elements naively inflates Title 16 by 298. Related: skipping such an
    element must not *remove* it — it is part of the enclosing section's verbatim XML.
13. **`@status` is not section-only and not a closed set.** Title 16's one `reserved` is on a
    `<subchapter>`; USLM 2.x Title 49 uses `renumbered`. Never model status as an enum.
14. **USLM 1.0.15 emits no `@temporalId` at all** — zero in a 32 MB title. Display-only field;
    do not build anything that assumes it is present.

## Fixtures

- `samples/uslm1/usc16.xml` — USLM 1.0.15, 32 MB. Primary parser fixture.
- `samples/uslm2/USLM2/` — USLM 2.x: `usc16.xml` (cross-schema parity), `usc49.xml` (heaviest
  table/layout markup), `usc01.xml` (253 K, fast iteration). Trimmed from OLRC's full 57-title,
  594 MB [sample zip](https://uscode.house.gov/currency/uscinuslmv2samples.zip) — re-download it if
  another title is needed.
- `tests/fixtures/usc16_slice.xml` — 878 KB verbatim slice of usc16.xml (ch.1 subchapters I–VI
  through §45f, plus schXIII for quoted sections and schXCVII for `reserved`). Every unit test runs
  against this. Regenerate with `make fixtures` (`scripts/extract_fixture.py`).
- Known-good assertion: `id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd` ↔ `/us/usc/t16/s45f/c/5`.
- Title 16 @ 119-102not101 — **two counts, don't conflate them (ADR-0005):**
  - raw `<section>` elements: **5,393**; 523 repealed / 102 omitted / 19 transferred.
  - real code sections the parser emits: **5,095**; 522 repealed / 102 omitted / 19 transferred.
  - The 298-element gap is `<section>` inside `<quotedContent>` — statutory text quoted by amending
    acts, with no `@identifier` and no `@id`. One of them is marked repealed, hence 523 vs 522.
  - The file's **single `reserved` is on a `<subchapter>`** (`/us/usc/t16/ch1/schXCVII`), not a
    section. Section status counts total 643, never 644.
- **Never commit `data/`** — the ~324 RP zips are 40–80 GB and are gitignored.

## Commands

```
make dev        # docker compose up -d db; alembic upgrade head; uvicorn --reload (local)
make test       # uv run pytest (-m 'not slow') — the specification; nothing merges without it green
make test-slow  # full-sample parser integration tests (~4 s): counts vs samples/, memory bound
make test-all   # both
make fixtures   # regenerate tests/fixtures/usc16_slice.xml from samples/uslm1/usc16.xml
make verify     # (TBD — stub, exits 1) full-corpus counts vs source XML → docs/verification/, PLAN §11.5, Day 7
docker compose up --build   # full containerized stack (db + api) instead of `make dev`'s local API

# python -m ingest load <xmlfile> --release <label> [--currency-date YYYY-MM-DD] [--source-url URL]
#   Parses one USLM title file and loads it into Postgres: content-hash dedupe against existing
#   section_versions, guid_map upsert, seq_in_title from document order, data/manifests/{release}.json
#   provenance manifest. --currency-date is required the first time a --release label is ingested
#   (source USLM files carry no currency date of their own); omit on later runs/titles for that release.
#   Example: uv run python -m ingest load samples/uslm1/usc16.xml --release 119-102not101 --currency-date 2026-07-12
```

Stack: Python 3.12 + uv, FastAPI, SQLAlchemy, Alembic, lxml, Postgres 16 via docker-compose
(`db` service; `api` service builds from `Dockerfile`, UV_PROJECT_ENVIRONMENT=/opt/venv so the
dev bind mount doesn't shadow the container venv). `db/config.py` reads `DATABASE_URL` (see
`.env.example`); Alembic's `env.py` pulls the same setting and `target_metadata` from
`db.models.Base` — no separate URL to keep in sync. Node 20 if the reader ends up React.

## Documentation duties (PLAN §11) — non-negotiable, this project is built in the open

1. **Every session ends by updating `BUILDLOG.md`** — one entry per session, in the format at the top
   of that file: date, tool/model, what was asked, what was decided (link ADRs), commits produced,
   what was verified and how to re-check it. Write it while context is hot, before the session ends.
2. **`docs/adr/`** — one short ADR per consequential decision. Skeptics audit reasoning, not results.
3. **Commit discipline** — small commits, imperative messages, preserve `Co-Authored-By` trailers.
   The git history is the walkthrough.
4. **Provenance manifests** — every ingest writes `data/manifests/{release}.json`: source URL,
   download timestamp, zip sha256, per-title section/element counts. Anyone can re-download and
   confirm.
5. **Verification artifacts committed** to `docs/verification/`, regenerated by `make verify` —
   reliability claims must be reproducible commands, not assertions.

## Model assignment (PLAN §7)

| Workstream | Agent / mode | Model |
|---|---|---|
| Architecture decisions, schema review, resolver design | Plan mode / `Plan` subagent | **Opus 5** |
| USLM parser + ingest pipeline | Main session | **Opus 5** |
| Repo scaffold, docker-compose, Alembic, CI | Main or worktree agent | **Sonnet 5** |
| FastAPI routes + repository impl | Worktree agent | **Sonnet 5** |
| Frontend reader UI | Worktree agent | **Sonnet 5** |
| Auth + watchlist | Worktree agent | **Sonnet 5** |
| Bulk download/backfill scripts | One session writes, then runs unattended | **Sonnet 5** (no LLM at runtime) |
| Test writing, fixture generation | `general-purpose` subagent per module | **Sonnet 5** |
| Verification, PR diff review | Separate reviewer session (fresh context) | **Opus 5**; **Haiku 4.5** for lint/link/doc sweeps |
| Exploration ("where is X handled?") | `Explore` subagent | **Haiku 4.5 / Sonnet 5** |
| Build-log & ADR upkeep | End of every session, same session | any |

Rhythm per module: plan (Opus) → approve → implement in a worktree → tests pass → fresh-context
reviewer reads the diff → merge. Merge order: schema → ingest → API → web → auth.

## External source etiquette

uscode.house.gov needs no credentials, but be polite: sequential downloads, ~1 req/sec, cache
everything, descriptive User-Agent. Reuse [dreamproit/loadusc-xcitedb](https://github.com/dreamproit/loadusc-xcitedb)
for the RP inventory/downloader and [dreamproit/versions](https://github.com/dreamproit/versions)
for the temporal diff approach — don't rediscover solved problems.
