"""The `AccountsRepository` interface — users, sessions, and watchlists (PLAN §4).

A second, narrower interface alongside `Repository` (`storage/repository.py`).
None of what lives here is version-resolution logic — it is ordinary CRUD over
who a user is and what they are watching — so it does not belong on the
`Repository` protocol whose whole shape is "how do we answer for a provision at
a release point." What both share is CLAUDE.md architecture rule 1's real
requirement: no SQL and no database session in `api/`, so the interface here is
just as much the line the XCiteDB swap (or any other accounts store) would sit
behind. See docs/adr/0017 for why this is a second module rather than new
methods bolted onto `Repository`.

Password verification is deliberately *not* here: hashing/verifying is a pure
function of a string, not a database concern, and `api/auth.py` calls argon2
directly the same way it would call `json.loads` — this module only ever
stores and returns the hash.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Protocol


class AccountsError(Exception):
    """Base for the errors this interface raises rather than returning None."""


class DuplicateEmailError(AccountsError):
    """`users.email` is unique; signing up twice with one address is a 409."""

    def __init__(self, email: str):
        super().__init__(f"an account already exists for {email!r}")
        self.email = email


class UnknownTitleError(AccountsError):
    """A watchlist item named a title this database has never ingested."""

    def __init__(self, title_num: str):
        super().__init__(f"no such title: {title_num!r}")
        self.title_num = title_num


class UnknownReleaseError(AccountsError):
    """A pinned release must be an exact, already-published label — the release
    picker only ever offers real ones, so an unknown label means a stale link."""

    def __init__(self, label: str):
        super().__init__(f"no such release point: {label!r}")
        self.label = label


@dataclass(frozen=True, slots=True)
class UserRef:
    id: uuid.UUID
    email: str
    password_hash: str | None
    created_at: datetime.datetime


@dataclass(frozen=True, slots=True)
class SessionRef:
    """One logged-in session, joined to its user in the same read."""

    token_hash: str
    csrf_token: str
    expires_at: datetime.datetime
    user: UserRef


@dataclass(frozen=True, slots=True)
class WatchlistRef:
    id: int
    user_id: uuid.UUID
    name: str
    item_count: int = 0


@dataclass(frozen=True, slots=True)
class WatchlistItemRef:
    id: int
    watchlist_id: int
    identifier: str
    title_num: str
    note: str | None
    pinned_release_label: str | None
    created_at: datetime.datetime


class AccountsRepository(Protocol):
    """Everything `api/auth.py` and `api/watchlists.py` need. Implemented by
    `PostgresAccounts` today."""

    # --------------------------------------------------------------- users

    def create_user(self, *, email: str, password_hash: str) -> UserRef:
        """Raises `DuplicateEmailError` if the email is already registered."""
        ...

    def get_user_by_email(self, email: str) -> UserRef | None: ...

    def get_user(self, user_id: uuid.UUID) -> UserRef | None: ...

    def update_password_hash(self, user_id: uuid.UUID, password_hash: str) -> None:
        """Argon2's own parameters change over time; a successful login with an
        outdated hash is the natural moment to re-hash and save (`check_needs_rehash`)."""
        ...

    # ------------------------------------------------------- login attempts

    def record_login_failure(self, *, email: str, ip: str | None) -> None:
        """Remember one failed attempt, for both the email and the address.

        Only failures. A successful login calls `clear_login_failures`, so what
        is stored is the tail of an ongoing guessing run — not an audit log.
        """
        ...

    def count_recent_login_failures(
        self, *, email: str, ip: str | None, since: datetime.datetime
    ) -> tuple[int, int]:
        """Failures for this email, and failures from this address, since `since`.

        Two numbers rather than one because they defend against different
        attacks: counting only by email lets one host spray many accounts, and
        counting only by address lets a botnet grind one account.
        """
        ...

    def clear_login_failures(self, *, email: str, ip: str | None) -> None:
        """Forget this account's failures — called on a successful login, so a
        person who mistypes twice and then succeeds is not left throttled."""
        ...

    def purge_login_failures(self, *, before: datetime.datetime) -> int:
        """Drop attempts older than the window; returns how many went."""
        ...

    # ------------------------------------------------------------ sessions

    def create_session(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        csrf_token: str,
        expires_at: datetime.datetime,
    ) -> SessionRef: ...

    def get_session(self, token_hash: str) -> SessionRef | None:
        """None for both "no such session" and "the session's user vanished" —
        callers only ever need to know whether the session is usable."""
        ...

    def delete_session(self, token_hash: str) -> None: ...

    def delete_expired_sessions(self, *, now: datetime.datetime) -> int:
        """Rows past their expiry are already treated as absent on read; this is
        what actually removes them. Returns how many went."""
        ...

    # ---------------------------------------------------------- watchlists

    def create_watchlist(self, *, user_id: uuid.UUID, name: str) -> WatchlistRef: ...

    def list_watchlists(self, user_id: uuid.UUID) -> list[WatchlistRef]:
        """Oldest first — the reader's default list is `[0]`."""
        ...

    def get_watchlist(self, watchlist_id: int) -> WatchlistRef | None: ...

    def delete_watchlist(self, watchlist_id: int) -> None:
        """Also deletes the watchlist's items — nothing else references them."""
        ...

    # ----------------------------------------------------------------- items

    def add_item(
        self,
        *,
        watchlist_id: int,
        identifier: str,
        title_num: str,
        note: str | None,
        pinned_release_label: str | None,
    ) -> WatchlistItemRef:
        """Raises `UnknownTitleError` / `UnknownReleaseError` rather than storing
        a foreign key to nothing."""
        ...

    def list_items(self, watchlist_id: int) -> list[WatchlistItemRef]:
        """Oldest first — the order a user added them."""
        ...

    def get_item(self, item_id: int) -> WatchlistItemRef | None: ...

    def update_item(
        self,
        item_id: int,
        *,
        note: str | None,
        pinned_release_label: str | None,
    ) -> WatchlistItemRef | None:
        """Replaces both fields outright (PUT-like) — the surface is small enough
        that partial-update sentinels would cost more than they save."""
        ...

    def delete_item(self, item_id: int) -> None: ...
