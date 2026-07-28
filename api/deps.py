"""Request-scoped dependencies, and the query parameters every route shares.

`api/` never touches a database session at all: `storage.get_repository` yields the
interface, and handlers depend on that (CLAUDE.md architecture rule 1). What lives
here is the HTTP-shaped part — query parameters, content negotiation, and turning
repository errors into status codes.
"""

from __future__ import annotations

import datetime
import re
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, Request

from storage import (
    AmbiguousReleaseError,
    ReleaseNotFoundError,
    Repository,
    ResolvedRelease,
    get_repository,
)

Format = Literal["json", "xml", "html"]

_US_DATE = re.compile(r"^(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})$")


RepositoryDep = Annotated[Repository, Depends(get_repository)]


def parse_date_param(value: str | None) -> datetime.date | None:
    """Accept both `2026-07-12` and `07/12/2026`.

    The second form is what uscode.house.gov shows and what PLAN §10's demo URL
    uses — rejecting it would make the documented demo 422.
    """
    if not value:
        return None
    us = _US_DATE.match(value.strip())
    if us:
        return datetime.date(
            int(us.group("year")), int(us.group("month")), int(us.group("day"))
        )
    try:
        return datetime.date.fromisoformat(value.strip())
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"date {value!r} is not YYYY-MM-DD or MM/DD/YYYY",
        ) from None


def normalize_identifier(path: str) -> str:
    """URL path → USLM `@identifier`. Both `/us/usc/t16/s45f` and `us/usc/t16/s45f`."""
    cleaned = path.strip().strip("/")
    return f"/{cleaned}" if cleaned else "/"


def resolve_release_or_404(
    repository: Repository,
    *,
    release: str | None,
    on_date: datetime.date | None,
    title_num: str | None = None,
) -> ResolvedRelease:
    """Run PLAN §3 step 1, translating the repository's errors into HTTP.

    An ambiguous label is a 409 rather than a 404: the request is answerable, the
    caller just has to say which release point they meant.
    """
    try:
        return repository.resolve_release(
            label=release, on_date=on_date, title_num=title_num
        )
    except AmbiguousReleaseError as exc:
        raise HTTPException(
            status_code=409,
            detail={"detail": str(exc), "candidates": exc.candidates},
        ) from exc
    except ReleaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def negotiated_format(request: Request, requested: Format | None) -> Format:
    """`?format=` wins; otherwise honour `Accept:` (PLAN §4 content negotiation)."""
    if requested:
        return requested
    accept = request.headers.get("accept", "")
    if "application/xml" in accept or "text/xml" in accept:
        return "xml"
    if "text/html" in accept and "application/json" not in accept:
        return "html"
    return "json"


ReleaseParam = Annotated[
    str | None,
    Query(
        description="Release-point label, e.g. `119-102not101`. A bare `119-102` "
        "resolves to it with a note.",
        examples=["119-102not101"],
    ),
]
DateParam = Annotated[
    str | None,
    Query(
        description="Resolve to the newest release point on or before this date. "
        "`YYYY-MM-DD` or `MM/DD/YYYY`.",
        examples=["07/12/2026"],
    ),
]
FormatParam = Annotated[
    Format | None,
    Query(description="Response format. Defaults to content negotiation on Accept."),
]
