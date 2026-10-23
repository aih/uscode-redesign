"""Every markup uscode.house.gov has served for the pages this project reads.

OLRC changes its pages without notice: on 2026-10-12 it relaunched the site at new
addresses with a new prior-release-points layout (ADR-0091), by 2026-10-22 its
classification tables linked Stat. pages a third way (ADR-0093), and by 2026-10-23
the prior page and the download page had changed again (ADR-0094). A parser that
assumes one markup reads the next one as an empty page.

So each page a poll reads is first matched against this registry, and the format
it matches decides which parser runs. One format per markup the source has
served, kept after OLRC retires it: the registry is the history, the parsers in
`ingest.inventory` and `ingest.classification` are keyed by its ids, and
`docs/source-formats.md` is the same history as prose.

A signature is a structural test, cheap and specific, and never a parse. Exactly
one format of a page kind matches a page or none does: two matches is a defect
in the registry, which `tests/test_source_formats.py` checks against a fixture of
every format. No match means OLRC has changed the page again, and the error names
the formats that were tried.

This module knows markup and nothing else: no network, no database, and no
import from the modules that parse what it detects.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

PRIOR_RELEASE_POINTS = "prior-release-points"
"""The page listing superseded release points."""
CURRENT_RELEASE_POINT = "current-release-point"
"""The download page, which carries the current release point."""
CLASSIFICATION_INDEX = "classification-index"
"""`tables.html` and `priortables.html`: the links to every classification table."""
CLASSIFICATION_TABLE = "classification-table"
"""One Public Law order table, `tbl{congress}pl[_{session}].html`."""
CLASSIFICATION_ECCT = "classification-ecct"
"""The Editorial Classification Change Table."""

PAGE_KINDS = (
    PRIOR_RELEASE_POINTS,
    CURRENT_RELEASE_POINT,
    CLASSIFICATION_INDEX,
    CLASSIFICATION_TABLE,
    CLASSIFICATION_ECCT,
)


@dataclass(frozen=True, slots=True)
class SourceFormat:
    """One markup one page has been served in."""

    id: str
    """`prior-release-points/li-label-html`: the page kind, a slash, a short name.
    Recorded on every check row, so it is never renamed."""

    page: str
    """One of `PAGE_KINDS`."""

    urls: tuple[str, ...]
    """The addresses it was served at, relative to `https://uscode.house.gov/`."""

    first_seen: date
    """The earliest day a capture of this markup is on record. OLRC may have served
    it earlier."""

    last_seen: date | None
    """The latest day a capture of this markup is on record; `None` while it is
    the markup the source serves now."""

    fixture: str
    """The committed capture under `tests/fixtures/` that the signature is tested
    against."""

    adr: str
    summary: str
    signature: Callable[[str], bool]

    @property
    def retired(self) -> bool:
        return self.last_seen is not None


class UnrecognisedSourceFormat(ValueError):
    """No registered format matches the page, or more than one does."""

    def __init__(self, page: str, url: str, message: str) -> None:
        self.page = page
        self.url = url
        super().__init__(message)


_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_LI_ENTRY_RE = re.compile(r'<li class="releasepoint">\s*<a class="releasepoint" href="([^"]+)"')
_USC_RP_HREF_RE = re.compile(r"releasepoints/us/pl/\d+/[^/\"]+/usc-rp@[^\"]+\.htm$")
_LABEL_HTML_HREF_RE = re.compile(r"^(?:download/)?\d+-[0-9a-z]+\.html$")
_RP_HEADING_RE = re.compile(r'<h3 class="releasepointinformation">(?P<text>.*?)</h3>', re.DOTALL)
_DATED_RE = re.compile(r"\(\s*\d{1,2}/\d{1,2}/\d{4}\s*\)")
_ZIP_HREF_RE = re.compile(r'href="(?P<prefix>(?:download/)?)releasepoints/us/pl/\d+/[^/"]+/xml_usc')
_TABLE_LINK_RE = re.compile(r'href="[^"]*tbl\d+(?:pl|cd)(?:_(?:1st|2nd))?\.(?P<ext>html?)"', re.IGNORECASE)
_PRE_RE = re.compile(r"<pre\b", re.IGNORECASE)
_TABLE_BODY_RE = re.compile(r'<tbody\s+id="classificationTableBody"\s*>\s*</tbody>', re.IGNORECASE)
_CT_RECORDS_RE = re.compile(r"\bvar\s+ctRecords\s*=\s*\[")
_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.DOTALL | re.IGNORECASE)
_ECCT_RE = re.compile(r"<th\b[^>]*>\s*Former Classification\s*</th>", re.IGNORECASE)


def _li_hrefs(html: str) -> list[str]:
    # Comments are kept: the pre-2026 page lists the current release point inside
    # one, and a page whose only entry is commented out is still that markup.
    return _LI_ENTRY_RE.findall(html)


def _li_usc_rp(html: str) -> bool:
    hrefs = _li_hrefs(html)
    return bool(hrefs) and all(_USC_RP_HREF_RE.search(href) for href in hrefs)


def _li_label_html(html: str) -> bool:
    hrefs = _li_hrefs(_COMMENT_RE.sub("", html))
    return bool(hrefs) and all(_LABEL_HTML_HREF_RE.match(href) for href in hrefs)


def _headings(html: str) -> list[str]:
    return [match.group("text") for match in _RP_HEADING_RE.finditer(_COMMENT_RE.sub("", html))]


def _rp_sections(html: str) -> bool:
    return bool(_headings(html)) and not _li_hrefs(html)


def _zip_prefixes(html: str) -> set[str]:
    return {match.group("prefix") for match in _ZIP_HREF_RE.finditer(_COMMENT_RE.sub("", html))}


def _current_dated(prefix: str) -> Callable[[str], bool]:
    def signature(html: str) -> bool:
        headings = _headings(html)
        return (
            len(headings) == 1
            and bool(_DATED_RE.search(headings[0]))
            and _zip_prefixes(html) == {prefix}
        )

    return signature


def _current_undated(html: str) -> bool:
    headings = _headings(html)
    return (
        len(headings) == 1
        and not _DATED_RE.search(headings[0])
        and _zip_prefixes(html) == {"download/"}
    )


def _index_with(ext: str) -> Callable[[str], bool]:
    def signature(html: str) -> bool:
        exts = {match.group("ext").lower() for match in _TABLE_LINK_RE.finditer(html)}
        return exts == {ext}

    return signature


def _table_pre(html: str) -> bool:
    return bool(_PRE_RE.search(html))


def _has_records(html: str) -> bool:
    # Inside a script, where the page keeps them; the array sits behind a `<!--`
    # there, so comments are not stripped first.
    return any(_CT_RECORDS_RE.search(script.group()) for script in _SCRIPT_RE.finditer(html))


def _table_viewer_empty(html: str) -> bool:
    return (
        not _PRE_RE.search(html)
        and bool(_TABLE_BODY_RE.search(html))
        and not _has_records(html)
    )


def _table_viewer_records(html: str) -> bool:
    return not _PRE_RE.search(html) and _has_records(html)


def _ecct_table(html: str) -> bool:
    return bool(_ECCT_RE.search(html))


REGISTRY: tuple[SourceFormat, ...] = (
    SourceFormat(
        id="prior-release-points/li-usc-rp-htm",
        page=PRIOR_RELEASE_POINTS,
        urls=("download/priorreleasepoints.htm",),
        first_seen=date(2026, 7, 27),
        last_seen=date(2026, 10, 11),
        fixture="priorreleasepoints_slice.htm",
        adr="ADR-0087",
        summary=(
            "One `<li class=\"releasepoint\">` per release point back to 2013, newest "
            "first. The label is in the href (`releasepoints/us/pl/119/99/usc-rp@119-99.htm`); "
            "the date (`06/12/2026`) and the changed titles are in the link text. The "
            "current release point is a commented-out `<li>`."
        ),
        signature=_li_usc_rp,
    ),
    SourceFormat(
        id="prior-release-points/rp-sections",
        page=PRIOR_RELEASE_POINTS,
        urls=("priorreleasepoints.html",),
        first_seen=date(2026, 10, 12),
        last_seen=date(2026, 10, 12),
        fixture="priorreleasepoints_relaunch_slice.html",
        adr="ADR-0091",
        summary=(
            "One section per release point, headed `<h3 class=\"releasepointinformation\">"
            "Public Law 119-118 (09/30/2026)</h3>` and laid out like the download page, one "
            "row of zip links per title. The label is in the zip links; changed titles are "
            "not marked. Lists a window of recent release points (one, on 2026-10-12)."
        ),
        signature=_rp_sections,
    ),
    SourceFormat(
        id="prior-release-points/li-label-html",
        page=PRIOR_RELEASE_POINTS,
        urls=("priorreleasepoints.html",),
        first_seen=date(2026, 10, 23),
        last_seen=None,
        fixture="priorreleasepoints_li_label.html",
        adr="ADR-0094",
        summary=(
            "One `<li class=\"releasepoint\">` per release point again, newest first, "
            "back to 119-73not60 (January 23, 2026). The href is the release point's own "
            "page, `download/119-121.html`, so the label is its basename; the link text "
            "spells the date out (`October 9, 2026`) and lists the changed titles."
        ),
        signature=_li_label_html,
    ),
    SourceFormat(
        id="current-release-point/dated-releasepoints-href",
        page=CURRENT_RELEASE_POINT,
        urls=("download/download.shtml",),
        first_seen=date(2026, 9, 18),
        last_seen=date(2026, 10, 11),
        fixture="download_current_slice.htm",
        adr="ADR-0087",
        summary=(
            "Heading `Public Law 119-108 (09/11/2026)`; zip links relative to `download/` "
            "(`releasepoints/us/pl/119/108/xml_usc26@119-108.zip`); a changed title's row "
            "is `<div class=\"usctitlechanged\" id=\"us/usc/t26\">`."
        ),
        signature=_current_dated(""),
    ),
    SourceFormat(
        id="current-release-point/dated-download-href",
        page=CURRENT_RELEASE_POINT,
        urls=("download.html",),
        first_seen=date(2026, 10, 12),
        last_seen=date(2026, 10, 12),
        fixture="download_relaunch_slice.html",
        adr="ADR-0091",
        summary=(
            "As before, at the site root: zip links begin `download/releasepoints/`, the "
            "heading still carries the date and a changed row still carries its title in "
            "`id`."
        ),
        signature=_current_dated("download/"),
    ),
    SourceFormat(
        id="current-release-point/undated-heading",
        page=CURRENT_RELEASE_POINT,
        urls=("download.html",),
        first_seen=date(2026, 10, 23),
        last_seen=None,
        fixture="download_undated.html",
        adr="ADR-0094",
        summary=(
            "Heading `Public Law 119-124` with no date; the date is in the description, "
            "spelled out (`current through Public Law 119-124 (October 15, 2026)`). A "
            "changed row is `<div class=\"usctitlechanged\">16 - Conservation</div>` with "
            "no `id`, so its title comes from the zip links in the same row."
        ),
        signature=_current_undated,
    ),
    SourceFormat(
        id="classification-index/htm-links",
        page=CLASSIFICATION_INDEX,
        urls=("classification/tables.shtml", "classification/priortables.shtml"),
        first_seen=date(2026, 8, 11),
        last_seen=date(2026, 10, 11),
        fixture="tables_slice.shtml",
        adr="ADR-0067",
        summary="One cell per congress-session; table links end `.htm`.",
        signature=_index_with("htm"),
    ),
    SourceFormat(
        id="classification-index/html-links",
        page=CLASSIFICATION_INDEX,
        urls=("classification/tables.html", "classification/priortables.html"),
        first_seen=date(2026, 10, 13),
        last_seen=None,
        fixture="tables_relaunch.html",
        adr="ADR-0093",
        summary="The same cells; table links end `.html` and the covered-law sentence holds a `<br />`.",
        signature=_index_with("html"),
    ),
    SourceFormat(
        id="classification-table/pre-text",
        page=CLASSIFICATION_TABLE,
        urls=("classification/tbl{congress}pl_{session}.htm", "classification/tbl{congress}pl_{session}.html"),
        first_seen=date(2026, 8, 11),
        last_seen=None,
        fixture="tbl118pl_2nd_slice.htm",
        adr="ADR-0067",
        summary=(
            "Fixed-width text inside `<pre>`: six columns whose offsets come from the "
            "header line. Stat. pages link `statviewer.htm` until 2026-10-11, "
            "`/images/stat/{v}/{p}.png` on 2026-10-13 and `statviewer.html` by 2026-10-22; "
            "the 104th and 110th carry no Stat. links."
        ),
        signature=_table_pre,
    ),
    SourceFormat(
        id="classification-table/viewer-empty",
        page=CLASSIFICATION_TABLE,
        urls=("classification/tbl{congress}pl_{session}.html",),
        first_seen=date(2026, 10, 13),
        last_seen=date(2026, 10, 13),
        fixture="tbl118pl_2nd_relaunch.html",
        adr="ADR-0093",
        summary=(
            "A table viewer with an empty `<tbody id=\"classificationTableBody\">`, no "
            "`<pre>` and no rows anywhere on the page."
        ),
        signature=_table_viewer_empty,
    ),
    SourceFormat(
        id="classification-table/viewer-records",
        page=CLASSIFICATION_TABLE,
        urls=("classification/tbl{congress}pl_{session}.html",),
        first_seen=date(2026, 10, 23),
        last_seen=None,
        fixture="tbl118pl_2nd_records_slice.html",
        adr="ADR-0094",
        summary=(
            "The same viewer, with the rows in a script as `var ctRecords = [{…}]`: one "
            "object per row, `usctitle`, `uscsection`, `uscdescription`, `publiclaw`, "
            "`publiclawsection`, `statutesatlargepage`, `statutesatlargevolume`, "
            "`dateofenactment` and five bookkeeping fields. The table body is filled by "
            "script. Served for the 117th's 2nd session and both of the 118th's."
        ),
        signature=_table_viewer_records,
    ),
    SourceFormat(
        id="classification-ecct/four-column-table",
        page=CLASSIFICATION_ECCT,
        urls=("classification/ecct.html", "classification/ECCT.html"),
        first_seen=date(2026, 8, 11),
        last_seen=None,
        fixture="ecct.html",
        adr="ADR-0067",
        summary=(
            "A four-column `<table>` headed Former Classification, New Classification, "
            "Provision Affected, Provision Prompting Change, with a `<div id=\"boxheads\">` "
            "opened inside it; unchanged by the relaunch apart from the site chrome."
        ),
        signature=_ecct_table,
    ),
)

_BY_ID = {source_format.id: source_format for source_format in REGISTRY}


def formats_for(page: str) -> tuple[SourceFormat, ...]:
    """The registered formats of one page kind, oldest first."""
    if page not in PAGE_KINDS:
        raise ValueError(f"not a page kind: {page!r}")
    return tuple(source_format for source_format in REGISTRY if source_format.page == page)


def get(format_id: str) -> SourceFormat:
    return _BY_ID[format_id]


def matching(page: str, html: str) -> tuple[SourceFormat, ...]:
    """Every registered format of `page` whose signature matches `html`."""
    return tuple(source_format for source_format in formats_for(page) if source_format.signature(html))


def detect(page: str, html: str, *, url: str = "") -> SourceFormat:
    """The one registered format of `page` that `html` is served in.

    Raises `UnrecognisedSourceFormat` when none matches — OLRC has changed the page
    and a new entry belongs in `REGISTRY` — or when more than one does. Callers
    check for the maintenance notice first, since a notice matches nothing.
    """
    found = matching(page, html)
    if len(found) == 1:
        return found[0]
    where = url or page
    if not found:
        tried = ", ".join(source_format.id for source_format in formats_for(page))
        raise UnrecognisedSourceFormat(
            page,
            url,
            f"{where} is in no known {page} format (tried {tried}) — the markup has "
            "probably changed; add its format to ingest/source_formats.py",
        )
    raise UnrecognisedSourceFormat(
        page,
        url,
        f"{where} matches more than one {page} format "
        f"({', '.join(source_format.id for source_format in found)})",
    )
