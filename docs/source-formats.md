# Source formats

Every markup uscode.house.gov has served for the pages the polls and loaders read, oldest first
within each page. The registry is `ingest/source_formats.py`; this file is the same history as
prose, and `tests/test_source_formats.py` fails when a format is in one and not the other. Each
format has a committed capture under `tests/fixtures/` that its signature is tested against.

Before a page is parsed it is matched against the formats registered for that page; the match
decides the parser, and the check row records it (`source_checks.source_formats`,
`classification_source_checks.source_formats`). A page that matches none is a failed check whose
error names the formats tried. Dates are the first and last day a capture is on record, which can
be narrower than the days OLRC served the markup.

## Adding a format

1. Capture the page (the session's network does not reach uscode.house.gov; a GitHub Actions
   runner does) and commit it, or a verbatim slice of it, under `tests/fixtures/` with a comment
   naming the URL and the date.
2. Add a `SourceFormat` to `REGISTRY` with a signature that matches the capture and none of the
   other captures of that page. Set `last_seen` on the format it replaces.
3. Add or reuse a parser, keyed by the new id.
4. Add a row below.

## Prior release points

| Format | Served at | Seen | Capture |
|---|---|---|---|
| `prior-release-points/li-usc-rp-htm` | `download/priorreleasepoints.htm` | to 2026-10-11 | `priorreleasepoints_slice.htm` |
| `prior-release-points/rp-sections` | `priorreleasepoints.html` | 2026-10-12 | `priorreleasepoints_relaunch_slice.html` |
| `prior-release-points/li-label-html` | `priorreleasepoints.html` | from 2026-10-23 | `priorreleasepoints_li_label.html` |

**`li-usc-rp-htm`** (ADR-0087). One `<li class="releasepoint">` per release point, newest first,
back to 113-21 in 2013:

```html
<li class="releasepoint"><a class="releasepoint" href="releasepoints/us/pl/119/99/usc-rp@119-99.htm">Public Law 119-99 (06/12/2026), affecting title 16.</a></li>
```

The label is in the href; the date (`MM/DD/YYYY`) and the changed titles are in the link text. The
current release point is a commented-out `<li>` at the top, uncommented once it is superseded.

**`rp-sections`** (ADR-0091). After the relaunch, one section per release point, laid out like
the download page: a heading, then one row of four zip links per title.

```html
<h3 class="releasepointinformation">Public Law 119-118 (09/30/2026)</h3>
… <a href="download/releasepoints/us/pl/119/118/xml_usc01@119-118.zip">[XML]</a> …
```

The label is in the zip links and the date in the heading. Changed titles are not marked. On
2026-10-12 the page listed one release point.

**`li-label-html`** (ADR-0094). A list again, newest first, from 119-73not60 (January 23, 2026):

```html
<li class="releasepoint"><a class="releasepoint" href="download/119-121.html">Public Law 119-121 (October 9, 2026), affecting title 15.</a></li>
<li class="releasepoint"><a class="releasepoint" href="download/119-102not101.html">Public Law 119-102not101 (July 12, 2026), except 119-101, affecting titles 5, 16.</a></li>
```

| | `li-usc-rp-htm` | `li-label-html` |
|---|---|---|
| href | `releasepoints/us/pl/{congress}/{rest}/usc-rp@{label}.htm` | `download/{label}.html` |
| date | `06/12/2026` | `June 12, 2026` |
| label in text | the law alone (`Public Law 119-102 (…), except 119-101`) | the whole label (`Public Law 119-102not101 (…), except 119-101`) |
| history | back to 2013 | back to January 2026 |
| current release point | commented out at the top | absent; it is on the download page |
| zip address | `download/releasepoints/us/pl/119/99/xml_usc16@119-99.zip` | unchanged |

The page of 2026-10-23 lists 119-117, which the page of 2026-10-12 did not, between 119-111 and
119-118. A poll places it there (`merge_inventory`) and plans the two titles it changed. The zips
of every release point the page lists answered HTTP 200 on 2026-10-23.

## Current release point

| Format | Served at | Seen | Capture |
|---|---|---|---|
| `current-release-point/dated-releasepoints-href` | `download/download.shtml` | 2026-09-18 to 2026-10-11 | `download_current_slice.htm` |
| `current-release-point/dated-download-href` | `download.html` | 2026-10-12 | `download_relaunch_slice.html` |
| `current-release-point/undated-heading` | `download.html` | from 2026-10-23 | `download_undated.html` |

**`dated-releasepoints-href`** (ADR-0087) and **`dated-download-href`** (ADR-0091) differ in the
zip links' prefix (`releasepoints/…` relative to `download/`, then `download/releasepoints/…` from
the site root). Both carry the date in the heading and the title of a changed row in its `id`:

```html
<h3 class="releasepointinformation">Public Law 119-120 (10/07/2026)</h3>
<div class="usctitlechanged" id="us/usc/t31">…</div>
```

**`undated-heading`** (ADR-0094). The heading names the law alone, the date is spelled out in the
description, and a changed row carries no `id`:

```html
<h3 class="releasepointinformation">Public Law 119-124</h3>
… All files are current through Public Law 119-124 (October 15, 2026). …
<div class="usctitlechanged">16 - Conservation</div>
```

The date is read from "current through Public Law {label} (…)" and a changed row's title from the
XML zip link in the same `uscitem`.

## Classification index

| Format | Served at | Seen | Capture |
|---|---|---|---|
| `classification-index/htm-links` | `classification/tables.shtml`, `priortables.shtml` | to 2026-10-11 | `tables_slice.shtml` |
| `classification-index/html-links` | `classification/tables.html`, `priortables.html` | from 2026-10-13 | `tables_relaunch.html` |

One cell per congress-session; the relaunch changed the table links from `.htm` to `.html` and put
a `<br />` inside the covered-law sentence (ADR-0093). One parser reads both.

## Classification tables

| Format | Served for | Seen | Capture |
|---|---|---|---|
| `classification-table/pre-text` | every table to 2026-10-11; every table but the three below since | from 2026-08-11 | `tbl118pl_2nd_slice.htm` |
| `classification-table/viewer-empty` | 117th 2nd session, 118th 1st and 2nd | 2026-10-13 | `tbl118pl_2nd_relaunch.html` |
| `classification-table/viewer-records` | 117th 2nd session, 118th 1st and 2nd | from 2026-10-23 | `tbl118pl_2nd_records_slice.html` |

**`pre-text`** (ADR-0067). Fixed-width text in `<pre>`, six columns whose offsets come from the
header line. Its Stat. page links have changed three times without the table changing:

| Stat. link | Seen |
|---|---|
| `statviewer.htm?volume=138&page=3` | to 2026-10-11 |
| `/images/stat/139/1677.png` | 2026-10-13 |
| `statviewer.html?volume=140&page=3` | from 2026-10-22 |

The 104th and 110th carry none.

**`viewer-empty`** (ADR-0093). A table viewer whose `<tbody id="classificationTableBody">` is empty,
with no `<pre>` and no rows. The loader skips the file and keeps the rows it stored.

**`viewer-records`** (ADR-0094). The same viewer, with the rows in its script, behind a `<!--`:

```js
var statVolume = "138";
var ctRecords = [
    {
        "usctitle": "18",
        "uscsection": "3551",
        "uscdescription": "nt",
        "publiclaw": "118-35",
        "publiclawsection": "101(3)",
        "statutesatlargepage": "3",
        "dateofenactment": "01/19/2024",
        "statutesatlargevolume": "138",
        "usckey": "1800000000355100000000000000000000AS",
        "tableupdate": "false",
        "status": "Online",
        "recordOrder": "0",
        "recordlevelcomment": ""
    },
```

The page fills the table body from the array and links `ct118-273{xml,json,txt}.zip`, which
answered HTTP 404 on 2026-10-23. The three tables hold 5,988 (117-2), 1,491 (118-1) and 2,987
(118-2) objects, the row counts of the `<pre>` tables loaded on 2026-08-11. A row keeps its object as JSON in `raw_line`; every other field
goes through the rules a `<pre>` row's cells do, and the 84 rows of the two captures agree field
for field.

## Editorial Classification Change Table

| Format | Served at | Seen | Capture |
|---|---|---|---|
| `classification-ecct/four-column-table` | `classification/ecct.html`, `ECCT.html` | from 2026-08-11 | `ecct.html` |

A four-column `<table>` headed Former Classification, New Classification, Provision Affected and
Provision Prompting Change, with a `<div id="boxheads">` opened inside it. The relaunch changed
the site chrome around it and nothing in it.
