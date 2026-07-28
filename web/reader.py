"""The reader: repository results → HTML pages (PLAN Day 1 item 5).

Server-rendered Jinja, no build step, no client framework — the pages are
documents, and a document that needs JavaScript to be read is a worse document.
The one script in the whole reader scrolls a highlighted provision into view.

Like `api/`, this layer talks only to the `Repository` (CLAUDE.md architecture
rule 1): it takes the frozen dataclasses `storage` returns, asks the repository
for the two extra things a page needs that a section result doesn't carry —
neighbours, and the release points this title exists at — and knows nothing about
tables, sessions or SQL.

Three things the reader must never quietly drop, because each is a fact the data
has and a naive UI loses:

  * the **caveat** on a `not` release point (gotcha 5) — `119-102not101` is *not*
    fully current through its date;
  * the **served-from note** when the requested release point was never ingested
    (gotcha 10) — the answer is right, but it came from a different release point
    and the page has to say so;
  * **status badges** — repealed, omitted and transferred sections keep their
    place in reading order (gotcha 9), so they appear in TOCs and in prev/next,
    labelled rather than hidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlencode

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from storage import (
    Repository,
    ResolvedRelease,
    SectionResult,
    TocEntry,
    TocResult,
    title_num_from_identifier,
)
from web.uslm_html import render_fragment

TEMPLATES = Path(__file__).parent / "templates"
STATIC = Path(__file__).parent / "static"

# Where the reader is mounted (ADR-0010). Every href the reader emits goes through
# `app_href` rather than being concatenated at the call site, so this prefix is
# stated once and the reader can move without a search-and-replace across five
# templates.
APP = "/app"
API = "/api/v1"


def app_href(identifier: str, at: str = "") -> str:
    """The reader's URL for an identifier. The one place `/app` is spelled out."""
    return f"{APP}{quote(identifier)}{at}"


def api_href(identifier: str, query: dict[str, str]) -> str:
    """The machine view of the same thing, on the other surface (ADR-0010)."""
    return f"{API}{quote(identifier)}?{urlencode(query)}"

_env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(frozen=True, slots=True)
class Crumb:
    href: str
    label: str


def render_home(repository: Repository) -> str:
    titles = [
        {
            "num": title.num,
            "name": title.name,
            "href": app_href(f"/us/usc/t{title.num}"),
            "releases": _count(len(title.ingested_releases), "release point"),
        }
        for title in repository.list_titles()
    ]
    return _env.get_template("home.html").render(
        page_title="U.S. Code — versioned retrieval",
        crumbs=[],
        picker=None,
        titles=titles,
    )


def render_section(
    repository: Repository,
    section: SectionResult,
    resolved: ResolvedRelease,
    *,
    requested_identifier: str,
    note: str | None = None,
) -> str:
    """One section, with the provision the URL named highlighted inside it."""
    at = _release_query(resolved)
    remainder = requested_identifier[len(section.identifier) :]
    neighbors = repository.neighbors(section.identifier, resolved)

    return _env.get_template("section.html").render(
        page_title=_page_title(
            f"{section.num or ''} {section.heading or section.identifier}",
            section.served_from.label,
        ),
        crumbs=_section_crumbs(repository, section, resolved, at),
        picker=_picker(repository, section.identifier, section.title_num, section.served_from.label),
        section={
            "identifier": section.identifier,
            "num": _trim(section.num),
            "heading": section.heading,
            "status": section.status,
            "guid": section.guid,
            "href": app_href(section.identifier, at),
        },
        served=_release_view(section.served_from),
        caveat=section.served_from.caveat,
        note=note,
        provision=(
            {
                "label": _provision_label(remainder),
                "found": bool(section.provision and section.provision.found),
            }
            if remainder
            else None
        ),
        body=render_fragment(
            section.xml,
            target_identifier=(
                requested_identifier if requested_identifier != section.identifier else None
            ),
        ),
        neighbors=(
            {
                "previous": _entry_view(neighbors.previous, at),
                "next": _entry_view(neighbors.next, at),
            }
            if neighbors
            else None
        ),
        formats={
            "xml": _with_format(requested_identifier, resolved, "xml"),
            "json": _with_format(requested_identifier, resolved, "json"),
            "versions": f"{API}/sections{quote(section.identifier)}/versions",
        },
    )


def render_toc(
    repository: Repository,
    toc: TocResult,
    resolved: ResolvedRelease,
    *,
    note: str | None = None,
) -> str:
    at = _release_query(resolved)
    title_num = title_num_from_identifier(toc.node.identifier)
    children = [_entry_view(child, at) for child in toc.children]

    return _env.get_template("toc.html").render(
        page_title=_page_title(
            f"{_trim(toc.node.num) or ''} {toc.node.heading or toc.node.identifier}",
            toc.served_from.label,
        ),
        crumbs=[_crumb(entry, at) for entry in toc.ancestors],
        picker=_picker(repository, toc.node.identifier, title_num, toc.served_from.label),
        node={
            "identifier": toc.node.identifier,
            "num": _trim(toc.node.num),
            "heading": toc.node.heading,
            "status": toc.node.status,
        },
        served=_release_view(toc.served_from),
        caveat=toc.served_from.caveat,
        note=note,
        children=children,
        children_label=_children_label(toc.children),
        sections=[_entry_view(entry, at) for entry in toc.sections],
    )


def render_error(status: int, detail: str, candidates: list[str] | None = None) -> str:
    headline = {
        404: "not found",
        409: "which release point?",
        422: "that request doesn't parse",
    }.get(status, "something went wrong")
    return _env.get_template("error.html").render(
        page_title=f"{status} — {headline}",
        crumbs=[],
        picker=None,
        status=status,
        headline=headline,
        detail=detail,
        candidates=candidates or [],
    )


# ------------------------------------------------------------------- internals


def _release_query(resolved: ResolvedRelease) -> str:
    """Carry the release point across every link on the page.

    Always as `?release=`, even when the request arrived as `?date=`: the date
    has already been resolved to one release point, and repeating the label keeps
    every link on the page unambiguous and pasteable.
    """
    return "?" + urlencode({"release": resolved.release.label})


def _with_format(identifier: str, resolved: ResolvedRelease, wanted: str) -> str:
    """The machine views of this page live on the other surface (ADR-0010), so
    "see the XML" is a link to `/api/v1`, not to this URL with a parameter."""
    return api_href(identifier, {"release": resolved.release.label, "format": wanted})


def _picker(
    repository: Repository,
    identifier: str,
    title_num: str | None,
    selected: str,
) -> dict | None:
    """The release picker offers the release points this title is *ingested* at.

    Offering all 382 would be offering 380 empty answers: `titles_affected` says
    where a title changed, `ingested_titles` says where we hold it, and only the
    second is something the reader can show today (PLAN §5 — the backfill is
    Session 6).
    """
    if title_num is None:
        return None
    options = [
        {"label": release.label, "date": f"{release.currency_date:%m/%d/%Y}"}
        for release in repository.list_releases()
        if title_num in release.ingested_titles
    ]
    if not options:
        return None
    if all(option["label"] != selected for option in options):  # pragma: no cover
        options.insert(0, {"label": selected, "date": ""})
    return {"action": app_href(identifier), "options": options, "selected": selected}


def _section_crumbs(
    repository: Repository,
    section: SectionResult,
    resolved: ResolvedRelease,
    at: str,
) -> list[Crumb]:
    """Breadcrumbs for a section: its parent node's own breadcrumbs, plus itself.

    The parent chain isn't on `SectionResult` — `section_release_map` carries only
    the immediate parent (ADR-0008) — so the reader asks the repository for the
    parent's table of contents and reuses its ancestors.
    """
    if section.parent_identifier is None:
        return []
    parent = repository.get_toc(section.parent_identifier, resolved)
    if parent is None:  # pragma: no cover - a parent that isn't a structure node
        return []
    return [_crumb(entry, at) for entry in (*parent.ancestors, parent.node)]


def _crumb(entry: TocEntry, at: str) -> Crumb:
    return Crumb(
        href=app_href(entry.identifier, at),
        label=_trim(entry.num) or entry.identifier,
    )


def _entry_view(entry: TocEntry | None, at: str) -> dict | None:
    if entry is None:
        return None
    return {
        "identifier": entry.identifier,
        "href": app_href(entry.identifier, at),
        "num": _trim(entry.num),
        "heading": entry.heading,
        "status": entry.status,
    }


def _release_view(release) -> dict:
    return {"label": release.label, "date": f"{release.currency_date:%m/%d/%Y}"}


def _children_label(children: tuple[TocEntry, ...]) -> str:
    """Name the subdivisions after what they actually are — Title 16 lists
    chapters, a chapter lists subchapters, and USLM 2.x titles have subtitles."""
    levels = {child.level for child in children}
    if len(levels) == 1:
        return f"{levels.pop().capitalize()}s"
    return "Subdivisions"


def _provision_label(remainder: str) -> str:
    """`/c/5` → `(c)(5)` — how a lawyer would write the thing the URL asked for."""
    return "".join(f"({part})" for part in remainder.strip("/").split("/") if part)


def _trim(num: str | None) -> str | None:
    """USLM `<num>` text carries its separator: `CHAPTER 1—`, `§ 45f.`"""
    return num.rstrip("—-–— .") if num else num


def _page_title(heading: str, release_label: str) -> str:
    return f"{' '.join(heading.split())} · {release_label} · U.S. Code"


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def section_url(identifier: str, release_label: str) -> str:
    """The reader URL for a provision at a release point — the form `?id=` lookups
    and watchlists (Day 5) should link to."""
    return app_href(identifier, "?" + urlencode({"release": release_label}))
