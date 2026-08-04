# Workstream A — state and plan

Paste `00-CONVENTIONS.md` above any task prompt, then this file, then the task you want.

**To resume in a new session, one line:**

> Read `CLAUDE.md` and `claude-code/WORKSTREAM-A-STATE.md`, then do task A4.

---

## Where the work is

Branch **`workstream-a-accessibility`**, 20 commits ahead of the 3 pre-existing guide commits it
was cut from (`898b085`). Working tree clean apart from untracked `claude-code/`. Nothing merged to
`main` yet.

All three suites green as of the last commit (`d6536e3`):

| suite | count |
|---|---|
| `make test` | 486 |
| `make test-web` | 227 |
| `make test-e2e` | 369 (252 of them the a11y scan) |

Two extra checks, both green: `uv run python scripts/contrast.py` (34 checks, 0 failures) and
`make shots` (reflow at 320 CSS px and at 1280 zoomed to 200%).

## Done: A1, A2, A6, A7

**A1 — the harness** (ADR-0039). `frontend/tests/e2e/a11y.spec.ts` runs axe-core over the matrix in
`docs/a11y/routes.json`: 27 route entries (one expands to every guide chapter on disk), three
viewports, both themes, one `forced-colors: active` pass, six interactive states. **251 scans,
~1m30s.** `make test-a11y` runs it alone; `make test-e2e` includes it. Results merge into
`docs/verification/a11y.json`. `docs/a11y/known-violations.json` is the ratchet.

**A2 — the inline/block partition** (ADR-0040). `scripts/inline_elements.py` measures which USLM
elements occur in running prose; `tests/uslm.test.ts` reads that artifact and asserts element by
element. `<date>` (20,513 occurrences, never isolated) and `<footnote>` were rendering as `<div>`
mid-sentence. `note` and `quotedContent` are decided per occurrence.

**A6 — the preview** (ADR-0041, amending ADR-0024 decision 4). The card was `aria-hidden="true"`
*and* `tabindex="0"`. Now `role="dialog"`, Tab moves in, Escape returns focus without scrolling, a
dismissal latches, and a failed fetch says so instead of showing nothing.

**A7 — colour** (ADR-0042). `scripts/contrast.py` computes 17 pairs × 2 themes from the token block
in `site.scss`. Six failures fixed, including the USWDS mobile nav at 2.5:1 on **every reader page**.
`--rule` split into decorative (`--rule`) and control boundary (`--edge`, held to 3:1). Status badges
gained border treatments. `forced-colors` and global `prefers-reduced-motion` blocks added.

### What the artifact says now

`docs/verification/a11y.json`: **8 route/rule pairs over 1,780 nodes** — 1 critical, 7 serious —
down from 41 over 2,251 at the A1 baseline.

Everything left is in `docs/a11y/known-violations.json`, and **none of it is the reader's own
markup**:

| owner | rule | routes |
|---|---|---|
| A4 | `scrollable-region-focusable` | `docs`, `diff` |
| A4 | `html-has-lang` | `/docs`, `/redoc` |
| A4 | reflow, 3px at 320 CSS px | `/app/docs` |
| A10 | `color-contrast` | Swagger UI, ReDoc |
| A10 | `nested-interactive` | Swagger UI |
| A10 | `select-name` (the one critical) | ReDoc |

## Remaining: A4, A3, A5, A8, A9, A10

**Do A4 next.** It owns three of the six remaining entries and is the only one that can empty
everything not vendored. Two of the three are already diagnosed:

- `html-has-lang` on `/docs` and `/redoc` is **ours, not the vendor's** — those shells come from
  `get_swagger_ui_html` and `get_redoc_html` in `main.py`. A one-line fix.
- `scrollable-region-focusable` + the 3px reflow are the **same parameter tables** on `/app/docs`,
  plus the source-XML pane on `/app/diff`.
- The rest of A4 (landmarks, heading order, skip link, `:focus-visible` at 3:1, `scroll-margin-top`
  under sticky chrome) is unmeasured. The focus-ring contrast is already computed and passing in
  `docs/verification/contrast.json`.

Then, in the order the workstream implies: **A3** (copy column tab stops + clipboard fallback),
**A5** (timeline/redline: `<ins>`/`<del>`, non-colour cues, live summary), **A8** (search, forms,
status messaging), **A9** (manual protocol — `docs/a11y/manual-protocol.md` does not exist yet),
**A10** (publish `/app/accessibility`).

`/app/accessibility` is already named in `routes.json` under `excluded`, with the instruction to add
it to the matrix in the same commit that adds the page.

## Standing decisions — do not silently reverse these

1. **The ratchet is weaker than A1 specified.** A1 asked that serious/critical violations fail
   regardless of the known-violations file. Every such violation already existed and each was owned
   by a later task, so a literal gate landed the harness red. `waiveSeverity` requires each exception
   to name the exact impact it waives, dated and owner-signed. Recorded as ADR-0039's cost. **When
   the file reaches zero, delete `waiveSeverity` and make the gate literal** — that is the intended
   end state.
2. **Light stays the default at every OS setting** (ADR-0027 decision 1). A7's
   `prefers-color-scheme` clause was **declined**, confirmed with the maintainer, and recorded in
   ADR-0042 under "What was declined". WCAG 2.1 AA requires neither direction.
3. **320px at 200% zoom is not asserted** — it lays out in 160 CSS px and WCAG 2.1 AA asks for
   reflow down to 320 and no further. The rows that ship are 320 CSS px (1.4.10) and 1280@200% =
   640 (1.4.4).
4. **The 429 state is not in the scan matrix.** Forcing one means hammering ADR-0029's budget from
   inside the suite that shares it. A6 asserts the degradation behaviourally instead; A8 should do
   the same rather than adding it to the matrix.
5. **`--rule` is decorative and deliberately fails 1.4.11 on paper.** Reported with
   `"decorative": true` and the numbers. A reviewer who disagrees has a real argument; do not
   "fix" it without reading ADR-0042 first.

## Traps already paid for

- **`make test-e2e` runs against `:8000`, which is the docker-built frontend.** `astro dev` on
  `:4321` hot-reloads; `:8000` does not. A source change is invisible to the browser suite until
  `docker compose up -d --build frontend`. This cost two full runs to discover.
- **A Playwright `globalSetup` inside `testDir` makes every spec under it collect as zero tests**,
  silently, reporting "No tests found" like a bad `--grep`. The a11y hooks live in
  `frontend/scripts/` for that reason.
- **USWDS puts backgrounds on inner elements.** `.usa-alert__body`, not `.usa-alert`;
  `.usa-footer__primary-section`, not `.usa-footer`. This has now been got wrong twice.
- **Do not take a token for a role it was not defined for.** `.endpoint__method` used `--panel` as a
  *text* colour over a fixed background; `--panel` inverts between themes.
- **`docs/verification/a11y.json` regenerates on any full `make test-e2e`**, so it appears in
  `git status` after unrelated runs.

## Candidate tasks found and deliberately not done

- **Nothing checks that the scan matrix exercises every component the reader can render.** No route
  carried a status badge through all of A1 and A6; a token audit found it, not the scan. Adding
  `/app/us/usc/t16/s688` fixed the one case. A component-level inventory against the matrix is the
  real fix.
- **`docs/screenshots/demo-video-*.png` churn on every `make shots` run** regardless of code
  changes — the `<video>` frame is nondeterministic. Four files show as modified in any session that
  regenerates shots. Pin the poster frame or drop that page from the shot set.
- **`/app/us/usc` answers 400 and `/app/us/usc/t5a/s3` answers 404** in the reader; neither is in the
  scan matrix. The appendix case is the known citation gap, but a reader 404 where the API explains
  is its own defect.
- **The contrast pair list is hand-declared.** A changed hex is caught; a *new* token painted on a
  new surface is a pair nobody added, and the script does not know to look.

## Where things live

```
docs/a11y/routes.json               the scan matrix, and what is excluded and why
docs/a11y/known-violations.json     the ratchet — axe entries and reflow entries
docs/verification/a11y.json         generated by make test-a11y
docs/verification/contrast.json     generated by uv run python scripts/contrast.py
docs/verification/inline-elements.json  generated by uv run python scripts/inline_elements.py
frontend/tests/e2e/a11y.spec.ts     the scan
frontend/tests/e2e/a11y-report.ts   shard format and merge
frontend/scripts/a11y-{setup,teardown}.ts   global hooks (outside testDir on purpose)
docs/adr/0039..0042                 the four decisions this workstream has recorded so far
```

Guide chapters claiming these ADRs: **09** (`checking-this-site`) holds 39 and 42; **02**
(`reading`) holds 40; **06** (`working-with-the-text`) holds 41. A new ADR turns `make test-web` red
until some chapter claims it.
