"""Email+password auth (PLAN §4): `/api/v1/auth/signup|login|logout|me`.

Argon2 hashing, an HTTP-only session cookie, and a readable CSRF cookie for the
double-submit check `require_csrf` enforces on state-changing routes here and in
`api/watchlists.py`. Session state is a server-side row (`auth_sessions`), not a
signed cookie — the id is `sha256(token)`, so a database read never discloses a
usable cookie value, and logout actually revokes something rather than just
telling the browser to forget a token the server would still honor.

Why login/signup don't require the CSRF header: `require_csrf` protects an
*existing* session from being driven by a forged cross-site request; there is no
session yet when a browser is signing up or logging in, so there is nothing for
a forged request to hijack (the residual "login CSRF" risk — a forged login
that logs the victim into an attacker's account — is accepted here, same as it
is in most JSON-only APIs without CORS enabled, since the browser's CORS
preflight already blocks a cross-site `fetch` and a plain HTML form cannot send
`application/json`; docs/adr/0017).

No `db.*` import here (CLAUDE.md architecture rule 1) — `storage.accounts` is
the only vocabulary this module knows.
"""

from __future__ import annotations

import datetime
import hashlib
import re
import secrets
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from params import cookies_are_secure, no_store, rate_limit
from storage import DuplicateEmailError, SessionRef, UserRef, get_accounts
from storage.accounts import AccountsRepository

SESSION_COOKIE = "usc_session"
CSRF_COOKIE = "usc_csrf"
CSRF_HEADER = "x-csrf-token"
SESSION_TTL = datetime.timedelta(days=14)

# RFC 5322 is not being reimplemented here — this rejects the obviously wrong
# inputs a signup form can send; the account is only ever confirmed by its
# owner successfully logging back in with it, not by mail-deliverability.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_hasher = PasswordHasher()

# A hash of a value nobody knows, verified against when the email is unknown so
# that "no such account" costs the same as "wrong password". Without it, the
# unknown-email path returns before argon2 runs and is measurably faster — which
# turns a login form into an account-enumeration oracle no matter how carefully
# the two cases are worded identically.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))

# Rate limiting (ADR-0019). Deliberately a delay rather than a lockout: locking
# an account on failed attempts lets anyone lock anyone out by guessing badly at
# their address, which turns the defence into the attack.
LOGIN_WINDOW = datetime.timedelta(minutes=15)
MAX_FAILURES_PER_EMAIL = 5
MAX_FAILURES_PER_IP = 50
"""Much higher than the per-email limit, because one address is legitimately
many people — an office, a campus, any NAT — while one email is one person.
Its job is to stop credential stuffing across many accounts from one host, not
to police a single account, which the per-email limit already does."""

auth = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
    # Session tokens and identity, on every route here. `no_store` is attached to
    # the router rather than the routes so one added later cannot forget it.
    dependencies=[Depends(no_store)],
)

AccountsDep = Annotated[AccountsRepository, Depends(get_accounts)]

_limit_signup = rate_limit("signup", capacity=10, per_second=30 / 3600)
"""ADR-0029. Signup is the most expensive unauthenticated route in the project
and the login throttle does not cover it: `PasswordHasher()` at argon2id
defaults costs **64 MiB and 4 threads per call**, and every call that succeeds
also writes a durable `users` row. Ten in a burst, then thirty an hour.

A browser reaches this directly rather than through the reader's server-side
render, so unlike `/labels` and `/search` the address here really is one
person's (`params.py`). "One person" still overstates it, for the reason
`MAX_FAILURES_PER_IP` is set so much higher than the per-email limit: an
office or a campus is one address and many people. Thirty an hour is chosen to
be well clear of a room full of people signing up and nowhere near a budget
worth spending 64 MiB a time against."""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _client_ip(request: Request) -> str | None:
    """The caller's address, as far as the deployment can be made to tell it.

    Behind Caddy every request arrives from the proxy, so the socket peer is the
    same address for everyone and useless as a rate-limit key. Uvicorn is started
    with `--proxy-headers`, which rewrites `request.client` from
    `X-Forwarded-For`, so `request.client` is the value to read.

    What makes that value trustworthy is *not* uvicorn. Both compose files pass
    `--forwarded-allow-ips "*"`, and in that mode uvicorn takes the header's
    leftmost entry — which the client wrote. The guarantee comes from Caddy
    instead: `deploy/Caddyfile` sets `header_up X-Forwarded-For {remote_host}`,
    which *overwrites* the header with the real peer of that hop, so nothing a
    caller sends survives to be read here. Until that line existed this throttle
    was bypassable by sending one header (ADR-0029).

    Reading the raw header directly would be wrong for the same reason, and
    would not be improved by the Caddy change: it is right only because a proxy
    is guaranteed in front, and a direct `uv run uvicorn` for development has no
    such proxy. `request.client` degrades to the socket peer there, which is
    correct for that case.
    """
    return request.client.host if request.client else None


class SignupIn(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL_RE.match(value):
            raise ValueError("not a valid email address")
        return value


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str

    @classmethod
    def of(cls, user: UserRef) -> "UserOut":
        return cls(id=str(user.id), email=user.email)


def _set_session_cookies(
    response: Response, request: Request, token: str, csrf_token: str
) -> None:
    secure = cookies_are_secure(request)
    max_age = int(SESSION_TTL.total_seconds())
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax", secure=secure,
        max_age=max_age, path="/",
    )
    response.set_cookie(
        CSRF_COOKIE, csrf_token, httponly=False, samesite="lax", secure=secure,
        max_age=max_age, path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _start_session(
    user: UserRef, request: Request, response: Response, accounts: AccountsRepository
) -> None:
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = datetime.datetime.now(datetime.timezone.utc) + SESSION_TTL
    accounts.create_session(
        user_id=user.id, token_hash=_hash_token(token), csrf_token=csrf_token,
        expires_at=expires_at,
    )
    _set_session_cookies(response, request, token, csrf_token)


# ---------------------------------------------------------------- dependencies


def current_session(
    accounts: AccountsDep,
    usc_session: Annotated[str | None, Cookie()] = None,
) -> SessionRef | None:
    """None for "not logged in" — every route decides for itself whether that's
    an error (`require_user`) or just a fact to branch on."""
    if not usc_session:
        return None
    session = accounts.get_session(_hash_token(usc_session))
    if session is None:
        return None
    if session.expires_at < datetime.datetime.now(datetime.timezone.utc):
        # Expired rows were only ever ignored, never removed, so `auth_sessions`
        # grew without bound. Presenting an expired cookie is the moment we know
        # one exists, and it is a rare path, so the sweep costs nothing on the
        # requests that matter.
        accounts.delete_expired_sessions(
            now=datetime.datetime.now(datetime.timezone.utc)
        )
        return None
    return session


CurrentSessionDep = Annotated[SessionRef | None, Depends(current_session)]


def require_user(session: CurrentSessionDep) -> UserRef:
    if session is None:
        raise HTTPException(status_code=401, detail="login required")
    return session.user


RequireUserDep = Annotated[UserRef, Depends(require_user)]


def require_csrf(
    session: CurrentSessionDep,
    x_csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> None:
    """The double-submit check: the header must echo the session's own CSRF
    cookie value. A page on another origin can trigger the request but cannot
    read this cookie to put its value in the header."""
    if session is None:
        raise HTTPException(status_code=401, detail="login required")
    if not x_csrf_token or not secrets.compare_digest(x_csrf_token, session.csrf_token):
        raise HTTPException(status_code=403, detail="missing or invalid CSRF token")


RequireCsrfDep = Annotated[None, Depends(require_csrf)]


# --------------------------------------------------------------------- routes


@auth.post(
    "/signup",
    response_model=UserOut,
    status_code=201,
    dependencies=[Depends(_limit_signup)],
)
def signup(
    body: SignupIn, request: Request, response: Response, accounts: AccountsDep
) -> UserOut:
    password_hash = _hasher.hash(body.password)
    try:
        user = accounts.create_user(email=body.email, password_hash=password_hash)
    except DuplicateEmailError as exc:
        raise HTTPException(
            status_code=409, detail="an account with this email already exists"
        ) from exc
    _start_session(user, request, response, accounts)
    return UserOut.of(user)


@auth.post("/login", response_model=UserOut)
def login(
    body: LoginIn, request: Request, response: Response, accounts: AccountsDep
) -> UserOut:
    email = body.email.strip().lower()
    ip = _client_ip(request)
    now = datetime.datetime.now(datetime.timezone.utc)

    by_email, by_ip = accounts.count_recent_login_failures(
        email=email, ip=ip, since=now - LOGIN_WINDOW
    )
    if by_email >= MAX_FAILURES_PER_EMAIL or by_ip >= MAX_FAILURES_PER_IP:
        # 429 before the password is even looked at, so a throttled attacker
        # learns nothing from the response and spends no argon2 time of ours.
        raise HTTPException(
            status_code=429,
            detail="too many failed login attempts; try again later",
            headers={"Retry-After": str(int(LOGIN_WINDOW.total_seconds()))},
        )

    user = accounts.get_user_by_email(email)
    # An unknown email is verified against a dummy hash rather than returning
    # early. Identical wording is not enough when the two paths take measurably
    # different amounts of time — that difference is an enumeration oracle.
    stored = user.password_hash if user and user.password_hash else _DUMMY_HASH
    try:
        _hasher.verify(stored, body.password)
        authenticated = user is not None and user.password_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        authenticated = False

    if not authenticated or user is None:
        accounts.record_login_failure(email=email, ip=ip)
        # Same message either way: which part was wrong is not this API's business.
        raise HTTPException(status_code=401, detail="invalid email or password")

    assert user.password_hash is not None
    if _hasher.check_needs_rehash(user.password_hash):
        accounts.update_password_hash(user.id, _hasher.hash(body.password))
    # Someone who mistypes twice and then succeeds should not stay throttled.
    accounts.clear_login_failures(email=email, ip=ip)
    _start_session(user, request, response, accounts)
    return UserOut.of(user)


@auth.post("/logout", status_code=204)
def logout(
    response: Response,
    accounts: AccountsDep,
    session: CurrentSessionDep,
    _csrf: RequireCsrfDep,
) -> Response:
    if session is not None:
        accounts.delete_session(session.token_hash)
    _clear_session_cookies(response)
    return Response(status_code=204)


@auth.get("/me", response_model=UserOut)
def me(user: RequireUserDep) -> UserOut:
    return UserOut.of(user)
