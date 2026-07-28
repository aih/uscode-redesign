"""The reader's routes, mounted at `/app` (ADR-0010).

Everything here answers in HTML, always — no negotiation, no `?format=`. The
identifier path scheme is the same one the API serves, because a reader URL and a
citation differ only in prefix; `/us/usc/…` itself is the redirector that picks
between them.

Like `web/reader.py`, this talks only to the `Repository` (CLAUDE.md architecture
rule 1) and imports nothing from `api/` — the two surfaces share `params.py` and
otherwise do not know that the other exists.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from params import (
    DateParam,
    ReleaseParam,
    RepositoryDep,
    normalize_identifier,
    not_found,
    parse_date_param,
    resolve_release_or_404,
    served_note,
)
from storage import Repository, ResolvedRelease, title_num_from_identifier
from web import reader
from web.reader import STATIC

router = APIRouter(prefix="/app", include_in_schema=False)

# The reader's stylesheet, at `/app/static/reader.css`. `router.frontend()` rather
# than a `StaticFiles` mount: it registers low-priority routes, so `/app/us/usc/…`
# is still matched first no matter what ends up in the directory later.
router.frontend("/static", directory=STATIC)


@router.get("/", response_class=HTMLResponse)
def home(repository: RepositoryDep) -> HTMLResponse:
    return HTMLResponse(content=reader.render_home(repository))


@router.get("/us/usc/")
def lookup_by_guid(
    repository: RepositoryDep,
    id: str = Query(description="An `@id` guid from the USLM."),
) -> RedirectResponse:
    """A guid pins (provision, release point), so it resolves to exactly one page
    and redirects there — the reader's own URLs stay identifier-shaped."""
    resolution = repository.resolve_id(id)
    if resolution is None:
        raise HTTPException(status_code=404, detail=f"no provision with @id {id!r}")
    return RedirectResponse(
        reader.section_url(resolution.identifier, resolution.release.label),
        status_code=307,
    )


@router.get("/us/usc/{identifier:path}", response_class=HTMLResponse)
def read(
    identifier: str,
    repository: RepositoryDep,
    release: ReleaseParam = None,
    date: DateParam = None,
) -> HTMLResponse:
    """One section with the provision the URL named highlighted inside it
    (ADR-0001), or — when the identifier names a structural node instead — that
    node's table of contents."""
    path = normalize_identifier(f"us/usc/{identifier}")
    resolved = _resolve_for(repository, path, release, date)

    section = repository.get_section(path, resolved)
    if section is not None:
        return HTMLResponse(
            content=reader.render_section(
                repository,
                section,
                resolved,
                requested_identifier=path,
                note=served_note(section, resolved),
            )
        )

    toc = repository.get_toc(path, resolved)
    if toc is not None:
        return HTMLResponse(
            content=reader.render_toc(repository, toc, resolved, note=resolved.note)
        )

    raise HTTPException(status_code=404, detail=not_found(path, resolved))


def _resolve_for(
    repository: Repository, path: str, release: str | None, date: str | None
) -> ResolvedRelease:
    return resolve_release_or_404(
        repository,
        release=release,
        on_date=parse_date_param(date),
        title_num=title_num_from_identifier(path),
    )
