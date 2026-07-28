"""The machine surface: PLAN §4's routes under `/api/v1`, and nothing else.

Two families, on purpose:

  * **`/api/v1/us/usc/…`** mirrors the USLM `@identifier` exactly, so a citation is
    a URL and a URL is a citation. One handler serves it, because the identifier
    decides what the thing *is* — `/us/usc/t16/ch1` is a TOC node,
    `/us/usc/t16/s45f/c/5` is a provision inside a section — and a caller shouldn't
    have to know which before asking.
  * **`/api/v1/{sections,releases,titles}/…`** for everything that is about a
    provision rather than being one: neighbours, version timeline, release points.

No SQL and no version-resolution logic lives here (CLAUDE.md architecture rule 1);
handlers resolve a release point, ask the `Repository`, and shape the answer.

Machine formats only (ADR-0010): JSON by default, verbatim USLM for `?format=xml`
or an XML `Accept:`. A browser's `Accept: text/html` gets JSON here rather than a
template — the surface that answers people is `/app`, and the bare citation URL
`/us/usc/…` is the redirector that sends each caller to the right one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response

from api.schemas import (
    ErrorOut,
    GuidOut,
    NeighborsOut,
    ReleaseOut,
    SectionOut,
    TitleOut,
    TocEntryOut,
    TocOut,
    VersionOut,
    VersionsOut,
)
from params import (
    MACHINE_FORMATS,
    DateParam,
    FormatParam,
    ReleaseParam,
    RepositoryDep,
    negotiated_format,
    normalize_identifier,
    not_found,
    parse_date_param,
    resolve_release_or_404,
    served_note,
)
from storage import (
    Repository,
    ResolvedRelease,
    SectionResult,
    title_num_from_identifier,
)

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
        raise HTTPException(status_code=404, detail=not_found(path, resolved))
    return NeighborsOut.of(result)


@api.get(
    "/labels",
    response_model=dict[str, TocEntryOut],
    summary="Num and heading for many identifiers at once",
)
def labels(
    repository: RepositoryDep,
    identifier: Annotated[
        list[str],
        Query(
            description="Repeat once per identifier. Unknown ones are absent from "
            "the answer rather than an error.",
            examples=[["/us/usc/t16/s45f", "/us/usc/t16/s1"]],
        ),
    ],
    release: ReleaseParam = None,
    date: DateParam = None,
) -> dict[str, TocEntryOut]:
    """What a list of citations *say*, in one request.

    A section's text can carry forty cross references, and a reader that labels
    them — hover text, so a citation is legible without following it — has to ask
    once, not forty times.
    """
    paths = [normalize_identifier(one) for one in identifier]
    resolved = resolve_release_or_404(
        repository,
        release=release,
        on_date=parse_date_param(date),
        title_num=next(
            (
                num
                for num in map(title_num_from_identifier, paths)
                if num is not None
            ),
            None,
        ),
    )
    return {
        found: TocEntryOut.of(entry)
        for found, entry in repository.labels(paths, resolved).items()
    }


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


@api.get(
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


@api.get(
    "/us/usc/{identifier:path}",
    tags=["us code"],
    summary="A provision, section, or table-of-contents node by identifier",
    response_model=None,
    responses={
        200: {
            "content": {
                "application/json": {},
                "application/xml": {},
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
    wanted = negotiated_format(request, format, allowed=MACHINE_FORMATS)

    section = repository.get_section(path, resolved)
    if section is not None:
        return _section_response(section, resolved, wanted)

    toc = repository.get_toc(path, resolved)
    if toc is not None:
        return TocOut.of(toc, note=resolved.note)

    raise HTTPException(status_code=404, detail=not_found(path, resolved))


def _section_response(
    section: SectionResult,
    resolved: ResolvedRelease,
    wanted: str,
) -> Response | SectionOut:
    note = served_note(section, resolved)
    headers = {
        # Content is immutable per (section text, release point): the same section
        # at the same release point can never change, so the hash of its content is
        # a true ETag (PLAN Day 6's cache-forever plan starts here).
        "ETag": f'"{section.content_hash}"',
        # JSON and XML still share this URL, so the ETag alone would let a cache
        # hand one caller the representation another asked for first.
        "Vary": "Accept",
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

    out = SectionOut.of(section, note=note)
    return Response(
        content=out.model_dump_json(),
        media_type="application/json",
        headers=headers,
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
