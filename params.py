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
import threading
import time
from typing import Annotated, Callable, Literal

from fastapi import Depends, HTTPException, Query, Request, Response
from pydantic_settings import BaseSettings, SettingsConfigDict

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

PRIVATE_PREFIXES = ("/api/v1/auth", "/api/v1/watchlist", "/api/v1/settings")
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


# -------------------------------------------------------------- rate limiting
#
# ADR-0029. Four ADRs (0016, 0020, 0024, 0028), docs/deploy.md and
# docs/verification/loadtest.json each say an expensive unauthenticated route
# must be limited before the URL is advertised. This is that limit.
#
# It lives here rather than in `api/` because `api/`, `citation.py` and the
# reader's own surface all need the same thing and none of them may import each
# other (ADR-0010) — the same reason `public_cache` and `no_store` are here.
#
# The amplifier that makes this urgent: every handler under `api/` is a sync
# `def`, so all of them share Starlette's 40-slot threadpool. Saturating it with
# one CPU-bound route stalls `/health` and every read route with it, which turns
# "an expensive endpoint" into "an outage".
#
# Two costs, stated rather than hidden:
#
#  1. **The state is per process.** That is honest for ADR-0020's single box and
#     wrong for a second instance, which would need shared state (Redis, or the
#     proxy doing it). Recorded in ADR-0029 rather than discovered later.
#
#  2. **The reader's server-side calls share one bucket.** `frontend/` renders on
#     the server and calls `/api/v1` over HTTP, so every reader's page view
#     arrives at `/labels`, `/search` and `/citation` from the *frontend
#     container's* address — one key for the whole readership. Those three limits
#     are therefore sized for a server, not a person, and the per-person limit
#     for the reader lives in `frontend/src/middleware.ts` where the browser's
#     own address is visible. The routes a browser calls directly (signup) and
#     the routes the reader does not call at all (diff, since ADR-0026 moved the
#     reader onto its own text redline) are sized for a person and are the tight
#     ones.


class _Bucket:
    __slots__ = ("tokens", "updated")

    def __init__(self, tokens: float, updated: float) -> None:
        self.tokens = tokens
        self.updated = updated


class RateLimiter:
    """A token bucket per client address.

    `capacity` is the burst a caller may spend at once; `per_second` is the rate
    it refills at, which is the sustained limit. A bucket that is full is
    indistinguishable from one that never existed, which is what makes the sweep
    below safe.
    """

    #: How often to walk the whole table looking for buckets to forget. The table
    #: is keyed on a client-supplied-adjacent value (an address), so it has to be
    #: bounded by something; sweeping on write costs one pass per interval rather
    #: than a background thread.
    SWEEP_INTERVAL = 600.0

    def __init__(self, *, name: str, capacity: int, per_second: float) -> None:
        self.name = name
        self.capacity = float(capacity)
        self.per_second = per_second
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._swept = time.monotonic()

    def check(self, key: str) -> float | None:
        """None if the request may proceed; otherwise seconds until it may.

        Under a threadpool this is called concurrently, so the whole
        read-modify-write is inside the lock. It is a few microseconds of
        arithmetic — the thing it is protecting takes milliseconds to seconds.
        """
        now = time.monotonic()
        with self._lock:
            if now - self._swept > self.SWEEP_INTERVAL:
                self._sweep(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(self.capacity, now)
                self._buckets[key] = bucket
            bucket.tokens = min(
                self.capacity, bucket.tokens + (now - bucket.updated) * self.per_second
            )
            bucket.updated = now
            if bucket.tokens < 1.0:
                # Ceil, so a client that obeys the header comes back with a whole
                # token rather than a fraction of one and a second 429.
                return max(1.0, (1.0 - bucket.tokens) / self.per_second)
            bucket.tokens -= 1.0
            return None

    def _sweep(self, now: float) -> None:
        """Forget buckets that have refilled: they hold no information."""
        full_after = self.capacity / self.per_second
        self._buckets = {
            key: bucket
            for key, bucket in self._buckets.items()
            if now - bucket.updated < full_after
        }
        self._swept = now

    def reset(self) -> None:
        """For tests. Nothing in the running app calls this."""
        with self._lock:
            self._buckets.clear()
            self._swept = time.monotonic()


def client_key(request: Request) -> str:
    """The rate-limit bucket key: the caller's address.

    `request.client` and not the raw `X-Forwarded-For`, for the reason spelled
    out at `api.auth._client_ip` — uvicorn's proxy-headers middleware fills it
    in, and `deploy/Caddyfile` overwrites the header with the real peer so that
    what it fills it in *with* cannot be chosen by the caller (ADR-0029). A
    request with no client at all (an ASGI transport with no peer, which is what
    a test client is) falls into one shared bucket, which is the safe direction.
    """
    return request.client.host if request.client else "-"


#: Every limiter, by name, so tests and `/health`-adjacent tooling can find them
#: without importing each route module.
LIMITERS: dict[str, RateLimiter] = {}


def rate_limit(
    name: str, *, capacity: int, per_second: float
) -> Callable[[Request], None]:
    """Build a FastAPI dependency that limits one route family.

    Returns 429 with `Retry-After`, reusing the shape `api/auth.py`'s login
    throttle already established (ADR-0019), so a caller meets one error surface
    rather than two.
    """
    limiter = RateLimiter(name=name, capacity=capacity, per_second=per_second)
    LIMITERS[name] = limiter

    def dependency(request: Request) -> None:
        retry_after = limiter.check(client_key(request))
        if retry_after is not None:
            raise HTTPException(
                status_code=429,
                detail="too many requests; try again shortly",
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

    return dependency


# ------------------------------------------------------------------- cookies


class CookieSettings(BaseSettings):
    """Cookie policy, which is an HTTP concern and so lives here rather than in
    `db/config.py` — `api/` may not import anything from `db/` but the session
    factory (`tests/test_architecture.py`)."""

    usc_cookie_secure: Literal["auto", "true", "false"] = "auto"
    """Whether session cookies carry `Secure` (ADR-0019).

    `auto` infers it from the request scheme, which is right locally and is what
    this has always done. Inference is not enough in production: behind a proxy
    the scheme uvicorn sees is `http` unless `--proxy-headers` is on *and* the
    proxy is trusted, and if either regresses the cookie goes out without
    `Secure` — a downgrade with no exception and no log line. A deployment
    served over HTTPS sets this to `true` and stops depending on inference.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


cookie_settings = CookieSettings()


def cookies_are_secure(request: Request) -> bool:
    setting = cookie_settings.usc_cookie_secure
    if setting == "auto":
        return request.url.scheme == "https"
    return setting == "true"


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
