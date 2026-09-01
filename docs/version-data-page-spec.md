# A reader-facing page for the version-change data — implementation spec

The version-change annotations (ADR-0074, ADR-0075) are computed for the whole corpus and reported
to `docs/verification/version-changes.json`. Nothing on the site explains how a change is
classified or shows what the corpus turned out to contain. This spec adds one page that does both,
and wires it so that regenerating the report is what updates it.

Read `docs/version-semantics-spec.md` and ADR-0074 first — the methodology this page describes is
theirs. This spec is about the page.

## The decisions already taken

Confirmed with the user before this spec was written; treat them as settled.

1. **Route: `/app/data/version-changes`**, page file `frontend/src/pages/data/version-changes.astro`.
   A standalone route in the same species as `/app/design` — a page that renders a committed
   artifact and is itself a regression surface. The `data/` directory leaves room for siblings
   (search relevance, corpus counts) without a second decision.
2. **A guide chapter cannot host it.** The chapters are markdown rendered by `GuideLayout`, and
   markdown cannot import JSON, so numbers in a chapter would be typed in by hand — which is the
   thing this page exists not to be. Guide chapter 09 (`09-checking-this-site.md`) gains a short
   section pointing at the page and claims the route in `covers.routes`.
3. **Corpus-wide totals *and* the full 56-title breakdown.** The per-title data is the most
   interesting part of the artifact (title 10 is 77.5% classified against title 1's 60%).

## What the page must contain

Three parts, in this order.

**Methodology.** What a version group is, and how the transition between two of them is classified
into `initial` / `text` / `notes` / `structure` from whitespace-insensitive hashes of the reading
text and of the notes. What `concurrent` marks. How a text change is attributed to a Public Law —
the delta of incorporated-law sets across the transition's window, honouring `excluded_laws`,
matched against the classification tables (ADR-0067) — and what `classified` and `none` mean on an
entry. Prose describes the behaviour; the *reasons* stay in ADR-0074 (documentation duty 7 and the
prose rules in `~/.claude/CLAUDE.md` — no justifying clauses, no aphoristic closers, no
rhetorical-question headings).

Two limitations belong here as flat statements, because a reader will otherwise read the numbers
wrongly:

- **Text attribution is 49.25%, and the gap is mostly age.** The classification tables begin at the
  104th Congress; a provision last amended before then has no row to match. Say it; do not
  apologise for it.
- **`concurrent` fired on 77,596 transitions (18.3%)** — recurring content, converter flip-flops and
  reverts, not the ~160 ADR-0021 duplicate pairs it was designed for. Window arithmetic is
  unreliable on those and the reader UI already says so.

**Results.** Corpus-wide: `change_rows`, `transitions`, `sections_covered`, the four `by_kind`
counts with shares, `text_classified` with its share, `concurrent`, `version_groups_hashed` against
`version_groups_total`.

**Per title.** All 56, sortable, reconciling to the corpus totals.

**Provenance.** `generated_at`, the command that produced it, where the artifact lives, and which
corpus it describes — see "Which corpus" below.

## Which corpus the numbers describe

The committed artifact is the **development** corpus's, which is the `database.json` rule: reports
generated on the box stay on the box. The page must say so rather than implying it describes the
site the reader is on.

It can say more than that, and should. The box was back-filled on 2026-09-01 (BUILDLOG 091, PR #67)
and **every leaf of its own report matches the committed one but `generated_at`** — all four
`by_kind` counts and shares, `change_rows`, `concurrent` 77,596, `law_rows` 30,250,
`text_classified` 16,201 at 49.25%, `transitions` 423,800. Two independently loaded corpora agreeing
is a stronger claim than either number alone, and it is the claim that makes the page honest about
describing the deployed site.

## How CI updates the page

The page reads a JSON file. The file is kept equal to the artifact by a check that fails the build.

**`frontend/src/data/version-changes.json` is a copy of `docs/verification/version-changes.json`.**
It has to be a copy: `docker-compose.prod.yml` builds the reader with `build: ./frontend`, so
nothing under `docs/` exists at image-build time. This is exactly the trap ADR-0053 recorded when
the colour-pair list moved to `frontend/src/data/color-pairs.json` for the same reason — do not
try to import across the boundary or alias it in Vite; the dev server would work and the deployed
image would not build.

**A make target syncs it and a Vitest test proves it is synced.** `make sync-verification` (or a
name the implementer prefers) copies the artifact; `frontend/tests/versiondata.test.ts` asserts the
two files are deep-equal and fails `make test-web` when they are not. That is the whole of "CI
updates the page each time the report is run": regenerate the report, run the sync, and the build
tells you if you forgot. It is the same shape as every other ratchet in this project — the guide
ratchet, the contrast artifact, the JS budgets.

**Declined: having `ingest` write both files.** `write_report` calls the shared
`write_verification_json`, and ingest writing into `frontend/` crosses the layering in
`tests/test_architecture.py`'s spirit — ingest is deliberately on the far side of the storage
boundary and has no business in the reader's source tree.

**Declined: fetching the numbers at runtime from a new API endpoint.** It would let the page
describe the deployed corpus exactly, and it costs a route, a repository method, a cache policy and
a rate limit, and it breaks the property in the next section. Worth revisiting only if the two
corpora ever stop agreeing.

## The page must reach no data

`/app/design` renders identically on an empty machine because it makes no API call and pins no
release point (ADR-0053). This page must have the same property, and for the same payoff: it lets
`make shots` and the axe matrix treat it as a fixed target, and it lets a guide scenario assert its
content in CI, where the fixture corpus is Title 16 at two release points and could never produce
these numbers.

`tests/e2e/design.spec.ts` has the existing test that enforces no-data on a page; mirror it.

## Traps, measured rather than guessed

Each of these was checked against the artifact and the codebase while writing this spec.

1. **`per_title[t].by_kind` is sparse.** Title `18a` has no `text` key at all —
   `{"initial": 26, "notes": 1, "structure": 21}`. A cell rendering `v.by_kind.text` prints
   `undefined` on that row. Default every missing kind to 0.
2. **`text_classified_share` is `null` where there are no text changes** (title `18a`), and
   `by_kind.initial.share` is `null` corpus-wide, because an initial group has no departing group to
   have changed from. Render both as a dash, not as `0%` and not as `null`.
3. **A title number is a string — gotcha 16 is live here.** The keys include `5a`, `18a` and `50a`,
   and sorting them lexically gives `1, 10, 11, 12, …, 18a, 19, 2` — which is what the front page
   listed for eight sessions. `titleSortKey` and its comparator already exist at
   `frontend/src/lib/url.ts:276`; use them.
4. **56 titles, not the corpus's 58.** `11a` and `28a` have no change rows. A reader who counts will
   notice, so the page should say what the number is and that a title with a single version group
   contributes only `initial` rows.
5. **The per-title figures reconcile exactly** — the 56 rows sum to 32,893 text changes and 489,738
   change rows, the corpus totals. Assert that in the Vitest test; it is a free check on both the
   artifact and the rendering.

## Ratchets this touches

A new reader route turns several checks red until each is fed. This list is the cost of the page and
it is the intended cost.

| What | File | Why |
|---|---|---|
| Guide ratchet | chapter 09's `covers.routes` | `frontend/tests/guide.test.ts` fails on a route no chapter claims |
| ADR coverage | chapter 09's `covers.adrs`, or the infrastructure list | the same test fails on an ADR classified nowhere |
| IA map | `docs/ia-map.md` Routes table | a row: purpose, reached from, exits to, chrome |
| Accessibility matrix | `docs/a11y/routes.json` | a route entry; the scan count in CLAUDE.md (329) moves |
| JS budget | `docs/js-budgets.json` | a ceiling; `docs/verification/js-bytes.json` regenerates via `make test-web` |
| Screenshots | `make shots` | no horizontal overflow at 320px or at 1280 zoomed to 200% |
| Guide scenario | chapter 09 | ADR-0038 — a behavioural claim carries a ` ```scenario ` block, which is also a Playwright test |

**The wide table is the accessibility risk.** Put it in an `overflow-x: auto` container that is
keyboard-reachable and has an accessible name — `docs/a11y/known-violations.json` already carries
two scrollable regions with no keyboard route in, owned by tasks A4/A10, and this must not become a
third. Give the table a `<caption>`, `scope="col"` headers, and `aria-sort` on the sorted column,
which is ADR-0071's established pattern. Note ADR-0071's two traps if the sort options become links:
`:root[data-theme="dark"] a` is 0-2-1 and beats a single-class pill, and USWDS paints
`th[aria-sort]` a fixed `#97d4ea` in the light theme, `aria-sort="none"` included.

**Sort without script.** `SortBar.astro` plus `?sort=` in ADR-0071's vocabulary, server-rendered, so
the ordering is citable by URL and the page keeps its zero-JS budget. `SortBar`'s props are at
`frontend/src/components/SortBar.astro:38`.

## Phases

Sequential — each depends on the one before, and the whole is one session's work. There is no
parallel wave here; saying so is better than inventing one.

**D1 — the data path.** Copy the artifact to `frontend/src/data/version-changes.json`, add the sync
target to the `Makefile`, add `frontend/tests/versiondata.test.ts` (deep-equal against the artifact,
plus the reconciliation assertion from trap 5). Green `make test-web` with no page yet.

**D2 — the page.** `frontend/src/pages/data/version-changes.astro`: methodology prose, the
corpus-wide figures, the sortable 56-row per-title table, the provenance block. A component for the
table if it earns one. Traps 1–3 are the implementation.

**D3 — the wiring.** Guide chapter 09 gains its section, `covers.routes` and `covers.adrs` and a
scenario; `docs/ia-map.md`, `docs/a11y/routes.json`, `docs/js-budgets.json`. A link in from
`SiteFooter` and from `/app/about`'s data links. An ADR recording the page and the sync mechanism.
Regenerate `docs/verification/js-bytes.json` and `docs/verification/a11y.json`; update CLAUDE.md's
counts.

## Verified before merging

- `make test` — 851 passed, 2 skipped at the time of writing
- `make test-web` — 437 passed, plus the new test file
- `make test-e2e` — includes the new guide scenario
- `make test-a11y` and `make shots` — both need `make dev-all` running
- The page renders on a machine with an empty database
