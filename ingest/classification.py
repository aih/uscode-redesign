"""The OLRC Classification Tables: which provision of which Public Law landed where.

`118-35 §101(3) → 18 U.S.C. 3551 note` is one row of one table. OLRC publishes one
table per congress-session in two sorts — Public Law order (`tbl118pl_2nd.htm`) and
US Code order (`tbl118cd_2nd.htm`) — carrying the same rows; only the `pl` files are
scraped here, because Code order is a sort in our own display. Alongside them sits
the Editorial Classification Change Table (`ecct.html`), which records where OLRC
moved *earlier* laws while classifying the new ones.

`docs/classification-spec.md` is the specification and
`docs/adr/0067-classification-tables.md` records the decisions. Four layers live
here, in this order, on `ingest/inventory.py`'s model of one module per source:

  * the parse side — HTML in, dataclasses out, no database and no network;
  * the fetch — one throttled request per page, cached under
    `data/classification/`;
  * `load_file`, which replaces one source document's rows wholesale, and
    `run_classification_load`, which walks the index pages doing that;
  * `poll_classification`, which asks whether anything changed and records the
    asking either way.

The tables are fixed-width text inside `<PRE><FONT face=Courier>` — there is no
`<table>` markup and no per-row identity of any kind. Six columns: Title, Section,
Description, Pub. L., Sec., Stat. Things the real files do that a guessed parser
would get wrong, each covered by a test in `tests/test_classification_parser.py`:

  * **Column offsets come from the header line, not the ruler.** The ruler merges
    Title and Section into one dash group (`-------------`), so it cannot supply six
    offsets. The header can, and it moves between vintages: 110th–119th are
    `0/6/19/36/45/67`, the 104th `0/6/20/42/51/68`. A header token that cannot be
    found is a `ClassificationParseError` — the format changed and this module needs
    revisiting, which is a louder thing than a bad row.
  * **Cells run into their neighbours with no separating space.** `tr to
    42/290ee-10118-84` is a 17-character description butted against `118-84`, and
    `1649(a) "Subchapter III"` overflows the Sec. column into Stat. Both are
    recovered by re-splitting the combined region on what the right-hand cell must
    look like — a Public Law number, or a run of page numbers.
  * **Anchors sit inside the fixed-width text.** Statviewer links carry the (volume,
    page) pair and are harvested before tags are stripped; the 104th and 110th wrap
    their Pub. L. cell in an `openPLaw` anchor instead, which carries nothing. After
    stripping, the visible text realigns to the column offsets — which is also why
    entities are unescaped rather than left alone: `&#160;` occupies one column on
    screen and must occupy one afterwards.
  * **The volume is in the header, not the row.** `138 Stat.` gives 138 for every row
    of the 118th's second session. The 104th spans two volumes, so its header reads
    `Stat. Page` and its rows have no volume unless a statviewer link supplies one
    (none do — that vintage predates the links).
  * **Appendix rows never derive a `usc_identifier`.** `5A / 101` is a real row, but
    appendix provisions are identified `/us/usc/t5a/pl/92/463/s1`, which `5A / 101`
    cannot produce (CLAUDE.md gotcha 7). Null by rule, not by failure.
  * **The description column is an open set**, not an enum: `nt`, `nt [tbl]`, `new`,
    `nt new`, `prec`, `gen amd`, `nt ed chg`, `omitted`, `repealed`,
    `tr to 42/290ee-10`, bare `to 36/300113` in older vintages, and act names on
    appendix rows (`Ethics Act nt new`, `IG Act nt`, `R Plan 2, 1968`).

The only function that reaches the network is `fetch_classification_page`, and
every test in the suite either injects an `Opener` or reads a committed slice, so
the suite runs offline (ADR-0013).
"""

from __future__ import annotations

import hashlib
import html as htmllib
import json
import re
import time
import urllib.request
import warnings
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from db.models import ClassificationEntry as ClassificationEntryRow
from db.models import ClassificationFile as ClassificationFileRow
from db.models import ClassificationSourceCheck
from db.models import EcctEntry as EcctEntryRow
from ingest.download import Opener, throttle
from ingest.inventory import USER_AGENT
from storage.classification import CLASSIFICATION_SOURCE_URL, law_in_ranges

CLASSIFICATION_BASE_URL = "https://uscode.house.gov/classification/"

# `CLASSIFICATION_SOURCE_URL` — the current congress's entry page, and the home
# of the change-detection key — and `law_in_ranges` are defined in
# `storage/classification.py` and imported back, so `/api/v1` can name the
# source and decide whether a public law is covered without importing the ingest
# layer. That is the `SOURCE_URL` precedent in `storage/repository.py`; both
# names are still addressed as `ingest.classification.<name>` by the CLI, the
# poll and their tests.

PRIOR_CLASSIFICATION_SOURCE_URL = CLASSIFICATION_BASE_URL + "priortables.shtml"
"""The 104th–118th entry page. Read by the backfill; the daily poll reads only
`CLASSIFICATION_SOURCE_URL`, since closed congresses do not gain laws."""

CACHE_DIR = Path("data/classification")
"""Where every fetched page is kept, under its own filename. Gitignored with the
rest of `data/`; the committed record of a run is the verification artifact."""

VERIFICATION_DIR = Path("docs/verification")
MANIFEST_PATH = Path("data/manifests/classification.json")

# --- entry pages -----------------------------------------------------------------

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_TABLE_HREF_RE = re.compile(
    r'href="(?P<href>[^"]*?(?P<filename>tbl(?P<congress>\d+)'
    r"(?P<order>pl|cd)(?:_(?P<session>1st|2nd))?"
    r'\.(?P<ext>htm|pdf)))"',
    re.IGNORECASE,
)
_ECCT_FILENAME_RE = re.compile(
    r"^ecct(?:_(?P<congress>\d+)-(?P<session>\d+))?\.html$", re.IGNORECASE
)
_ECCT_HREF_RE = re.compile(
    r'href="(?P<href>[^"]*?(?P<filename>ecct(?:_(?P<congress>\d+)-(?P<session>\d+))?'
    r"\.html))\"",
    re.IGNORECASE,
)
_CELL_OPEN_RE = re.compile(r"<td\b", re.IGNORECASE)
_ANCHOR_OPEN_RE = re.compile(r"<a\b", re.IGNORECASE)
_CONGRESS_SESSION_RE = re.compile(
    r"(?P<congress>\d+)(?:st|nd|rd|th)\s+Congress,\s*(?P<session>\d)(?:st|nd|rd|th)\s+Session",
    re.IGNORECASE,
)
_COVERED_START_RE = re.compile(r"Public Laws?\s+\d+-\d+")
_COVERED_STOP_RE = re.compile(
    r"\s*(?:Sorted in\b|Public Law order\b|U\.?\s?S\.? Code order\b|\(HTML|\(\*\*PDF)",
    re.IGNORECASE,
)
_COVERED_RANGE_RE = re.compile(
    r"(?P<congress>\d+)-(?P<first>\d+)(?:\s*(?:through|to)\s*(?:\d+-)?(?P<last>\d+))?"
)
_SESSION_NUMBERS = {"1st": 1, "2nd": 2}

# --- table files -----------------------------------------------------------------

_PRE_OPEN_RE = re.compile(r"<pre[^>]*>", re.IGNORECASE)
_PRE_CLOSE_RE = re.compile(r"</pre>|</div>", re.IGNORECASE)
_RULER_RE = re.compile(r"^\s*-{5,}")
_STATVIEWER_RE = re.compile(
    r"statviewer\.htm\?volume=(?P<volume>\d+)&(?:amp;)?page=(?P<page>\d+)",
    re.IGNORECASE,
)
_HEADER_TOKENS = ("Title", "Section", "Description", "Pub. L.", "Sec.")
_STAT_HEADER_RE = re.compile(r"(?:(?P<volume>\d+)\s+)?Stat\.")
_FILE_COVERED_RE = re.compile(r"\(\s*(?:Covering\s+)?(?P<text>Public Laws?[^)]*)\)")
_PREPARED_RE = re.compile(r"Prepared\s+by", re.IGNORECASE)
_LAST_UPDATED_RE = re.compile(r"last updated on\s+(?P<date>\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE)
_NUMERIC_DATE_RE = re.compile(r"(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})")
_LONG_DATE_RE = re.compile(
    r"(?P<month>January|February|March|April|May|June|July|August|September|October"
    r"|November|December)\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})",
    re.IGNORECASE,
)
_MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "january february march april may june july august september "
            "october november december"
        ).split(),
        start=1,
    )
}

_DATA_LINE_RE = re.compile(r"^(?P<title>\d+[A-Za-z]?)(?=\s|$)")
_CORRECTED_ROW_RE = re.compile(r"^(?P<marker>\*+)(?P<title>\d+[A-Za-z]?)\s+(?=\S)")
_PL_CELL_RE = re.compile(r"^(?P<congress>\d{2,3})-(?P<num>\d{1,4})$")
_PL_OVERFLOW_RE = re.compile(r"^(?P<description>.*?)(?P<pl>\d{2,3}-\d{1,4})\s*$")
_STAT_PAGE_TOKEN = r"\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?"
_STAT_CELL_RE = re.compile(
    rf"^\s*(?:{_STAT_PAGE_TOKEN}(?:[,\s]+{_STAT_PAGE_TOKEN})*)?\s*$"
)
"""What a Stat. cell can look like: page tokens, separated by commas or spaces.

A page is not always a number and not always digits. `110 Stat. 3009-587` is one
page and so is `113 Stat. 1501A-594` — the appropriations volumes number their
divisions with a letter, and 3,323 rows across the 105th–107th cite one. A cell
this rejects is a cell the row's own Sec. column has overrun into, which is what
the caller then tries to re-split."""
_QUOTED_SECTION_RE = re.compile(r'^(?P<section>.*?)\s*"(?P<quote>[^"]*)"\s*$')
_TRANSFER_RE = re.compile(
    r"(?:\btr\s+)?\b(?P<direction>to|fr)\s+(?P<target>(?:\d+[A-Za-z]?/)?\d[\w.\-–]*)"
)
_SECTION_IDENTIFIER_RE = re.compile(r"^\d+[a-z]*(?:-\d*[a-z]*\d*)*$")
_DESCRIPTION_KEYWORDS = frozenset(
    {"nt", "nts", "note", "new", "prec", "repealed", "omitted", "gen", "amd", "ed", "chg", "[tbl]"}
)
_NOTE_MARKERS = frozenset({"nt", "nts", "note"})

# --- ECCT ------------------------------------------------------------------------

_ECCT_ROW_RE = re.compile(r"<tr\b[^>]*>(?P<cells>.*?)</tr>", re.IGNORECASE | re.DOTALL)
_ECCT_CELL_RE = re.compile(
    r"<(?P<tag>td|th)\b[^>]*>(?P<body>.*?)</(?P=tag)>", re.IGNORECASE | re.DOTALL
)
_ECCT_CLASSIFICATION_RE = re.compile(
    r"^(?P<title>\d+[A-Za-z]?):(?P<section>\S+)(?:\s+(?P<description>.*))?$"
)
_PL_CITATION_RE = re.compile(r"Pub\.\s*L\.\s*(?P<congress>\d+)-(?P<num>\d+)")


class ClassificationParseError(ValueError):
    """Raised when a classification page yields nothing parseable — OLRC changed its
    markup and this module needs revisiting, rather than the table having genuinely
    gone empty. One bad *row* is a `warnings.warn` and a kept row; only zero rows, a
    missing `<PRE>`, or a header this module cannot read raise."""


# ---------------------------------------------------------------------------------
# Entry pages
# ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TableLink:
    """One classification document linked from `tables.shtml` or `priortables.shtml`."""

    kind: str
    """`'pl'` or `'ecct'` — a string, not an enum: OLRC has added document kinds
    before (the PDF variants, the Title 10 disposition tables) and will again."""

    congress: int
    session: int
    """`1` or `2`; `0` for the 104th's single whole-congress file."""

    filename: str
    url: str
    covered_laws_text: str = ""
    """The index page's own words, verbatim — "Public Law 119-70 and Public Laws
    119-74 through 119-102". This is the change-detection key (spec §1 hazard 6):
    the pages carry no usable `Last-Modified` and embed a per-request `jsessionid`,
    so raw-byte hashing detects nothing. Empty for ECCT links."""

    covered_ranges: tuple[str, ...] = ()
    """Gap-aware segments of law numbers within `congress`: `('70-70', '74-102')`."""

    first_law: int | None = None
    last_law: int | None = None

    def as_json(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "congress": self.congress,
            "session": self.session,
            "filename": self.filename,
            "url": self.url,
            "covered_laws_text": self.covered_laws_text,
            "covered_ranges": list(self.covered_ranges),
            "first_law": self.first_law,
            "last_law": self.last_law,
        }

    @classmethod
    def from_json(cls, record: dict[str, object]) -> "TableLink":
        return cls(
            kind=str(record["kind"]),
            congress=int(record["congress"]),  # type: ignore[arg-type]
            session=int(record["session"]),  # type: ignore[arg-type]
            filename=str(record["filename"]),
            url=str(record["url"]),
            covered_laws_text=str(record.get("covered_laws_text", "")),
            covered_ranges=tuple(str(r) for r in record.get("covered_ranges", [])),  # type: ignore[union-attr]
            first_law=_optional_int(record.get("first_law")),
            last_law=_optional_int(record.get("last_law")),
        )


def parse_tables_index(html: str, *, base_url: str = CLASSIFICATION_BASE_URL) -> list[TableLink]:
    """Every `pl` table and every ECCT linked from one entry page, in page order.

    Handles `tables.shtml` (the current congress) and `priortables.shtml`
    (104th–118th). `cd` files and the PDF variants some vintages also link are
    dropped here rather than downstream: Code order is the same rows resorted, and
    HTML exists for every vintage.

    The covered-law text is read from the *cell* the link sits in, up to the first
    anchor in it — the run between them says "Sorted in Public Law order", which
    contains the words "Public Law" and would otherwise win a nearest-match search.
    """
    links: list[TableLink] = []
    seen: set[str] = set()

    for match in _TABLE_HREF_RE.finditer(html):
        if match.group("order").lower() != "pl" or match.group("ext").lower() != "htm":
            continue
        filename = match.group("filename")
        if filename in seen:
            continue
        seen.add(filename)
        session_token = match.group("session")
        covered_text = _covered_text_for(html, match.start())
        ranges, first_law, last_law = parse_covered_laws(covered_text)
        links.append(
            TableLink(
                kind="pl",
                congress=int(match.group("congress")),
                # The 104th is one file for both sessions; 0 says "whole congress"
                # rather than inventing a session the source does not claim.
                session=_SESSION_NUMBERS[session_token.lower()] if session_token else 0,
                filename=filename,
                url=base_url + filename,
                covered_laws_text=covered_text,
                covered_ranges=ranges,
                first_law=first_law,
                last_law=last_law,
            )
        )

    newest = max(((link.congress, link.session) for link in links), default=(0, 0))
    for match in _ECCT_HREF_RE.finditer(html):
        filename = match.group("filename")
        if filename in seen:
            continue
        seen.add(filename)
        if match.group("congress"):
            congress, session = int(match.group("congress")), int(match.group("session"))
        else:
            # The unsuffixed `ecct.html` is the current session's. The sentence
            # linking it names that session; if OLRC ever stops writing it, fall
            # back to the newest `pl` table on the same page.
            congress, session = _congress_session_near(html, match.start(), newest)
        links.append(
            TableLink(
                kind="ecct",
                congress=congress,
                session=session,
                filename=filename,
                url=base_url + filename,
            )
        )

    if not links:
        raise ClassificationParseError(
            "no classification tables found on the entry page — the markup at "
            f"{CLASSIFICATION_SOURCE_URL} has probably changed"
        )
    return links


def parse_covered_laws(text: str) -> tuple[tuple[str, ...], int | None, int | None]:
    """`"Public Law 119-70 and Public Laws 119-74 through 119-102"` →
    `(('70-70', '74-102'), 70, 102)`.

    Segments rather than one span, because the ranges have gaps: a law enacted in one
    session is sometimes classified in the table for the other, and the entry page
    says so by writing two ranges around it. "through" and "to" are both used, the
    second endpoint appears with and without its congress prefix, and a lone law
    becomes a one-law segment.
    """
    segments: list[str] = []
    for match in _COVERED_RANGE_RE.finditer(text):
        first = int(match.group("first"))
        last = int(match.group("last")) if match.group("last") else first
        segment = f"{first}-{last}"
        if segment not in segments:
            segments.append(segment)
    if not segments:
        return (), None, None
    bounds = [tuple(int(part) for part in segment.split("-")) for segment in segments]
    return tuple(segments), min(b[0] for b in bounds), max(b[1] for b in bounds)


def _covered_text_for(html: str, href_pos: int) -> str:
    cell_start = max((m.end() for m in _CELL_OPEN_RE.finditer(html, 0, href_pos)), default=0)
    cell = html[cell_start:href_pos]
    anchor = _ANCHOR_OPEN_RE.search(cell)
    if anchor is not None:
        cell = cell[: anchor.start()]
    text = _clean_text(cell)
    start = _COVERED_START_RE.search(text)
    if start is None:
        return ""
    text = text[start.start() :]
    stop = _COVERED_STOP_RE.search(text)
    return text[: stop.start()].strip() if stop else text.strip()


def _congress_session_near(html: str, pos: int, fallback: tuple[int, int]) -> tuple[int, int]:
    cell_start = max((m.end() for m in _CELL_OPEN_RE.finditer(html, 0, pos)), default=0)
    matches = list(_CONGRESS_SESSION_RE.finditer(_clean_text(html[cell_start:pos])))
    if matches:
        return int(matches[-1].group("congress")), int(matches[-1].group("session"))
    return fallback


# ---------------------------------------------------------------------------------
# Table rows
# ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClassificationEntry:
    """One row of one classification table: a provision of a law and where it landed.

    Every column is kept twice — verbatim as the source printed it, and parsed
    best-effort. A row whose Pub. L. cell will not parse keeps null `pl_congress`
    and `pl_num` and is warned about; it is never dropped, because a dropped row is
    invisible and a null one is a question somebody can answer later.
    """

    row_seq: int
    """0-based position in the file. The source has no row identity of its own, and
    this is the only thing that reproduces Public Law order after a reload."""

    raw_line: str
    """The line with tags stripped and entities resolved; verbatim otherwise."""

    title_raw: str
    """`'18'`, `'5A'` — column 1 as printed."""

    title_num: str
    """`'18'`, `'5a'` — a string. Never `ORDER BY` it (CLAUDE.md gotcha 16)."""

    is_appendix: bool
    section_raw: str
    section_norm: str
    """Lowercased, with U+2013 and U+2011 folded to `-` (CLAUDE.md gotcha 17)."""

    description_raw: str
    """Column 3 as printed; `''` means the section was amended."""

    is_note: bool
    action: str | None = None
    """`'new'`, `'prec new'`, `'repealed'`, `'tr to'`, … — an open set, and null for a
    plain amendment. The note marker is not part of it; that is `is_note`."""

    transfer_counterpart: str | None = None
    """`'42/290ee-10'` — the other end of a `tr to` / `tr fr`, as printed."""

    act_name: str | None = None
    """`'Ethics Act'`, `'IG Act'`, `'R Plan 2, 1968'` — the underlying act named on
    appendix rows, where the Code section number alone identifies nothing."""

    usc_identifier: str | None = None
    """`'/us/usc/t18/s3551'`, or null. See `derive_usc_identifier`."""

    pl_congress: int | None = None
    pl_num: int | None = None
    pl_section_raw: str = ""
    """`'101(3)'`, `'2(6), (7)'`, `''` for a whole-law row. Verbatim: the section
    designators of an act are the act's business, not a shape we can impose."""

    new_section_quote: str | None = None
    """The quoted string trailing the Sec. cell — `202 "1948"` names section 1948 of
    the underlying act, being added by section 202 of the law."""

    stat_volume: int | None = None
    stat_pages: tuple[int, ...] = ()
    """The cell's page numbers, as integers. An ascending range contributes its two
    endpoints and not the pages between (`4264-4267` → `(4264, 4267)`); a hyphenated
    page *label* contributes nothing, because it is not an integer. See
    `stat_page_labels`."""

    stat_page_labels: tuple[str, ...] = ()
    """The cell's page tokens verbatim — `('3009-587',)`, `('1544', '1545')`.

    Statutes at Large pages are not always numbers. The Omnibus Consolidated
    Appropriations Act, 1997 begins at 110 Stat. 3009-1, and 1,658 of the 104th's
    11,737 rows cite a page of that shape. `4264-4267` is a range and `3009-587` is
    one page; nothing but the direction distinguishes them, so an ascending pair is
    read as a range and a descending pair as a label."""

    def as_json(self) -> dict[str, object]:
        return {
            "row_seq": self.row_seq,
            "raw_line": self.raw_line,
            "title_raw": self.title_raw,
            "title_num": self.title_num,
            "is_appendix": self.is_appendix,
            "section_raw": self.section_raw,
            "section_norm": self.section_norm,
            "description_raw": self.description_raw,
            "is_note": self.is_note,
            "action": self.action,
            "transfer_counterpart": self.transfer_counterpart,
            "act_name": self.act_name,
            "usc_identifier": self.usc_identifier,
            "pl_congress": self.pl_congress,
            "pl_num": self.pl_num,
            "pl_section_raw": self.pl_section_raw,
            "new_section_quote": self.new_section_quote,
            "stat_volume": self.stat_volume,
            "stat_pages": list(self.stat_pages),
            "stat_page_labels": list(self.stat_page_labels),
        }

    @classmethod
    def from_json(cls, record: dict[str, object]) -> "ClassificationEntry":
        return cls(
            row_seq=int(record["row_seq"]),  # type: ignore[arg-type]
            raw_line=str(record["raw_line"]),
            title_raw=str(record["title_raw"]),
            title_num=str(record["title_num"]),
            is_appendix=bool(record["is_appendix"]),
            section_raw=str(record["section_raw"]),
            section_norm=str(record["section_norm"]),
            description_raw=str(record["description_raw"]),
            is_note=bool(record["is_note"]),
            action=_optional_str(record.get("action")),
            transfer_counterpart=_optional_str(record.get("transfer_counterpart")),
            act_name=_optional_str(record.get("act_name")),
            usc_identifier=_optional_str(record.get("usc_identifier")),
            pl_congress=_optional_int(record.get("pl_congress")),
            pl_num=_optional_int(record.get("pl_num")),
            pl_section_raw=str(record.get("pl_section_raw", "")),
            new_section_quote=_optional_str(record.get("new_section_quote")),
            stat_volume=_optional_int(record.get("stat_volume")),
            stat_pages=tuple(int(p) for p in record.get("stat_pages", [])),  # type: ignore[union-attr]
            stat_page_labels=tuple(str(p) for p in record.get("stat_page_labels", [])),  # type: ignore[union-attr]
        )

    @property
    def pl_label(self) -> str | None:
        """`'118-35'`. Derived, never stored (spec §2)."""
        if self.pl_congress is None or self.pl_num is None:
            return None
        return f"{self.pl_congress}-{self.pl_num}"


@dataclass(frozen=True, slots=True)
class ParsedClassificationFile:
    """One `tbl…pl…htm` file, parsed. The registry row plus its rows."""

    kind: str
    congress: int
    session: int
    source_filename: str
    source_url: str
    covered_laws_text: str
    covered_ranges: tuple[str, ...]
    first_law: int | None
    last_law: int | None
    prepared_date: date | None
    stat_volume: int | None
    """The volume named in the column header. Null for the 104th, which spans two."""

    content_hash: str
    """sha256 of the extracted `<PRE>` text. Not of the response body: the pages
    embed a per-request `jsessionid`, so no two downloads are byte-identical."""

    column_offsets: tuple[int, ...]
    entries: tuple[ClassificationEntry, ...] = ()
    skipped_lines: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def row_count(self) -> int:
        return len(self.entries)

    def as_json(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "congress": self.congress,
            "session": self.session,
            "source_filename": self.source_filename,
            "source_url": self.source_url,
            "covered_laws_text": self.covered_laws_text,
            "covered_ranges": list(self.covered_ranges),
            "first_law": self.first_law,
            "last_law": self.last_law,
            "prepared_date": self.prepared_date.isoformat() if self.prepared_date else None,
            "stat_volume": self.stat_volume,
            "content_hash": self.content_hash,
            "column_offsets": list(self.column_offsets),
            "row_count": self.row_count,
            "entries": [entry.as_json() for entry in self.entries],
            "skipped_lines": list(self.skipped_lines),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_json(cls, record: dict[str, object]) -> "ParsedClassificationFile":
        prepared = record.get("prepared_date")
        return cls(
            kind=str(record["kind"]),
            congress=int(record["congress"]),  # type: ignore[arg-type]
            session=int(record["session"]),  # type: ignore[arg-type]
            source_filename=str(record["source_filename"]),
            source_url=str(record["source_url"]),
            covered_laws_text=str(record["covered_laws_text"]),
            covered_ranges=tuple(str(r) for r in record.get("covered_ranges", [])),  # type: ignore[union-attr]
            first_law=_optional_int(record.get("first_law")),
            last_law=_optional_int(record.get("last_law")),
            prepared_date=date.fromisoformat(str(prepared)) if prepared else None,
            stat_volume=_optional_int(record.get("stat_volume")),
            content_hash=str(record["content_hash"]),
            column_offsets=tuple(int(o) for o in record.get("column_offsets", [])),  # type: ignore[union-attr]
            entries=tuple(
                ClassificationEntry.from_json(e) for e in record.get("entries", [])  # type: ignore[union-attr]
            ),
            skipped_lines=tuple(str(s) for s in record.get("skipped_lines", [])),  # type: ignore[union-attr]
            warnings=tuple(str(w) for w in record.get("warnings", [])),  # type: ignore[union-attr]
        )

    def report(self) -> "ClassificationParseReport":
        """The verification artifact for this file — see `ClassificationParseReport`."""
        laws = [e.pl_num for e in self.entries if e.pl_num is not None]
        labels = [e.pl_label for e in self.entries if e.pl_label is not None]
        return ClassificationParseReport(
            congress=self.congress,
            session=self.session,
            source_filename=self.source_filename,
            rows_parsed=self.row_count,
            skipped_lines=len(self.skipped_lines),
            warnings=self.warnings,
            pl_span=(labels[0], labels[-1]) if labels else None,
            covered_ranges=self.covered_ranges,
            rows_outside_covered_ranges=sum(
                1 for law in laws if not law_in_ranges(law, self.covered_ranges)
            )
            if self.covered_ranges
            else 0,
            rows_without_pl=sum(1 for e in self.entries if e.pl_num is None),
            rows_without_identifier=sum(1 for e in self.entries if e.usc_identifier is None),
            distinct_titles=tuple(dict.fromkeys(e.title_num for e in self.entries)),
        )


@dataclass(frozen=True, slots=True)
class ClassificationParseReport:
    """What one parse found, for `docs/verification/classification-{c}-{s}.json`.

    Reliability claims in this project are re-runnable commands (PLAN §11.5), and
    "the parser read 2,987 rows off a file the source says covers 118-35 through
    118-274, warned about none of them, and left 149 rows without an identifier
    because they are appendix rows" is the whole of what this scraper can promise.
    """

    congress: int
    session: int
    source_filename: str
    rows_parsed: int
    skipped_lines: int
    warnings: tuple[str, ...]
    pl_span: tuple[str, str] | None
    """First and last Public Law seen in row order — checked against
    `covered_ranges`, which is what the source claims the file covers."""

    covered_ranges: tuple[str, ...]
    rows_outside_covered_ranges: int
    rows_without_pl: int
    rows_without_identifier: int
    distinct_titles: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        return {
            "congress": self.congress,
            "session": self.session,
            "source_filename": self.source_filename,
            "rows_parsed": self.rows_parsed,
            "skipped_lines": self.skipped_lines,
            "warnings": list(self.warnings),
            "pl_span": list(self.pl_span) if self.pl_span else None,
            "covered_ranges": list(self.covered_ranges),
            "rows_outside_covered_ranges": self.rows_outside_covered_ranges,
            "rows_without_pl": self.rows_without_pl,
            "rows_without_identifier": self.rows_without_identifier,
            "distinct_titles": list(self.distinct_titles),
        }

    @classmethod
    def from_json(cls, record: dict[str, object]) -> "ClassificationParseReport":
        span = record.get("pl_span")
        return cls(
            congress=int(record["congress"]),  # type: ignore[arg-type]
            session=int(record["session"]),  # type: ignore[arg-type]
            source_filename=str(record["source_filename"]),
            rows_parsed=int(record["rows_parsed"]),  # type: ignore[arg-type]
            skipped_lines=int(record["skipped_lines"]),  # type: ignore[arg-type]
            warnings=tuple(str(w) for w in record.get("warnings", [])),  # type: ignore[union-attr]
            pl_span=(str(span[0]), str(span[1])) if span else None,  # type: ignore[index]
            covered_ranges=tuple(str(r) for r in record.get("covered_ranges", [])),  # type: ignore[union-attr]
            rows_outside_covered_ranges=int(record.get("rows_outside_covered_ranges", 0)),  # type: ignore[arg-type]
            rows_without_pl=int(record.get("rows_without_pl", 0)),  # type: ignore[arg-type]
            rows_without_identifier=int(record.get("rows_without_identifier", 0)),  # type: ignore[arg-type]
            distinct_titles=tuple(str(t) for t in record.get("distinct_titles", [])),  # type: ignore[union-attr]
        )


@dataclass
class _Collector:
    """Warnings are both emitted and kept: `warnings.warn` is for the operator running
    the load, the list is for the verification artifact that outlives the run."""

    messages: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.messages.append(message)
        warnings.warn(message, stacklevel=3)


def parse_classification_file(
    html: str,
    *,
    filename: str,
    source_url: str | None = None,
    covered_laws_text: str | None = None,
) -> ParsedClassificationFile:
    """Parse one `tbl{congress}pl[_{session}].htm` into its registry row and its rows.

    `covered_laws_text` overrides the range printed in the file's own header. The
    loader passes the entry page's wording, because that is what a poll compares
    against and the two are written independently.
    """
    congress, session = _split_filename(filename)
    pre_text, pre_start = _extract_pre(html, filename)
    raw_lines = pre_text.split("\n")
    lines = [_visible(line) for line in raw_lines]

    ruler_index = next(
        (i for i, line in enumerate(lines) if _RULER_RE.match(line) and i > 0), None
    )
    if ruler_index is None:
        raise ClassificationParseError(
            f"{filename}: no column ruler found inside <pre> — the table layout changed"
        )
    header_line = lines[ruler_index - 1]
    offsets = refine_offsets(
        column_offsets(header_line, filename=filename), lines[ruler_index + 1 :]
    )
    stat_match = _STAT_HEADER_RE.search(header_line, offsets[5])
    stat_volume = (
        int(stat_match.group("volume")) if stat_match and stat_match.group("volume") else None
    )

    # Everything before the ruler, which is where both the covered range and the
    # prepared date live — and, in the 104th, before the `<pre>` as well, since that
    # file opens the block above its own title page.
    head_end = pre_start + sum(len(line) + 1 for line in raw_lines[:ruler_index])
    head_text = _clean_text(_COMMENT_RE.sub("", html[:head_end]))
    prepared_date = _prepared_date(head_text)
    if covered_laws_text is None:
        covered = _FILE_COVERED_RE.search(head_text)
        covered_laws_text = covered.group("text").strip() if covered else ""
    covered_ranges, first_law, last_law = parse_covered_laws(covered_laws_text)

    collector = _Collector()
    data_lines = raw_lines[ruler_index + 1 :]
    entries: list[ClassificationEntry] = []
    skipped: list[str] = []
    for raw_line in data_lines:
        printed = _visible(raw_line)
        if not printed.strip():
            continue
        visible, marker = realign_corrected_row(printed, title_width=offsets[1])
        if not _DATA_LINE_RE.match(visible):
            # Not a row and not blank: a footnote, a repeated header on a page
            # break, or a format this parser has not seen. Counted and shown in the
            # verification artifact rather than discarded silently.
            skipped.append(printed)
            collector.warn(f"{filename}: line does not start with a title number: {printed!r}")
            continue
        entries.append(
            _parse_row(
                raw_line,
                visible,
                printed=printed,
                marker=marker,
                row_seq=len(entries),
                offsets=offsets,
                file_stat_volume=stat_volume,
                filename=filename,
                collector=collector,
            )
        )

    if not entries:
        raise ClassificationParseError(
            f"{filename}: no rows parsed from {len(data_lines)} lines after the ruler"
        )

    return ParsedClassificationFile(
        kind="pl",
        congress=congress,
        session=session,
        source_filename=filename,
        source_url=source_url or (CLASSIFICATION_BASE_URL + filename),
        covered_laws_text=covered_laws_text,
        covered_ranges=covered_ranges,
        first_law=first_law,
        last_law=last_law,
        prepared_date=prepared_date,
        stat_volume=stat_volume,
        content_hash=hashlib.sha256(pre_text.encode("utf-8")).hexdigest(),
        column_offsets=tuple(offsets),
        entries=tuple(entries),
        skipped_lines=tuple(skipped),
        warnings=tuple(collector.messages),
    )


def column_offsets(header_line: str, *, filename: str = "") -> list[int]:
    """The six column starts, read off the header line.

    The ruler underneath merges Title and Section into one dash group, so it can
    only ever give five. A header token that is not there raises: the offsets are
    the whole parse, and guessing them would put plausible garbage in every row.
    """
    offsets: list[int] = []
    at = 0
    for token in _HEADER_TOKENS:
        position = header_line.find(token, at)
        if position < 0:
            raise ClassificationParseError(
                f"{filename or 'header'}: column header {token!r} not found in "
                f"{header_line!r} — the table format changed"
            )
        offsets.append(position)
        at = position + len(token)
    stat = _STAT_HEADER_RE.search(header_line, at)
    if stat is None:
        raise ClassificationParseError(
            f"{filename or 'header'}: no Stat. column in {header_line!r} — the table "
            "format changed"
        )
    offsets.append(stat.start())
    return offsets


_OFFSET_SPLIT_TOLERANCE = 0.2
"""Above this share of rows, a boundary that splits a token is the boundary being
wrong rather than the rows overrunning it. The two are far apart in the real
files: the worst legitimate overrun is 3% of a file's rows, and the two files
whose Sec. column sits one character left of where their header puts it split
99.9% and 74% of theirs."""

_OFFSET_SEARCH = (-1, 1, -2, 2)

_OFFSET_MINIMUM_ROWS = 20
"""Below this many rows a file cannot say anything about its own columns: one row
that overruns is 100% of a one-row file. The smallest published table is 517 rows,
so this bound only ever applies to a fragment."""


def refine_offsets(offsets: list[int], data_lines: Iterable[str], *, sample: int = 500) -> list[int]:
    """Move a column boundary the file's own rows disagree with.

    The header is where the offsets come from, and in 29 of the 31 published
    tables it is right. In `tbl112pl_2nd.htm` and `tbl113pl_1st.htm` the Sec.
    column starts one character to the left of where their header puts it, and
    the header is not wrong about anything else — every other column lines up.
    Read from the header alone, the Pub. L. cell of every row in those files ends
    in the first digit of the Sec. cell, `_PL_CELL_RE` rejects it, and the guard
    against inventing a truncated law number leaves 3,717 rows with no public law
    at all. That is the largest defect the first full-corpus run found.

    A boundary that lands between two non-space characters has cut one value in
    half. Rows do that legitimately when a cell overruns (spec §1 hazard 2), so
    the signal is not any single row but the share of them: a boundary that splits
    a token in more than a fifth of the file's rows is moved to whichever nearby
    column splits fewest, and one that does not is left exactly where the header
    said. A boundary is never moved onto or past its neighbour, and a file with
    too few rows to measure keeps the header's answer whatever its rows do.
    """
    lines = [line for line in data_lines if line.strip()][:sample]
    if len(lines) < _OFFSET_MINIMUM_ROWS:
        return offsets
    refined = list(offsets)
    for index in range(1, len(refined)):
        rate = _split_rate(lines, refined[index])
        if rate <= _OFFSET_SPLIT_TOLERANCE:
            continue
        best = refined[index]
        for delta in _OFFSET_SEARCH:
            candidate = refined[index] + delta
            if candidate <= refined[index - 1] or (
                index + 1 < len(refined) and candidate >= refined[index + 1]
            ):
                continue
            candidate_rate = _split_rate(lines, candidate)
            if candidate_rate < rate:
                best, rate = candidate, candidate_rate
        refined[index] = best
    return refined


def _split_rate(lines: Sequence[str], at: int) -> float:
    """The share of rows in which this boundary falls inside a value."""
    return sum(_boundary_splits_a_token(line, at) for line in lines) / len(lines)


def _boundary_splits_a_token(visible: str, at: int) -> bool:
    """True when a column boundary falls between two non-space characters.

    The columns are fixed-width and the values are not, so a boundary with no space
    on either side of it has cut one value in half rather than separated two. Both
    overflow recoveries below turn on this: the source writes no separator when a
    cell overruns, and the halves it leaves are each shaped like a valid cell.
    """
    if at <= 0 or at >= len(visible):
        return False
    return not visible[at - 1].isspace() and not visible[at].isspace()


def realign_corrected_row(visible: str, *, title_width: int) -> tuple[str, str]:
    """Put a corrected row's columns back where the header says they are.

    OLRC marks a row it has since corrected with an asterisk in front of the title
    number, and a second round of corrections with two — "`*` denotes an item that
    was corrected as of October 6, 2005" says the footnote of `tbl108pl_1st.htm`.
    The marker is written into the Title column, which is six characters wide and
    holds at most four, and it does not always fit in the padding: `*16   3503`
    leaves every later column where it was, `*42    7619` moves them one to the
    right and `**15    683` two. Twenty-nine rows across three files are marked,
    and unmarked ones start with a digit, so before this they were not recognised
    as rows at all and were dropped.

    The Title cell is rewritten without the marker and padded back to its declared
    width, which restores the alignment of every column after it. Returns the
    realigned line and the marker, which goes back onto `title_raw` — column 1 as
    printed — and into no parsed field. There is no column of its own for it, and
    inventing one would be a schema for an annotation the source explains in a
    footnote.
    """
    match = _CORRECTED_ROW_RE.match(visible)
    if match is None:
        return visible, ""
    return match.group("title").ljust(title_width) + visible[match.end() :], match.group("marker")


def _split_near(region: str, nominal: int) -> tuple[str, str] | None:
    """Split an overrun Sec./Stat. region at the gap nearest the declared boundary.

    A cell that overruns pushes the one after it to the right, so the true gap is the
    first whitespace run ending at or after where the header puts the boundary.
    Splitting at the first gap of any kind cuts `101, 102, 103, 104, 105` after
    `101,`; splitting at the last cuts `1544, 1545` after the comma. Returns None when
    no gap leaves something Stat.-shaped on the right, which the caller warns about.
    """
    for match in re.finditer(r"\s+", region):
        if match.end() < nominal:
            continue
        section, stat = region[: match.start()].strip(), region[match.end() :].strip()
        if section and stat and _STAT_CELL_RE.match(stat):
            return section, stat
    return None


def normalize_section(section: str) -> str:
    """Lowercase, and fold U+2013/U+2011 to a plain hyphen.

    OLRC writes section numbers with an EN DASH in USLM (CLAUDE.md gotcha 17) and
    with a hyphen in these tables. Normalizing both to the hyphen is what lets a row
    join a section, and what lets a reader's typed `45a-1` match either.
    """
    return section.strip().lower().replace("–", "-").replace("‑", "-")


def derive_usc_identifier(title_num: str, section_norm: str, *, is_appendix: bool) -> str | None:
    """`('18', '3551')` → `/us/usc/t18/s3551`; null where the table cannot say.

    Three rules, each measured against the real files:

      * **Appendix rows derive nothing.** An appendix provision's `@identifier` is
        `/us/usc/t5a/pl/92/463/s1` or `/us/usc/t50a/act/1917-05-18/ch15/s212`; not
        one of the corpus's 461 appendix sections uses the flat `t5a/s101` form the
        table's `5A / 101` would produce (ADR-0065).
      * **Anything that is not a single section number derives nothing** — a range,
        a list, a subchapter name. `2680-3` and `254c-15` are single sections and do
        derive; the shape, not the hyphen, decides.
      * **Note and `prec` rows derive the parent section's identifier.** `18 / 3551 /
        nt` is a note *to* § 3551 and belongs on that section's page; `is_note` and
        `action` say which it is, so nothing downstream has to read a note as text.

    The number is spelled back with an EN DASH, which is how the corpus writes it and
    therefore the only spelling that joins: all 5,697 hyphenated section identifiers
    in the corpus use U+2013 and none uses U+002D, so `/us/usc/t42/s254c-15` matches
    no row while `/us/usc/t42/s254c–15` matches one (CLAUDE.md gotcha 17). The plain
    hyphen stays on `section_norm`, which is what typed input is matched against;
    the 342 corpus identifiers that do contain a hyphen are appendix date paths
    (`/us/usc/t50a/act/1917-10-06/ch106/s1`), which rule 1 derives nothing for.
    """
    if is_appendix:
        return None
    if not _SECTION_IDENTIFIER_RE.match(section_norm):
        return None
    return f"/us/usc/t{title_num}/s{section_norm.replace('-', '–')}"


def parse_stat_pages(cell: str) -> tuple[tuple[str, ...], tuple[int, ...]]:
    """The Stat. cell → `(labels verbatim, page numbers as integers)`.

    `'1544, 1545'` → `(('1544', '1545'), (1544, 1545))`;
    `'4264-4267'` → `(('4264-4267',), (4264, 4267))` — a range, endpoints only;
    `'3009-587'` → `(('3009-587',), ())` — one page of 110 Stat., which has no
    integer form. A hyphenated pair is a range when it ascends and a page label when
    it does not, which is the only signal the source gives.
    """
    labels: list[str] = []
    pages: list[int] = []
    for token in (part.strip() for part in cell.split(",")):
        if not token:
            continue
        labels.append(token)
        span = re.fullmatch(r"(?P<first>\d+)-(?P<last>\d+)", token)
        if span is not None:
            first, last = int(span.group("first")), int(span.group("last"))
            if last > first:
                pages.extend((first, last))
            continue
        if token.isdigit():
            pages.append(int(token))
    return tuple(labels), tuple(pages)


def parse_description(description: str) -> tuple[bool, str | None, str | None, str | None]:
    """Column 3 → `(is_note, action, transfer_counterpart, act_name)`.

    The column is an open set (spec §1) and this splits it into the parts a query
    needs without closing it: the note marker is a flag, the transfer target is
    lifted out with its title, whatever is left that this module recognises becomes
    the action, and whatever is left that it does not becomes the act name — which
    is how `Ethics Act nt new` and `nt new IG Act` reach the same three values from
    opposite word orders.
    """
    text = description.strip()
    if not text:
        return False, None, None, None

    transfer = _TRANSFER_RE.search(text)
    counterpart: str | None = None
    action_tokens: list[str] = []
    if transfer is not None:
        counterpart = transfer.group("target")
        # Both `tr to 36/300113` and the older bare `to 36/300113` mean a transfer;
        # normalizing the older form spares every consumer the two spellings.
        action_tokens.append(f"tr {transfer.group('direction')}")
        text = (text[: transfer.start()] + " " + text[transfer.end() :]).strip()

    is_note = False
    keywords: list[str] = []
    other: list[str] = []
    for token in text.split():
        if token.lower() in _NOTE_MARKERS:
            is_note = True
        elif token.lower() in _DESCRIPTION_KEYWORDS:
            keywords.append(token)
        else:
            other.append(token)

    action = " ".join(keywords + action_tokens) or None
    return is_note, action, counterpart, " ".join(other) or None


def _split_at_linked_page(region: str, links: Sequence[tuple[int, int]]) -> tuple[str, str] | None:
    """Split an overrun Sec./Stat. region where the row's own statviewer link says
    the page number starts.

    `4001(b)(2)(A), (B), (D)(iii)1967` has no whitespace for `_split_near` to cut
    at, and the page is butted straight against the designator. The anchor around
    it names page 1967, which is evidence from the document rather than a guess, so
    the last occurrence of those digits is the split — provided what follows is
    Stat.-shaped, which is what stops a designator that happens to contain the page
    number from being cut in half.
    """
    for _volume, page in links:
        index = region.rfind(str(page))
        if index <= 0:
            continue
        section, stat = region[:index].strip(), region[index:].strip()
        if section and _STAT_CELL_RE.match(stat):
            return section, stat
    return None


def _parse_row(
    raw_line: str,
    visible: str,
    *,
    printed: str | None = None,
    marker: str = "",
    row_seq: int,
    offsets: list[int],
    file_stat_volume: int | None,
    filename: str,
    collector: _Collector,
) -> ClassificationEntry:
    # Harvested before the tags go, because the (volume, page) pair lives in the
    # href and the visible text carries only the page.
    links = [
        (int(m.group("volume")), int(m.group("page")))
        for m in _STATVIEWER_RE.finditer(raw_line)
    ]

    cells = [
        visible[start:end].strip()
        for start, end in zip(offsets, list(offsets[1:]) + [len(visible)])
    ]
    title_raw, section_raw, description_raw, pl_raw, section_of_law, stat_raw = cells

    pl_match = _PL_CELL_RE.match(pl_raw)
    if pl_match is None:
        # The description overran its column with no separating space
        # (`tr to 42/290ee-10118-84`). Re-split on what the right-hand cell must be.
        combined = visible[offsets[2] : offsets[4]].strip()
        if _boundary_splits_a_token(visible, offsets[4]):
            # The overrun reached past the Sec. column too, so `combined` ends in
            # the middle of the law number and `_PL_OVERFLOW_RE` would anchor on
            # what is left of it — `118-274` read as `118-2`. Leave the law null,
            # which spec §2 provides for, rather than store a different law's.
            collector.warn(
                f"{filename}: row {row_seq} overruns the Sec. column, so its "
                f"Pub. L. number is cut off at {combined!r}: {visible!r}"
            )
        else:
            overflow = _PL_OVERFLOW_RE.match(combined)
            if overflow is not None:
                description_raw = overflow.group("description").strip()
                pl_raw = overflow.group("pl")
                pl_match = _PL_CELL_RE.match(pl_raw)
    if pl_match is None:
        collector.warn(
            f"{filename}: row {row_seq} has no parseable Pub. L. cell "
            f"({pl_raw!r}) — keeping the row: {visible!r}"
        )

    if not _STAT_CELL_RE.match(stat_raw) or _boundary_splits_a_token(visible, offsets[5]):
        # The Sec. cell overran instead: `1649(a) "Subchapter III"` is 24 characters
        # in a 22-character column. The boundary test is there because a Sec. cell
        # that overruns with digits — `101, 102, 103, 104, 105` — leaves a Stat. cell
        # of `5 3` that `_STAT_CELL_RE` accepts, and 29 of the 31 files carry no
        # statviewer links for the cross-check below to catch it with.
        region = visible[offsets[4] :]
        overflow = _split_near(region, offsets[5] - offsets[4]) or _split_at_linked_page(
            region, links
        )
        if overflow is not None:
            section_of_law, stat_raw = overflow
        else:
            collector.warn(
                f"{filename}: row {row_seq} has no parseable Stat. cell "
                f"({stat_raw!r}) — keeping the row: {visible!r}"
            )
            stat_raw = ""

    new_section_quote = None
    quoted = _QUOTED_SECTION_RE.match(section_of_law)
    if quoted is not None:
        section_of_law = quoted.group("section").strip()
        new_section_quote = quoted.group("quote")

    stat_page_labels, stat_pages = parse_stat_pages(stat_raw)
    stat_volume = links[0][0] if links else file_stat_volume
    for _, page in links:
        if page not in stat_pages:
            # The link and the text disagree, which means the slice is off by a
            # column somewhere. Cheap to check and the only thing that would catch a
            # silent realignment of a whole file.
            collector.warn(
                f"{filename}: row {row_seq} links Stat. page {page} but the cell "
                f"reads {stat_raw!r}: {visible!r}"
            )

    is_appendix = bool(title_raw) and title_raw[-1].isalpha()
    title_num = title_raw.lower()
    # A corrected row's asterisks are part of column 1 as printed and of no
    # parsed field; `title_num` is what anything downstream joins on.
    title_raw = marker + title_raw
    section_norm = normalize_section(section_raw)
    is_note, action, counterpart, act_name = parse_description(description_raw)

    return ClassificationEntry(
        row_seq=row_seq,
        raw_line=printed if printed is not None else visible,
        title_raw=title_raw,
        title_num=title_num,
        is_appendix=is_appendix,
        section_raw=section_raw,
        section_norm=section_norm,
        description_raw=description_raw,
        is_note=is_note,
        action=action,
        transfer_counterpart=counterpart,
        act_name=act_name,
        usc_identifier=derive_usc_identifier(
            title_num, section_norm, is_appendix=is_appendix
        ),
        pl_congress=int(pl_match.group("congress")) if pl_match else None,
        pl_num=int(pl_match.group("num")) if pl_match else None,
        pl_section_raw=section_of_law,
        new_section_quote=new_section_quote,
        stat_volume=stat_volume,
        stat_pages=stat_pages,
        stat_page_labels=stat_page_labels,
    )


def _split_filename(filename: str) -> tuple[int, int]:
    match = re.match(
        r"tbl(?P<congress>\d+)pl(?:_(?P<session>1st|2nd))?\.htm$", filename, re.IGNORECASE
    )
    if match is None:
        raise ClassificationParseError(
            f"{filename!r} is not a Public Law order classification table filename"
        )
    session_token = match.group("session")
    return (
        int(match.group("congress")),
        _SESSION_NUMBERS[session_token.lower()] if session_token else 0,
    )


def _extract_pre(html: str, filename: str) -> tuple[str, int]:
    """The `<PRE>` block's text and where it starts. The 104th never closes its
    `<pre>`, so the enclosing `</div>` ends it instead."""
    opening = _PRE_OPEN_RE.search(html)
    if opening is None:
        raise ClassificationParseError(f"{filename}: no <pre> block — this is not a table page")
    rest = html[opening.end() :]
    closing = _PRE_CLOSE_RE.search(rest)
    return rest[: closing.start()] if closing else rest, opening.end()


def _prepared_date(head_text: str) -> date | None:
    """The date under "Prepared by / Office of the Law Revision Counsel", or the
    104th's "This page was last updated on 07/23/1997" when there is no other."""
    prepared = _PREPARED_RE.search(head_text)
    if prepared is not None:
        parsed = _parse_date(head_text[prepared.end() : prepared.end() + 300])
        if parsed is not None:
            return parsed
    updated = _LAST_UPDATED_RE.search(head_text)
    return _parse_date(updated.group("date")) if updated else None


def _parse_date(text: str) -> date | None:
    long_match = _LONG_DATE_RE.search(text)
    if long_match is not None:
        return date(
            int(long_match.group("year")),
            _MONTHS[long_match.group("month").lower()],
            int(long_match.group("day")),
        )
    match = _NUMERIC_DATE_RE.search(text)
    if match is None:
        return None
    return date(int(match.group("year")), int(match.group("month")), int(match.group("day")))


# ---------------------------------------------------------------------------------
# Editorial Classification Change Table
# ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EcctEntry:
    """One row of the ECCT: where OLRC moved an earlier law, and what prompted it."""

    row_seq: int
    former_raw: str
    """`'42:294t nt'` — the classification as it was."""

    new_raw: str
    """`'42:294u new'`."""

    provision_affected: str
    """The full Pub. L. citation of the provision that moved, verbatim."""

    provision_prompting: str
    """The full Pub. L. citation of the provision that prompted the move."""

    former_title_num: str | None = None
    former_section_norm: str | None = None
    former_is_note: bool = False
    new_title_num: str | None = None
    new_section_norm: str | None = None
    new_is_note: bool = False
    affected_pl_congress: int | None = None
    affected_pl_num: int | None = None
    prompting_pl_congress: int | None = None
    prompting_pl_num: int | None = None

    def as_json(self) -> dict[str, object]:
        return {
            "row_seq": self.row_seq,
            "former_raw": self.former_raw,
            "new_raw": self.new_raw,
            "provision_affected": self.provision_affected,
            "provision_prompting": self.provision_prompting,
            "former_title_num": self.former_title_num,
            "former_section_norm": self.former_section_norm,
            "former_is_note": self.former_is_note,
            "new_title_num": self.new_title_num,
            "new_section_norm": self.new_section_norm,
            "new_is_note": self.new_is_note,
            "affected_pl_congress": self.affected_pl_congress,
            "affected_pl_num": self.affected_pl_num,
            "prompting_pl_congress": self.prompting_pl_congress,
            "prompting_pl_num": self.prompting_pl_num,
        }

    @classmethod
    def from_json(cls, record: dict[str, object]) -> "EcctEntry":
        return cls(
            row_seq=int(record["row_seq"]),  # type: ignore[arg-type]
            former_raw=str(record["former_raw"]),
            new_raw=str(record["new_raw"]),
            provision_affected=str(record["provision_affected"]),
            provision_prompting=str(record["provision_prompting"]),
            former_title_num=_optional_str(record.get("former_title_num")),
            former_section_norm=_optional_str(record.get("former_section_norm")),
            former_is_note=bool(record.get("former_is_note", False)),
            new_title_num=_optional_str(record.get("new_title_num")),
            new_section_norm=_optional_str(record.get("new_section_norm")),
            new_is_note=bool(record.get("new_is_note", False)),
            affected_pl_congress=_optional_int(record.get("affected_pl_congress")),
            affected_pl_num=_optional_int(record.get("affected_pl_num")),
            prompting_pl_congress=_optional_int(record.get("prompting_pl_congress")),
            prompting_pl_num=_optional_int(record.get("prompting_pl_num")),
        )


@dataclass(frozen=True, slots=True)
class ParsedEcctFile:
    """`ecct.html`, parsed. Zero rows is a valid answer; zero headers is not."""

    kind: str
    congress: int
    session: int
    source_filename: str
    source_url: str
    content_hash: str
    entries: tuple[EcctEntry, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def row_count(self) -> int:
        return len(self.entries)

    def as_json(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "congress": self.congress,
            "session": self.session,
            "source_filename": self.source_filename,
            "source_url": self.source_url,
            "content_hash": self.content_hash,
            "row_count": self.row_count,
            "entries": [entry.as_json() for entry in self.entries],
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_json(cls, record: dict[str, object]) -> "ParsedEcctFile":
        return cls(
            kind=str(record["kind"]),
            congress=int(record["congress"]),  # type: ignore[arg-type]
            session=int(record["session"]),  # type: ignore[arg-type]
            source_filename=str(record["source_filename"]),
            source_url=str(record["source_url"]),
            content_hash=str(record["content_hash"]),
            entries=tuple(EcctEntry.from_json(e) for e in record.get("entries", [])),  # type: ignore[union-attr]
            warnings=tuple(str(w) for w in record.get("warnings", [])),  # type: ignore[union-attr]
        )


def parse_ecct(
    html: str,
    *,
    filename: str = "ecct.html",
    source_url: str | None = None,
    congress: int = 0,
    session: int = 0,
) -> ParsedEcctFile:
    """Parse the Editorial Classification Change Table.

    The document is a real `<table>` and a malformed one — a `<div id="boxheads">`
    opens inside it and its `</div>` closes before `</table>` — so the rows are read
    by regex. An HTML parser is entitled to reparent the whole table when it meets
    that.

    Zero data rows is valid: the current table has one. Zero *header* cells is not —
    that means the four columns this reads by position are no longer there.
    """
    rows = list(_ECCT_ROW_RE.finditer(html))
    headers = 0
    entries: list[EcctEntry] = []
    collector = _Collector()

    for row_seq, row in enumerate(rows):
        cells = list(_ECCT_CELL_RE.finditer(row.group("cells")))
        if not cells:
            # `_ECCT_CELL_RE` needs a closing tag, which a document this malformed
            # may not write. A row carrying text and yielding no cells is a row
            # being lost, so it is warned about; an empty `<tr></tr>` is not.
            if _clean_text(row.group("cells")):
                collector.warn(
                    f"{filename}: row {row_seq} has text but no parseable cells: "
                    f"{_clean_text(row.group('cells'))!r}"
                )
            continue
        if all(cell.group("tag").lower() == "th" for cell in cells):
            headers += len(cells)
            continue
        values = [_clean_text(cell.group("body")) for cell in cells]
        if len(values) < 4:
            collector.warn(f"{filename}: row {row_seq} has {len(values)} cells, not 4")
            continue
        former_title, former_section, former_is_note = _split_classification(values[0])
        new_title, new_section, new_is_note = _split_classification(values[1])
        affected = _PL_CITATION_RE.search(values[2])
        prompting = _PL_CITATION_RE.search(values[3])
        entries.append(
            EcctEntry(
                row_seq=len(entries),
                former_raw=values[0],
                new_raw=values[1],
                provision_affected=values[2],
                provision_prompting=values[3],
                former_title_num=former_title,
                former_section_norm=former_section,
                former_is_note=former_is_note,
                new_title_num=new_title,
                new_section_norm=new_section,
                new_is_note=new_is_note,
                affected_pl_congress=int(affected.group("congress")) if affected else None,
                affected_pl_num=int(affected.group("num")) if affected else None,
                prompting_pl_congress=int(prompting.group("congress")) if prompting else None,
                prompting_pl_num=int(prompting.group("num")) if prompting else None,
            )
        )

    if headers == 0:
        raise ClassificationParseError(
            f"{filename}: no header cells found — the ECCT markup has changed"
        )

    return ParsedEcctFile(
        kind="ecct",
        congress=congress,
        session=session,
        source_filename=filename,
        source_url=source_url or (CLASSIFICATION_BASE_URL + filename),
        content_hash=hashlib.sha256(
            "\n".join(row.group("cells") for row in rows).encode("utf-8")
        ).hexdigest(),
        entries=tuple(entries),
        warnings=tuple(collector.messages),
    )


def _split_classification(value: str) -> tuple[str | None, str | None, bool]:
    """`'42:294t nt'` → `('42', '294t', True)`."""
    match = _ECCT_CLASSIFICATION_RE.match(value.strip())
    if match is None:
        return None, None, False
    description = match.group("description") or ""
    return (
        match.group("title").lower(),
        normalize_section(match.group("section")),
        any(token.lower() in _NOTE_MARKERS for token in description.split()),
    )


# ---------------------------------------------------------------------------------


def _visible(line: str) -> str:
    """One `<PRE>` line as the browser lays it out: tags gone, entities resolved,
    NBSP a space. Every step is one-glyph-for-one-glyph, so the column offsets that
    were true on screen are still true here."""
    return htmllib.unescape(_TAG_RE.sub("", line)).replace("\xa0", " ").rstrip()


# ---------------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------------


def page_filename(url: str) -> str:
    """`'…/classification/tbl118pl_2nd.htm'` → `'tbl118pl_2nd.htm'`."""
    return url.rsplit("/", 1)[-1].split("?", 1)[0]


def fetch_classification_page(
    url: str,
    *,
    cache_dir: Path | None = CACHE_DIR,
    filename: str | None = None,
    timeout: float = 60.0,
    opener: Opener | None = None,
) -> str:
    """GET one classification page, throttled, and keep a copy on disk.

    The throttle is `ingest.download.throttle` and the User-Agent is
    `ingest.inventory.USER_AGENT`, so a run that fetches tables and a run that
    fetches title zips share one ~1 req/sec budget at uscode.house.gov
    (CLAUDE.md's source etiquette). A full backfill is ~33 requests.

    **The cache is a record of what was fetched, not a way to avoid fetching.**
    Every call here makes the request; what avoids requests is the covered-law
    gate in `run_classification_load`, which skips a file without asking for it.
    Reading a cached copy back is `read_cached_page`, which the `--from-file`
    path uses. A cache consulted here would be actively wrong: the one page that
    changes is the current session's, and serving last week's copy of it is
    exactly the failure the poll exists to catch.

    The body lands in a `.part` file and is renamed, so an interrupted fetch
    cannot leave a truncated page that a later `--from-file` run parses as real.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    throttle()
    with (opener or _default_opener)(request, timeout) as response:
        charset = getattr(response.headers, "get_content_charset", lambda: None)() or "utf-8"
        html = response.read().decode(charset, errors="replace")

    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / (filename or page_filename(url))
        partial = target.with_suffix(target.suffix + ".part")
        partial.write_text(html, encoding="utf-8")
        partial.replace(target)
    return html


def read_cached_page(directory: Path, filename: str) -> str | None:
    """A page already on disk, or None. The offline half of the fetch."""
    path = directory / filename
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _default_opener(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - fixed https host


# ---------------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FileLoadResult:
    """What `load_file` did to one source document."""

    kind: str
    congress: int
    session: int
    source_filename: str
    action: str
    """`'inserted'`, `'replaced'`, or `'unchanged'` — the last meaning the
    extracted `<PRE>` text hashed the same, so the registry row was refreshed
    and no row was touched."""

    rows_written: int
    rows_deleted: int
    file_id: int | None = None

    @property
    def loaded(self) -> bool:
        return self.action != "unchanged"


def load_file(
    session: Session,
    parsed: ParsedClassificationFile | ParsedEcctFile,
    *,
    force: bool = False,
) -> FileLoadResult:
    """Replace one source document's rows wholesale. Commits nothing.

    The source has no row identity of any kind — no ids, no keys, and rows that
    shift position when OLRC republishes the current session's file with new laws
    in it — so there is nothing to diff against (ADR-0067 decision 3). A file
    whose `<PRE>` text hashes differently has its entries deleted and re-inserted;
    a file that hashes the same has its registry row refreshed and its rows left
    alone, because the index page can reword its covered-law sentence without the
    table changing.

    The delete is explicit for both kinds rather than left to `ON DELETE CASCADE`:
    the registry row is updated in place, not deleted, so the cascade never fires.

    The caller owns the transaction. `run_classification_load` commits once per
    file, which is what makes an interrupted backfill resumable — the registry is
    the state.
    """
    row = session.scalars(
        select(ClassificationFileRow).where(
            ClassificationFileRow.kind == parsed.kind,
            ClassificationFileRow.congress == parsed.congress,
            ClassificationFileRow.session == parsed.session,
        )
    ).one_or_none()

    unchanged = row is not None and row.content_hash == parsed.content_hash and not force
    values = _registry_values(parsed)

    if row is None:
        row = ClassificationFileRow(**values)
        session.add(row)
        action = "inserted"
    else:
        for name, value in values.items():
            setattr(row, name, value)
        row.fetched_at = datetime.now(timezone.utc)
        action = "unchanged" if unchanged else "replaced"
    session.flush()

    if unchanged:
        return FileLoadResult(
            kind=parsed.kind,
            congress=parsed.congress,
            session=parsed.session,
            source_filename=parsed.source_filename,
            action=action,
            rows_written=0,
            rows_deleted=0,
            file_id=row.id,
        )

    table = EcctEntryRow if parsed.kind == "ecct" else ClassificationEntryRow
    deleted = session.execute(
        delete(table).where(table.file_id == row.id)
    ).rowcount or 0

    payload = [
        {"file_id": row.id, **entry.as_json()} for entry in parsed.entries
    ]
    if payload:
        # One statement rather than 11,737 ORM objects: the 104th's file is the
        # size that decides whether a full backfill takes a minute or an hour.
        session.execute(insert(table), payload)

    return FileLoadResult(
        kind=parsed.kind,
        congress=parsed.congress,
        session=parsed.session,
        source_filename=parsed.source_filename,
        action=action,
        rows_written=len(payload),
        rows_deleted=deleted,
        file_id=row.id,
    )


def _registry_values(
    parsed: ParsedClassificationFile | ParsedEcctFile,
) -> dict[str, object]:
    """The `classification_files` columns for either kind of parsed document.

    An ECCT has no covered-law range, no prepared date and no Stat. volume — the
    columns are NULL for it rather than absent, because one registry table holds
    both kinds. `skipped_lines` is a count here and the lines themselves in the
    verification artifact: the column is an `Integer`.
    """
    common: dict[str, object] = {
        "kind": parsed.kind,
        "congress": parsed.congress,
        "session": parsed.session,
        "source_url": parsed.source_url,
        "source_filename": parsed.source_filename,
        "content_hash": parsed.content_hash,
        "row_count": parsed.row_count,
    }
    if isinstance(parsed, ParsedEcctFile):
        return {
            **common,
            "covered_laws_text": None,
            "covered_ranges": [],
            "first_law": None,
            "last_law": None,
            "prepared_date": None,
            "stat_volume": None,
            "skipped_lines": 0,
        }
    return {
        **common,
        "covered_laws_text": parsed.covered_laws_text,
        "covered_ranges": list(parsed.covered_ranges),
        "first_law": parsed.first_law,
        "last_law": parsed.last_law,
        "prepared_date": parsed.prepared_date,
        "stat_volume": parsed.stat_volume,
        "skipped_lines": len(parsed.skipped_lines),
    }


# ---------------------------------------------------------------------------------
# The backfill
# ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClassificationLoadReport:
    """What one `python -m ingest classification` run did."""

    links_seen: int
    results: tuple[FileLoadResult, ...]
    skipped: tuple[tuple[str, str], ...]
    """`(filename, why)` for a file the covered-law gate answered without
    fetching, and for a file `--from-file` had no copy of."""

    failures: tuple[tuple[str, str], ...]
    elapsed_seconds: float = 0.0

    @property
    def rows_written(self) -> int:
        return sum(result.rows_written for result in self.results)

    @property
    def loaded(self) -> int:
        return sum(1 for result in self.results if result.loaded)

    @property
    def unchanged(self) -> int:
        """Fetched, and its `<PRE>` text hashed the same — the second gate. Counted
        separately from `skipped`, which never asked for the file at all."""
        return sum(1 for result in self.results if not result.loaded)

    @property
    def sound(self) -> bool:
        return not self.failures


def run_classification_load(
    session_factory: Callable[[], Session],
    *,
    congress: int | None = None,
    session_num: int | None = None,
    force: bool = False,
    from_dir: Path | None = None,
    cache_dir: Path | None = CACHE_DIR,
    load: bool = True,
    verification_dir: Path | None = VERIFICATION_DIR,
    manifest_path: Path | None = MANIFEST_PATH,
    urls: Sequence[str] = (CLASSIFICATION_SOURCE_URL, PRIOR_CLASSIFICATION_SOURCE_URL),
    opener: Opener | None = None,
    on_event: Callable[[str], None] | None = None,
) -> ClassificationLoadReport:
    """Walk the two index pages, load every table that changed, write the artifacts.

    Resumable and hash-gated, in two stages. A closed congress's file is skipped
    without a request, because the index page's covered-law sentence already
    matches the registry (ADR-0067 decision 5) — which is what keeps a re-run at
    two requests rather than 33. A file that *is* fetched is still hash-gated:
    OLRC rewords that sentence without touching the table often enough that the
    `<PRE>` hash is the cheaper of the two answers to trust.

    `from_dir` reads both the index pages and the tables off disk instead, which
    is the offline path `make ci-data` takes. What is in that directory is what
    gets loaded: a linked file it does not hold is skipped and reported rather
    than failing the run, and a table it holds that neither index page links is
    loaded anyway, with its covered-law range read from its own header. The
    fixture directory is both at once — the slices link a dozen files and hold
    three, one of which the slices of the index pages do not mention.
    """
    started = time.monotonic()
    say = on_event or (lambda _message: None)

    links: list[TableLink] = []
    failures: list[tuple[str, str]] = []
    for url in urls:
        try:
            html = _index_html(url, from_dir=from_dir, cache_dir=cache_dir, opener=opener)
        except Exception as exc:
            failures.append((page_filename(url), f"{type(exc).__name__}: {exc}"))
            continue
        if html is None:
            say(f"skipped {page_filename(url)}: not in {from_dir}")
            continue
        links.extend(parse_tables_index(html))

    if from_dir is not None:
        links.extend(links_on_disk(from_dir, exclude={link.filename for link in links}))

    wanted = [
        link
        for link in links
        if (congress is None or link.congress == congress)
        and (session_num is None or link.session == session_num)
    ]
    say(f"{len(links)} documents linked, {len(wanted)} selected")

    registry = _registry_snapshot(session_factory) if load else {}
    results: list[FileLoadResult] = []
    skipped: list[tuple[str, str]] = []

    for link in wanted:
        known = registry.get((link.kind, link.congress, link.session))
        if not force and _can_skip_without_fetching(link, known):
            assert known is not None
            skipped.append((link.filename, "covered laws unchanged"))
            say(f"skipped {link.filename}: covered laws unchanged ({known.row_count} rows)")
            continue

        try:
            html = _document_html(link, from_dir=from_dir, cache_dir=cache_dir, opener=opener)
            if html is None:
                skipped.append((link.filename, f"not in {from_dir}"))
                say(f"skipped {link.filename}: not in {from_dir}")
                continue
            parsed = _parse_document(link, html)
        except Exception as exc:
            failures.append((link.filename, f"{type(exc).__name__}: {exc}"))
            say(f"FAILED {link.filename}: {type(exc).__name__}: {exc}")
            continue

        if load:
            with session_factory() as db:
                try:
                    result = load_file(db, parsed, force=force)
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    failures.append((link.filename, f"{type(exc).__name__}: {exc}"))
                    say(f"FAILED {link.filename}: {type(exc).__name__}: {exc}")
                    # The artifacts are written below, and a file that did not
                    # land in the database must not get one claiming it did.
                    continue
            results.append(result)
            say(
                f"{result.action} {link.filename}: {result.rows_written} rows written, "
                f"{result.rows_deleted} replaced"
            )
            if result.action == "unchanged":
                # The parse is the one the committed artifact already describes,
                # so rewriting it would move a timestamp and nothing else.
                continue
        else:
            say(f"parsed {link.filename}: {parsed.row_count} rows (not loaded)")

        if verification_dir is not None:
            write_verification(parsed, directory=verification_dir)
        if manifest_path is not None:
            write_classification_manifest(parsed, path=manifest_path)

    return ClassificationLoadReport(
        links_seen=len(links),
        results=tuple(results),
        skipped=tuple(skipped),
        failures=tuple(failures),
        elapsed_seconds=time.monotonic() - started,
    )


def links_on_disk(directory: Path, *, exclude: Iterable[str] = ()) -> list[TableLink]:
    """Every classification document in a directory, as links, by filename alone.

    The offline counterpart to `parse_tables_index`, and the reason `--from-file`
    does not need the index pages: a table's congress and session are in its name
    and its covered-law range is in its own header. An unsuffixed `ecct.html`
    found this way has no congress to belong to — the sentence that dates it is on
    the index page — so it gets 0/0, which is what the registry stores for "the
    source did not say".
    """
    skip = set(exclude)
    found: list[TableLink] = []
    for path in sorted(directory.iterdir()):
        if path.name in skip or not path.is_file():
            continue
        ecct = _ECCT_FILENAME_RE.match(path.name)
        if ecct is not None:
            found.append(
                TableLink(
                    kind="ecct",
                    congress=int(ecct.group("congress") or 0),
                    session=int(ecct.group("session") or 0),
                    filename=path.name,
                    url=CLASSIFICATION_BASE_URL + path.name,
                )
            )
            continue
        try:
            congress, session_num = _split_filename(path.name)
        except ClassificationParseError:
            continue
        found.append(
            TableLink(
                kind="pl",
                congress=congress,
                session=session_num,
                filename=path.name,
                url=CLASSIFICATION_BASE_URL + path.name,
            )
        )
    return found


def _index_html(
    url: str, *, from_dir: Path | None, cache_dir: Path | None, opener: Opener | None
) -> str | None:
    if from_dir is not None:
        return read_cached_page(from_dir, page_filename(url))
    return fetch_classification_page(url, cache_dir=cache_dir, opener=opener)


def _document_html(
    link: TableLink, *, from_dir: Path | None, cache_dir: Path | None, opener: Opener | None
) -> str | None:
    if from_dir is not None:
        return read_cached_page(from_dir, link.filename)
    return fetch_classification_page(link.url, cache_dir=cache_dir, opener=opener)


def _parse_document(
    link: TableLink, html: str
) -> ParsedClassificationFile | ParsedEcctFile:
    if link.kind == "ecct":
        return parse_ecct(
            html,
            filename=link.filename,
            source_url=link.url,
            congress=link.congress,
            session=link.session,
        )
    return parse_classification_file(
        html,
        filename=link.filename,
        source_url=link.url,
        # The index page's wording, not the file's own: it is what a poll
        # compares against, and the two are written independently.
        covered_laws_text=link.covered_laws_text or None,
    )


@dataclass(frozen=True, slots=True)
class _KnownFile:
    """One registry row as plain values — the two gates below read nothing else."""

    source_filename: str
    covered_laws_text: str | None
    content_hash: str
    row_count: int


def _registry_snapshot(
    session_factory: Callable[[], Session],
) -> dict[tuple[str, int, int], _KnownFile]:
    """The registry, keyed `(kind, congress, session)`.

    Read once, in its own short session, and detached: the loop above holds no
    transaction open across a network fetch.
    """
    with session_factory() as db:
        return {
            (row.kind, row.congress, row.session): _KnownFile(
                source_filename=row.source_filename,
                covered_laws_text=row.covered_laws_text,
                content_hash=row.content_hash,
                row_count=row.row_count,
            )
            for row in db.scalars(select(ClassificationFileRow))
        }


def _can_skip_without_fetching(link: TableLink, known: _KnownFile | None) -> bool:
    """Whether the index page still says about this file exactly what the registry
    holds — the gate that keeps a re-run at two requests rather than 33.

    Never true for an ECCT link, which carries no covered-law sentence for the
    index page to have changed. The ECCT is one small table; the backfill fetches
    it every run and lets the `<PRE>` hash decide.
    """
    if known is None or link.kind != "pl" or not link.covered_laws_text:
        return False
    return known.covered_laws_text == link.covered_laws_text


def _index_reports_change(link: TableLink, known: _KnownFile | None) -> bool:
    """Whether the index page says something about this document that the registry
    does not — the question the poll answers, in one request.

    A document the registry has never seen is a change. For a `pl` file so is a
    reworded covered-law sentence, which is what OLRC writes when it classifies a
    new law (ADR-0067 decision 5). An ECCT already in the registry is *not*: the
    page carries nothing about it that could have changed, so its content is only
    ever compared during a load.
    """
    if known is None:
        return True
    return link.kind == "pl" and known.covered_laws_text != link.covered_laws_text


# ---------------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------------


def write_verification(
    parsed: ParsedClassificationFile | ParsedEcctFile,
    *,
    directory: Path = VERIFICATION_DIR,
) -> Path:
    """One committed artifact per source document (PLAN §11.5).

    What the parse found, and nothing it found *in* the table: no entry rows, so
    the file stays a few kilobytes and a diff between two runs is a diff between
    two parses. `skipped_lines` is the lines themselves here, which is the only
    place they survive — the column on `classification_files` is a count.
    """
    directory.mkdir(parents=True, exist_ok=True)
    if isinstance(parsed, ParsedEcctFile):
        name = f"classification-ecct-{parsed.congress}-{parsed.session}.json"
        document: dict[str, object] = {
            "kind": "ecct",
            "congress": parsed.congress,
            "session": parsed.session,
            "source_filename": parsed.source_filename,
            "source_url": parsed.source_url,
            "content_hash": parsed.content_hash,
            "rows_parsed": parsed.row_count,
            "warnings": list(parsed.warnings),
        }
    else:
        name = f"classification-{parsed.congress}-{parsed.session}.json"
        document = {
            "kind": "pl",
            "source_url": parsed.source_url,
            "content_hash": parsed.content_hash,
            "column_offsets": list(parsed.column_offsets),
            "prepared_date": (
                parsed.prepared_date.isoformat() if parsed.prepared_date else None
            ),
            "stat_volume": parsed.stat_volume,
            "covered_laws_text": parsed.covered_laws_text,
            **parsed.report().as_json(),
            "skipped_line_text": list(parsed.skipped_lines),
        }
    document["generated_at"] = datetime.now(timezone.utc).isoformat()
    path = directory / name
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return path


def write_classification_manifest(
    parsed: ParsedClassificationFile | ParsedEcctFile,
    *,
    path: Path = MANIFEST_PATH,
) -> Path:
    """One provenance manifest for the whole scrape (documentation duty 4).

    Keyed by source filename and merged in place, the way `write_manifest` merges
    a title into a release's manifest: loading one congress still leaves one file
    describing everything loaded so far.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}
    if path.exists():
        manifest = json.loads(path.read_text())
    manifest["source_url"] = CLASSIFICATION_SOURCE_URL
    manifest["prior_source_url"] = PRIOR_CLASSIFICATION_SOURCE_URL
    files = manifest.setdefault("files", {})

    entry: dict[str, object] = {
        "kind": parsed.kind,
        "congress": parsed.congress,
        "session": parsed.session,
        "source_url": parsed.source_url,
        "content_hash": parsed.content_hash,
        "row_count": parsed.row_count,
        "warnings": len(parsed.warnings),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    if isinstance(parsed, ParsedClassificationFile):
        report = parsed.report()
        entry.update(
            covered_laws_text=parsed.covered_laws_text,
            covered_ranges=list(parsed.covered_ranges),
            prepared_date=(
                parsed.prepared_date.isoformat() if parsed.prepared_date else None
            ),
            stat_volume=parsed.stat_volume,
            skipped_lines=len(parsed.skipped_lines),
            rows_without_pl=report.rows_without_pl,
            rows_without_identifier=report.rows_without_identifier,
            distinct_titles=len(report.distinct_titles),
        )
    files[parsed.source_filename] = entry

    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


# ---------------------------------------------------------------------------------
# The poll
# ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClassificationCheckResult:
    """What one poll of `tables.shtml` found. Mirrors the check row it writes."""

    ok: bool
    links: tuple[TableLink, ...]
    changed_files: tuple[str, ...]
    """Source filenames the registry does not hold, or holds with different
    covered-law text. The answer to "is there anything to load"."""

    latest_covered_text: str | None = None
    error: str | None = None

    @property
    def has_changes(self) -> bool:
        return bool(self.changed_files)


def record_classification_check(
    session: Session,
    *,
    source_url: str,
    ok: bool,
    files_seen: int | None = None,
    changed_files: Sequence[str] = (),
    latest_covered_text: str | None = None,
    error: str | None = None,
) -> ClassificationSourceCheck:
    """Write one `classification_source_checks` row. On success *and* on failure.

    The failure case is the one that matters, for ADR-0036's reason: a scraper
    that stopped running looks exactly like a source with nothing new, and only
    the record of the attempt tells them apart. `files_seen` stays NULL on a
    failure rather than becoming 0 — the page never parsed, so nothing was seen.
    """
    row = ClassificationSourceCheck(
        source_url=source_url,
        ok=ok,
        files_seen=files_seen,
        changed_files=list(changed_files),
        latest_covered_text=latest_covered_text,
        # Truncated for `SourceCheck`'s reason: an error here is a one-line
        # diagnosis, and an HTML error page would push a status response into
        # the kilobytes.
        error=(error[:500] if error else None),
    )
    session.add(row)
    return row


def poll_classification(
    session: Session,
    *,
    url: str = CLASSIFICATION_SOURCE_URL,
    cache_dir: Path | None = CACHE_DIR,
    opener: Opener | None = None,
) -> ClassificationCheckResult:
    """Ask `tables.shtml` whether anything changed, and record the asking.

    One request and one check row per call, whatever happens. Commits nothing —
    the caller owns the transaction.

    Only the current congress's page is polled: a closed congress does not gain
    laws, so `priortables.shtml` is a backfill concern. A file this database
    holds that the page no longer lists fails the check rather than deleting
    anything, the same refusal `poll_source` makes for a vanished release point:
    a document never leaves OLRC's index, so its absence means a truncated
    response or changed markup, and neither is news. The comparison is scoped to
    the congresses the fetched page covers, since this page is not where the
    other thirty files are listed.
    """
    try:
        html = fetch_classification_page(url, cache_dir=cache_dir, opener=opener)
        links = parse_tables_index(html)
    except Exception as exc:  # network, HTTP, or ClassificationParseError
        error = f"{type(exc).__name__}: {exc}"
        record_classification_check(session, source_url=url, ok=False, error=error)
        return ClassificationCheckResult(ok=False, links=(), changed_files=(), error=error)

    registry = {
        (row.kind, row.congress, row.session): _KnownFile(
            source_filename=row.source_filename,
            covered_laws_text=row.covered_laws_text,
            content_hash=row.content_hash,
            row_count=row.row_count,
        )
        for row in session.scalars(select(ClassificationFileRow))
    }
    congresses = {link.congress for link in links}
    seen = {(link.kind, link.congress, link.session) for link in links}
    vanished = sorted(
        known.source_filename
        for (kind, congress, session_num), known in registry.items()
        if congress in congresses and (kind, congress, session_num) not in seen
    )
    if vanished:
        error = (
            f"{len(vanished)} document(s) this database holds are missing from "
            f"{page_filename(url)} ({', '.join(vanished[:5])}"
            f"{', …' if len(vanished) > 5 else ''}) — refusing to treat a page "
            "that looks truncated as news"
        )
        record_classification_check(session, source_url=url, ok=False, error=error)
        return ClassificationCheckResult(ok=False, links=(), changed_files=(), error=error)

    changed = tuple(
        link.filename
        for link in links
        if _index_reports_change(link, registry.get((link.kind, link.congress, link.session)))
    )
    latest = _latest_covered_text(links)
    record_classification_check(
        session,
        source_url=url,
        ok=True,
        files_seen=len(links),
        changed_files=changed,
        latest_covered_text=latest,
    )
    return ClassificationCheckResult(
        ok=True, links=tuple(links), changed_files=changed, latest_covered_text=latest
    )


def _latest_covered_text(links: Sequence[TableLink]) -> str | None:
    """The covered-law sentence of the newest `pl` file on the page — the string
    the next poll compares against, kept on the check row so a change is visible
    in the record even after the load that answered it."""
    pl_links = [link for link in links if link.kind == "pl" and link.covered_laws_text]
    if not pl_links:
        return None
    return max(pl_links, key=lambda link: (link.congress, link.session)).covered_laws_text


def _clean_text(raw: str) -> str:
    return " ".join(htmllib.unescape(_TAG_RE.sub("", raw)).replace("\xa0", " ").split())


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)  # type: ignore[arg-type]


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)
