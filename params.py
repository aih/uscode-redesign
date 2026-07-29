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

from fastapi import Depends, HTTPException, Query, Request, Response

from storage import (
    AmbiguousReleaseError,
    ReleaseNotFoundError,
    Repository,
    ResolvedRelease,
    SectionResult,
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


def served_note(section: SectionResult, resolved: ResolvedRelease) -> str | None:
    """Say when the answer came from a different release point than the one asked
    for — the alternative is a silently wrong-looking date (gotcha 10).

    Both surfaces owe the caller this sentence, and they have to owe it in the
    same words: the reader prints it and the API returns it as `note`.
    """
    parts = [resolved.note] if resolved.note else []
    if not section.is_exact:
        parts.append(
            f"{section.release.label} is not ingested; this is Title "
            f"{section.title_num} as published at {section.served_from.label} "
            f"({section.served_from.currency_date.isoformat()}), which is the "
            "latest release point at or before it that carries this title."
        )
    return " ".join(parts) or None


def not_found(path: str, resolved: ResolvedRelease) -> str:
    """404s say which release point was searched — "no such provision" and "not at
    this release point" are different answers, and only one of them means the URL
    is wrong."""
    return (
        f"nothing at {path} in release point {resolved.release.label} "
        f"({resolved.release.currency_date.isoformat()})"
    )


# ------------------------------------------------------------------- caching
#
# PLAN Day 6a: a (section, release point) response is immutable, so cache it
# forever. The trap is that "the release point" is not what the URL says — it is
# what the URL *resolved to*.
#
# `/us/usc/t16/s45f?release=119-99` names one release point and can never mean a
# different one, so its answer can never change. `/us/usc/t16/s45f` with no
# release, or with `?date=`, is answered from the newest ingested release point
# at or before the request (gotcha 10) — and that answer changes the moment a
# newer release point is loaded. Caching those two the same way would serve
# superseded law from a cache with no way to invalidate it.
#
# So immutability is a property of the resolution, not of the URL. Everything
# else revalidates against the ETag, which is cheap because the ETag is the
# content hash and identical text across release points hashes the same.

IMMUTABLE = "public, max-age=31536000, immutable"
"""A year, which is as close to forever as `max-age` is worth spelling."""

REVALIDATE = "public, max-age=300"
"""Short, because "newest at or before" moves when a release point is ingested."""

NO_STORE = "private, no-store"
"""Anything a signed-in user sees. A shared cache holding one reader's watchlist
and handing it to the next reader is the failure this exists to prevent."""

PRIVATE_PREFIXES = ("/api/v1/auth", "/api/v1/watchlist")
"""The path prefixes that must never be cached, by path rather than by route.

The routers carry `no_store` as a dependency, but a raised `HTTPException`
bypasses the response that dependency wrote to — so the error handler in
`main.py` re-applies the header by matching these. `/api/v1/watchlist` covers
`/api/v1/watchlists` too, which is the intent, not an accident of prefixes."""


def cache_control(resolved: ResolvedRelease) -> str:
    """`immutable` only when the caller pinned a release point and got it."""
    return IMMUTABLE if resolved.requested_label and resolved.is_exact else REVALIDATE


def if_none_match(request: Request, etag: str) -> bool:
    """True when the client already holds this exact representation.

    `If-None-Match` is a comma-separated list, entries may be weak (`W/"..."`),
    and `*` matches anything the server has. Comparison is on the opaque tag, so
    a weak validator matches a strong one of the same value — which is what the
    weak-comparison rule in RFC 9110 §8.8.3.2 requires for conditional GETs.
    """
    header = request.headers.get("if-none-match", "")
    if not header:
        return False
    if header.strip() == "*":
        return True
    wanted = etag.strip().removeprefix("W/").strip('"')
    return any(
        candidate.strip().removeprefix("W/").strip('"') == wanted
        for candidate in header.split(",")
    )


def public_cache(response: Response) -> None:
    """A FastAPI dependency for routes whose answer is public but not pinned.

    Used on the routes that return a model rather than a hand-built `Response` —
    setting the header here leaves their `response_model` serialization alone.
    """
    response.headers["Cache-Control"] = REVALIDATE


def no_store(response: Response) -> None:
    """A FastAPI dependency for the signed-in surfaces.

    Attached to the auth and watchlist routers as a whole rather than to each
    route, so a route added later cannot forget it. `Vary: Cookie` rides along
    because these responses differ by session cookie, and a cache that missed
    that would key them all together.
    """
    response.headers["Cache-Control"] = NO_STORE
    response.headers["Vary"] = "Cookie"


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
