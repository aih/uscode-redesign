# Workstream B — state and plan

Paste `00-CONVENTIONS.md` above any task prompt, then this file, then the task you want.

**Workstream B is complete.** B1–B6 and B7–B11 have all landed. What is left on this workstream is
the re-measurement noted under "Candidate tasks" below, which needs the deployed box.

---

## Where the work is

**Merged.** B1–B3 landed in PR #24, B7–B10 in PRs #38 and #39. B5, B6 and B11 are on branch
`b5-b6-b11`, twelve commits, `d2477eb`..`611d17c`.

All suites green as of the last commit:

| suite | count |
|---|---|
| `make test` | 558 |
| `make test-web` | 346 |
| `make test-e2e` | 536 passed, 2 skipped (272 of them the a11y scan) |
| `make shots` | reflow clean at 320 CSS px and 1280@200% |

`docs/verification/a11y.json`: **8 route/rule pairs over 1,990 nodes**, and everything in it is still
`docs/a11y/known-violations.json`'s. The node count is reproducible run to run since session 44.

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

## Done: B3, measure half (session 28)

Three artifacts against the deployed box, each regenerable by one command:
`make loadtest` (with `BASE=`), `make navprofile`, `make spine-explain`. BUILDLOG 046 has the full
account; the numbers that decide what to fix are below.

**The wait is not the server's.** A reader's four clicks down the spine cost **823 ms**, of which
**221 ms is the origin and 601 ms (73%) is the network**. Origin, section page, warm p50: 41 ms
Astro's own render, 37 ms for the five API calls' critical path, ~3 ms of that in Postgres. Caddy's
own share is small and cannot be pinned down more precisely than that — the same page measured twice
gives 0.4 ms and 11.1 ms.

**The two open questions from session 27 are answered.**

- **ADR-0043's fourth call is free in wall clock.** The parent TOC costs 16 ms and runs in the same
  `Promise.all` as the release list at 27 ms, so it adds nothing to the page. Under load it
  is the *fastest* API row: 61.9 rps, 116.9 ms p50, 2,168 wire bytes. The 156 rps / p95 83 ms figure
  it replaces was a laptop against a partial corpus.
- **The transient 502 did not recur** in 813 timed requests plus a full load test.

**What is actually slow, in the order the numbers put it:**

1. **The reader page under concurrency** — 195 ms for one reader, **702 ms p50 at 11.0 rps with 8
   concurrent** on 2 vCPUs. The JSON routes hold up; the SSR page does not.
2. **`/api/v1/releases?ingested_title=N`** — 27.0 ms at the API container and ~247 ms p50 at 8
   concurrent, the slowest unlimited API route, fetched on every section page *and* every TOC page to
   fill a picker with 381 options. **ADR-0045 fixed this**; the throughput figure was measured against
   `?title=`, which is the cheaper parameter, so it understates what was being paid.
3. **The API diff: 5.1 s per request.** The limiter sheds correctly (23 × 429 at C=10) but the
   requests it *admits* still exceed a 20 s client timeout. B5 owns this.
4. **`structure_nodes` has no index on `identifier` alone** — the unique constraint is
   `(title_id, identifier)`, which a lookup by identifier cannot use, so it seq-scans 9,916 rows at
   1.3 ms, in `get_section`, both `get_toc` paths and `resolve_id`. Everything else in Postgres is
   fine: no repository call exceeds 2 ms, and the 96,204,776-row `guid_map` answers in 0.035 ms.

## Done: B3, fix half (session 28b)

Three fixes taken, one declined, in the order the numbers put them rather than B3's.

- **The `structure_nodes.identifier` index** (migration `d5c81f27a930`). Seq Scan 1.497 ms with 9,915
  rows removed by filter → Index Scan 0.135 ms. The local table has the same 9,916 rows as the box,
  so that comparison is faithful.
- **ADR-0045 — the release list, once per title per five minutes.** Entries hold the in-flight
  promise, so eight concurrent cold-cache views make **one** call rather than eight; warm views make
  none. Counted from the API's access log, not from intentions.
- **ADR-0046 — a per-route inline-script byte budget** in `make test-web`, counted from source
  because there is no bundle to weigh, and validated against a live page to within exactly the two
  accounts-gated components.
- **ADR-0047 — fix 1 declined.** The audit found ADR-0018's policy already correct on the deployed
  host. What is missing is a shared cache to read those headers, and a cache on the box addresses the
  27% of a reader's wait that is the origin rather than the 73% that is the network.

`docs/verification/b3-fixes.md` holds the commands and the before/after. **The re-measurement is
done** — PR #24 merged, the deploy ran, and all three artifacts were regenerated against the box:

- **The spine's plans**, the one result attributable to B3 alone since nothing else in the deploy
  touches Postgres: `get_section` 1.649 → **0.348 ms**, `resolve_id` over the 96 M-row `guid_map`
  1.388 → **0.119 ms**, and no watched table sequentially scanned by any of the thirteen calls.
- **Under load:** reader TOC page 14.4 → **35.0 rps**, 525.5 → **183.7 ms** p50; reader section page
  11.0 → **15.6 rps**, 702.4 → **480.0 ms**.
- **One reader:** the spine's four clicks 823 → 801 ms, of which the **origin is 221 → 159 ms**. The
  network share is unchanged and still dominates — ADR-0047's argument, restated by its own
  re-measurement.

**It is not a clean A/B, for two reasons the artifact states.** The previous deploy was `387ff3a`,
the commit this branch was cut from, so the *before* box had none of B1, B2 or B3 — the after box's
section page carries a rail, a release band and a switcher it did not have, and makes five API calls
where it made four. And the twelve untouched routes drifted to a median 1.073× their before p50, so
the gains are understated by about that much.

**A measurement error from the measure half, corrected here:** the reader calls
`/api/v1/releases?**ingested_title**=`, and both scripts had asked for `?title=`. Different work
(`?title=` filters in the repository; `?ingested_title=` fetches all 382 release points and filters
in Python) and different cost — **27.0 ms against 20.1 ms**. The release list was a worse offender
than the measure half reported.

## Done: B4 (session 29)

**Ranking is measured** (ADR-0049). `docs/verification/search-judgements.json` is 37 queries and
529 graded documents (312 of them graded relevant), pooled from every candidate profile before grading; `scripts/search_eval.py`
scores them. deployed **0.6894** → shipping **0.7159** nDCG@10, recall@10 **0.7672** → **0.8016**.
Thirteen queries better, nine worse, fifteen unmoved.

**The heading weight was never the one written down** — a deprecated index-time `boost: 2.0` in the
mapping multiplied with the query's `heading^2`, so the real weight was 4. The baseline profile is
`heading^4` on that evidence, and it reproduces the old scores exactly.

**`all-versions` scored highest and was declined**, because it changes what a result is. The default
still reads the text in force and reports the rest as "also matched in N earlier versions".

**Six scopes** — `heading:`, `title:`, `chapter:`, `status:`, `release:`, `date:` — lifted out of
the query before the cluster sees it, so ADR-0031's forgiving parser stands. **Facets edit the
query**, so a filtered search is citable by its URL alone. **`?sort=`** offers relevance, citation
order and most-recently-amended.

Two counting defects fixed on the way: `hits.total` was capped at 10,000, and under collapse it
counted versions while the page listed sections.

**The rail is pinned** (ADR-0050) — asked for mid-session, and it reverses standing decision 3
below.

**The index rebuilds itself on a mapping change** (ADR-0051). The names are aliases now, over a
physical index named for its mapping's fingerprint; `reindex_search --if-changed` rebuilds only what
drifted and builds beside the live index, so search stays up. `deploy-on-box.sh` runs it. The
failure it prevents is silent — a field the new code queries and the old index lacks is *absent, not
broken*, so `title:16` returns an empty page that looks like a title with nothing in it.

## Done: B5, B6, B11 (session 44)

**B11 — the chrome's six loose ends** (all six; item 1 settled as an ADR-0064 addendum, item 6 as a
fix). The a11y node count is reproducible — a route may declare `readyWhen` and the two vendored
bundles do, because a scan that lost the race against their own first paint reported **one** node
where a rendered one reports 174. `make measure` is split: the character-count check runs in
`make test-e2e` on every push, the scroll lengths stay in the target and name the commit they were
taken at. `--ink` on `--rule` is a declared pair (12.92:1 / 7.54:1). `.navdrop--more`'s `open` was
not merely inert — closing it at 375 is invisible and shows up at 1280. The theme control stays in
both places, on a measurement and on the fact that the bar's copy carries no word. `[` and `]` say
why they did nothing, and the shortcut list is in the Help menu.

**B6 — dead ends** (ADR-0065). The nearest resolving ancestor with its trail; a provision absent
here saying when it is present; one appendix explanation given by both surfaces, naming both real
forms; and `/app/429`, a shed diff rendered as a page at the URL it asked for. **No search box on
the error page** and **the redirects table declined** — both deliberate, both in the ADR.

**B5 — compare in two clicks** (ADR-0066). `CompareWith` on every section header, defaulting to the
last release point that held *different* text. `?at=` carries the provision through and the redline
marks it inside the whole section. The API diff drops `@id` by default and memoises on the resolved
pair: **§ 1536 4,063.9 ms → 1.8 ms**, 399 ops → 3 on § 668dd (`make diffcost`).

## Standing decisions — do not silently reverse these

0. **The compare default is read from the version timeline, never from `content_first_seen`.** That
   field follows the stored fragment's `first_release_id` and an incremental load can attach an
   earlier release point to a row without lowering it, so on real data § 45f's newest group reports
   `first_seen: 119-99` while its own `releases` run from `117-80`. Using it ships a "Compare with…"
   whose default produces "No changes", which looks exactly like a broken feature. `versions[].releases`
   comes from `section_release_map` and is authoritative. `compare.test.ts` pins this.



1. **The release switcher is not in the sticky chrome, and that is measured.** Before the move the
   stack had 19px of headroom under `--sticky-h` at 700px and 55px at 1280px; the date field costs
   about eighty. `--sticky-h` is what `scroll-margin-top` spends, and `docs/backlog.md` already flags
   that band for carrying 19rem of chrome. After the move: 89px and 85px.
   `tests/e2e/sticky.spec.ts` asserts ≥60px spare at both, so eating it requires raising the token on
   purpose. The **release point itself stays pinned as text** (`.contextbar__rp`).
2. **`/app/versions` and `/app/diff` get the breadcrumb but no release band.** The first spans every
   release point, the second is about two. This is a narrower reading of B2's "every reader page"
   than the task asked for, taken deliberately and recorded in ADR-0044.
3. ~~**The rail is not sticky**~~ — **reversed in session 29 (ADR-0050)**, on request. It is pinned
   from 64em with `max-height: calc(100vh - var(--sticky-h) - 1.5rem)` and its own scrollbar. The
   bounded height is what the earlier attempt was missing: `top` alone pins the rail and then lets
   it run past the bottom of the viewport, so its tail is unreachable without scrolling the
   document. Asserted in `sticky.spec.ts`, which also had to stop counting the rail as chrome —
   left in, it is the tallest sticky thing on the page and made two headroom probes measure it
   instead.

   **It is still not a `<details>`.** CSS cannot force the element open, so at desktop width the
   summary would report itself collapsed with its content visible.
4. **The map found no duplicated navigation route.** `/app/goto` vs `/app/search`, the three
   prev/next affordances, and the two from/to pickers were each checked and are each one path. B1
   asked for deletions; there were none to make. The real defect was the opposite — unreachable and
   thinly-reachable routes.

5. **A measurement of this site asks for compression, or it is not measuring this site.** curl sends no
   `Accept-Encoding` unless told and `hey` needs `-H`, while Caddy compresses only what asks — so an
   unadorned run times every reader page at 76,021 bytes against the 21,246 a browser receives. Both
   scripts now ask, and `%{size_download}` under `--compressed` reports wire bytes.
6. **The rate-limited routes are measured twice on purpose**, once inside their budget and once past
   it, and the artifact says which. A single flat run measures ADR-0029 and reads as a throughput
   *improvement* on whichever route shed the most.

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
- **Astro's own render is the largest single component of the origin cost** — 41 ms against 37 ms for
  all five API calls' critical path — and the reader page, not the API, is what collapses under
  concurrency. Profiling inside the Node process is a task of its own and is on no workstream's list.
- **The box's own throughput ceiling is unmeasured.** At C=8 over a ~120 ms round trip the ceiling is
  8 ÷ 0.12 ≈ 65 rps as arithmetic, and every fast row sits just under it — so those rows describe the
  link, not the box. Measuring the box needs a load generator running on it.
- **`docs/verification/loadtest.json` is stale for `/app/diff` three times over** — ADR-0026 moved the
  reader off the API endpoint, ADR-0066 made that endpoint 150–2,000x cheaper, and the reader's own
  limiter went 8/0.5s to 20/1s. Regenerating it needs the deployed box (`make loadtest BASE=…`), and
  it is the one measurement this workstream still owes.
- **The reader's diff limiter was resized on an argument, not a measurement.** ADR-0066 argues a
  comparison is now one click where it was three, so a reader asks more often — but the change was
  found by the browser suite shedding its own requests. Worth re-deriving from what `/app/diff`
  actually costs.
- **Nothing pages the "Compare with…" select** — 380 options in the markup of every section page on a
  full corpus, which is the release-switcher debt now carried twice on one page.
- **`scripts/loadtest.sh` speaks HTTP/1.1** — `hey` has an `-h2` flag and the script does not pass it,
  while `navprofile.py` negotiates h2 through curl. The two artifacts' latencies are not directly
  comparable until it does.

## Where things live

```
docs/ia-map.md                          the map, and the unfindable-route list
docs/verification/navprofile.json        journeys, four vantages, the layer split
docs/verification/loadtest.json          throughput, every row naming its limiter
docs/verification/spine-explain.json     the spine's query plans on the real corpus
scripts/navprofile.py                    ships itself to the box over SSM
scripts/spine_explain.py                 explains what the repository sent, never transcribed SQL
docs/verification/search-judgements.json 37 queries, 529 graded documents
docs/verification/search-relevance.json  nDCG@10 per profile, per query
scripts/search_eval.py                   pool | score — the harness, over the shipping query
storage/searchquery.py                   the parser, the profiles and the request body
frontend/src/lib/searchscope.ts          the same scopes, read and written by the facet links
docs/adr/0043                           one navigation chrome
docs/adr/0044                           release context, and the switcher that keeps your place
docs/adr/0049                           the measured ranking, and the scopes
docs/adr/0050                           the pinned rail
docs/adr/0051                           the index rebuilds itself (there is no ADR-0048)
docs/adr/0065                           a dead end says where else to go
docs/adr/0066                           compare from the section header, and the guid-free diff
docs/verification/diffcost.json          what the API redline costs, with and without the guids
scripts/diffcost.py                      make diffcost — times the diff in process, past the limiter
frontend/src/lib/compare.ts              which release point to compare with, and why not the previous
frontend/src/components/CompareWith.astro
frontend/src/pages/429.astro             the shed-request page the middleware rewrites to
frontend/tests/e2e/shed.spec.ts          its own Playwright project: it empties a global bucket
frontend/src/layouts/Base.astro         where the chrome is assembled
frontend/src/components/ChapterRail.astro
frontend/src/components/ReleaseContext.astro   replaces the deleted Provenance.astro
frontend/src/components/ReleasePicker.astro    two GET forms
frontend/src/middleware.ts              the empty-?release= canonical redirect
frontend/tests/e2e/sticky.spec.ts       the headroom the switcher's move bought
frontend/scripts/scenarios.mjs          the scenario DSL, now with a `select` verb
```

Guide chapters claiming these ADRs: **02** (`reading`) holds 43 and 64; **03**
(`reading-at-a-point-in-time`) holds 44; **01** (`what-this-site-is`) holds 65; **04**
(`version-history-and-redlines`) holds 66. A new ADR turns `make test-web` red until some chapter
claims it.
