"""The routes of PLAN §4.

Two families, on purpose:

  * **`/us/usc/…`** mirrors the USLM `@identifier` exactly, so a citation is a URL
    and a URL is a citation. One handler serves it, because the identifier decides
    what the thing *is* — `/us/usc/t16/ch1` is a TOC node, `/us/usc/t16/s45f/c/5`
    is a provision inside a section — and a caller shouldn't have to know which
    before asking.
  * **`/api/v1/…`** for everything that is about a provision rather than being one:
    neighbours, version timeline, the release-point list.

No SQL and no version-resolution logic lives here (CLAUDE.md architecture rule 1);
handlers resolve a release point, ask the `Repository`, and shape the answer.
"""

from __future__ import annotations

from html import escape

from fastapi import APIRouter, HTTPException, Query, Request, Response

from api.deps import (
    DateParam,
    FormatParam,
    ReleaseParam,
    RepositoryDep,
    negotiated_format,
    normalize_identifier,
    parse_date_param,
    resolve_release_or_404,
)
from api.render import PAGE_CSS, render_page
from api.schemas import (
    ErrorOut,
    GuidOut,
    NeighborsOut,
    ReleaseOut,
    SectionOut,
    TitleOut,
    TocOut,
    VersionOut,
    VersionsOut,
)
from storage import (
    Repository,
    ResolvedRelease,
    SectionResult,
    TocResult,
    title_num_from_identifier,
)

router = APIRouter()
api = APIRouter(prefix="/api/v1", tags=["api"])


@api.get("/releases", response_model=list[ReleaseOut], summary="All release points")
def list_releases(
    repository: RepositoryDep,
    title: str | None = Query(
        default=None, description="Only release points that changed this title."
    ),
) -> list[ReleaseOut]:
    """Every known release point, newest first.

    `titles_affected` is what OLRC says the release point changed;
    `ingested_titles` is what this database actually holds for it. The two differ
    for as long as the backfill is incomplete, and conflating them would make an
    empty answer look like a missing law.
    """
    return [ReleaseOut.of(r) for r in repository.list_releases(title_num=title)]


@api.get("/titles", response_model=list[TitleOut], summary="Ingested titles")
def list_titles(repository: RepositoryDep) -> list[TitleOut]:
    return [TitleOut.of(t) for t in repository.list_titles()]


@api.get(
    "/sections/{identifier:path}/neighbors",
    response_model=NeighborsOut,
    summary="Previous and next section in reading order",
)
def neighbors(
    identifier: str,
    repository: RepositoryDep,
    release: ReleaseParam = None,
    date: DateParam = None,
) -> NeighborsOut:
    """Reading order at one release point, skipping nothing: repealed, omitted and
    transferred sections keep their place and arrive badged (gotcha 9)."""
    path = normalize_identifier(identifier)
    resolved = _resolve_for(repository, path, release, date)
    result = repository.neighbors(path, resolved)
    if result is None:
        raise HTTPException(status_code=404, detail=_not_found(path, resolved))
    return NeighborsOut.of(result)


@api.get(
    "/sections/{identifier:path}/versions",
    response_model=VersionsOut,
    summary="Release points at which a section changed",
)
def versions(identifier: str, repository: RepositoryDep) -> VersionsOut:
    """The section's change timeline — one entry per distinct text, not one per
    release point, since most release points leave most sections untouched."""
    path = normalize_identifier(identifier)
    found = repository.versions(path)
    if not found:
        raise HTTPException(status_code=404, detail=f"no section at {path}")
    return VersionsOut(
        identifier=path, versions=[VersionOut.of(version) for version in found]
    )


@router.get(
    "/us/usc/",
    response_model=GuidOut,
    tags=["us code"],
    summary="Look a provision up by its XML @id",
    responses={404: {"model": ErrorOut}},
)
def lookup_by_guid(
    repository: RepositoryDep,
    id: str = Query(
        description="An `@id` guid from the USLM, e.g. "
        "`id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd`.",
        examples=["id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd"],
    ),
) -> GuidOut:
    """No release parameter, by design: a guid identifies (provision, release point)
    on its own, which makes it the stable citation for *this exact text at this
    exact moment* (ADR-0003)."""
    resolution = repository.resolve_id(id)
    if resolution is None:
        raise HTTPException(status_code=404, detail=f"no provision with @id {id!r}")
    return GuidOut.of(resolution)


@router.get(
    "/us/usc/{identifier:path}",
    tags=["us code"],
    summary="A provision, section, or table-of-contents node by identifier",
    response_model=None,
    responses={
        200: {
            "content": {
                "application/json": {},
                "application/xml": {},
                "text/html": {},
            }
        },
        404: {"model": ErrorOut},
        409: {"model": ErrorOut},
    },
)
def get_by_identifier(
    identifier: str,
    request: Request,
    repository: RepositoryDep,
    release: ReleaseParam = None,
    date: DateParam = None,
    format: FormatParam = None,
) -> Response | SectionOut | TocOut:
    """Resolve a US Code identifier at a release point.

    Longest-prefix match means `/us/usc/t16/s45f/c/5` returns section 45f *with*
    paragraph (c)(5) extracted and anchored, rather than the paragraph alone —
    sub-section provisions are cut from the section at request time (ADR-0001), so
    the reader never loses context.

    If the identifier names no section, it is tried as a structural node, and a
    table of contents comes back instead.
    """
    path = normalize_identifier(f"us/usc/{identifier}")
    resolved = _resolve_for(repository, path, release, date)
    wanted = negotiated_format(request, format)

    section = repository.get_section(path, resolved)
    if section is not None:
        return _section_response(section, resolved, wanted, path)

    toc = repository.get_toc(path, resolved)
    if toc is not None:
        if wanted == "html":
            return Response(
                content=_toc_html(toc), media_type="text/html; charset=utf-8"
            )
        return TocOut.of(toc, note=resolved.note)

    raise HTTPException(status_code=404, detail=_not_found(path, resolved))


def _section_response(
    section: SectionResult, resolved: ResolvedRelease, wanted: str, requested_path: str
) -> Response | SectionOut:
    note = _served_note(section, resolved)
    headers = {
        # Content is immutable per (section text, release point): the same section
        # at the same release point can never change, so the hash of its content is
        # a true ETag (PLAN Day 6's cache-forever plan starts here).
        "ETag": f'"{section.content_hash}"',
        "X-Release-Point": section.release.label,
        "X-Served-From": section.served_from.label,
    }
    if section.release.caveat:
        headers["X-Release-Caveat"] = section.release.caveat

    if wanted == "xml":
        # Exactly what the identifier names: the provision if one was asked for,
        # otherwise the whole section, verbatim USLM either way.
        fragment = (
            section.provision.xml
            if section.provision and section.provision.found and section.provision.xml
            else section.xml
        )
        return Response(
            content=fragment, media_type="application/xml; charset=utf-8", headers=headers
        )

    if wanted == "html":
        return Response(
            content=render_page(
                section.xml,
                title=f"{section.num or ''} {section.heading or section.identifier}".strip(),
                subtitle=_html_subtitle(section, note),
                target_identifier=requested_path if requested_path != section.identifier else None,
            ),
            media_type="text/html; charset=utf-8",
            headers=headers,
        )

    out = SectionOut.of(section, note=note)
    return Response(
        content=out.model_dump_json(),
        media_type="application/json",
        headers=headers,
    )


def _not_found(path: str, resolved: ResolvedRelease) -> str:
    """404s say which release point was searched — "no such provision" and "not at
    this release point" are different answers, and only one of them means the URL
    is wrong."""
    return (
        f"nothing at {path} in release point {resolved.release.label} "
        f"({resolved.release.currency_date.isoformat()})"
    )


def _resolve_for(
    repository: Repository, path: str, release: str | None, date: str | None
) -> ResolvedRelease:
    return resolve_release_or_404(
        repository,
        release=release,
        on_date=parse_date_param(date),
        title_num=title_num_from_identifier(path),
    )


def _served_note(section: SectionResult, resolved: ResolvedRelease) -> str | None:
    """Say when the answer came from a different release point than the one asked
    for — the alternative is a silently wrong-looking date."""
    parts = [resolved.note] if resolved.note else []
    if not section.is_exact:
        parts.append(
            f"{section.release.label} is not ingested; this is Title "
            f"{section.title_num} as published at {section.served_from.label} "
            f"({section.served_from.currency_date.isoformat()}), which is the "
            "latest release point at or before it that carries this title."
        )
    return " ".join(parts) or None


def _html_subtitle(section: SectionResult, note: str | None) -> str:
    bits = [
        f"<strong>{escape(section.served_from.label)}</strong> "
        f"({section.served_from.currency_date:%m/%d/%Y})"
    ]
    if section.status:
        bits.append(f'<span class="status">{escape(section.status)}</span>')
    if section.served_from.caveat:
        bits.append(escape(section.served_from.caveat))
    if note:
        bits.append(escape(note))
    return " &middot; ".join(bits)


def _toc_html(toc: TocResult) -> str:
    node = toc.node
    rows = []
    for entry in list(toc.children) + list(toc.sections):
        status = (
            f' <span class="status">{escape(entry.status)}</span>' if entry.status else ""
        )
        rows.append(
            f'<li><a href="{escape(entry.identifier)}">'
            f'<span class="uslm-num">{escape(entry.num or "")}</span> '
            f"{escape(entry.heading or '')}</a>{status}</li>"
        )
    crumbs = " / ".join(
        f'<a href="{escape(a.identifier)}">{escape((a.num or a.identifier).rstrip("—"))}</a>'
        for a in toc.ancestors
    )
    served = toc.served_from
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(node.heading or node.identifier)}</title>"
        f"<style>{PAGE_CSS}</style></head><body>"
        f'<div class="meta">{crumbs} &middot; <strong>{escape(served.label)}</strong> '
        f"({served.currency_date:%m/%d/%Y})</div>"
        f"<h1>{escape(node.num or '')} {escape(node.heading or '')}</h1>"
        f"<ul>{''.join(rows)}</ul></body></html>"
    )
