# ADR-0076 — The version-change data has a page, fed by a synced artifact

- **Status:** Accepted
- **Date:** 2026-09-01
- **Context:** `docs/version-data-page-spec.md` (the decisions taken before
  implementation); ADR-0053 (`/app/design` renders a committed artifact and
  reaches no data), ADR-0067 (the classification tables), ADR-0071 (sortable
  tables and their two traps), ADR-0074 (the stored classification and
  attribution), ADR-0075 (the reader's two views of a version history).
  Session 92.

## Context

ADR-0074 computes a classification of every transition between two stored
versions of a section and, for a text change, an attribution to the Public Laws
the OLRC classification tables record. The full-corpus backfill reports to
`docs/verification/version-changes.json`: 489,738 change rows over 423,800
transitions, 75.14% structure / 17.10% notes / 7.76% text, 49.25% of text
changes attributed, `concurrent` on 77,596.

ADR-0075 spends that on one section at a time — a version history defaults to
statutory changes and says which law is recorded against each. Nothing on the
site said how the distinction is made, and nothing showed what the corpus turned
out to contain. A reader looking at a history with three entries where the
timeline used to have eleven had no page to go to.

## Decision

1. **One reader route, `/app/data/version-changes`.** Methodology, the
   corpus-wide totals, the full per-title breakdown, and provenance, in that
   order. The `data/` segment leaves room for siblings — search relevance,
   corpus counts — without a second decision about where such a page lives.

   Not a guide chapter. The chapters are markdown rendered by `GuideLayout`, and
   markdown cannot import JSON, so every number in a chapter is typed in by
   hand. Guide chapter 09 gains a section pointing here and claims the route.

2. **The page reaches no data**, the property ADR-0053 gave `/app/design`. No
   API call, no database, no release point. It renders identically on an empty
   machine, which is what lets `make shots` and the axe matrix treat it as a
   fixed target and lets the guide's scenario assert its content in CI, where
   the fixture corpus is Title 16 at two release points and could never produce
   these numbers.

3. **The figures come from a copy of the artifact, and a test fails on drift.**
   `frontend/src/data/version-changes.json` is `make sync-verification`'s copy
   of `docs/verification/version-changes.json`;
   `frontend/tests/versiondata.test.ts` asserts the two are equal leaf for leaf.
   It has to be a copy: `docker-compose.prod.yml` builds the reader with
   `build: ./frontend`, so nothing under `docs/` exists at image-build time.
   Importing across that boundary or aliasing it in Vite gives a working dev
   server and an image that does not build — ADR-0053 met this when the
   colour-pair list moved for the same reason.

   The same test asserts that the 56 per-title rows sum to all four corpus kind
   counts, to `change_rows` and to `text_classified`. That is a check on the
   artifact as much as on the rendering, and neither could make it alone.

4. **Declined: `ingest` writing both files.** `write_report` goes through the
   shared `write_verification_json`, and ingest writing into the reader's source
   tree crosses the layering `tests/test_architecture.py` exists to hold — ingest
   is deliberately on the far side of the storage boundary.

5. **Declined: a runtime endpoint.** It would let the page describe the deployed
   corpus exactly, and it costs a route, a repository method, a cache policy and
   a rate limit, and it ends the property in decision 2. Worth revisiting if the
   two corpora ever stop agreeing.

6. **The page says which corpus it describes.** The committed artifact is the
   development corpus's, which is `database.json`'s rule: reports generated on a
   box stay on that box. The deployed box was back-filled on 2026-09-01 and
   every leaf of its own report matches the committed one but `generated_at`, so
   the page states that two independently loaded corpora produce the same
   classification of the same 423,800 transitions rather than implying the
   numbers are the deployed site's directly.

7. **The sort is `?sort=` resolved on the server**, in ADR-0071's shape: four
   keys (`title`, `rows`, `text`, `classified`), each reversible, the option in
   force a link that reverses it, and the four sortable column headings the same
   control carrying `aria-sort`. The page keeps a zero-JavaScript budget and a
   sorted table is citable by its address. The default is the Code's order and
   is omitted from the URL.

   `SortBar`'s `activeKey` read the classification vocabulary by name
   (`sort.startsWith("code") ? "code" : "pl"`), which gave every unrecognised
   value to `pl`. It now strips the `-desc` suffix — the same answer for
   `pl`/`code`, and the right one for a second vocabulary.

8. **A count column's first direction is largest first.** `SortBar` sends an
   option that is not in force to its own forward direction, so a size column
   opened by a reader who wants the big titles would otherwise start at title
   18a's 48 rows. The forward direction is the useful one and the words under
   the option say which it is; `-desc` reverses it. A reversed order is the
   forward list reversed rather than a second comparator (ADR-0071's rule): 10
   of the 56 titles tie some other title on at least one sortable column.

## Costs and limits, named

- **The artifact and its copy can drift for exactly one commit.** The test
  catches it on the next `make test-web`, which is every push, but a
  `version-changes --report` run that does not also run `make sync-verification`
  leaves a working tree whose page and whose artifact disagree.

- **The numbers describe the corpus at one moment.** `generated_at` is on the
  page, and nothing recomputes it: a corpus load moves the real figures and the
  page keeps saying what the last report said until someone re-runs it. The
  deployed box runs `version-changes` from `update-corpus.sh` (ADR-0074) but
  writes no report and could not commit one if it did.

- **The claim that the deployed corpus agrees is dated, not continuous.** It was
  true on 2026-09-01, recorded in BUILDLOG 091 and `docs/deploy-status.md`, and
  nothing re-checks it. Decision 5's endpoint is what would.

- **Two titles are absent and the page has to explain them.** 11a and 28a hold
  no sections at any of their 20 and 19 title-releases, so they have no version
  groups; the corpus is 58 titles and the table is 56 rows. A reader who counts
  would otherwise find a discrepancy the page does not answer.

- **The artifact is sparse and the page must not print `undefined`.** Title 18a
  carries no `text` key and 50a no `structure` key, and a share is `null`
  wherever its denominator is zero — `by_kind.initial.share` corpus-wide, and
  18a's `text_classified_share`. `lib/versiondata.ts` defaults a missing kind to
  0 and renders a `null` share as an em dash; both are asserted rather than
  eyeballed.

- **The per-title table has eight columns and scrolls on a narrow window.** All
  three tables are in a `role="region"` with `tabindex="0"` and an accessible
  name — `docs/a11y/known-violations.json` already carries two scrollable
  regions with no keyboard route in, owned by tasks A4 and A10, and these are
  not a third. The cost is a tab stop per table at every width, which is
  `ClassificationTable`'s existing bargain.
