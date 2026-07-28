"""The HTTP-shaped helpers the reader, the API, and the citation URL all share.

These used to live in `api/deps.py`, back when one router served every surface.
ADR-0010 split the surfaces — reader at `/app`, API at `/api/v1`, and the bare
citation URL a redirector between them — and all three still need the same four
things: a repository, the `?release`/`?date`/`?format` parameters, the translation
of a repository error into a status code, and `Accept:` parsing.

Keeping them here rather than in `api/` is what lets `web/` stop importing `api/`
(and `api/` stop importing Jinja): neither surface depends on the other, both
depend on this.

Nothing here touches a database session — `storage.get_repository` is the
dependency, per CLAUDE.md architecture rule 1.
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


_ACCEPTED: dict[str, Format] = {
    "text/html": "html",
    "application/xhtml+xml": "html",
    "application/xml": "xml",
    "text/xml": "xml",
    "application/json": "json",
}

MACHINE_FORMATS: frozenset[Format] = frozenset({"json", "xml"})
ALL_FORMATS: frozenset[Format] = frozenset({"json", "xml", "html"})


def negotiated_format(
    request: Request,
    requested: Format | None,
    *,
    allowed: frozenset[Format] = ALL_FORMATS,
) -> Format:
    """`?format=` wins; otherwise honour `Accept:` (PLAN §4 content negotiation).

    The q-values have to be read, not just the media types. Chrome asks for
    `text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8` — a
    substring check for `application/xml` matches that and hands a person the
    raw USLM. Highest q wins; ties go to whichever the client listed first; a
    client that asks for nothing we serve gets JSON, which is what a program
    with `*/*` wants.

    `allowed` narrows the answer to what the surface can actually produce: the
    citation redirector negotiates all three, but `/api/v1` serves no HTML, so a
    browser's header there is not a reason to look for a template — it falls back
    to JSON like any other unservable preference.
    """
    if requested and requested in allowed:
        return requested

    best: tuple[float, Format] | None = None
    for part in request.headers.get("accept", "").split(","):
        media_type, _, parameters = part.strip().partition(";")
        candidate = _ACCEPTED.get(media_type.strip().lower())
        if candidate is None or candidate not in allowed:
            continue
        quality = 1.0
        for parameter in parameters.split(";"):
            key, _, value = parameter.partition("=")
            if key.strip() == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        if quality > 0 and (best is None or quality > best[0]):
            best = (quality, candidate)
    return best[1] if best else "json"


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
