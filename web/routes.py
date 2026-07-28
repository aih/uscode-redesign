"""Reader pages that are not identifier lookups.

There is exactly one of them today — the front page. Everything under
`/us/usc/…` is served by `api/routes.py`, because the identifier *is* the URL and
splitting it across two routers would mean two things owning one URL scheme; that
handler negotiates format and calls `web.reader` for the HTML case.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from params import RepositoryDep
from web import reader

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def home(repository: RepositoryDep) -> HTMLResponse:
    return HTMLResponse(content=reader.render_home(repository))
