"""The composition root: the FastAPI half of the site.

Two things are mounted here — the machine surface at `/api/v1` and the citation
redirector at `/us/usc/…` — and one thing deliberately is not: the reader. Since
Session 7 the reader is an Astro application in `frontend/`, served at `/app` by
the proxy in `deploy/Caddyfile` (ADR-0011), so this process holds no templates
and serves no reader pages of its own.

It does now serve a small `static/` directory, which is the one amendment to
that shape and is worth naming rather than leaving to be discovered: the
interactive API docs and the site's favicon. Both are assets FastAPI's own pages
need, both used to be fetched from someone else's domain, and the CSP this site
ships names no domain but its own (ADR-0030, ADR-0032). None of it is reader
markup — the reader still has no HTML here.

That is the shape ADR-0010 was aiming at. The redirector still sends browsers to
`/app`; whether anything is listening there is the proxy's business, not this
app's, which is exactly the independence the split was for.

Every question about *which text* belongs to *which release point* is answered by
the `Repository` behind `storage/` (CLAUDE.md architecture rule 1).
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from api.auth import auth
from api.classification import router as classification_router
from api.routes import api
from api.settings import settings
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

**Classification tables.** `/api/v1/classifications/…` mirrors OLRC's
Classification Tables — which provision of which public law was classified to
which Code section — and the Editorial Classification Change Table. They are a
mirror of published documents rather than a view of the corpus, so no route
there takes a release point.

* `/api/v1/classifications/pl/118/35` — everything Public Law 118-35 classified.
  **404 and an empty page mean different things**: 404 says no table covers that
  law, 200 with no rows says one does and the law classified nothing.
* `/api/v1/classifications/code/18/3551` — everything ever classified to a
  section, newest law first.
* `/api/v1/classifications/tables/119/2/entries` — one session's table, sorted
  `pl` or `code`, filtered and paged. `session` is `1`, `2` or `all`.

The bare citation URL — `/us/usc/t16/s45f/c/5` — is not documented here because it
is not a machine route: it is a **307 redirect** to whichever surface the caller
can read (`/app` for HTML, `/api/v1` otherwise), so `curl` it with `-L` or address
`/api/v1` directly. ADR-0010.

Release points are named for the last public law they incorporate, and `not` in a
label means a law that was *skipped*: at `119-102not101` the text is current
through 07/12/2026 **except** for Public Law 119-101. Responses carry that caveat
rather than only a date.

**Rate limits.** Seven route families are throttled per client (ADR-0029). Each is
a token bucket: a burst up to the capacity, refilled at the sustained rate. Over
budget, the response is **429** with a `Retry-After` header in seconds.

* `GET /api/v1/search` — burst 120, then 10 a second.
* `GET /api/v1/citation` — burst 120, then 10 a second.
* `GET /api/v1/labels` — burst 300, then 30 a second.
* `GET /api/v1/classifications/…` — burst 120, then 10 a second.
* `GET /api/v1/classifications/suggest` — burst 30, then 5 a second. Tighter than
  the rest of that family because a browser calls it directly, as someone types.
* `GET /api/v1/sections/{identifier}/diff` — burst 5, then 1 every 5 seconds.
* `POST /api/v1/auth/signup` — burst 10, then 30 an hour.

`POST /api/v1/auth/login` is throttled by failure count rather than by request
rate: 5 failures for one email address, or 50 from one client address, and further
attempts answer 429 (ADR-0019).

**`HEAD` is not routed.** Every route here is registered for its own method alone,
so a `HEAD` request answers **405**.

**`/api/v1` is the only version.** A breaking change would land at `/api/v2`.
"""


STATIC = Path(__file__).resolve().parent / "static"
#: Where the vendored Swagger UI / ReDoc bundles are addressed from.
APIDOCS = "/static/apidocs"
FAVICON = "/favicon.svg"

# `docs_url=None`/`redoc_url=None` turns off FastAPI's built-in pages so the
# custom ones below can take those paths. The OpenAPI schema itself is untouched
# and still served at /openapi.json — it is the *pages* that need rewriting, not
# the document they read (ADR-0032).
app = FastAPI(
    title="uscode-redesign",
    version="0.1.0",
    summary="Versioned US Code retrieval: any provision, at any release point.",
    description=DESCRIPTION,
    docs_url=None,
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory=STATIC), name="static")

app.include_router(api)  # the machine surface, at /api/v1
app.include_router(auth)  # /api/v1/auth: signup, login, logout, me (PLAN §4)
app.include_router(watchlists)  # /api/v1/watchlists CRUD
app.include_router(default_watchlist)  # /api/v1/watchlist: the reader's default list
app.include_router(settings)  # /api/v1/settings: per-user preferences
app.include_router(classification_router)  # /api/v1/classifications: OLRC's tables
app.include_router(citation_router)  # the citation URL, redirecting to a surface
from api.search import router as search_router
app.include_router(search_router)


@app.get("/health", tags=["ops"], summary="Liveness check")
def health() -> dict[str, str]:
    """`{"status": "ok"}` if the process is up. It touches no database and no
    search cluster, so it says nothing about whether either is reachable — for
    that, ask `/api/v1/status`."""
    return {"status": "ok"}


# ------------------------------------------------------------- the docs pages
#
# Swagger UI and ReDoc, served from this origin instead of cdn.jsdelivr.net.
#
# Both pages were arriving 200 with an empty body. The reason is one line of the
# Caddyfile: `default-src 'self'` with no CDN named, which is not a rule anyone
# chose *for* these pages — it is a description of a site that loads no
# third-party anything (ADR-0030). FastAPI's stock docs HTML points at jsdelivr,
# so the browser fetched the page, blocked every asset in it, and showed a blank
# div. Nothing in the server logs says so; the evidence is entirely in the
# browser console, which is why it survived two sessions of the site being
# looked at.
#
# Widening the CSP was the alternative and is the wrong trade: it would put a
# third-party script origin into the policy protecting the reader's `set:html`
# sinks, permanently, to serve two developer pages. ADR-0032.
#
# `/app/docs` remains the readable reference, in the site's own chrome. These two
# are the ones with a "Try it" button.


@app.get("/docs", include_in_schema=False)
def swagger_ui() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title=f"{app.title} — Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url=f"{APIDOCS}/swagger-ui-bundle.js",
        swagger_css_url=f"{APIDOCS}/swagger-ui.css",
        # Stock value is https://fastapi.tiangolo.com/img/favicon.png — a third
        # host, and blocked by `img-src 'self' data:` just as surely as the
        # scripts were.
        swagger_favicon_url=FAVICON,
    )


@app.get(app.swagger_ui_oauth2_redirect_url or "/docs/oauth2-redirect", include_in_schema=False)
def swagger_ui_redirect() -> HTMLResponse:
    """Kept because turning off `docs_url` also unmounts this.

    Nothing here uses OAuth, so it is never reached — but Swagger UI names this
    path in its own configuration, and a page that 404s the URL it just told the
    browser to use is a worse thing to leave behind than four lines.
    """
    return get_swagger_ui_oauth2_redirect_html()


@app.get("/redoc", include_in_schema=False)
def redoc() -> HTMLResponse:
    return get_redoc_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title=f"{app.title} — ReDoc",
        redoc_js_url=f"{APIDOCS}/redoc.standalone.js",
        redoc_favicon_url=FAVICON,
        # Montserrat and Roboto, from fonts.googleapis.com. `font-src 'self'`
        # blocks them, and ReDoc falls back to the system stack without
        # complaint — so this is one request saved rather than a compromise.
        with_google_fonts=False,
    )


@app.get(FAVICON, include_in_schema=False)
def favicon() -> FileResponse:
    """The tab mark, at the root where a browser looks for it unprompted.

    One file for the whole site: the reader links it from `Base.astro` and both
    docs pages above point at this same path. It lives on this surface rather
    than in `frontend/public/` because `/favicon.svg` is not under `/app`, and
    Caddy sends everything that is not to this process.
    """
    return FileResponse(
        STATIC / "favicon.svg",
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico() -> Response:
    """Browsers ask for this without being told to. Answer, rather than 404."""
    return Response(status_code=301, headers={"Location": FAVICON})


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
        status_code=exc.status_code,
        content={"detail": exc.detail},
        # Headers raised with the exception are part of the answer, not
        # decoration: `Retry-After` on a 429 is the only thing that tells a
        # throttled caller when to come back (ADR-0019).
        headers=exc.headers,
    )
    if request.url.path.startswith(PRIVATE_PREFIXES):
        response.headers["Cache-Control"] = NO_STORE
        response.headers["Vary"] = "Cookie"
    return response
