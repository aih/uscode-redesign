# Classification tables — implementation spec for aih/uscode-redesign

**Status:** spec written 2026-08-11. **Wave 1 landed 2026-08-11** and is merged into `main`
([PR #44](https://github.com/aih/uscode-redesign/pull/44)) — C1 (parser, fixtures, ADR-0067)
and C2a (schema, migration `3c8d9ab6d527`); see
[§ What Wave 1 measured](#what-wave-1-measured) for the six places this spec was wrong.
**Wave 2 landed 2026-08-11** and is merged into `main`
([PR #45](https://github.com/aih/uscode-redesign/pull/45)) — C2b (fetch, loader, CLI, poll,
migration `0044883c483c`), with the whole corpus loaded once from the live source; see
[§ What Wave 2 measured](#what-wave-2-measured). **Wave 3 landed 2026-08-11** on branch
`c4-classification-reader` (unmerged) — C3 (storage protocol, seven API routes) and C4 (three reader
routes, the lookup, the table); see [§ What Wave 3 measured](#what-wave-3-measured).
**Wave 4 landed 2026-08-13** on branch `c5-classification-chrome`, which stacks on Wave 3 and is
also unmerged — C5 (the chrome, guide chapter 10, `docs/ia-map.md`, the `/app/design` specimens and
the `update-corpus.sh` wiring); see [§ What Wave 4 measured](#what-wave-4-measured). **The
workstream is complete** but for one step it could not take from a worktree: the two branches want
merging into `main`, and the backfill on the deployed box is owed
(`docs/deploy-status.md`).

The OLRC Classification Tables record which provision of each new Public Law was classified to
which US Code section (118-35 §101(3) → 18 USC 3551 note). The site holds nothing of this today.
This spec covers scraping the tables and the Editorial Classification Change Table (ECCT),
storing them, serving them at `/api/v1/classifications/…`, and displaying them under
`/app/classification` with sorting, filtering, and a lookup box. Editorial Reclassification (the
title-reorganization project) is out of scope.

Scope decisions confirmed with the user 2026-08-11:

- Filtering is page-local, backed by Postgres. The global search box, OpenSearch, and the search
  scope vocabulary are untouched.
- Rows link into the reader one-way. Section pages are not modified; the by-identifier API route
  ships now so a section-page panel can be added later.
- Per-session pages mirroring the source, plus a classification lookup with autocomplete: a PL or
  PL-provision query (shorthand `118-33`, `118-33 101`) navigates to the right session page
  filtered to that law; a US Code citation query leads to the section's notes in the reader
  (`#section-notes`, the ADR-0055 anchor) when the section resolves — OLRC's notes carry a
  provision's classification history — with a second suggestion linking the classification rows
  for that section.
- Pub. L. citations link to govinfo (`https://www.govinfo.gov/app/details/PLAW-{congress}publ{num}`
  — predictable URLs; congress.gov's are bill-keyed). Stat. pages link to OLRC's statviewer
  (`https://uscode.house.gov/statviewer.htm?volume=V&page=P`) as the source tables do.

## 1. Source structure (measured 2026-08-11)

### Inventory

- Entry pages: `https://uscode.house.gov/classification/tables.shtml` (current congress, 119th)
  and `priortables.shtml` (104th–118th).
- Filename scheme: `tbl{congress}{pl|cd}_{1st|2nd}.htm`. `pl` = Public Law order, `cd` = US Code
  order — the same rows resorted (verified against tbl118pl_2nd/tbl118cd_2nd). Scrape only `pl`;
  Code order is a sort in our display. The 104th is one whole-congress file (`tbl104pl.htm`,
  covering 104-1 through 104-333). ~31 `pl` files. Some vintages also link PDF variants — ignore;
  HTML exists for all.
- Scale: 118-2nd ≈ 2,990 rows, 104th ≈ 11,740 → corpus ~100–150k rows. Postgres handles this
  without OpenSearch.
- The current-session file is republished as OLRC classifies new laws. The page header carries the
  covered PL range with gap syntax — "Public Law 119-70 and Public Laws 119-74 through 119-102" —
  and a "Prepared … {date}" block (the 104th instead has a "last updated MM/DD/YYYY" line).

### Table format

Fixed-width text inside `<PRE><FONT face=Courier>`; no `<table>` markup. Six columns:

```
 U. S. Code
Title Section      Description      Pub. L.  Sec.                  138 Stat.
-------------      -----------      -------------                  ---------
18    3551         nt               118-35   101(3)                   3
42    254c-15      tr to 42/290ee-10118-84   2(6), (7)                1544, 1545
5A    101          Ethics Act nt new110-24   1                        100
```

- Title: `18`, `5A` (A suffix = Appendix → our `t5a` form).
- Description (an open set — never model as an enum): blank = amended; `nt`, `nt [tbl]`, `new`,
  `nt new`, `prec`, `tr fr T/S`, `tr to T/S`, `omitted`, `repealed`, `gen amd`,
  `nt ed chg`/`ed chg` (cross-reference to the ECCT), act names prefixed on appendix rows.
- Sec.: `101(3)`, `2(6), (7)`, blank (whole-law rows); a trailing quoted string (`202 "1948"`)
  names the new section being added to the underlying act.
- Stat.: page number(s), hyperlinked to `/statviewer.htm?volume=138&page=3` in recent vintages,
  plain text in old ones. The volume is in the column header (`138 Stat.`); the 104th header is
  `Stat. Page` (that congress spans two Stat volumes), so its volume is null unless a statviewer
  link supplies it.

### Parsing hazards (each observed in the downloaded files)

1. Column offsets come from the header line, not the ruler — the ruler merges Title+Section into
   one dash group. Offsets differ by era: 110th–119th `0/6/19/36/45/67`, 104th `0/6/20/42/51/68`.
   Derive per file from header-token positions; a missing token is a parse error (the format
   changed and the parser needs revisiting).
2. The Description column can overrun into the Pub. L. column with no separating space
   (`tr to 42/290ee-10118-84`, `Ethics Act nt new110-24`). When the fixed-width Pub. L. cell does
   not match `^\d+-\d+$`, re-split the combined region with `^(.*?)(\d{2,3}-\d{1,4})\s*$`.
3. Statviewer `<a>` tags carry (volume, page) and must be harvested before tag-stripping; the
   104th has `openPLaw` anchors to strip. After stripping, lines realign to the fixed widths.
4. Multi-value stat pages (`1544, 1545`) and Sec. cells (`2(6), (7)`). NBSP is replaced 1-for-1
   with a space so column offsets survive.
5. Appendix rows never derive a `usc_identifier` — appendix identifiers are
   `/us/usc/t5a/pl/92/463/s1` / `/us/usc/t50a/act/…` shapes that the table's `5A / 405` cannot
   produce. Null by rule, not by failure.
6. No usable `Last-Modified`/`ETag`; pages embed a per-request `jsessionid`, so raw-byte hashing
   detects nothing. Change detection is the covered-PL-range text on `tables.shtml`; the stored
   `content_hash` is sha256 of the extracted `<PRE>` text.

### ECCT

`ecct.html` (current session) plus archived `ecct_119-{n}.html`; only the 119th exists. A real but
malformed HTML table (stray `</div>` inside `<table>`) — extract rows by regex, not an HTML
parser. Four columns: Former Classification (`42:294t nt`), New Classification (`42:294u new`),
Provision Affected, Provision Prompting Change (both full PL citation strings). Zero data rows is
valid (the current table has one row); zero header cells is a parse error.

## 2. Database schema

Four tables in `db/models.py`, one Alembic migration with a real `downgrade()`. House
conventions: plural snake_case, integer surrogate PKs, `ARRAY` where the data is a list, named
`ix_<table>_<cols>` indexes each with a comment naming the query it serves.

**`classification_files`** — one row per source document, `kind` `'pl' | 'ecct'` (string, open
set): `id, kind, congress, session (1|2; 0 = the 104th's whole-congress file), source_url,
source_filename, covered_laws_text (verbatim — the change-detection key; null for ECCT),
covered_ranges ARRAY(String) (gap-aware segments: ['70-70','74-102']), first_law, last_law,
prepared_date, stat_volume (null for the 104th), content_hash, fetched_at, row_count,
skipped_lines`. `UniqueConstraint(kind, congress, session)`.

**`classification_entries`** — raw columns verbatim plus parsed best-effort fields:
`id, file_id FK CASCADE, row_seq (0-based order within the file), raw_line (tag-stripped,
verbatim), title_raw ('5A'), title_num ('5a' — a string; order through title_sort_key, never
directly), is_appendix, section_raw, section_norm (lowercased, U+2013/U+2011 → '-'),
description_raw ('' = amended), is_note, action (str | null, open set), transfer_counterpart
('42/290ee-10'), act_name (appendix rows), usc_identifier ('/us/usc/t18/s3551' | null),
pl_congress, pl_num (nullable — a row whose Pub. L. cell fails to parse is kept and warned about,
never dropped), pl_section_raw, new_section_quote, stat_volume, stat_pages ARRAY(Integer)`.
Indexes: `(pl_congress, pl_num, row_seq)`; `(title_num, section_norm)`; `(usc_identifier)`.
`UniqueConstraint(file_id, row_seq)`. No stored `pl_label` (derivable); no `session` on entries
(it is on the file). Note rows and `prec` rows do derive the parent section's identifier,
qualified by `is_note`/`action`.

**`ecct_entries`**: `id, file_id FK, row_seq, former_raw, former_title_num, former_section_norm,
former_is_note, new_raw, new_title_num, new_section_norm, new_is_note, provision_affected (Text,
verbatim), provision_prompting, affected_pl_congress, affected_pl_num, prompting_pl_congress,
prompting_pl_num`. Indexes on former and new `(title_num, section_norm)`.

**`classification_source_checks`** — a sibling of `source_checks`, not a reuse of it:
`PostgresRepository.last_source_check()` takes the newest row regardless of `source_url` and
feeds `/api/v1/status`; interleaving classification polls would make the corpus-freshness answer
flap between two sources. Columns: `id, checked_at, source_url, ok, files_seen,
changed_files ARRAY(String), latest_covered_text, error (truncated to 500 chars)`. Written on
success and on failure.

**Load policy: wholesale replace per file, one transaction.** When a file's extracted-PRE hash
changed: delete that file's entries, re-insert all rows, update the registry row in place, commit
once. The source has no row identity to diff against; nothing FKs into entries; entry ids are
never exposed as permalinks. Closed congresses short-circuit on the hash. A file link vanishing
from a fetched index page marks the check failed rather than deleting data (the same refusal
`poll_source` makes for vanished release-point labels).

## 3. Scraper (`ingest/classification.py`)

Model `ingest/inventory.py`: module-level compiled regexes (no BeautifulSoup), frozen slotted
dataclasses with `as_json`/`from_json`, `warnings.warn` per unparseable line, a
`ClassificationParseError(ValueError)` raised only when zero rows parse. Politeness per
`ingest/download.py`: `USER_AGENT` imported from `inventory.py`, 1 req/s throttle, urllib only,
`Opener` injection for tests, `.part`-then-rename, disk cache at `data/classification/{filename}`.
A first full run is ~33 requests, ~40 seconds.

Per `pl` file: parse header metadata (covered text → gap segments by iterating
`(\d+)-(\d+)(?:\s+through\s+\d+-(\d+))?`; prepared date, with the 104th's "last updated"
fallback) → locate the `<PRE>`, find the ruler line, take the line above it as the header →
derive the six column offsets from header tokens → per data line: harvest statviewer refs, strip
tags, slice by offsets, recover Description/Pub. L. overflow, peel the trailing quote off Sec.,
parse description tokens, derive `usc_identifier` only when non-appendix and `section_norm`
matches `^\d+[a-z]*(?:-\d*[a-z]*\d*)*$` (a single section number — no ranges, no spaces). Emit a
`ParsedClassificationFile` and a `ClassificationParseReport` (`rows_parsed, skipped_lines,
warnings, pl_span` checked against `covered_ranges`, `rows_without_pl, rows_without_identifier,
distinct_titles`) → written to `docs/verification/classification-{congress}-{session}.json` and
summarized into `data/manifests/classification.json`.

`parse_tables_index(html)` handles both entry pages: `tbl\d+pl(?:_1st|_2nd)?\.htm` hrefs plus
`ecct*.html` links; covered text is the nearest preceding "Public Law…" run (the 119-1st entry
spans `<br/>` lines — join and collapse whitespace).

CLI, in `ingest/__main__.py`'s dispatch dict:

- `python -m ingest classification [--congress N] [--session S] [--force] [--from-file DIR]
  [--no-load]` — backfill/load, hash-gated, resumable. `load_file` commits nothing; the CLI owns
  the transaction. `--from-file` is the offline path `make ci-data` uses.
- `python -m ingest classification-check` — one request to `tables.shtml`; compare covered text
  (and the ECCT link set) against the registry; write a `classification_source_checks` row either
  way. Exit codes match `check`: 0 nothing new / 10 changed / 1 failed. `deploy/update-corpus.sh`
  gains two lines: run the check; on exit 10, run `classification`. The weekly `--force` sweep
  rides the existing Actions backstop.

## 4. Storage and API

Third storage protocol, on the ADR-0017 pattern:

- `storage/classification.py` — `ClassificationRepository(Protocol)`; frozen refs
  `ClassificationFileInfo`, `ClassificationEntryRef`, `EcctEntryRef`, `ClassificationPage
  (items, total, limit, offset)`; error hierarchy `ClassificationError` /
  `UnknownPublicLawError`; and `CLASSIFICATION_SOURCE_URL =
  "https://uscode.house.gov/classification/tables.shtml"` (the cross-layer constant lives here;
  ingest imports it back, per the `SOURCE_URL` precedent in `storage/repository.py`).
- `storage/postgres_classification.py` — `PostgresClassification`, a sibling of
  `PostgresRepository`, not a subclass.
- `storage/session.py` gains `get_classification()`; `storage/__init__.py` re-exports in
  `__all__`; `tests/test_architecture.py` gains a fourth
  `..._protocol_and_the_postgres_implementation_agree` test.

`api/classification.py` — `APIRouter(prefix="/api/v1", tags=["classification"],
dependencies=[Depends(public_cache)])`. Cache is `REVALIDATE` everywhere: nothing here is
request-pinned, and old tables can be editorially corrected (the ECCT documents exactly that).
Two module-level limiters with docstrings justifying the numbers: `_limit_classification`
(reader-server traffic, start at capacity 120 / 10.0 per second) and
`_limit_classification_suggest` (browser-direct, sized for a person, start at 30 / 5.0). Routes:

1. `GET /classifications/tables` — the registry plus freshness from
   `last_classification_check()`.
2. `GET /classifications/tables/{congress}/{session}/entries` — the session-page route.
   `?sort=pl|code` (pl = `row_seq`; code = title via `title_sort_key`, then `section_norm`),
   `?pl=118-33`, `?pl_section=101` (prefix), `?title=42`, `?section=` (normalized, en-dash
   variant tried), `limit ≤ 500`, `offset`. Returns `{items, total, limit, offset}`.
3. `GET /classifications/pl/{congress}/{law_num}` — PL order; `?section=` prefix-matches
   `pl_section_raw`. 404 "no classification table covers Public Law {c}-{n}" when the law falls
   outside every file's `covered_ranges`; 200 with empty items for a covered law that classified
   nothing. The two answers mean different things.
4. `GET /classifications/code/{title_num}/{section}` — input normalized (lowercase, en-dash →
   hyphen; CLAUDE.md gotcha 17); `?congress=`, `?exact=false` for prefix matching; ordered
   `pl_congress DESC, pl_num DESC, row_seq` (newest law first — section-history order).
5. `GET /classifications/us/usc/{identifier:path}` — rows by `usc_identifier`, bounded
   `limit=200`. This is the future section-panel endpoint; it ships now.
6. `GET /classifications/suggest?q=` — the lookup's autocomplete. Typed suggestions:
   - PL shorthand (`118-33`, `118-33 101`, `pl 118-33`) → `{kind:'pl', label, congress, session,
     href}` targeting the session page filtered to that law (`?pl=`, plus `&pl_section=` when
     given). Filtering is the positioning mechanism — with paging in play it beats a scroll
     anchor, and the URL stays citable.
   - A US Code citation (parsed server-side by the existing citation machinery — never a second
     TypeScript parser; `citeparse.py` is the single source of truth) → two suggestions when it
     resolves: "§ … — notes, in the reader" → `appHref(identifier) + "#section-notes"`, and
     "Classification entries for § …" → the code-filtered view.
7. `GET /classifications/ecct` — the whole table; `?congress=`/`?session=` once more sessions
   exist.

Response models in `api/schemas.py` (`<Thing>Out` with `of()` classmethods, `Field(description,
examples)`); router included in `main.py` plus a `DESCRIPTION` paragraph naming the rate limits
(ADR-0057).

## 5. Frontend

Routes (Astro `base: "/app"`), all fetching through `lib/api.ts` (`getJson`, `ApiError` →
`ErrorPage`) — model `search.astro`, not `releases.astro`'s bare fetch:

- `src/pages/classification/index.astro` — `/app/classification`: the lookup box, the current
  session's summary and freshness, the congress/session index with covered ranges, the ECCT link.
- `src/pages/classification/[congress]/[session].astro` — the table. `session ∈ 1|2|all` (`all`
  = the 104th's whole-congress file). Sort control on the `search.astro` `sortbar` pattern
  (unrecognized `?sort=` falls back silently; offset drops on sort change; hrefs rebuilt through
  one helper so filters survive paging). Active `?pl=`/`?title=` filters shown as dismissable
  pills. Paged.
- `src/pages/classification/ecct.astro` — the ECCT as one small table.

Table markup: `usa-table usa-table--striped` with `<caption>` and `scope` attributes (the
`releases.astro` shape), wrapped in the `uslm-tablewrap` scroll-region pattern (`role="region"`,
`tabindex="0"`, labelled) so 320 px reflow passes `make shots`. Columns: US Code citation
(`resultCitation` from `lib/cite.ts`, linked via `appHref` when `usc_identifier` is present —
`encodePath` handles en-dashes), Description, Pub. L. (govinfo link), Section, Stat. (statviewer
link when volume and page are known).

Lookup island `ClassificationLookup.astro`: combobox/listbox ARIA, debounced fetch to
`/classifications/suggest`, keyboard navigable; without JS it degrades to a plain GET form whose
server-side handler applies the same PL-shorthand parse. Its open state joins the a11y `states[]`.

`lib/url.ts` gains `classificationHref(congress?, session?, {pl?, plSection?, title?, section?,
sort?, offset?})`, `classificationSuggestHref(q)`, `govinfoPlawHref(congress, num)`,
`statViewerHref(volume, page)` — `/app` spelled once, defaults omitted so one view has one URL.

Menus (each asserted by ordered-text lists in `tests/e2e/chrome.spec.ts` — update in the same
commit): SiteHeader More ▸ Reference gains "Classification tables" beside Release points;
SiteFooter's Browse group gains it (the `footnav-browse` count assertion moves 2 → 3);
`siteCommands()` in `lib/palette.ts` gains a row (asserted by `palette.test.ts` and
`palette.spec.ts`).

Ratchets owed by the new routes — each is a hard gate:

- Guide: a new chapter in `frontend/src/pages/guide/` with `covers.routes` naming the three
  routes and `covers.adrs` naming the new ADR(s); ```scenario blocks runnable against the CI
  fixture corpus — so `make ci-data` must load the classification fixtures via `--from-file`.
  Prose per CLAUDE.md documentation duty 7.
- `docs/js-budgets.json` — entries for all three routes (the build fails without them).
- `docs/a11y/routes.json` — three route entries plus a `states[]` entry for the open lookup.
- `docs/ia-map.md` — rows with inbound file:line references.
- `frontend/scripts/screenshots.mjs` `PAGES` — the session-table page (the wide-table reflow is
  what this gate catches).

## 6. Verification

- Parser: `pytest tests/test_classification_parser.py` — one test per hazard in §1, against
  committed fixture slices. Full-corpus scratch run: 118-2nd = 2,990 rows, 104th = 11,740, zero
  unexpected warnings.
- Migration: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`.
- Load: `python -m ingest classification` (live) → per-file
  `docs/verification/classification-*.json` with `rows_parsed == row_count` and `skipped_lines`
  small and explained; a re-run is a no-op.
- Poll: `classification-check` twice → exit 0; against an edited covered range → exit 10; check
  rows written on both paths.
- API: an en-dash input-variant test is mandatory; the 404-vs-empty-page distinction is tested;
  paging bounds; `make test` green (integration tests skip without a DB and fail-if-skipped under
  `USC_REQUIRE_INTEGRATION=1`).
- Frontend: `make test-web` (guide ratchet, js budgets, palette), `make test-e2e` (chrome lists,
  new scenarios, the lookup's keyboard path), `make test-a11y`, `make shots`.

## What Wave 1 measured

Where this section and an earlier one disagree, this one is the later measurement.

1. **The row counts in §6 are three too high, in both files, for two different reasons.** The parser
   emits **2,987** rows for `tbl118pl_2nd.htm` and **11,737** for `tbl104pl.htm`. In the 118th file
   the extra three are the `U. S. Code` banner, the column header and the ruler. In the 104th the
   `<pre>` is never closed, so the site chrome at the end of the document (`14v4`, `About the
   Office`, `Privacy Policy`) falls inside it. The 110th file is 2,122 rows. All three parse with
   zero skipped lines and zero warnings.
2. **`classification_entries` gains `stat_page_labels ARRAY(String)`.** Statutes at Large pages are
   not always numbers — 110 Stat. 1321-9 and 3009-587 are single pages — and **1,658 of the 104th's
   11,737 rows** cite one, which `stat_pages ARRAY(Integer)` cannot hold. The column also keeps a
   range distinguishable from its endpoints (`863-866` is one token there and two integers in
   `stat_pages`). Amended into migration `3c8d9ab6d527` rather than added by a second migration.
3. **`usc_identifier` is spelled with an EN DASH.** The tables write `254c-15`; the corpus writes
   `/us/usc/t42/s254c–15`, and all 5,697 of its hyphenated section identifiers use U+2013 while none
   uses U+002D (gotcha 17). Derived with the table's own hyphen, 697 of the 9,299 distinct
   identifiers the measured files produce join nothing; spelled with the en dash, 611 join. The 342
   corpus identifiers that do contain a hyphen are appendix date paths, which derive nothing anyway.
   `section_norm` keeps the plain hyphen — it is what typed input is matched against, so §4's
   routes still normalize their input to the hyphen and §5's links still go through `encodePath`.
4. **The ADR is 0067**, not the 0068 the C1 prompt names; `docs/adr/` topped out at 0066.
5. **`ecct_entries` has neither `ondelete="CASCADE"` nor `UniqueConstraint(file_id, row_seq)`**,
   because §2 specifies both for `classification_entries` and neither here. C2b's wholesale replace
   must therefore delete ECCT rows explicitly, and nothing in the database stops a re-load doubling
   them. Decide it in C2b rather than smoothing it here.
6. **Two things C2b will trip over.** `db.models.ClassificationEntry`/`EcctEntry` collide by name
   with `ingest.classification.ClassificationEntry`/`EcctEntry`, and a loader importing both must
   alias one side. `classification_files.skipped_lines` is an `Integer` while the parser produces a
   tuple of the lines themselves, so the count is stored and the lines survive only in the
   verification JSON.

## What Wave 2 measured

The first full-corpus run. Where this section and an earlier one disagree, this one is the later
measurement.

1. **The corpus is 144,837 rows across 31 `pl` files, plus 21 ECCT rows in two files.** The estimate
   in §1 was 100–150k. 131 warnings, 0 skipped lines, 2 rows without a public law, 1,533 rows
   without a `usc_identifier` (1,531 of them appendix rows, which derive none by rule), 6,053 whose
   Stat. page has no integer form, and 107 seconds to fetch and load all 33 documents from cold.
2. **Wave 1's three measured files were not representative, and the other 28 carried four defects.**
   The first parse of them warned 10,584 times, left 3,717 rows with no public law at all, and
   dropped 29 lines. Two files put their Sec. column one character left of their header; a Stat.
   page is not always a number (`113 Stat. 1501A-594`); a row OLRC has corrected carries an asterisk
   in front of its title number, which sometimes shifts every later column; and a Sec. cell butted
   against its Stat. page can be split where the row's own statviewer anchor says the page begins.
   All four are fixed, tested, and recorded in ADR-0067's addendum.
3. **What remains is 0.09% of the rows, in two classes.** 127 rows have a Sec. cell whose bracket
   runs straight into a letter-numbered page (`101(f) [405(d)(24), (25)]2681-423`) in a vintage with
   no statviewer anchors to key on, and 2 rows in `tbl112pl_2nd.htm` have a description long enough
   to push the law number past the Sec. column, where reading it would mean reading `112-239` as
   `112-23`. All 129 keep their `raw_line` and are warned about.
4. **`ecct_entries` got `ondelete="CASCADE"` and `UniqueConstraint(file_id, row_seq)`** — the choice
   §What Wave 1 measured left to this wave, in migration `0044883c483c`.
5. **The poll cannot see a change to the ECCT alone**, and a database that has loaded the fixture
   slices will skip the real tables until something forces it. Both are ADR-0067's consequences now;
   the second is why `make ci-data` writes its artifacts under `.ci-data`.

One ratchet is deferred rather than met: ADR-0067 is listed in `INFRASTRUCTURE_ADRS` in
`frontend/tests/guide.test.ts`, because Wave 1 ships no reader surface for a chapter to describe.
**C5 removes that line when it writes the chapter** — it is named in the C5 prompt.

## What Wave 3 measured

Where this section and an earlier one disagree, this one is the later measurement.

1. **§4's own 404 example is false against the loaded corpus.** `tbl119pl_1st.htm` covers
   `['1-69', '71-73']`, so Public Law 119-72 *is* covered and route 3 returns 200 with empty items.
   The 119th is covered through 102; **119-103 and up is the genuinely uncovered case**, and no law
   in the corpus actually falls in a gap — each congress's two files are complementary. The
   distinction is still real and still tested; the example was wrong.
2. **§4 asks for "a fourth `..._agree` test" and there were two** (`Repository`,
   `AccountsRepository`), so `ClassificationRepository`'s is the third.
3. **§4 names four refs and needs five.** `last_classification_check()` had no return type;
   `ClassificationCheckInfo` is a sibling of `SourceCheckInfo` and reuses `SOURCE_CHECK_STALE_AFTER`.
4. **A default `limit` with no `offset` truncates silently, and this wave shipped it twice.** Route
   5 (`/classifications/us/usc/{identifier:path}`) was fixed at 200 rows unpaged: **14 identifiers
   exceed it and `/us/usc/t10/s113` carries 412**, and because the order is newest-law-first the
   dropped rows were the oldest. The reader's by-section view then repeated it against route 4's
   default of 100 — `?title=42&section=1396a` reported 353 rows in its heading and rendered 100.
   Both now page. **9,163** rows carry an EN DASH in `usc_identifier` across 3,398 distinct ones;
   143,304 of the 144,837 rows derive an identifier at all, naming 40,967 distinct ones.
5. **§4's suggest route names a "code-filtered view" that §5 never defines.** It is
   `/app/classification?title=…&section=…` — the index page, which is where the lookup box already
   is; a code-filtered view spans every congress and session, so it has no home on a per-session
   page.
6. **A reader href may never be composed from a title and a section number.** `ecct.astro` built
   `/us/usc/t{title}/s{section_norm}` by concatenation and **7 of its 30 links 404'd** — every one a
   *Former classification* cell, the column whose meaning is that the provision moved away. The rule
   is the loader's: link where `usc_identifier` is present, render text where it is not.
7. **`/app/docs` overflows because of unbreakable `<code>` endpoint paths, not its parameter
   tables.** C3's seven routes pushed 320 px overflow from a recorded 3 px to 146 px and started a
   91 px overflow at 375 px, where there had been none. The widest span is
   `/api/v1/classifications/tables/119/2/entries` — 422 px, right edge 466, which is exactly
   `466−320` and `466−375`. `.table-scroll` and `.uslm-tablewrap` are already the same two
   declarations and the parameter table already scrolls inside its wrapper. `overflow-wrap: anywhere`
   on `.apidocs__intro code, .endpoint__prose code` takes both widths to **0**, so both `reflow`
   entries were deleted rather than a third added — and `main`'s recorded 3 px was already stale, the
   page having overflowed 50 px at 320 with no classification route present.
8. **The reflow ratchet has no magnitude bound.** `screenshots.mjs` matches a known violation on
   `(page, view)` alone, so 3 px growing to 146 px would have passed unrecorded. Remeasuring is
   voluntary. Unlike ADR-0039's `waiveSeverity`, which weakened the gate's rule, widening this
   ledger is the documented process — but the ledger cannot tell a fixed page from a worsening one.

## What Wave 4 measured

Where this section and an earlier one disagree, this one is the later measurement.

1. **`/app/design` can render the lookup in full, and the no-data property still holds.** The
   island fetches on input and nothing on that page types into it, so `design.spec.ts`'s request
   recorder sees no `/api/` call with the specimen on the page. The cost is bytes rather than
   requests: the island is **4,383** of them, and `/app/design`'s inline-script ceiling goes
   **34,000 → 39,000** against a measured 38,383. It is the page that renders every island, so it
   pays for each one twice — once as a component and once as the chrome around it.
2. **§4's 404-vs-empty distinction has three renderings, and the middle one is the common case.**
   **40 of the 119th Congress's first 102 public laws** are covered by a table and classified
   nothing, so "covered, no rows" is not an edge case to be described in passing. The three are: a
   covered law with no rows (the session table says it classified nothing matching the filter), a
   law past every covered range (the lookup finds nothing; the API 404s naming the law), and a
   congress and session with no published table (a reader 404). Guide chapter 10 states all three.
3. **The guide chapter costs 7 accessibility scans and no violations.** The matrix is **322**
   rather than 315, because `docs/a11y/routes.json`'s `guide-chapters` entry expands from disk, and
   the totals are unchanged: 8 route/rule pairs over 2,623 nodes, every one of them
   `docs/a11y/known-violations.json`'s.
4. **The chrome's cost is one row and 57px, none of it in the sticky stack.** The sheet gains a
   53.44px row at every width below 64em and the header is still 104px with a 225.13px stack
   (`make mobilebar`), because the panel is absolutely positioned. The footer's link block goes
   **675 → 732px at 320 and 375** and is unchanged from 420 up, where it has columns to spend the
   row on (`make footnav`).
5. **The deployed box now holds the rows and cannot yet serve them.** Its image already carried the
   loader — it runs `66354dd` with migration `0044883c483c` at head — so the backfill ran there
   directly: **33 documents, 33 loaded, 0 failed, 144,858 rows in 110.0 s**, which is 144,837
   entries and 21 ECCT rows, the development corpus's totals. The API and reader routes are not
   deployed at all, since C3, C4 and C5 are unmerged, so `/app/classification` and
   `/api/v1/classifications/tables` answer 404 there until they are.
   `classification_source_checks` is empty: the loader writes no check row, and the daily cron
   writes the first one within a day of the deploy.
6. **`footnav.mjs` cited the wrong ADR in three places** — ADR-0062 for the footer grouping, which
   is ADR-0063. The committed artifact had been corrected by hand, so every regeneration undid it.

## Waves — parallel agent dispatch

The house rhythm applies: implement in a worktree → tests pass → fresh-context reviewer reads the
diff → merge; merge order schema → ingest → API → web. The phases have a dependency spine
(parser → loader → API → pages) with two places for parallel Opus agents. Each agent's prompt
names its verification commands and the files its wave partner owns (which it must not touch).

- **Wave 1 — two agents in parallel, disjoint files.** Agent A runs prompt C1 (parser +
  fixtures; touches `ingest/classification.py`, `tests/fixtures/`, its test file, the ADR).
  Agent B runs prompt C2a (schema + migration; touches `db/models.py`, `alembic/versions/`,
  model tests). Merge A then B.
- **Wave 2 — one agent.** Prompt C2b (loader + CLI + poll) — the join point; needs A and B
  merged.
- **Wave 3 — two agents in parallel, decoupled by this spec's API contract.** Agent C runs
  prompt C3 (storage protocol + API) and merges first. Agent D runs prompt C4 (reader pages +
  lookup) in a worktree against the response shapes fixed in §4–§5, integration-verifies against
  the real API after C merges, then merges. On drift, this spec is the arbiter: whichever side
  deviated fixes itself.
- **Wave 4 — one agent, then review.** Prompt C5 (menus, guide, poll wiring, deploy) — sequential
  because it edits shared chrome files and asserts on everything earlier waves produced.

After every wave: a fresh-context reviewer agent reads the merged diff; the wave is done when
`make test` and `make test-web` are green (plus `make test-e2e` from Wave 3 on) and the BUILDLOG
entry is written.

## Phase prompts

Each prompt is self-contained for an Opus session or subagent. All of them start the same way:
*Read `CLAUDE.md`, then `docs/classification-spec.md` (this file) in full. Work in a worktree on a
branch named for the phase. Small commits, imperative messages, `Co-Authored-By` trailer.*

### C1 — Parser and fixtures (Wave 1, agent A)

> Implement the classification-table parser: `ingest/classification.py`, parse side only — no
> database code, no network in tests. Follow `ingest/inventory.py`'s shape exactly: module-level
> compiled regexes, frozen slotted dataclasses with `as_json`/`from_json`, `warnings.warn` per
> unparseable line, `ClassificationParseError` only when zero rows parse. Implement
> `parse_tables_index`, `parse_classification_file`, `parse_ecct`, and the
> `ClassificationParseReport` per spec §3. Download the source files fresh (politely — 1 req/s,
> the project User-Agent): tables.shtml, priortables.shtml, tbl118pl_2nd.htm, tbl110pl_1st.htm,
> tbl104pl.htm, ecct.html. Commit fixture slices to `tests/fixtures/` (the
> `priorreleasepoints_slice.htm` precedent): `tbl118pl_2nd_slice.htm` (~80 rows including the
> `tr to 42/290ee-10118-84` overflow, a `1544, 1545` stat cell, `nt [tbl]`, `gen amd`,
> `202 "1948"`, statviewer links), `tbl110pl_1st_slice.htm` (`openPLaw` anchors,
> `Ethics Act nt new110-24`, `5A` appendix rows), `tbl104pl_slice.htm` (wider columns,
> `Stat. Page` header, lowercase `<pre>`, whole-congress range), entry-page slices with the gap
> and `<br/>` covered-range forms, and `ecct.html` verbatim. Write
> `tests/test_classification_parser.py` with one test per hazard in spec §1 plus the
> identifier-derivation rules (appendix → null, range → null, note/prec → parent section's
> identifier). Also write `docs/adr/0068-classification-tables.md` (0067 is taken — check
> `docs/adr/` for the next free number before writing) recording: scrape `pl` files
> only; header-line column offsets; wholesale replace per file; a separate
> `classification_source_checks` table; covered-text change detection; Postgres only, no
> OpenSearch; the identifier-derivation rules. Do not touch `db/`, `storage/`, `api/`, or
> `alembic/` — Wave 1's other agent owns `db/models.py`. Verify: the new pytest file green; a
> scratch run over the full downloaded files reports 118-2nd = 2,990 rows and 104th = 11,740 with
> zero unexpected warnings.

### C2a — Schema and migration (Wave 1, agent B)

> Add the four classification tables to `db/models.py` per spec §2: `classification_files`,
> `classification_entries`, `ecct_entries`, `classification_source_checks` — exact columns,
> constraints, and indexes as specified, with the house index-comment and docstring conventions
> (read `SourceCheck` and `SectionReleaseMap` first). Generate one Alembic migration
> (autogenerate naming, real `downgrade()` dropping indexes then tables). Extend
> `tests/test_models.py`-style coverage for the new tables. Do not touch `ingest/` — Wave 1's
> other agent owns `ingest/classification.py`. Verify: `alembic upgrade head && alembic
> downgrade -1 && alembic upgrade head` clean; `make test` green.

### C2b — Loader, CLI, and poll (Wave 2)

> With C1 and C2a merged, implement the load and poll sides of `ingest/classification.py`:
> `load_file` (wholesale replace per file in one transaction — delete entries, re-insert, update
> the registry row in place; commits nothing, the CLI owns the transaction),
> `poll_classification` + `record_classification_check` (spec §3; a file link missing from a
> fetched index page fails the check rather than deleting data), the fetch layer (disk cache at
> `data/classification/`, `.part`-then-rename, throttle and User-Agent from the existing
> modules), and the `classification` / `classification-check` subcommands in
> `ingest/__main__.py` with exit codes 0/10/1. Write the per-file verification JSON to
> `docs/verification/` and the manifest to `data/manifests/classification.json`. Extend
> `make ci-data` to load the fixture slices via `--from-file`. Run the full live backfill once
> and commit the verification artifacts. Verify: re-run is a no-op; `classification-check` exits
> 0, then 10 against an edited covered range; check rows written on success and failure paths;
> `make test` green including the new integration tests.

### C3 — Storage protocol and API (Wave 3, agent C)

> Implement spec §4: `storage/classification.py` (protocol, refs, errors,
> `CLASSIFICATION_SOURCE_URL`), `storage/postgres_classification.py`, `get_classification()` in
> `storage/session.py`, `storage/__init__.py` exports, the fourth `..._agree` test in
> `tests/test_architecture.py`, `api/classification.py` with the seven routes, schemas in
> `api/schemas.py`, inclusion + `DESCRIPTION` paragraph in `main.py`. Rate limiters and cache
> policy per spec §4. The suggest route's citation half goes through the existing citation
> machinery server-side. Write `tests/test_classification_api.py`: the en-dash input variant, the
> 404-vs-empty-page distinction, paging bounds, suggest's PL-shorthand and citation paths.
> Verify: `make test` green; manual spot checks of routes 2–6 against the loaded dev corpus.

### C4 — Reader pages and lookup (Wave 3, agent D — worktree until C3 merges)

> Implement spec §5: the three Astro routes, `ClassificationLookup.astro`, the `lib/url.ts`
> helpers, table markup in the `uslm-tablewrap` scroll-region pattern, the `sortbar` sort
> control, filter pills, paging. Data access only through `lib/api.ts` (model `search.astro`;
> `releases.astro`'s bare fetch is the recorded outlier). Build against the response shapes in
> spec §4; integration-verify once C3 is merged. Add `docs/js-budgets.json` entries for the three
> routes, `docs/a11y/routes.json` entries plus the open-lookup state, and the session-table page
> to `frontend/scripts/screenshots.mjs`. Do not touch SiteHeader/SiteFooter/palette — C5 owns the
> chrome. Verify: `make test-web`, `make test-e2e`, `make test-a11y`, `make shots` all green.

### C5 — Menus, guide, poll wiring, deploy (Wave 4)

> Finish the workstream: remove ADR-0067 from `INFRASTRUCTURE_ADRS` in
> `frontend/tests/guide.test.ts` — the chapter you write below is what replaces it. Add
> "Classification tables" to SiteHeader's More ▸ Reference group,
> SiteFooter's Browse group, and `siteCommands()` in `lib/palette.ts`, updating the ordered-text
> assertions in `tests/e2e/chrome.spec.ts` and the palette tests in the same commits. Write the
> guide chapter (`covers.routes` = the three routes, `covers.adrs` = the classification ADR's
> number; scenario blocks
> answerable from the CI fixture corpus; prose per documentation duty 7). Update
> `docs/ia-map.md`. Add `/app/design` specimens for any new component C4 introduced. Wire
> `classification-check` into `deploy/update-corpus.sh` (run check; on exit 10 run
> `classification`). Run the backfill on the deployed box. Write the BUILDLOG entry and update
> this spec's status line. Verify: all three test suites green locally and in CI; the deployed
> `/app/classification` serves the full corpus.

## Reference files for implementers

`ingest/inventory.py`, `ingest/download.py`, `ingest/__main__.py`, `db/models.py`,
`storage/repository.py`, `storage/accounts.py`, `storage/session.py`, `params.py`,
`api/routes.py` (the labels route), `frontend/src/pages/search.astro`,
`frontend/src/lib/url.ts`, `frontend/src/lib/cite.ts`, `frontend/src/lib/palette.ts`,
`frontend/src/components/SiteHeader.astro`, `frontend/tests/guide.test.ts`,
`tests/test_architecture.py`, `docs/adr/0017-*.md`, `docs/adr/0036-*.md`.
