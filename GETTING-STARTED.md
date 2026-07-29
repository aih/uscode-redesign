# Getting Started — Step-by-Step Guide to Executing PLAN.md

This guide assumes no prior experience with Claude Code. Follow it top to bottom. Companion documents: [PLAN.md](PLAN.md) (what we're building and why), [BUILDLOG.md](BUILDLOG.md) (the running record of how).

---

## 1. What Claude Code is, in one paragraph

Claude Code is Anthropic's coding agent that runs **in your terminal, inside a project folder**. You type instructions in plain English; it reads your files, writes code, runs tests, and makes git commits — showing you every change before or as it happens. Unlike the Claude chat app, it works directly on this repository on your machine. You will use it as your builder; your job is to direct, review, and approve.

## 2. Accounts: what you have vs. what you need

**You have:** Claude Pro ($20/mo) + $100 in API credits (console.anthropic.com).

**The gap:** Pro includes Claude Code, but with **Sonnet only — no Opus** — and daily limits sized for light use. PLAN.md assigns Opus 5 to the hardest work (architecture, the USLM parser, the version resolver, code review) and needs multi-hour sessions.

**Do this:**
1. **Upgrade Pro → Max.** Go to [claude.ai](https://claude.ai) → Settings → Billing → change plan. Choose:
   - **Max 20x ($200/mo) — recommended** for the build week (parallel sessions Days 2–4 will hit 5x limits), or
   - **Max 5x ($100/mo)** if budget-constrained; expect to pause occasionally mid-afternoon.
   - You can downgrade after the build week; billing is monthly.
2. **Keep the $100 API credits in reserve.** Two uses: (a) the Claude GitHub Action for automatic PR review (Step 9), which bills to the API key; (b) overflow — if your Max session hits its limit at a bad moment, run `claude` with an API key instead (it will offer the choice at login, or use `/login` to switch). Rough API cost awareness: an hour of heavy Opus work can run $10–30, so credits are for surgical use, not the default.
3. **No other accounts needed to start.** GitHub you have (this repo). Hosting accounts (Fly.io/Render/Hetzner) aren't needed until Day 6. uscode.house.gov requires no credentials.

## 3. Install the tools (one-time, ~30 minutes)

Open **Terminal** (Mac: ⌘-space, type "Terminal"). Copy-paste each line, press Enter, wait for it to finish.

```bash
# 1. Claude Code
curl -fsSL https://claude.ai/install.sh | bash

# 2. Verify
claude --version

# 3. Docker Desktop (runs Postgres locally) — download and install from:
#    https://www.docker.com/products/docker-desktop/  (open the app once after installing)

# 4. Python tooling (uv manages Python versions and packages)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

If a command says "command not found" after install, close and reopen Terminal.

## 4. First launch

```bash
cd ~/Documents/workspace/aih/uscode-redesign
claude
```

- First run asks you to log in: choose **"Claude account with subscription"** and authorize in the browser window that opens.
- You're now at a prompt inside your repo. Everything you type is an instruction; Claude Code proposes file edits and commands, and **asks your permission** before running anything consequential.

**The five things to know:**

| Action | How |
|---|---|
| Switch model | type `/model` → pick Opus or Sonnet |
| Plan mode (Claude proposes a plan, edits nothing until you approve) | press **Shift+Tab** until it shows "plan mode", or `/plan` |
| Clear context between tasks (do this often) | `/clear` |
| Interrupt Claude mid-action | press **Esc** |
| Quit | `/exit` or Ctrl+C twice |

Rule of thumb from PLAN.md §7: **plan and review in Opus, implement in Sonnet.** Switching is just `/model`.

## 5. Add the USLM 2.x samples (before Session 1)

```bash
cd ~/Documents/workspace/aih/uscode-redesign
mkdir -p samples/uslm1 samples/uslm2
# put your usc16.xml copy in samples/uslm1/
curl -o /tmp/uslm2samples.zip https://uscode.house.gov/currency/uscinuslmv2samples.zip
unzip /tmp/uslm2samples.zip -d samples/uslm2/
git add samples && git commit -m "Add USLM 1.x and 2.x sample files from uscode.house.gov"
```

(Note: the full usc16.xml is 32 MB — that's fine for git, but don't commit the ~324 release-point zips later; `.gitignore` the `data/` directory.)

## 6. Session 0 — teach Claude Code the project (~20 min)

Start `claude`, switch to Opus (`/model`), and paste:

> Read PLAN.md in full. Then create a CLAUDE.md file for this repo that captures: the architecture rules (Repository interface only; schema-plural parser layer per PLAN §2), the identifier semantics (identifier = cross-release identity; guid = (provision, release point) pin, globally unique; temporalId = display only), the gotchas in PLAN §9, the documentation duties in PLAN §11 (every session ends by updating BUILDLOG.md), test and run commands as they come to exist, and the model-assignment table from PLAN §7. Keep it under 150 lines — it's loaded into every future session.

Review what it writes, then: `git add CLAUDE.md && git commit`. CLAUDE.md is automatically read at the start of every session — it's how a multi-session build stays coherent.

## 7. The build sessions — exact prompts

Work one session per module. **Always:** start in plan mode (Shift+Tab), read the plan it proposes, approve or redirect, let it implement, make sure tests pass, then end with the documentation prompt (Step 8). `/clear` between sessions.

**Session 1 — Scaffold (Sonnet):**
> Execute PLAN.md Day 1 item 1: repo scaffold with ingest/, api/, web/, db/ packages, pyproject via uv, docker-compose.yml with Postgres 16, Alembic wired up, pytest configured, Makefile with `make dev`, `make test`, `make verify` targets. Commit in small steps.

**Session 2 — Parser layer (Opus; the hardest session): ✅ done, BUILDLOG 004.**
> Execute PLAN.md Day 1 item 2: the UslmParser protocol, detect_uslm_version() (inspect samples/uslm1 and samples/uslm2 to derive the detection rule — record it in an ADR), Uslm1Parser as a streaming lxml.iterparse implementation emitting normalized SectionRecords, and a Uslm2Parser stub that passes detection and basic section extraction on the samples. Follow the fixture strategy in PLAN.md Day 1 item 2: first script-extract tests/fixtures/usc16_slice.xml (wrapper + ch.1 through §45f + one each repealed/omitted/transferred section) and unit-test against the slice; the full 32 MB file is a @pytest.mark.slow integration test asserting known-good counts (**5,095 real sections out of 5,393 `<section>` elements; 522 repealed / 102 omitted / 19 transferred, and the one `reserved` is on a subchapter** — the session *corrected* the 523/102/19/1 figures this prompt originally carried; see ADR-0005; guid id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd ↔ /us/usc/t16/s45f/c/5). Default make test must stay under a few seconds.

**Session 3 — Ingest (Sonnet, Opus review): ✅ done, BUILDLOG 005.** *(schema landed in Session 1; this session started by clearing its two debts)*
> First clear the BUILDLOG 002 debts: run alembic downgrade base && alembic upgrade head, and docker compose up --build end-to-end; fix anything that breaks. Then add the secondary indexes from PLAN.md §3 as a migration (guid_map(release_id, identifier); section_release_map(release_id); section_versions(section_id, first_release_id)). Then implement the ingest command: `python -m ingest load <xmlfile> --release 119-102not101`, with content-hash dedupe, guid_map population, seq_in_title, and the provenance manifest from PLAN §11.4. Load Title 16 at the current release point and verify: **5,095 sections stored out of 5,393 `<section>` elements, status counts 522/102/19** (this prompt originally said 5,393 and 523/102/19/1 — the raw element tally, which ADR-0005 had already superseded; the session flagged the contradiction rather than ingesting the wrong number).

**Before Session 4 — two prerequisites the earlier plan didn't surface. ✅ both cleared in BUILDLOG 006, together with Session 4 itself.** Both were found by reviewing Session 3's result against what Sessions 4–5 assume; details and rationale in PLAN.md Day 1 items 3–5.

1. **A second release point must be loaded, and it should be chosen from the RP inventory, not guessed.** Only `119-102not101` is in the database; PLAN Day 1 item 3 and the §10 demo both need two RPs (the release picker has nothing to flip between). The prior-RP XML is not in `samples/` — it has to be downloaded. Pick the RP using `titlesAffected` from the release-point inventory so Title 16 actually *differs* between the two; an arbitrary neighbour like 119-94 may be byte-identical, in which case dedupe correctly collapses it to one version and the demo shows two identical texts. This makes the **inventory half of Session 6 a prerequisite for Session 4**, not Day-2 work — and it also supplies the real `currency_date` and global `seq` that `?date=` resolution needs (Session 3 left both as per-ingest stopgaps).
2. **Nothing stores the title's hierarchy, so the TOC routes have no data source.** Ingest persists sections only; `SectionRecord.ancestors` carries `(level, identifier)` but is dropped on load, and no table holds chapter/subchapter names. `GET /us/usc/t16` and `/t16/ch1` (PLAN §4) and the Session 5 TOC page therefore cannot be served from the current schema. This needs a structure table + a TOC pass in ingest **before** the API session, and it is ingest work, not API work.

**Session 3.5 — RP inventory + TOC pass: ✅ done, BUILDLOG 006** (run with Session 4, in one Opus session, after Ari chose "full 3.5 then Session 4" over deferring the TOC routes).
> Two things, both ingest-side. (1) Port just the inventory half of ../loadusc-xcitedb/downloadusc.py: fetch the release-point list, write data/uscreleasepoints.json, and seed the release_points table from it — real currency_date and a true global seq (labels don't sort; parse to congress/law/exclusions per ingest/release_label.py), replacing the sequential stopgap from BUILDLOG 005. Then use titlesAffected to pick a prior RP where Title 16 actually changed, download that one title zip (~1 req/sec, descriptive User-Agent), and load it with the existing `python -m ingest load` — confirming the dedupe path on real data (unchanged sections should reuse section_versions rows; only changed ones get new ones). (2) Add hierarchy storage: a structure table (title/chapter/subchapter/part/subpart with identifier, num, heading, parent, seq) plus a TOC pass in the parser layer that fills it. **Read the headings off the structural elements (`<chapter><num>/<heading>`), not off the `<toc>` element** — the structural markup is nearly identical across USLM 1.x and 2.x, whereas `<toc>` is one of the three things OLRC actually changed in 2.x (`tocItem`/`column` → `referenceItem`/`designator`/`label`/`target`), so this avoids the biggest schema divergence and is unit-testable against the existing fixture, whose `<toc>` bodies are truncated to 5 items but whose chapter/subchapter headings are intact. Mind gotcha 6: taking iterparse `end` events on `<chapter>` buffers a whole chapter — track the open-ancestor stack and capture num/heading as they close instead. Record the structure-elements-over-toc choice as an ADR.

**Session 4 — API + resolver: ✅ done, BUILDLOG 006 (Opus 5).** Three things the prompt below did not anticipate, all of which changed the design: the content-hash dedupe from Session 3 turned out to collapse nothing on real data (ADR-0007), reading order and parent chapter had to move off the deduped row (ADR-0008), and a request can legitimately name a release point that was never ingested — answered from the newest ingested one before it, reported as `served_from`.
> Implement the FastAPI app per PLAN.md §4: identifier routes with ?release/?date/?format, the guid lookup route, TOC, neighbors, versions, releases. Resolver algorithm per PLAN §3. Repository interface only — no SQL in handlers. Integration tests against the loaded Title 16 at both release points. Decide up front where the Repository lives: PLAN §2's diagram says `storage/`, the repo has `db/` (models + config only) — put the `Repository` protocol and its Postgres implementation in `storage/`, importing models from `db/`, so the XCiteDB second implementation has an obvious home. Note that ingest writes to `db/` models directly and deliberately stays outside the Repository boundary (that rule governs `api/` and `web/`).

**Session 5 — Reader UI: ✅ done, BUILDLOG 007 (Opus 5).** Built as server-rendered Jinja in `web/`, at the *same* `/us/usc/…` URLs as the API rather than under a `/read/` prefix (ADR-0009) — and that choice immediately exposed a live bug: `Accept:` was substring-matched, so browsers had been getting raw USLM at the demo URL while `?format=html` covered for it in every test.
> Build the minimal reader per PLAN.md Day 1 item 5: TOC page, section page with provision anchor highlighting, prev/next, release picker, status badges. Server-rendered Jinja is fine. Make /us/usc/t16/s45f/c/5?date=07/12/2026 demonstrable end to end.

**Session 1.5 — Study prior art: ✅ done (BUILDLOG 010, `docs/prior-art.md`).** Kept for the record — it was originally scheduled before Session 2 and ran just before Session 6, which is when it was actually needed. Clone commands, for reference:

```bash
cd ~/Documents/workspace/aih
git clone https://github.com/dreamproit/loadusc-xcitedb
git clone https://github.com/dreamproit/versions
```

Then in `claude`:
> Read ../loadusc-xcitedb (release-point downloader, uscreleasepoints.json format, XCiteDB loader) and ../versions (older working USC display site with temporal version diffs, pre-FastAPI). Write docs/prior-art.md summarizing: what each does, what we will reuse directly (downloader logic, RP inventory format, diff algorithm, XCiteDB query patterns), and what we will deliberately do differently. Cite specific files.

This makes the prior art available to every later session via a small summary instead of re-reading two repos each time.

**Session 6 — Bulk downloader: ✅ done (ADR-0012, BUILDLOG 010).** The tool exists and is trialled; **the run itself is yours to start** — it's unattended and needs no Claude session:

```bash
cd ~/Documents/workspace/aih/uscode-redesign
df -h .                                    # ~10 GB is enough — measured ~9 GB corpus, not the old 40–80 GB guess
uv run python -m ingest backfill --plan-only | head    # sanity: ~3,197 downloads planned
caffeinate -i nohup uv run python -m ingest backfill > backfill.log 2>&1 &
tail -f backfill.log                       # watch; Ctrl-C the tail freely — the run keeps going
```

Measured, not estimated: OLRC serves ~50 KB/s, so the full run is **40–50 hours** for ~9 GB — it spans sleep cycles, which is why the recommended path is the **remote run**: a disposable EC2 `t4g.micro` that pulls resume state from S3, backfills, pushes hourly, and powers itself off when done, for well under $1 (**[docs/remote-ops.md](docs/remote-ops.md)**, ADR-0013 — bucket + role once, `mirror push` the laptop's partial state, launch with `scripts/ec2-user-data.sh`). Either way it's resumable: re-run (or reboot the box) and it continues from the ledger with zero re-downloads. When it finishes: `uv run python -m ingest verify-downloads --deep`, commit `docs/verification/downloads.json`, and skim the ledger for `failed` entries (`--retry-unavailable` exists for the stubborn ones). Local dev never needs the full corpus — `uv run python -m ingest mirror pull --title 16` fetches a verified slice.

**Session 8 — Bulk load: ✅ done (ADR-0014, BUILDLOG 013; run on the partial corpus — 715 title-releases, 87.0% deduped).** Re-running `make load-all` as more zips land is Session 9's job. Original prompt kept for the record:
> Implement `python -m ingest load-all`: walk data/releases/ledger.json in inventory seq order (oldest first — the baseline RP loads first by construction), unzip each ok entry, and run the existing load path per title with its release label; idempotent (re-running loads nothing new), resumable, batched commits, one provenance manifest per release point. Then run it to completion. Afterward, implement make verify for real per PLAN §11.5: per-title-per-RP section counts vs the source XML, written to docs/verification/ and committed. Report: rows in section_versions vs sections×RPs (the dedupe ratio is the headline number), disk size of the database, any count mismatches — a mismatch is a finding, not a rounding error. Update BUILDLOG.md and commit.

**Session 7 — Frontend: separation + Astro/USWDS reader: ✅ done, BUILDLOG 014 (Opus 5).** Both parts landed in one session; ADR-0015 records the two decisions the prompt left open (a Caddy owns the origin; the USLM→HTML renderer lives in the frontend, not as an API field). Three things cost time and are worth knowing before a similar session: a second checkout's Docker container already owned port 8000, Astro strips `base` before its dev proxy sees a URL, and a test that asserted a title was *absent* went stale within the hour because the shared database was mid-bulk-load. *(spec from the Session-5 UI review [BUILDLOG 008], ADR-0010 [reader/API separation], and ADR-0011 [Astro + USWDS, proposed]. This lands before Day 4's polish because everything Day 4 adds sits on this layout. This session is larger than the others — expect it to take two sittings; part A is a complete, shippable checkpoint.)*
>
> **Part A — separate the surfaces (ADR-0010), in the existing codebase:**
> Mount the Jinja reader at /app/us/usc/... with its own router; strip the HTML branch and Jinja imports out of api/ so /api/v1/us/usc/... is machine-only (JSON default, ?format=xml verbatim); make the bare citation URL /us/usc/... a thin redirector — 307 to /app for HTML-winning Accept:, 307 to /api/v1 otherwise, ?format= wins, query string preserved, Vary: Accept. Convert the negotiation tests to redirect tests; add an architecture test that api/ imports no Jinja. Update README's demo commands (curl -L). Commit — this checkpoint stands alone.
>
> **Part B — the Astro + USWDS reader (ADR-0011), replacing the Jinja pages at /app:**
> Scaffold frontend/ as an Astro 5 + TypeScript SSR app styled with USWDS (framework-agnostic CSS — no react-uswds), consuming /api/v1 only; wire compose + make dev so one proxy serves /app → Astro and everything else → FastAPI. Port web/uslm_html.py's USLM→HTML mapping to a typed renderer (record in the BUILDLOG whether it lives in frontend/ or becomes a rendered-HTML field on the API — either is fine, say why). Then implement the BUILDLOG 008 acceptance spec, which is the parity bar for retiring Jinja:
> 1. **Mobile-first**: USWDS's grid and tokens, base styles for ~360px screens; deep provision indents via an --indent-step variable (small on phones, 1.6rem wide); form controls ≥16px, tap targets ≥44px. Headless screenshots at 375px and 1280px of the demo URL, a TOC page, and home.
> 2. **Site navbar**: USWDS header component — brand, Titles, Release points, API docs; breadcrumbs (USWDS breadcrumb) + release picker in a contextual bar below; skip-nav link and landmarks.
> 3. **Section title**: `§ 45f. Mineral King Valley addition authorized` as one reading-face line — num inline, badge after, meta below. Same on TOC pages.
> 4. **Navigation top and bottom**: compact ← prev · up · next → strip under the title bar; full neighbors block + site footer at the bottom.
> 5. **Refs**: internal /us/usc/ refs keep the page's ?release= and get title="§ num — heading" hover text from ONE batched lookup per page (no N+1); /us/pl/ and /us/stat/ refs map to the govinfo link service (verify URL patterns at govinfo.gov first) or degrade to spans — never a local 404. Tests: internal rewriting, pl/stat mapping, unknown-ref degradation, and no rendered page contains a relative /us/pl/ or /us/stat/ href.
> 6. Statutory text ships as server-rendered HTML with zero client JS by default; islands only where interaction demands it (the release picker stays a GET form). Run make test + frontend tests, screenshot before/after, update BUILDLOG.md and README, commit in small steps. When all six pass in Astro, retire the Jinja templates (git keeps them) and record it.

**Session 9 — Corpus completion + deep verification (Sonnet): ⬅ UNBLOCKED — the backfill is complete** (ledger: 3,197 planned, 3,153 ok, 44 recorded unavailable). This is the next session to run:
> The backfill is done (check: python -m ingest backfill --plan-only reports nothing left but recorded unavailables). Re-run make load-all for every zip that landed since the last pass, then push the final corpus state to the mirror (python -m ingest mirror push). Run make verify-deep over the WHOLE corpus — the independent recount from source XML, not the loader's bookkeeping — and commit docs/verification/database.json. Every count mismatch is a finding: classify it (parser gap / source inconsistency like 113-36's missing 18A / loader bug) and either fix it or record it explicitly; do not average it away. Report the headline numbers: corpus-wide dedupe ratio, total sections stored vs section×RP pairs, database disk size, guid_map row count. Update README's Status section with the final numbers. BUILDLOG entry and commit.

**Session 10 — Day 4 reader polish: ✅ done (BUILDLOG 019, ADR-0016).** Version timeline, source-level diff view, keyboard-nav island, no-JS collapsibles, heading-depth fix — plus the session's real find: `frontend/src/lib/` had never been in git (an unanchored `lib/` line in `.gitignore`), so `make test-web` had been testing nothing. Original prompt kept for the record:
> Build Day 4 on the Astro layout, clearing the recorded reader debts (CLAUDE.md status):
> 1. Version timeline: a reader page per section listing the release points where its text actually changed (the /versions data), each linking to that version — this is the feature the whole versioned architecture exists for, so make it prominent (link near the section title, not buried in the footer).
> 2. Diffs between any two versions of a section. Port the approach from ../versions per docs/prior-art.md — including Diff_Timeout: 0, which prior-art records as load-bearing. Decide and record where the diff computes (an /api/v1 .../diff?from=&to= endpoint through the Repository, with presentation in the frontend, is the default answer — element names stay out of api/).
> 3. Keyboard navigation as a small island (the only new client JS): ←/→ or j/k for prev/next section, u for up a level. Document keys in a footer hint; no modifier traps.
> 4. Notes and sourceCredit as collapsible details/summary (no JS), open by default on desktop, closed on mobile.
> 5. Fix the flat heading outline: USLM headings should render h2/h3/h4 by structural depth, not h2 everywhere (this is the Day 7 accessibility debt — clear it now while touching the renderer).
> Tests for each (renderer depth mapping, diff endpoint, timeline data), make shots, BUILDLOG, small commits.

**Session 11 — Day 5 auth + watchlist: ✅ done (BUILDLOG 020, ADR-0017).** Argon2, server-side sessions keyed by `sha256(token)`, double-submit CSRF, watchlist CRUD with ownership checks, Watch button + My Provisions. Named scope cuts: no email verification, no password reset, no login rate-limiting; the multi-list CRUD has no UI yet. Original prompt kept for the record:
> Implement auth and watchlists per PLAN §4: email+password signup/login in api/ (argon2 hashing, HTTP-only session cookies, CSRF on state-changing routes; users/watchlists/watchlist_items tables already exist from Session 1). API routes: watchlist CRUD, items = identifier + optional pinned release + note. Reader: a "Watch" button on section pages (island), a My Provisions page listing watched items with one-click open at current-or-pinned release, and status badges if a watched section went repealed/transferred since being added. Architecture rules hold: auth lives in api/, the reader consumes /api/v1, no SQL outside storage/. Tests incl. auth-required boundaries and the architecture suite. BUILDLOG, commits.

**Session 12 — Day 6 performance, CI, deploy, and the auth debts (Opus plan first, then Sonnet):**
> Performance: (a) a (section, release) response is immutable — set ETag (already the content hash) + long Cache-Control on /api/v1 and /app section pages, with the Caddy config caching accordingly, and make sure the auth/watchlist routes and any page rendered for a logged-in user are explicitly no-store (a cached "My Provisions" served to the wrong person is the failure mode to design against); (b) fix the recorded debt that a section page's breadcrumbs cost an extra get_toc call; (c) quick load test (hey or locust) against the top routes, numbers in the BUILDLOG.
> CI: add a GitHub Actions workflow running make test + make test-web on every push (Postgres service container, dev-data fixture load) — this closes the standing gap that no independent machine re-runs the suites.
> Auth debts before public exposure (BUILDLOG 020 named these as scope cuts; deploying without them is what makes them real): login rate-limiting / lockout on repeated failures, and a decision recorded either way on password reset — either implement it or state in the ADR that accounts are throwaway until email exists. Also verify the session cookie gets `secure` when served behind Caddy over HTTPS: `api/auth.py` decides from `request.url.scheme`, which is http behind a proxy unless proxy headers are trusted — check it end-to-end on the deployed box, don't assume.
> Deploy: plan-mode first — pick between a Hetzner/DO VPS running compose vs Fly.io given the measured database size from Session 9; then deploy db+api+frontend+Caddy behind HTTPS with the S3 mirror as the data source (mirror pull, load-all on the box). Record the choice as an ADR; smoke-test the demo URL publicly; BUILDLOG.

**Session 13 — Day 7 hardening (Opus):**
> 1. Uslm2Parser to full parity: TOC, tables, and the indent model against samples/uslm2 (usc49 is the table-heavy fixture), cross-schema parity tests extended beyond s45f; when OLRC flips to 2.x, ingest must not notice.
> 2. Accessibility pass on the reader: axe-core audit in CI, heading outline (done in Session 10 — verify), focus order, skip links, contrast in both color schemes, screen-reader labels on the picker/badges/diff view.
> 3. The skeptic's page: a public /about/how page in the reader that tells the build story — data provenance (manifests, mirror, verify-deep results), the test counts, links to BUILDLOG and the ADRs on GitHub. This is the walkthrough the repo's documentation regime has been feeding all week.
> 4. Sweep the debt list in CLAUDE.md's status line to zero or to explicitly-deferred; final README pass; BUILDLOG entry closes Week 1.

For each: plan mode first, one module per session, tests before merge. Sessions 9 and 10 are independent (ingest vs frontend) — worktrees if you want them concurrent.

## 7a. Autonomous sessions — how this repo is configured

`.claude/settings.json` (checked in) is set up so a session runs a full PLAN.md task **without permission prompts**:

- **`defaultMode: "acceptEdits"`** — all file edits in this repo are auto-approved.
- **Allow list** — every command the build actually uses (uv, make, pytest, alembic upgrade/revision, docker compose up/build/logs, git add/commit/push/branch/worktree/merge, curl, unzip, psql, file utilities) runs without asking. WebFetch is allowed only for uscode.house.gov, GitHub, and the core library docs.
- **Ask list** — genuinely destructive-but-sometimes-needed operations still prompt: `alembic downgrade`, `docker compose down`, `docker volume rm`, package uninstalls. These are rare, so sessions stay hands-off in practice.
- **Deny list** — never allowed, even if requested: `sudo`, `rm -rf` outside the repo, force-push, `git reset --hard`, `git clean`, reading `.env`.

**What keeps this reasonably safe:** everything is in git (any bad edit is one revert away); force-push and hard-reset are denied, so history can't be silently rewritten; the blast radius is this repo — no sudo, no system-level writes; and the BUILDLOG + small-commit discipline means you review by reading diffs after the fact instead of clicking prompts during.

To launch a fully hands-off session, give it the whole job in one prompt, e.g.:

```bash
claude "Execute Session 3.5 from GETTING-STARTED.md §7 in full: seed release_points from the RP inventory, load a second Title 16 release point chosen via titlesAffected, add hierarchy storage and the TOC pass, run make test, update BUILDLOG.md, and commit in small steps. Do not stop to ask unless a test fails twice."
```

One caveat learned in Session 3: a fully hands-off prompt still can't resolve a genuine ambiguity, and shouldn't pretend to. That session was told to verify "5,393 sections, 523/102/19/1" — numbers the repo's own ADR-0005 had already superseded — and the useful behaviour was to ingest the correct 5,095/522/102/19, then say plainly which number was asked for and which was right. If a prompt and the repo's documented decisions disagree, the disagreement is the finding.

Check back when it's done; review with `git log --oneline` + `git diff main@{1}` (or the GitHub PR if you're on branches).

## 8. End every session with this prompt

> Update BUILDLOG.md with an entry for this session: date, model, what was asked, key decisions (link any new ADR), commits made, what was verified and how. If any architectural decision was made, add a docs/adr/ file for it. Then commit.

This is the raw material for your blog posts and the site's "how it was built" page. Skipping it once is how the record dies.

## 9. Optional but recommended: automatic PR review (uses your API credits)

Once you're pushing to GitHub: in a Claude Code session run `/install-github-app` and follow the prompts (this installs the Claude GitHub Action; it bills the API key, which is what your $100 is for). Then work in branches — every pull request gets an independent Opus review before you merge. An independent reviewer with fresh context catches what the authoring session can't see, and the review comments become part of the public provenance trail.

## 10. Parallel work (Days 2+, optional)

With Sessions 1–6 merged (1 ✅ 1.5 ✅ 2 ✅ 3 ✅ 3.5 ✅ 4 ✅ 5 ✅ 6 ✅), the three live tracks are fully independent and can all run at once: **the backfill run** (no Claude session — see Session 6 above; it's just bandwidth), **Session 7** (frontend: separation + Astro/USWDS reader), and — once zips are on disk — **Session 8** (bulk load; works on a partial corpus). Day 4's deeper polish (keyboard nav, notes toggles, version timeline, diffs) follows Session 7, since it builds on that layout. If running Sessions 7 and 8 together, use worktrees (`frontend/`+`web/`+`api/` vs `ingest/` — disjoint):

```bash
git worktree add ../uscode-web feature/reader-polish
# Terminal tab 1: cd ~/Documents/workspace/aih/uscode-redesign && claude   (downloader session)
# Terminal tab 2: cd ../uscode-web && claude                               (reader session)
```

Merge order per PLAN §7: schema → ingest → API → web → auth.

## 11. When things go wrong

- **Claude Code proposes something that contradicts PLAN.md** — say so: "That contradicts PLAN.md §3; re-read it and revise." The plan is the contract.
- **A session gets confused/circular** — `/clear` and restart the task with a tighter prompt; long messy context is the usual cause.
- **Hit usage limits** — switch that session to API-key billing (`/login`), or wait for the reset, or downshift the task to Sonnet.
- **Verify, don't trust:** after each session, run `make test` yourself and click through the demo path. PLAN §11.5 exists so that "it works" is always a command you can run, not a claim.
