# Wave 4 kickoff — classification tables, C5 (menus, guide, deploy)

Paste the block below into a fresh Claude Code session on this repository, with Opus selected.
Everything it needs beyond `CLAUDE.md` is in `docs/classification-spec.md`.

**Before pasting:** Wave 3 is on branch `c4-classification-reader` (tip `28d47d0`) and is
**unmerged** — Wave 3's session was harness-pinned to a worktree and could not write to the primary
checkout. Merge it first:

```
cd /Users/arihershowitz/Documents/workspace/aih/uscode-redesign
git merge --no-ff c4-classification-reader
```

The branch carries both C3 and C4, thirteen commits on top of `66354dd`. `make test` is 738 and
`make test-web` is 369 on that tip, both re-run against it. If `frontend/package-lock.json` shows
`"peer": true` markers, that is `npm install`'s doing and not a dependency change.

---

Read `CLAUDE.md`, then `docs/classification-spec.md` in full — §5 (frontend), §6 (verification),
the § What Wave N measured sections, and the C5 phase prompt. Waves 1, 2 and 3 are merged: the four
tables, the parser, the loader, the poll, the two `python -m ingest classification*` subcommands,
the storage protocol, seven API routes under `/api/v1/classifications` and three reader routes
under `/app/classification` are all in `main`, and 144,837 classification rows plus 21 ECCT rows
are loaded on the dev box. **The three reader routes are reachable only by typing their URL** —
nothing in the chrome links them, no guide chapter describes them, `docs/ia-map.md` has no rows for
them, and the deployed box holds no classification rows at all.

Execute Wave 4 — one agent, sequential, because it edits shared chrome files and asserts on
everything the earlier waves produced. Work in a worktree on a branch named for the phase, small
commits, imperative messages, `Co-Authored-By` trailer.

## What C5 owns

The C5 phase prompt is the specification. In summary:

1. **The chrome.** "Classification tables" into SiteHeader's More ▸ Reference group beside Release
   points, into SiteFooter's Browse group (the `footnav-browse` count assertion moves 2 → 3), and
   into `siteCommands()` in `frontend/src/lib/palette.ts`. The ordered-text assertions in
   `frontend/tests/e2e/chrome.spec.ts` and the palette tests move **in the same commits**.
2. **The guide chapter.** `covers.routes` = the three routes, `covers.adrs` = ADR-0067. Then delete
   both deferrals in one commit: the three routes in `UNDOCUMENTED_ROUTES` in
   `frontend/tests/guide.test.ts` (C4 left them there in a commit of its own, with a comment naming
   C5) and ADR-0067 in `INFRASTRUCTURE_ADRS` in the same file. Scenario blocks must be answerable
   from the CI fixture corpus, which `make ci-classification-data` loads offline — 4 documents, 192
   rows. Prose per documentation duty 7.
3. **`docs/ia-map.md`** — rows for the three routes with inbound `file:line` references, which
   exist only once item 1 lands.
4. **`/app/design` specimens** for the two components C4 introduced, `ClassificationTable` and
   `ClassificationLookup`. See the caveat below.
5. **`deploy/update-corpus.sh`** — run `python -m ingest classification-check`; on exit 10 run
   `python -m ingest classification`. The weekly `--force` sweep rides the existing Actions
   backstop.
6. **The backfill on the deployed box**, and `/app/classification` serving the full corpus there.

## Five things Wave 3 left you, which the C5 prompt does not say

1. **A `ClassificationLookup` specimen would break `/app/design`'s no-data property.** The island
   fetches `/api/v1/classifications/suggest` on input, and `design.spec.ts` enforces that the page
   reaches no data — which is exactly why `WatchButton` is excluded (ADR-0053). Three options, in
   C4's order of preference: render the specimen and never type into it, since the fetch is
   input-triggered and a static specimen reaches nothing; add an `endpoint`-less mode that renders
   the markup with no script; or exclude it as `WatchButton` is and say so on the page. The
   `idPrefix` prop and multi-instance binding are already in place for whichever you choose.
2. **`ClassificationTable` needs specimen data, not a fetch.** `/app/design` renders every part
   from the component given specimen data or from the library function that builds that markup
   elsewhere (ADR-0053). The specimen provision is under title 0, which OLRC does not publish, so
   its citations resolve to nothing — a classification row's citation cell must therefore render
   in both its states, linked and unlinked, since 1,533 of the corpus's rows have no
   `usc_identifier`.
3. **The 404-vs-empty distinction has three renderings and the guide should say so**: a covered law
   that classified nothing reads as an answer, a congress/session with no file is an `ErrorPage`
   404, and a law no table covers 404s from the API. **§4's own example is wrong** — 119-72 *is*
   covered; 119-103 and up is the uncovered case. Do not repeat 119-72 in guide prose or a
   scenario.
4. **`j`/`k`, `?sort=citation` and the rest of the guide's existing limitations are not yours.**
   What *is* yours to state flatly: the tables cover 1996 onward, so a section last touched before
   then has no rows; 129 rows keep their Stat. citation in `raw_line` alone; appendix rows derive
   no identifier by rule, so their citation cells do not link; and a change to the ECCT alone is
   invisible to the poll.
5. **`shed.spec.ts` is timing-sensitive and this wave made it likelier to trip.**
   `spendTheBucket` must out-run a one-token-per-second refill across 80 sequential requests, and
   Wave 3 added 43 axe scans and 4 e2e tests to the run. It is not bucket contention — the
   classification routes take their own API-side buckets and `frontend/src/middleware.ts` is
   untouched. If it fails on a combined run and passes alone, that is this, not your change.

## Verify, and report each

`make test`, `make test-web`, `make test-e2e`, `make test-a11y` and `make shots` green locally and
in CI; the guide's new scenarios running as tests; the chrome assertions updated rather than
deleted; `docs/ia-map.md` regenerating cleanly; and the deployed `/app/classification` serving all
144,837 rows. A fresh-context reviewer reads the merged diff before the wave is called done.

End the session by updating `docs/classification-spec.md`'s status line, appending the BUILDLOG
entry, and recording in `docs/deploy-status.md` what the box now holds. The workstream is complete
after this wave.
