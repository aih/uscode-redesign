"""The composition root: the FastAPI half of the site.

Two things are mounted here — the machine surface at `/api/v1` and the citation
redirector at `/us/usc/…` — and one thing deliberately is not: the reader. Since
Session 7 the reader is an Astro application in `frontend/`, served at `/app` by
the proxy in `deploy/Caddyfile` (ADR-0011), so this process holds no templates,
no static assets and no HTML at all.

That is the shape ADR-0010 was aiming at. The redirector still sends browsers to
`/app`; whether anything is listening there is the proxy's business, not this
app's, which is exactly the independence the split was for.

Every question about *which text* belongs to *which release point* is answered by
the `Repository` behind `storage/` (CLAUDE.md architecture rule 1).
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from api.auth import auth
from api.routes import api
from api.watchlists import default_watchlist, watchlists
from citation import router as citation_router
from params import NO_STORE, PRIVATE_PREFIXES

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

app.include_router(api)  # the machine surface, at /api/v1
app.include_router(auth)  # /api/v1/auth: signup, login, logout, me (PLAN §4)
app.include_router(watchlists)  # /api/v1/watchlists CRUD
app.include_router(default_watchlist)  # /api/v1/watchlist: the reader's default list
app.include_router(citation_router)  # the citation URL, redirecting to a surface


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(HTTPException)
def http_exception(request: Request, exc: HTTPException) -> Response:
    """Errors are JSON, because everything this process serves is.

    The reader renders its own error pages from the status the API returns — a
    404 that names the release point it searched is still the answer, and `/app`
    is where it becomes a page.

    The private surfaces get their `no-store` re-applied here. A raised
    `HTTPException` never reaches the `Response` the `no_store` dependency wrote
    to — this handler builds a fresh one — so without this a 401 from
    `/api/v1/auth/me` would go out with no cache directives at all, and a shared
    cache is free to heuristically store an uncacheable-looking error and hand it
    to the next reader.
    """
    response = JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}
    )
    if request.url.path.startswith(PRIVATE_PREFIXES):
        response.headers["Cache-Control"] = NO_STORE
        response.headers["Vary"] = "Cookie"
    return response
