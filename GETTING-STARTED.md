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

**Session 2 — Parser layer (Opus; the hardest session):**
> Execute PLAN.md Day 1 item 2: the UslmParser protocol, detect_uslm_version() (inspect samples/uslm1 and samples/uslm2 to derive the detection rule — record it in an ADR), Uslm1Parser as a streaming lxml.iterparse implementation emitting normalized SectionRecords, and a Uslm2Parser stub that passes detection and basic section extraction on the samples. Unit tests must cover /us/usc/t16/s45f including the (c)(5) provision and its guid id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd, plus repealed/omitted/transferred sections.

**Session 3 — Schema + ingest (Sonnet, Opus review):**
> Implement the Postgres schema from PLAN.md §3 as Alembic migrations, then the ingest command: `python -m ingest load <xmlfile> --release 119-102not101`. Include content-hash dedupe, guid_map population, seq_in_title, and the provenance manifest from PLAN §11.4. Load Title 16 at the current release point and verify: 5,393 sections expected.

**Session 4 — API + resolver (Opus for resolver, Sonnet for routes):**
> Implement the FastAPI app per PLAN.md §4: identifier routes with ?release/?date/?format, the guid lookup route, TOC, neighbors, versions, releases. Resolver algorithm per PLAN §3. Repository interface only — no SQL in handlers. Integration tests against the loaded Title 16.

**Session 5 — Reader UI (Sonnet):**
> Build the minimal reader per PLAN.md Day 1 item 5: TOC page, section page with provision anchor highlighting, prev/next, release picker, status badges. Server-rendered Jinja is fine. Make /us/usc/t16/s45f/c/5?date=07/12/2026 demonstrable end to end.

**Session 1.5 — Study prior art (Opus, read-only, ~30 min):** before Session 2, clone your existing repos next to this one so Claude Code can read them:

```bash
cd ~/Documents/workspace/aih
git clone https://github.com/dreamproit/loadusc-xcitedb
git clone https://github.com/dreamproit/versions
```

Then in `claude`:
> Read ../loadusc-xcitedb (release-point downloader, uscreleasepoints.json format, XCiteDB loader) and ../versions (older working USC display site with temporal version diffs, pre-FastAPI). Write docs/prior-art.md summarizing: what each does, what we will reuse directly (downloader logic, RP inventory format, diff algorithm, XCiteDB query patterns), and what we will deliberately do differently. Cite specific files.

This makes the prior art available to every later session via a small summary instead of re-reading two repos each time.

**Session 6 — Bulk downloader (Sonnet), start of Day 2:**
> Using ../loadusc-xcitedb/downloadusc.py and docs/prior-art.md as reference, port the release-point downloader into ingest/ as a modern, resumable tool (Python 3.12, checksum cache, ~1 req/sec, descriptive User-Agent), and write the loader that seeds the release_points table from uscreleasepoints.json (name → parsed congress/law/exclusions, date, titlesAffected, url). Record in an ADR what was reused vs. changed.

Then continue with PLAN.md Days 2–7 the same way (backfill, reader polish, auth + watchlist, deploy, hardening). For each: plan mode first, one module per session, tests before merge.

## 8. End every session with this prompt

> Update BUILDLOG.md with an entry for this session: date, model, what was asked, key decisions (link any new ADR), commits made, what was verified and how. If any architectural decision was made, add a docs/adr/ file for it. Then commit.

This is the raw material for your blog posts and the site's "how it was built" page. Skipping it once is how the record dies.

## 9. Optional but recommended: automatic PR review (uses your API credits)

Once you're pushing to GitHub: in a Claude Code session run `/install-github-app` and follow the prompts (this installs the Claude GitHub Action; it bills the API key, which is what your $100 is for). Then work in branches — every pull request gets an independent Opus review before you merge. An independent reviewer with fresh context catches what the authoring session can't see, and the review comments become part of the public provenance trail.

## 10. Parallel work (Days 2+, optional)

When you're comfortable, run two sessions at once with git worktrees so agents don't collide:

```bash
git worktree add ../uscode-web feature/reader-ui
# Terminal tab 1: cd ~/Documents/workspace/aih/uscode-redesign && claude   (backend session)
# Terminal tab 2: cd ../uscode-web && claude                               (frontend session)
```

Merge order per PLAN §7: schema → ingest → API → web → auth.

## 11. When things go wrong

- **Claude Code proposes something that contradicts PLAN.md** — say so: "That contradicts PLAN.md §3; re-read it and revise." The plan is the contract.
- **A session gets confused/circular** — `/clear` and restart the task with a tighter prompt; long messy context is the usual cause.
- **Hit usage limits** — switch that session to API-key billing (`/login`), or wait for the reset, or downshift the task to Sonnet.
- **Verify, don't trust:** after each session, run `make test` yourself and click through the demo path. PLAN §11.5 exists so that "it works" is always a command you can run, not a claim.
