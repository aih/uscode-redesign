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
