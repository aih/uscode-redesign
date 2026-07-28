"""The composition root: one FastAPI app, assembled from the surfaces.

It lives outside `api/` on purpose. `api/` is the machine surface and must import
no template engine (ADR-0010); `web/` is the reader; neither should have to know
the other exists. Something has to mount both, so that something is here, and it
is the only module in the project allowed to import from both.

Every question about *which text* belongs to *which release point* is answered by
the `Repository` behind `storage/` (CLAUDE.md architecture rule 1).
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from api.routes import api
from citation import READER
from citation import router as citation_router
from web import reader
from web.routes import router as web_router

DESCRIPTION = """
Any provision of the US Code, at any release point, addressed by a URL that mirrors
the USLM `@identifier`.

* `/api/v1/us/usc/t16/s45f/c/5?date=07/12/2026` — a provision, in the context of
  its section, at the release point current on that date.
* `/api/v1/us/usc/?id=id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd` — the same provision
  by its XML `@id`. A guid identifies (provision, release point), so no release
  parameter is needed, and the link keeps meaning the same text forever.
* `/api/v1/us/usc/t16/ch1` — a table of contents at a release point.

The bare citation URL — `/us/usc/t16/s45f/c/5` — is not documented here because it
is not a machine route: it is a **307 redirect** to whichever surface the caller
can read (`/app` for HTML, `/api/v1` otherwise), so `curl` it with `-L` or address
`/api/v1` directly. ADR-0010.

Release points are named for the last public law they incorporate, and `not` in a
label means a law that was *skipped*: at `119-102not101` the text is current
through 07/12/2026 **except** for Public Law 119-101. Responses carry that caveat
rather than only a date.
"""


app = FastAPI(
    title="uscode-redesign",
    version="0.1.0",
    summary="Versioned US Code retrieval: any provision, at any release point.",
    description=DESCRIPTION,
)

app.include_router(web_router)  # the reader, at /app
app.include_router(api)  # the machine surface, at /api/v1
app.include_router(citation_router)  # the citation URL, redirecting between them


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(HTTPException)
def http_exception(request: Request, exc: HTTPException) -> Response:
    """Errors answer in the shape of the surface that raised them.

    The surface decides, not the `Accept:` header: everything under `/app` is a
    page, everything else is JSON. A reader that hands a browser a JSON blob when
    a citation is wrong has stopped being a reader at the moment it most needs to
    explain itself — and a 409 on an ambiguous release label is a question, so the
    HTML version offers the candidates as links.
    """
    detail = exc.detail
    candidates = None
    if isinstance(detail, dict):
        candidates = detail.get("candidates")
        detail = detail.get("detail", "")

    if request.url.path.startswith(f"{READER}/"):
        return HTMLResponse(
            content=reader.render_error(exc.status_code, str(detail), candidates),
            status_code=exc.status_code,
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
