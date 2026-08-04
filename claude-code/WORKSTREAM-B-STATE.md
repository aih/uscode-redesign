# Workstream B — state and plan

Paste `00-CONVENTIONS.md` above any task prompt, then this file, then the task you want.

**To resume in a new session, one line:**

> Read `CLAUDE.md` and `claude-code/WORKSTREAM-B-STATE.md`, then do task B3.

---

## Where the work is

Branch **`workstream-b-navigation-ia`**, cut from `main` at `387ff3a` (workstream A merged).
Working tree clean apart from untracked `claude-code/`.

All suites green as of the last commit:

| suite | count |
|---|---|
| `make test` | 486 |
| `make test-web` | 227 |
| `make test-e2e` | 373 (251 of them the a11y scan) |
| `make shots` | reflow clean at 320 CSS px and 1280@200% |

`docs/verification/a11y.json`: **8 route/rule pairs over 1,780 nodes** — unchanged from the ADR-0039
baseline, and everything in it is still `docs/a11y/known-violations.json`'s.

## Done: B1, B2

**B1 — the IA map and one navigation chrome** (ADR-0043).

`docs/ia-map.md` is the map: every route from the guide ratchet's own `readerRoutes()`, its purpose,
its inbound links **with the file and line that make them**, its exits, and the chrome it carries.

What it found, and what was built from it:

- **Only one page carried any chrome.** `us/usc/[...identifier].astro` was the sole caller passing
  `crumbs`/`release`/`bar` to `Base`. `/app/versions` and `/app/diff` had no trail at all; both do
  now.
- **The breadcrumb stopped at the parent.** It ends at the provision on screen now, as a
  `usa-current` item with `aria-current="page"`.
- **`SectionBar`'s steps were bare arrows.** They name the neighbour from 40em up.
- **`ChapterRail`** is new: the parent subdivision's sections in reading order, the one being read
  marked `aria-current`, status badges shown in place. Left rail from 64em, after the text below it.

**B2 — release context and the switcher** (ADR-0044).

- `ReleaseContext` replaces `Provenance` and adds the fact `Provenance` never stated: **whether the
  release point being read is the newest**.
- **The switcher dropped the provision anchor.** Its action came from `section.identifier`, so
  switching release on `/us/usc/t16/s45f/c/5` landed on the whole section. Fixed, and covered by the
  `switch-keeps-provision` scenario.
- The switcher offers all three ways to ask — newest, a date, a named release point — as **two GET
  forms**, because `?release=` beats `?date=` in `resolve_release` and one form would send both.
- It **left the sticky stack**; the release point stays there as text. See "Standing decisions".

## Remaining: B3, B4, B5, B6

**Do B3 next**, and its measure half first — the package's own running order puts B3-measure in
Phase 1, and both B4 and B5 want numbers that do not exist yet.

- `docs/verification/loadtest.json` is from **2026-07-29** and is stale for four separate reasons now:
  ADR-0029's limiters, ADR-0026's redline, ADR-0037's `Disallow: /`, and ADR-0043's fourth API call
  per section view.
- The deployed box answers: `https://uscode.linkedlegislation.org/app/` returned 200 in ~0.4s during
  this session (it also returned one transient 502, worth watching). `hey` is installed.
- ADR-0043 added a per-section-view call whose cost is asserted nowhere. The last measurement of that
  exact route — `/api/v1/us/usc/t16/ch1/schVI` — was 156 rps, p95 83ms, 9,794 bytes, and it is stale.

Then **B4** (search relevance and operators), **B5** ("Compare with…" on the section header —
`/app/diff` is still two hops from the text it compares), **B6** (dead ends).

## Standing decisions — do not silently reverse these

1. **The release switcher is not in the sticky chrome, and that is measured.** Before the move the
   stack had 19px of headroom under `--sticky-h` at 700px and 55px at 1280px; the date field costs
   about eighty. `--sticky-h` is what `scroll-margin-top` spends, and `docs/backlog.md` already flags
   that band for carrying 19rem of chrome. After the move: 89px and 85px.
   `tests/e2e/sticky.spec.ts` asserts ≥60px spare at both, so eating it requires raising the token on
   purpose. The **release point itself stays pinned as text** (`.contextbar__rp`).
2. **`/app/versions` and `/app/diff` get the breadcrumb but no release band.** The first spans every
   release point, the second is about two. This is a narrower reading of B2's "every reader page"
   than the task asked for, taken deliberately and recorded in ADR-0044.
3. **The rail is not sticky, and is not a `<details>`.** Both were tried. Sticky honouring
   `--sticky-h` as a `top` offset starts a third of the way down the page, which is the trap
   `.guide__nav` already records. `<details>` cannot be forced open by CSS, so at desktop width the
   summary would report itself collapsed with its content visible.
4. **The map found no duplicated navigation route.** `/app/goto` vs `/app/search`, the three
   prev/next affordances, and the two from/to pickers were each checked and are each one path. B1
   asked for deletions; there were none to make. The real defect was the opposite — unreachable and
   thinly-reachable routes.

## Traps already paid for

- **`make test-e2e` runs against `:8000`, the docker-built frontend.** `docker compose up -d --build
  frontend` after every source change, or the browser sees the old bundle. (Inherited from
  workstream A and paid for again here.)
- **`Astro.slots.has(name)` does not mean "the slot was filled".** A slot whose content is behind a
  false condition still reports `true`. Every TOC page took the two-column layout with an empty first
  column until `Base` got an explicit `rail` prop.
- **Anything new in the breadcrumb bar needs a colour from a token.** The unlinked current crumb was
  the first non-link text ever put there, so it inherited USWDS's own breadcrumb ink — derived from
  `$theme-breadcrumb-background-color`, which assumes a light page — and failed `color-contrast` in
  dark on every reader page. Same shape as ADR-0042's `.usa-nav__link`.
- **USWDS scopes the breadcrumb `›` separator to 480px and up**, where its own breadcrumb is a single
  back link. `--wrap` shows the whole trail at every width, so below 480px the items ran together.
- **A `demo: true` scenario needs a caption on every step**, including a trailing `expect`.

## Candidate tasks found and deliberately not done

- **`/app/settings` is unreachable.** `AuthNav:49` is its only linker and `SiteHeader` does not
  render `AuthNav` while `ACCOUNTS_ENABLED` is false. Only guide chapter 06 links it, in prose.
- **`previewHref` in `lib/url.ts` has no caller.** `CitePreview.astro:176` builds
  `` `/app/preview${identifier}` `` inline in browser JavaScript instead — which is a reader href
  built outside `url.ts` (architecture rule 5), and is the exact inlining `previewHref`'s own
  docstring says it exists to replace.
- **`us/usc/index.astro:22` calls `fetch` with its own `process.env.API_BASE_URL`** rather than going
  through `lib/api`.
- **The release menu carries every release point for the title** — 115 options locally, 381
  corpus-wide, in the markup of every section page.
- **`docs/screenshots/demo-video-*.png` churn on every `make shots`** regardless of code changes.
  (Also carried by workstream A.)

## Where things live

```
docs/ia-map.md                          the map, and the unfindable-route list
docs/adr/0043                           one navigation chrome
docs/adr/0044                           release context, and the switcher that keeps your place
frontend/src/layouts/Base.astro         where the chrome is assembled
frontend/src/components/ChapterRail.astro
frontend/src/components/ReleaseContext.astro   replaces the deleted Provenance.astro
frontend/src/components/ReleasePicker.astro    two GET forms
frontend/src/middleware.ts              the empty-?release= canonical redirect
frontend/tests/e2e/sticky.spec.ts       the headroom the switcher's move bought
frontend/scripts/scenarios.mjs          the scenario DSL, now with a `select` verb
```

Guide chapters claiming these ADRs: **02** (`reading`) holds 43; **03**
(`reading-at-a-point-in-time`) holds 44. A new ADR turns `make test-web` red until some chapter
claims it.
