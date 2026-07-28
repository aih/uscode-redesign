# CLAUDE.md — uscode-redesign

Versioned US Code retrieval site: any provision, at any release point (RP), via a URL scheme
mirroring the USLM `@identifier`. FastAPI + Postgres v1, XCiteDB later behind a repository
interface. Full context in [PLAN.md](PLAN.md); decisions in `docs/adr/`.

**Status:** Day 1 complete — items 3, 3a, 4 (BUILDLOG 006) and 5 (BUILDLOG 007). The release-point inventory is seeded (382 RPs with real `currency_date` and a true global `seq`); Title 16 is loaded at **two** release points, 119-99 and 119-102not101, with working dedupe (2 new / 5,093 deduped — see ADR-0007); `structure_nodes` holds the hierarchy (569 nodes) from a streaming TOC pass (ADR-0006); `storage/` has the `Repository` protocol + Postgres implementation; `api/` serves PLAN §4's routes — identifier lookup with `?release`/`?date`/`?format`, `?id=` guid lookup, TOC, neighbors, versions, releases; and `web/` is the reader — server-rendered Jinja at **the same identifier URLs**, chosen by `Accept:`/`?format=` (ADR-0009), with provision highlighting, breadcrumbs, prev/next, a release picker and status badges; and `ingest/backfill.py` is the resumable bulk downloader (ADR-0012) — `python -m ingest backfill`, driven by `titlesAffected` (3,197 files, not 22,156), with a ledger at `data/releases/ledger.json` and hash-dedupe verification; and the corpus mirrors to S3 (ADR-0013) — `python -m ingest mirror push/pull`, a disposable EC2 box runs the backfill unattended and powers itself off (`docs/remote-ops.md`), sized by measurement at **~9 GB / 40–50 h**, not the old 40–80 GB guess. `make test` = 212 tests. **Next: launch the EC2 backfill run (remote-ops §1–3), then load what it fetches (Session 8) ∥ Session 7 (reader interface overhaul — GETTING-STARTED §7; mobile-first CSS, site navbar, one-line section title, top+bottom nav, ref hover text, and the live bug that source credits emit relative `/us/pl/`+`/us/stat/` links that 404 locally). The two touch disjoint code; run in parallel worktrees.** Open debts: **the backfill run is in progress (local trial; hand off to EC2 per remote-ops §2–3) — only Title 16 at 2 RPs is *loaded***; a deduped fragment carries the guids of the release its text first appeared at (ADR-0007's recorded cost); `structure_nodes` is unversioned (`first_release_id` filters, `last_release_id` is informational); reader has no keyboard nav, notes toggles, or version timeline UI (Day 4), a flat `<h2>` heading outline (Day 7 accessibility), and section breadcrumbs cost an extra `get_toc` (Day 6); `Uslm2Parser` has no table/indent handling (Day 7); `make verify` is real now (ADR-0014) but the corpus load is mid-flight. **Test speed rule:** default `make test` never parses the 32 MB usc16.xml — unit tests use `tests/fixtures/usc16_slice.xml` (regenerate with `make fixtures`); full-sample tests are `@pytest.mark.slow`, run by `make test-slow`. API integration tests need a loaded database (`make dev-data`) and skip without one.

## Architecture rules (PLAN §2)

1. **API and UI talk only to the `Repository` interface** (`storage/repository.py`) —
   `resolve_release(...)`, `get_section(identifier, release)`, `get_toc(...)`, `resolve_id(...)`,
   `neighbors(...)`, `versions(...)`, `list_releases(...)`. Postgres is implementation v1
   (`storage/postgres.py`, the only SQL in the project); XCiteDB becomes a second implementation
   with no API/UI changes. **No raw SQL in API handlers**, and nothing version-resolution-related
   outside the Repository. `api/` holds no database session either — `storage.get_repository` is
   the FastAPI dependency. `tests/test_architecture.py` enforces all of this; ingest is
   deliberately on the other side of the boundary and writes `db/` models directly.
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
5. **Reader and API separated; the citation URL redirects (ADR-0010, amends ADR-0009 — not yet
   implemented; Session 7).** Target state: reader at `/app/us/usc/…` (always HTML), API at
   `/api/v1/us/usc/…` (JSON default, `?format=xml` verbatim; no Jinja imports under `api/`), and
   the bare citation URL `/us/usc/…` a thin redirector — 307 to `/app` for HTML-winning `Accept:`,
   307 to `/api/v1` otherwise, `?format=` wins, `Vary: Accept`. Until Session 7 lands, the code
   still implements ADR-0009's single negotiated route. Frontend direction (ADR-0011, proposed):
   Astro 5 + TypeScript + USWDS in `frontend/`, consuming `/api/v1` only; Jinja `web/` stays until
   the Astro app passes the BUILDLOG 008 acceptance spec. Presentation — the sole place outside
   the parsers allowed to know USLM element names — lives in `web/uslm_html.py` and its typed
   successor in the Astro app.

## Identifier semantics (PLAN §1, ADR-0003) — the thing most likely to be gotten wrong

| Attribute | Meaning | Use for |
|---|---|---|
| `@identifier` | Logical path `/us/usc/t16/s45f/c/5`. **Cross-release identity.** Stable across RPs *unless renumbered*. | Primary key for the URL scheme; joining a provision to itself over time |
| `@id` (guid) | `id0b32dff7-810c-11f1-…`. **Pins (provision, release point)** — regenerated at every RP *by design*, and that pair is globally unique. | Global `guid_map` index; `?id=` lookup needs no release param; stable "this exact text at this exact time" citation |
| `@temporalId` | `s1201_a_1_A`. **Not guaranteed unique.** | Display only — never a key |
| `@status` | `repealed` / `omitted` / `transferred` / `reserved` | Must stay retrievable and badged in UI |

A guid is never a cross-release identity — that is `@identifier`'s job, and only its job.

## Gotchas (PLAN §9) — encoded here because each one has already bitten someone

1. **Guids regenerate per RP by design.** Version pin, never cross-release identity. **This
   defeats naive content dedupe** — an untouched section's raw XML differs at every RP, so
   hashing it collapses nothing (measured: 0 of 5,095 Title 16 sections identical between
   119-99 and 119-102not101; 5,093 identical once `@id` was stripped). Hash
   `SectionRecord.content_key`, never `.xml` (ADR-0007).
2. **Dual schemas** — no USLM 1.x paths outside `Uslm1Parser` (see architecture rule 2).
3. **Renumbering/transfers break `@identifier` continuity.** Track `status="transferred"`; consider a
   redirects table. An identifier can vanish at an RP *without* being repealed.
4. **RP labels do not sort lexically.** Parse into (congress, law_num, excluded_laws[], update_num)
   plus a global `seq` taken from the inventory page's order. Skip labels compound
   (`277not255not268`), and 17 of the 385 published RPs carry a `u1` update suffix (`118-22u1`) —
   `118-22` is a *different* release point with different files.
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
    The flip side is a *retrieval* rule: a request for an RP that was never ingested is answerable
    from the newest ingested RP at or before it, because the title didn't change in between. The
    Repository does that and reports it as `served_from` — answer, but never silently.
11. **XCiteDB is the near future,** not "someday" — respect rule 1 strictly.
12. **`<section>` inside `<quotedContent>` is not a section** — it is statutory text quoted by an
    amending act, carries no `@identifier`/`@id`, and must never be stored or counted (ADR-0005).
    Counting `<section>` elements naively inflates Title 16 by 298. Related: skipping such an
    element must not *remove* it — it is part of the enclosing section's verbatim XML.
13. **`@status` is not section-only and not a closed set.** Title 16's one `reserved` is on a
    `<subchapter>`; USLM 2.x Title 49 uses `renumbered`. Never model status as an enum.
14. **USLM 1.0.15 emits no `@temporalId` at all** — zero in a 32 MB title. Display-only field;
    do not build anything that assumes it is present. It also emits no `<dc:title>`, so a title's
    real name (`CONSERVATION`) comes from the root structural element, not `<meta>`.
15. **Facts that can change while the text does not** — reading order, parent chapter — belong on
    `section_release_map`, never on the content-deduped `section_versions` row (ADR-0008).

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
- **Never commit `data/`** — the RP zips (measured ~9 GB via `titlesAffected`; 40–80 GB only if
  every title were fetched at every RP) are gitignored; the corpus of record is the S3 mirror
  (ADR-0013).

## Commands

```
make dev        # docker compose up -d db; alembic upgrade head; uvicorn --reload (local)
                # then http://localhost:8000/ is the reader and /docs the API
make dev-data   # seed release_points from the RP inventory, then load Title 16 at 119-99
                # (downloaded, ~5 MB) and 119-102not101 (from samples/) — what the API
                # integration tests need; they skip without it
make test       # uv run pytest (-m 'not slow') — the specification; nothing merges without it green
make test-slow  # full-sample parser integration tests (~4 s): counts vs samples/, memory bound
make test-all   # both
make fixtures   # regenerate tests/fixtures/usc16_slice.xml from samples/uslm1/usc16.xml
make verify     # (TBD — stub, exits 1) full-corpus counts vs source XML → docs/verification/, PLAN §11.5, Day 7
docker compose up --build   # full containerized stack (db + api) instead of `make dev`'s local API

# python -m ingest inventory [--from-file PATH] [--no-seed]
#   Fetches uscode.house.gov/download/priorreleasepoints.htm, writes data/uscreleasepoints.json
#   ({name, date, titlesAffected, url} per RP, loadusc-xcitedb's shape), and seeds release_points
#   with real currency dates, titles_affected, and a global seq from page order.
#
# python -m ingest fetch --release <label> --title <num>
#   Downloads and unpacks one title's zip into data/releases/{label}/ (~1 req/sec, cached on disk).
#   Raises on failure — the interactive single-title path. The bulk path records and continues.
#
# python -m ingest backfill [--title N]... [--release LABEL]... [--limit N] [--plan-only]
#                           [--retry-unavailable] [--no-baseline]
#   The full corpus, resumably (ADR-0012). Plans from data/uscreleasepoints.json driven by
#   titlesAffected — 3,197 downloads, not 382×58=22,156 — with the oldest RP fetched in full
#   as the baseline a delta needs. Re-run to resume: outcomes live in data/releases/ledger.json
#   (ok / unavailable / failed), and a zip on disk with no ledger entry is re-hashed and
#   adopted, so a lost ledger costs a hashing pass rather than a re-download. Hours long and
#   interruptible; Ctrl-C saves the ledger.
#
# python -m ingest mirror {push,pull} [--bucket B] [--title N]... [--release L]...
#   S3 mirror of the corpus (ADR-0013; bucket from $USC_MIRROR_BUCKET; ops guide
#   docs/remote-ops.md). push uploads zips+inventory+manifests then the ledger LAST, so the
#   mirror never advertises files it lacks; pull fetches (a slice of) the mirror and
#   re-hashes it against the ledger — transport is aws s3 sync, trust is ours. One writer
#   rule: the ledger's writer is wherever the backfill runs; everyone else pulls.
#
# python -m ingest load-all [--title N]... [--release L]... [--limit N] [--plan-only]
#   Bulk load of the downloaded corpus (ADR-0014), ledger-driven, in inventory seq order so
#   the baseline lands before the deltas. Resume state is the DATABASE, not a second ledger:
#   `title_versions.sections_loaded` is stamped last, so a crash mid-title leaves NULL and the
#   pair is redone (load_release is idempotent). Each zip is extracted to a temp dir and
#   deleted, so the corpus never doubles on disk. `make load-all`.
#
# python -m ingest verify [--deep]      (`make verify` / `make verify-deep`)
#   Shallow: recorded `sections_loaded` vs the rows `section_release_map` actually holds —
#   seconds. --deep re-parses every source file for an INDEPENDENT recount, which is the only
#   version that can catch a parser confirming its own bookkeeping. Writes
#   docs/verification/database.json. Headline metric: the dedupe ratio.
#
# python -m ingest verify-downloads [--deep]
#   Hash-dedupe over the downloaded corpus → docs/verification/downloads.json. Same title at
#   two RPs with identical bytes is reported (OLRC republished it unchanged; also the u1
#   substitution signature); two *different* titles sharing a zip fails the report, because
#   that means URL construction collapsed two addresses. --deep re-hashes from disk.
#
# python -m ingest load <xmlfile> --release <label> [--currency-date YYYY-MM-DD] [--source-url URL]
#                                                   [--source-zip PATH]
#   Parses one USLM title file into Postgres: content-hash dedupe (over the guid-stripped
#   content_key — ADR-0007), guid_map upsert, structure_nodes from the TOC pass, per-release
#   seq_in_title/parent_identifier, and a data/manifests/{release}.json provenance manifest.
#   --currency-date is only needed for a release the inventory doesn't list.
#   Example: uv run python -m ingest load samples/uslm1/usc16.xml --release 119-102not101
```

Stack: Python 3.12 + uv, FastAPI, SQLAlchemy, Alembic, lxml, Postgres 16 via docker-compose
(`db` service; `api` service builds from `Dockerfile`, UV_PROJECT_ENVIRONMENT=/opt/venv so the
dev bind mount doesn't shadow the container venv). `db/config.py` reads `DATABASE_URL` (see
`.env.example`); Alembic's `env.py` pulls the same setting and `target_metadata` from
`db.models.Base` — no separate URL to keep in sync. Node 20+ required once the Astro
frontend (ADR-0011) lands in Session 7.

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
