# ADR-0067 — The classification tables are scraped, stored in Postgres, and replaced wholesale

**Status:** accepted (2026-08-11)

**Task:** the classification-tables workstream, phase C1 (parser and fixtures). The schema, loader,
API and reader pages that follow are C2a–C5 of `docs/classification-spec.md`; the decisions here bind
all of them.

**Related:** [ADR-0003](0003-identifier-vs-guid-vs-temporalid.md) (what an `@identifier` is),
[ADR-0013](0013-s3-mirror-of-record-disposable-downloader.md) (never fetch from
uscode.house.gov in a test), [ADR-0036](0036-poll-daily-record-every-check.md) (the source-check
pattern this copies and deliberately does not share),
[ADR-0065](0065-a-dead-end-says-where-else-to-go.md) (what an appendix identifier really looks like)

## Context

OLRC publishes a Classification Table for each session of each congress: which provision of each new
Public Law was classified to which section of the Code, and how — amended, added, repealed,
transferred, or made a note. `118-35 §101(3) → 18 U.S.C. 3551 note` is one row. The site holds
nothing of this today, and it is the answer to "what did this law actually do to the Code", which the
release-point corpus can only show as before-and-after text.

The source is 31 files of fixed-width text inside `<PRE>`, from 1996 to now, plus a small Editorial
Classification Change Table recording where OLRC moved *earlier* laws while classifying new ones.
Measured on 2026-08-11: the 118th's second session is 2,987 rows, the 104th's whole-congress file
11,737, and the corpus is on the order of 100–150k rows.

Six decisions were forced by what the files turned out to be.

## Decisions

### 1. Scrape the `pl` files only

Every session is published twice — `tbl118pl_2nd.htm` in Public Law order and `tbl118cd_2nd.htm` in
Code order — and the two carry the same rows. Code order is a sort, and this project already has
`title_sort_key` (gotcha 16) to produce it. Scraping both would double the corpus to hold the same
facts twice and give the loader two rows that must be kept in agreement with no key that says they
are the same row. The PDF variants some vintages link are the same file again; HTML exists for all
31.

### 2. Column offsets come from the header line, and a missing token is a parse error

The ruler under the header merges Title and Section into one dash group, so it can supply five
offsets where six are needed. The header supplies six, and they move between vintages: the 110th and
118th files measure `0/6/19/36/45/67`, the 104th `0/6/20/42/51/68`. They are derived per file from
the positions of `Title`, `Section`, `Description`, `Pub. L.`, `Sec.` and the Stat. token. Three of
the 31 `pl` files have been through this parser; the other 28 are unmeasured, and the rule below is
what makes an unmeasured vintage a failed backfill rather than a corrupted one.

A header token this parser cannot find raises `ClassificationParseError` rather than falling back to
a guess. Guessed offsets do not fail — they slice plausible garbage out of every row of the file and
store it. A bad *row* is different: it is warned about and kept, with the fields that would not parse
left null, because a dropped row is invisible and a null one is a question somebody can answer later.

### 3. Wholesale replace per file, in one transaction

The source has no row identity of any kind — no ids, no keys, and rows that shift position when
OLRC republishes the current session's file with new laws in it. There is nothing to diff against,
so a changed file deletes its entries and re-inserts all of them, updating the registry row in place,
committing once. Nothing has a foreign key into `classification_entries` and no entry id is ever
exposed as a permalink, so nothing outside the transaction can notice.

### 4. A separate `classification_source_checks` table

`PostgresRepository.last_source_check()` takes the newest `source_checks` row regardless of
`source_url` and feeds `/api/v1/status`, which is the site's answer to "how current is this mirror".
Writing classification polls into the same table would make that answer flap between two sources that
change on different schedules — the corpus-freshness claim would silently start meaning "we checked
*something* recently". A sibling table with the same shape and the same discipline (a row written on
success *and* on failure, per ADR-0036) keeps both answers true.

### 5. Change detection is the covered-PL-range text, not a hash of the response

These pages carry no usable `Last-Modified` or `ETag` and embed a per-request `jsessionid` in every
internal link, so two downloads of an unchanged page are never byte-identical and a body hash detects
nothing. What does change when OLRC classifies a new law is the sentence on `tables.shtml` naming the
laws the current file covers — "Public Law 119-70 and Public Laws 119-74 through 119-102". That
string is stored verbatim as `covered_laws_text` and compared on every poll. The `content_hash` this
project also stores is sha256 of the extracted `<PRE>` text, which is stable across downloads and is
what gates the reload of a file already known to be interesting.

The ranges are stored gap-aware — `['70-70', '74-102']` — because the gaps are real: a law enacted in
one session is sometimes classified in the other session's table, and the page says so by writing two
ranges around it. Without the gaps, `GET /classifications/pl/119/72` could not tell "no table covers
this law" from "a table covers it and it classified nothing", which are different answers.

### 6. Postgres only, no OpenSearch

At ~150k short rows this is a filtered table, not a corpus. The queries the pages need are exact:
this Public Law, this title and section, this congress. Three btree indexes serve all of them.
Putting classification rows in the search cluster would also change what a search result *is* —
ADR-0049 declined the `all-versions` profile for that reason — and would add a second index to
rebuild on every mapping change (ADR-0051). Filtering on the classification pages is page-local and
the global search box is untouched.

### 7. Identifier derivation is three rules, and null is a valid answer

`usc_identifier` is what joins a classification row to the reader. It is derived only where the table
can actually name a provision, and it is spelled the way the corpus spells it:

* **A hyphen in a section number becomes an EN DASH.** The tables write `254c-15` with U+002D and
  the corpus writes `/us/usc/t42/s254c–15` with U+2013 — all 5,697 hyphenated section identifiers
  use the en dash and none uses the hyphen (CLAUDE.md gotcha 17). Derived without the fold, 697 of
  the 9,299 distinct identifiers the three measured files produce match no section, which is ~5% of
  all rows. `section_norm` keeps the plain hyphen, because that is the column typed input is matched
  against; the 342 corpus identifiers that do contain a hyphen are appendix date paths
  (`/us/usc/t50a/act/1917-10-06/ch106/s1`), which rule 1 derives nothing for.

* **Appendix rows derive nothing.** The table writes `5A / 101`; an appendix provision's real
  identifier is `/us/usc/t5a/pl/92/463/s1` or `/us/usc/t50a/act/1917-05-18/ch15/s212`, and not one of
  the corpus's 461 appendix sections uses the flat form `5A / 101` would produce (ADR-0065). Null by
  rule, not by failure — 149 rows of the 104th and 22 of the 110th.
* **Anything that is not a single section number derives nothing** — a range, a list, a subchapter
  name. The shape decides, not the hyphen: `254c-15` and `2680-3` are single sections and do derive.
* **Note and `prec` rows derive the parent section's identifier**, qualified by `is_note` and
  `action`. A note to § 3551 belongs on § 3551's page; OLRC's own notes are where a provision's
  classification history is written, which is what makes this join worth having.

## Consequences

**A `stat_pages ARRAY(Integer)` cannot hold every page these tables cite.** Statutes at Large pages
are not always numbers: the Omnibus Consolidated Appropriations Act, 1997 begins at 110 Stat. 3009-1,
and 1,658 of the 104th's 11,737 rows cite a page of that shape. `4264-4267` is a range and `3009-587`
is one page, and only the direction distinguishes them — so an ascending pair is read as a range
(endpoints only, not the pages between) and a descending pair as a label. The parser emits both
`stat_pages` (integers, per the spec's schema) and `stat_page_labels` (the tokens verbatim); until a
text column exists, those 1,658 rows have their citation in `raw_line` alone and cannot be linked to
statviewer.

**The description column is an open set and is stored decomposed *and* verbatim.** `description_raw`
keeps what OLRC wrote; `is_note`, `action`, `transfer_counterpart` and `act_name` are what a query
can use. An unrecognised word becomes the act name rather than a parse failure, which is how
`Ethics Act nt new` and `nt new IG Act` reach the same three values from opposite word orders. Older
vintages write transfers without the `tr` (`to 36/300113`), normalized here to the modern `tr to` so
that consumers see one spelling; the raw column keeps both.

**Row counts in `docs/classification-spec.md` §1 and §6 are three too high.** The figures 2,990 and
11,740 count the three header lines — the `U. S. Code` banner, the column header and the ruler —
along with the data rows. The parser reports 2,987 and 11,737, which is the number of rows, and the
verification artifacts carry that.

**Nothing in the parse layer touches the network**, so the whole of `tests/test_classification_parser.py`
runs offline against committed slices of the real pages (ADR-0013's rule). The slices are verbatim:
page head, column header and selected data rows, with only the site chrome removed and a provenance
comment added. `tests/fixtures/ecct.html` is the whole page, because the ECCT is one small malformed
table — a `<div>` opens inside the `<table>` and closes before `</table>` — and walking past the
chrome is part of what the parser has to do. That malformation is also why the ECCT is read by regex:
an HTML parser is entitled to reparent a table it meets that in.
