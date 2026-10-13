# ADR-0093 — The classification tables at their relaunched addresses

**Status:** accepted (2026-10-13)

**Amends:** ADR-0067 (the classification tables), ADR-0091 (its last consequence).
**Related:** ADR-0036 (the daily poll), ADR-0074 (attribution reads these rows).

## Context

ADR-0091 moved the release-point poll to the relaunched uscode.house.gov and left the
classification poll reading `classification/tables.shtml`, which now answers HTTP 200 with a
"Page Not Found" page. `update-corpus.sh` runs that poll on every run, so the run of 2026-10-13
that loaded 119-118 and 119-120 ended red on it, and so would every daily run.

What the relaunched classification pages serve, read from a GitHub Actions runner on 2026-10-13
(`tests/fixtures/*relaunch*` are those pages, whole or sliced):

| Address | Answer |
|---|---|
| `classification/tables.html` | the 119th Congress's two tables, `tbl119pl_2nd.html` and `tbl119pl_1st.html`, and `ECCT.html` and `ECCT_119-1.html`; the covered-law sentence in the same cell as before, with a `<br />` inside it |
| `classification/priortables.html` | the 104th to 118th, 29 tables, every link `.html` |
| `tbl119pl_2nd.html`, `tbl119pl_1st.html`, `tbl110pl_1st.html`, `tbl104pl.html` | the same `<pre>` table; each Stat. page links `/images/stat/{volume}/{page}.png` where it linked `statviewer.htm?volume=…&page=…` |
| `tbl117pl_2nd.html`, `tbl118pl_1st.html`, `tbl118pl_2nd.html` | a table viewer whose `<tbody id="classificationTableBody">` is empty, no `<pre>`, and an empty script |
| `statviewer.htm` | "Page Not Found" |
| `images/stat/{v}/{p}.png` | a page image for volumes 139 and 140; "Page Not Found" for 109, 121, 130, 136, 137 and 138 |
| govinfo `link/statute/{v}/{p}` | a PDF for 121/5 and 138/290; HTTP 400 for 139/1677 and 140/1057 |
| `download/download.shtml` | "Page Not Found"; `download.html` is the download page |

## Decision

1. The poll reads `tables.html` and the backfill `priortables.html` as well. Table links ending
   `.html` are read; `.htm` still is, and PDFs are still dropped. A `<br>` in the covered-law
   sentence is a space.
2. A row's (volume, page) comes from either link form. The relaunched tables link every Stat.
   page, so a quoted new section butted against its page (`7201(c)(1) "Subchapter I"1677`), which
   the column split could not separate, is split at the linked page number: `tbl119pl_1st.html`
   parses its 3,049 rows with 0 warnings where it gave 5.
3. A table page with the empty viewer and no `<pre>` raises `ClassificationTableUnavailable`.
   The load reports the file as skipped, "the source page carries no rows", keeps the rows it
   stored, and stays sound. Any other page without a `<pre>` is still a failure.
4. The reader links a Stat. page to OLRC's page image from volume 139 and to govinfo's link
   service before it (`statuteHref`, `OLRC_STAT_IMAGES_FROM`). The header, footer and About page
   link `download.html`.

## Consequences

- The first poll after deploy reports both 119th Congress tables as changed, since their
  covered-law sentences now run to 119-118. The next corpus run loads them and re-attributes.
- A prior table whose covered-law sentence is unchanged is skipped without a request, as
  before. The weekly `--force` sweep requests all of them; the empty viewers are skipped there
  and keep their rows and their `.htm` `source_url`, which no longer answers.
- A table whose `<pre>` is unchanged but whose links changed has a new `content_hash` and is
  rewritten; its rows gain the row-level volume the links carry.
- The CI fixture corpus still loads the pre-relaunch slices, copied to the new index names in
  `make ci-classification-data`, so every count the API and reader tests assert is unchanged.
- The image threshold is a measurement of one day. Volumes OLRC adds images for, or govinfo
  publishes, move the answer, and `OLRC_STAT_IMAGES_FROM` is the one number to change.
- The reader's own cross references to the Statutes at Large (`lib/refs.ts`) still go to govinfo
  for every volume, so a reference to volume 139 or 140 in the statutory text answers 400 there.
