# ADR-0094 — Detect the source format before parsing

**Status:** accepted (2026-10-23)

**Amends:** ADR-0091 (a poll only appends), ADR-0093 (the empty table viewer).
**Related:** ADR-0036 (the daily poll), ADR-0067 (the classification tables), ADR-0087 (the
current release point's page).

## Context

`/api/v1/status` on 2026-10-23 reported the last check, at 2026-10-22 06:41 UTC, as failed:
`InventoryParseError: no release points found — the markup at
https://uscode.house.gov/priorreleasepoints.html has probably changed`. The deployed corpus stood
at 119-121; the source's notice said it was current through 119-124.

The pages, read from a GitHub Actions runner on 2026-10-23 (`tests/fixtures/priorreleasepoints_li_label.html`,
`download_undated.html`, `tbl118pl_2nd_records_slice.html`):

| Page | Served | Read as |
|---|---|---|
| `priorreleasepoints.html` | a `<li>` per release point again, newest first, 119-73not60 to 119-121; hrefs `download/119-121.html`; dates spelled out | neither markup the parser knew: the `<li>`s did not match the 2013–2026 href pattern and there was no section heading |
| `download.html` | 119-124 under the heading `Public Law 119-124`, with no date; the date only in the description; changed rows without the `id` that named their title | the heading's date was required |
| `tbl117pl_2nd.html`, `tbl118pl_1st.html`, `tbl118pl_2nd.html` | the empty viewer of 2026-10-13, now with every row in its script as `var ctRecords = [{…}]`: 5,988, 1,491 and 2,987 objects, the row counts of the `<pre>` tables loaded on 2026-08-11 | `ClassificationTableUnavailable`, so the rows were never read |
| the zips of all 22 listed release points and 119-124 | HTTP 200 | — |

The prior page lists 119-117 (titles 16 and 54) between 119-111 and 119-118. The page of
2026-10-12 listed only 119-118, so the deployed corpus has no 119-117, and ADR-0091's merge
refuses a new release point listed before one this site holds.

Each parser had grown its own fallbacks for the markups it had met, inside one function, so what
the source had served and when was recoverable only from the ADRs.

## Decision

1. **A registry of source formats.** `ingest/source_formats.py` holds one `SourceFormat` per markup
   OLRC has served for each page kind the polls and loaders read: the prior page, the download
   page, the classification index, a classification table and the ECCT. Each has an id, the
   addresses it was served at, the first and last day a capture is on record, the committed
   capture, the ADR, and a structural signature. A retired format stays in the registry.
   `docs/source-formats.md` is the same history as prose, with the markup of each.
2. **Detect, then parse.** Every parse of one of those pages first matches it against the
   registered formats of its kind. Exactly one must match; the match picks the parser. No match is
   checked for the maintenance notice and is otherwise an `InventoryParseError` or a
   `ClassificationParseError` naming every format tried. `tests/test_source_formats.py` matches
   each capture against its own format and no other, parses each, and fails when the registry and
   `docs/source-formats.md` disagree.
3. **The check rows record the formats.** `source_checks.source_formats` and
   `classification_source_checks.source_formats` (migration `c4d9e2f7a1b3`) hold the id of each
   page the check read; `python -m ingest check` and `classification-check` print them. A table
   file's verification artifact carries its `source_format`.
4. **Three new formats.** `prior-release-points/li-label-html` reads the label from the href's
   basename and the date in either form. `current-release-point/undated-heading` reads the date
   from "current through Public Law {label} (…)" and a changed row's title from the XML zip link
   in its own `uscitem`. `classification-table/viewer-records` decodes the array as JSON and puts
   each object through the field rules a `<pre>` row's cells go through; the row's `raw_line` is
   the object as JSON. The 84 rows of `tbl118pl_2nd_slice.htm` and of the records slice agree on
   every parsed field.
5. **A new release point goes where the source lists it.** `merge_inventory` inserts a release
   point this site does not hold immediately before the next one on the source that it does, or at
   the end, provided its date lies between its new neighbours'; every later `seq` moves up, which
   `seed_release_points` already does for the whole table. Its changed titles are used when the
   release point the source lists before it is the one before it here, and every title otherwise.
   The order of held release points is still never changed.

## Consequences

- The first poll after deploy reads both pages, inserts 119-117 between 119-111 and 119-118 and
  appends 119-124, and plans titles 16 and 54 at 119-117 and 16 and 29 at 119-124.
- 119-118 and 119-121 keep the every-title `titles_affected` they were loaded with; the source now
  marks 42 and 15. A held entry is not rewritten.
- The next forced classification sweep reads the three records tables, whose content hashes
  differ from the `<pre>` ones, and replaces their rows wholesale. Each row's `raw_line` becomes
  its JSON object; the parsed columns are what the `<pre>` gave. Their `source_url` becomes the
  `.html` address.
- `tableupdate` is `"true"` on 64 of the 2,987 objects of 118-2. Whether that is the asterisk the
  `<pre>` tables print on a corrected row is not checked; it is kept in `raw_line` and read into
  nothing.
- The `ct{congress}-{law}{xml,json,txt}.zip` downloads the viewers link answered HTTP 404 on
  2026-10-23 and are not read.
- The registry records what a capture showed on a day. The deployed corpus holds 119-121
  (October 9), so the 2026-10-12 markups were still served, and read, after their last capture;
  the markups of 2026-10-23 began on a day between then and 2026-10-22 that is not on record.
- A signature that is too loose turns a changed page into a wrong parse rather than a failure.
  Each signature is checked against every other capture of its page kind; nothing checks it
  against a markup nobody has captured.
