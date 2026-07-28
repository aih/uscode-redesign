"""FastAPI application: versioned US Code retrieval (PLAN §4).

The app is thin on purpose — routes, content negotiation, and HTTP semantics. Every
question about *which text* belongs to *which release point* is answered by the
`Repository` behind `storage/` (CLAUDE.md architecture rule 1).
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from api.deps import negotiated_format
from api.routes import api, router
from web import reader
from web.reader import STATIC
from web.routes import router as web_router

DESCRIPTION = """
Any provision of the US Code, at any release point, addressed by a URL that mirrors
the USLM `@identifier`.

* `/us/usc/t16/s45f/c/5?date=07/12/2026` — a provision, in the context of its
  section, at the release point current on that date.
* `/us/usc/?id=id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd` — the same provision by its
  XML `@id`. A guid identifies (provision, release point), so no release parameter
  is needed, and the link keeps meaning the same text forever.
* `/us/usc/t16/ch1` — a table of contents at a release point.

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

app.include_router(web_router)
app.include_router(router)
app.include_router(api)

# The reader's stylesheet. `app.frontend()` rather than a `StaticFiles` mount:
# it registers low-priority routes, so `/us/usc/…` is still matched first no
# matter what ends up in the directory later.
app.frontend("/static", directory=STATIC)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(HTTPException)
def http_exception(request: Request, exc: HTTPException) -> Response:
    """Errors answer in the format that was asked for.

    A reader that hands a browser a JSON blob when a citation is wrong has
    stopped being a reader at the moment it most needs to explain itself — and a
    409 on an ambiguous release label is a question, so the HTML version offers
    the candidates as links.
    """
    detail = exc.detail
    candidates = None
    if isinstance(detail, dict):
        candidates = detail.get("candidates")
        detail = detail.get("detail", "")

    if negotiated_format(request, request.query_params.get("format")) == "html":
        return HTMLResponse(
            content=reader.render_error(exc.status_code, str(detail), candidates),
            status_code=exc.status_code,
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
