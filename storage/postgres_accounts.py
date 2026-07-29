"""The Postgres `AccountsRepository` implementation — users, sessions, watchlists.

A sibling to `postgres.py`, not an extension of it: `PostgresRepository` is the
version-resolution `Repository` (CLAUDE.md architecture rule 1's `resolve_release`,
`get_section`, etc.); this file is ordinary CRUD over `users` / `auth_sessions` /
`watchlists` / `watchlist_items` and never touches a release point's content.
Both live under `storage/` so `api/` still holds no session and no SQL either
way (docs/adr/0017).
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import AuthSession, ReleasePoint, Title, User, Watchlist, WatchlistItem
from storage.accounts import (
    DuplicateEmailError,
    SessionRef,
    UnknownReleaseError,
    UnknownTitleError,
    UserRef,
    WatchlistItemRef,
    WatchlistRef,
)


def _user_ref(user: User) -> UserRef:
    return UserRef(
        id=user.id,
        email=user.email,
        password_hash=user.password_hash,
        created_at=user.created_at,
    )


class PostgresAccounts:
    """`AccountsRepository` over the Day-1 `users`/`watchlists` schema."""

    def __init__(self, session: Session):
        self._session = session

    # --------------------------------------------------------------- users

    def create_user(self, *, email: str, password_hash: str) -> UserRef:
        user = User(email=email, password_hash=password_hash)
        self._session.add(user)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateEmailError(email) from exc
        self._session.commit()
        return _user_ref(user)

    def get_user_by_email(self, email: str) -> UserRef | None:
        user = self._session.scalars(select(User).where(User.email == email)).first()
        return _user_ref(user) if user else None

    def get_user(self, user_id: uuid.UUID) -> UserRef | None:
        user = self._session.get(User, user_id)
        return _user_ref(user) if user else None

    def update_password_hash(self, user_id: uuid.UUID, password_hash: str) -> None:
        user = self._session.get(User, user_id)
        if user is None:
            return
        user.password_hash = password_hash
        self._session.commit()

    # ------------------------------------------------------------ sessions

    def create_session(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        csrf_token: str,
        expires_at: datetime.datetime,
    ) -> SessionRef:
        row = AuthSession(
            id=token_hash, user_id=user_id, csrf_token=csrf_token, expires_at=expires_at
        )
        self._session.add(row)
        self._session.commit()
        user = self._session.get(User, user_id)
        assert user is not None  # the caller just authenticated this user
        return SessionRef(
            token_hash=token_hash, csrf_token=csrf_token, expires_at=expires_at,
            user=_user_ref(user),
        )

    def get_session(self, token_hash: str) -> SessionRef | None:
        row = self._session.get(AuthSession, token_hash)
        if row is None:
            return None
        user = self._session.get(User, row.user_id)
        if user is None:  # pragma: no cover - a user row never disappears in practice
            return None
        return SessionRef(
            token_hash=row.id, csrf_token=row.csrf_token, expires_at=row.expires_at,
            user=_user_ref(user),
        )

    def delete_session(self, token_hash: str) -> None:
        row = self._session.get(AuthSession, token_hash)
        if row is not None:
            self._session.delete(row)
            self._session.commit()

    # ---------------------------------------------------------- watchlists

    def create_watchlist(self, *, user_id: uuid.UUID, name: str) -> WatchlistRef:
        row = Watchlist(user_id=user_id, name=name)
        self._session.add(row)
        self._session.commit()
        return WatchlistRef(id=row.id, user_id=row.user_id, name=row.name, item_count=0)

    def list_watchlists(self, user_id: uuid.UUID) -> list[WatchlistRef]:
        counts = dict(
            self._session.execute(
                select(WatchlistItem.watchlist_id, func.count())
                .join(Watchlist, Watchlist.id == WatchlistItem.watchlist_id)
                .where(Watchlist.user_id == user_id)
                .group_by(WatchlistItem.watchlist_id)
            ).all()
        )
        rows = self._session.scalars(
            select(Watchlist).where(Watchlist.user_id == user_id).order_by(Watchlist.id)
        )
        return [
            WatchlistRef(id=w.id, user_id=w.user_id, name=w.name, item_count=counts.get(w.id, 0))
            for w in rows
        ]

    def get_watchlist(self, watchlist_id: int) -> WatchlistRef | None:
        row = self._session.get(Watchlist, watchlist_id)
        if row is None:
            return None
        count = (
            self._session.scalar(
                select(func.count())
                .select_from(WatchlistItem)
                .where(WatchlistItem.watchlist_id == watchlist_id)
            )
            or 0
        )
        return WatchlistRef(id=row.id, user_id=row.user_id, name=row.name, item_count=count)

    def delete_watchlist(self, watchlist_id: int) -> None:
        self._session.execute(
            delete(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id)
        )
        row = self._session.get(Watchlist, watchlist_id)
        if row is not None:
            self._session.delete(row)
        self._session.commit()

    # ----------------------------------------------------------------- items

    def _item_ref(self, row: WatchlistItem) -> WatchlistItemRef:
        title = self._session.get(Title, row.title_id)
        pinned_label = None
        if row.pinned_release_id is not None:
            release = self._session.get(ReleasePoint, row.pinned_release_id)
            pinned_label = release.label if release else None
        return WatchlistItemRef(
            id=row.id,
            watchlist_id=row.watchlist_id,
            identifier=row.identifier,
            title_num=title.num if title else "",
            note=row.note,
            pinned_release_label=pinned_label,
            created_at=row.created_at,
        )

    def add_item(
        self,
        *,
        watchlist_id: int,
        identifier: str,
        title_num: str,
        note: str | None,
        pinned_release_label: str | None,
    ) -> WatchlistItemRef:
        title = self._session.scalars(select(Title).where(Title.num == title_num)).first()
        if title is None:
            raise UnknownTitleError(title_num)
        pinned_release_id = None
        if pinned_release_label is not None:
            release = self._session.scalars(
                select(ReleasePoint).where(ReleasePoint.label == pinned_release_label)
            ).first()
            if release is None:
                raise UnknownReleaseError(pinned_release_label)
            pinned_release_id = release.id
        row = WatchlistItem(
            watchlist_id=watchlist_id,
            identifier=identifier,
            title_id=title.id,
            note=note,
            pinned_release_id=pinned_release_id,
        )
        self._session.add(row)
        self._session.commit()
        return self._item_ref(row)

    def list_items(self, watchlist_id: int) -> list[WatchlistItemRef]:
        rows = self._session.scalars(
            select(WatchlistItem)
            .where(WatchlistItem.watchlist_id == watchlist_id)
            .order_by(WatchlistItem.created_at)
        )
        return [self._item_ref(r) for r in rows]

    def get_item(self, item_id: int) -> WatchlistItemRef | None:
        row = self._session.get(WatchlistItem, item_id)
        return self._item_ref(row) if row else None

    def update_item(
        self, item_id: int, *, note: str | None, pinned_release_label: str | None
    ) -> WatchlistItemRef | None:
        row = self._session.get(WatchlistItem, item_id)
        if row is None:
            return None
        row.note = note
        if pinned_release_label is not None:
            release = self._session.scalars(
                select(ReleasePoint).where(ReleasePoint.label == pinned_release_label)
            ).first()
            if release is None:
                raise UnknownReleaseError(pinned_release_label)
            row.pinned_release_id = release.id
        else:
            row.pinned_release_id = None
        self._session.commit()
        return self._item_ref(row)

    def delete_item(self, item_id: int) -> None:
        row = self._session.get(WatchlistItem, item_id)
        if row is not None:
            self._session.delete(row)
            self._session.commit()
