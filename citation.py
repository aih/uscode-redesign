"""The citation URL: `/us/usc/…`, kept alive as a thin redirector (ADR-0010).

This is what people paste, cite in briefs, and print, so it cannot be allowed to
mean only one of the two surfaces. It holds no logic beyond reading `Accept:`:
a caller that prefers HTML is sent to the reader at `/app`, everyone else to the
machine surface at `/api/v1`, and `?format=` overrides the header exactly as it
did when one handler served both (ADR-0009's principle — a citation is one URL —
survives; only its mechanism changed).

307 rather than 301/302: it preserves the method, it is not cached forever by a
browser that saw one `Accept:` header once, and `Vary: Accept` tells any cache in
between that the answer depends on who asked.

The query string is copied through verbatim rather than rebuilt — `?release=`,
`?date=`, and the `?id=` guid form all have to arrive intact, and the redirector
has no business parsing any of them.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from params import FormatParam, negotiated_format

READER = "/app"
API = "/api/v1"

router = APIRouter(include_in_schema=False)


def _redirect_to(prefix: str, request: Request) -> RedirectResponse:
    target = f"{prefix}{request.url.path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(target, status_code=307, headers={"Vary": "Accept"})


@router.api_route("/us/usc/{identifier:path}", methods=["GET", "HEAD"])
def citation(request: Request, identifier: str, format: FormatParam = None):
    """A cited provision, sent to whichever surface the caller can read.

    The empty identifier is the `?id=` guid form (`/us/usc/?id=id0b32…`), which
    needs no special case here: it is a citation like any other, and the surface
    it lands on knows what to do with it.
    """
    wanted = negotiated_format(request, format)
    return _redirect_to(READER if wanted == "html" else API, request)


@router.api_route("/", methods=["GET", "HEAD"])
def home(request: Request) -> RedirectResponse:
    """The front door is the reader's front page."""
    return RedirectResponse(f"{READER}/", status_code=307)
