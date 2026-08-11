"""The OLRC Classification Tables: which provision of which Public Law landed where.

`118-35 §101(3) → 18 U.S.C. 3551 note` is one row of one table. OLRC publishes one
table per congress-session in two sorts — Public Law order (`tbl118pl_2nd.htm`) and
US Code order (`tbl118cd_2nd.htm`) — carrying the same rows; only the `pl` files are
scraped here, because Code order is a sort in our own display. Alongside them sits
the Editorial Classification Change Table (`ecct.html`), which records where OLRC
moved *earlier* laws while classifying the new ones.

This module is the parse side: HTML in, dataclasses out, no database and no network.
`docs/classification-spec.md` is the specification and
`docs/adr/0067-classification-tables.md` records the decisions.

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

Politeness, the disk cache, the loader and the poll are C2b's; nothing here touches
the network, so every test in the suite runs offline.
"""

from __future__ import annotations

import hashlib
import html as htmllib
import re
import warnings
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

CLASSIFICATION_BASE_URL = "https://uscode.house.gov/classification/"
CLASSIFICATION_SOURCE_URL = CLASSIFICATION_BASE_URL + "tables.shtml"
"""The current congress's entry page, and the home of the change-detection key.

Spec §4 gives this constant to `storage/classification.py`, so `/api/v1` can name
the source without importing the ingest layer — the `SOURCE_URL` precedent in
`storage/repository.py`. That module is phase C3 and does not exist yet, so the
value lives here until it does, and is re-imported from storage afterwards."""

PRIOR_CLASSIFICATION_SOURCE_URL = CLASSIFICATION_BASE_URL + "priortables.shtml"
"""The 104th–118th entry page. Read by the backfill; the daily poll reads only
`CLASSIFICATION_SOURCE_URL`, since closed congresses do not gain laws."""

# --- entry pages -----------------------------------------------------------------

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_TABLE_HREF_RE = re.compile(
    r'href="(?P<href>[^"]*?(?P<filename>tbl(?P<congress>\d+)'
    r"(?P<order>pl|cd)(?:_(?P<session>1st|2nd))?"
    r'\.(?P<ext>htm|pdf)))"',
    re.IGNORECASE,
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
_PL_CELL_RE = re.compile(r"^(?P<congress>\d{2,3})-(?P<num>\d{1,4})$")
_PL_OVERFLOW_RE = re.compile(r"^(?P<description>.*?)(?P<pl>\d{2,3}-\d{1,4})\s*$")
_STAT_CELL_RE = re.compile(r"^[\d,\s\-]*$")
_STAT_OVERFLOW_RE = re.compile(r"^(?P<section>.*?)\s+(?P<stat>\d[\d,\s\-]*)$")
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


def law_in_ranges(law_num: int, ranges: Iterable[str]) -> bool:
    """Whether a law number falls inside any `'70-70'`-style covered segment."""
    return any(
        int(segment.split("-")[0]) <= law_num <= int(segment.split("-")[1])
        for segment in ranges
    )


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
    offsets = column_offsets(header_line, filename=filename)
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
        visible = _visible(raw_line)
        if not visible.strip():
            continue
        if not _DATA_LINE_RE.match(visible):
            # Not a row and not blank: a footnote, a repeated header on a page
            # break, or a format this parser has not seen. Counted and shown in the
            # verification artifact rather than discarded silently.
            skipped.append(visible)
            collector.warn(f"{filename}: line does not start with a title number: {visible!r}")
            continue
        entries.append(
            _parse_row(
                raw_line,
                visible,
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
    """
    if is_appendix:
        return None
    if not _SECTION_IDENTIFIER_RE.match(section_norm):
        return None
    return f"/us/usc/t{title_num}/s{section_norm}"


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


def _parse_row(
    raw_line: str,
    visible: str,
    *,
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

    if not _STAT_CELL_RE.match(stat_raw):
        # The Sec. cell overran instead: `1649(a) "Subchapter III"` is 24 characters
        # in a 22-character column.
        combined = visible[offsets[4] :].strip()
        overflow = _STAT_OVERFLOW_RE.match(combined)
        if overflow is not None:
            section_of_law = overflow.group("section").strip()
            stat_raw = overflow.group("stat").strip()
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
    section_norm = normalize_section(section_raw)
    is_note, action, counterpart, act_name = parse_description(description_raw)

    return ClassificationEntry(
        row_seq=row_seq,
        raw_line=visible,
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
    that, and a table that quietly loses its rows is worse than no table.

    Zero data rows is valid: the current table has one. Zero *header* cells is not —
    that means the four columns this reads by position are no longer there.
    """
    rows = list(_ECCT_ROW_RE.finditer(html))
    headers = 0
    entries: list[EcctEntry] = []
    collector = _Collector()

    for row in rows:
        cells = list(_ECCT_CELL_RE.finditer(row.group("cells")))
        if not cells:
            continue
        if all(cell.group("tag").lower() == "th" for cell in cells):
            headers += len(cells)
            continue
        values = [_clean_text(cell.group("body")) for cell in cells]
        if len(values) < 4:
            collector.warn(f"{filename}: row {len(entries)} has {len(values)} cells, not 4")
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


def _clean_text(raw: str) -> str:
    return " ".join(htmllib.unescape(_TAG_RE.sub("", raw)).replace("\xa0", " ").split())


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)  # type: ignore[arg-type]


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)
