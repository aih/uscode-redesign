"""Watchlist CRUD (PLAN §4): `/api/v1/watchlists` plus a `/api/v1/watchlist`
convenience singular the reader uses for its one "My Provisions" list and its
Watch button.

Two routers, on purpose:

  * **`/api/v1/watchlists`** — the general CRUD the schema supports: a user may
    have several named lists, each with items.
  * **`/api/v1/watchlist`** — the reader only ever needs "the current user's
    provisions," so it is handed a default list (auto-created as "My
    Provisions" on first use) rather than having to look up an id first.

Every route requires a logged-in session (`RequireUserDep`); every
state-changing one also requires the CSRF header (`RequireCsrfDep`). Ownership
is checked before every read or write on a specific watchlist/item — a
watchlist that exists but belongs to someone else answers 404, the same as one
that doesn't exist, so the response never confirms another user's data.

No `db.*` import, no SQL (CLAUDE.md architecture rule 1) — everything here goes
through `AccountsRepository` (storage/accounts.py) for user data and the
version-resolution `Repository` (storage/repository.py) only to enrich items
with what they currently say.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.auth import AccountsDep, RequireCsrfDep, RequireUserDep
from api.schemas import (
    WatchlistCreateIn,
    WatchlistItemCreateIn,
    WatchlistItemOut,
    WatchlistItemUpdateIn,
    WatchlistOut,
    WatchlistSummaryOut,
)
from params import RepositoryDep
from storage import (
    AmbiguousReleaseError,
    ReleaseNotFoundError,
    Repository,
    ResolvedRelease,
    TocEntry,
    UnknownReleaseError,
    UnknownTitleError,
    title_num_from_identifier,
)
from storage.accounts import AccountsRepository, UserRef, WatchlistItemRef, WatchlistRef

watchlists = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"])
default_watchlist = APIRouter(prefix="/api/v1/watchlist", tags=["watchlists"])

DEFAULT_NAME = "My Provisions"


def _owned_watchlist(
    watchlist_id: int, user_id, accounts: AccountsRepository
) -> WatchlistRef:
    watchlist = accounts.get_watchlist(watchlist_id)
    if watchlist is None or watchlist.user_id != user_id:
        raise HTTPException(status_code=404, detail=f"no watchlist {watchlist_id}")
    return watchlist


def _owned_item(
    watchlist_id: int, item_id: int, user_id, accounts: AccountsRepository
) -> WatchlistItemRef:
    _owned_watchlist(watchlist_id, user_id, accounts)
    item = accounts.get_item(item_id)
    if item is None or item.watchlist_id != watchlist_id:
        raise HTTPException(status_code=404, detail=f"no item {item_id}")
    return item


def _default_watchlist(user_id, accounts: AccountsRepository) -> WatchlistRef:
    existing = accounts.list_watchlists(user_id)
    if existing:
        return existing[0]
    return accounts.create_watchlist(user_id=user_id, name=DEFAULT_NAME)


def _enrich(items: list[WatchlistItemRef], repository: Repository) -> list[WatchlistItemOut]:
    """Current num/heading/status per item, batched per resolved release point —
    the same `labels()` call a section page uses for its citations, so a
    watchlist of forty provisions costs a handful of queries, not forty."""
    groups: dict[str, list[str]] = {}
    resolved_by_group: dict[str, ResolvedRelease] = {}
    resolved_for_item: dict[int, str | None] = {}

    for item in items:
        try:
            resolved = repository.resolve_release(
                label=item.pinned_release_label, title_num=item.title_num
            )
        except (ReleaseNotFoundError, AmbiguousReleaseError):
            resolved_for_item[item.id] = None
            continue
        key = resolved.release.label
        resolved_by_group[key] = resolved
        groups.setdefault(key, []).append(item.identifier)
        resolved_for_item[item.id] = key

    labels_by_group: dict[str, dict[str, TocEntry]] = {
        key: repository.labels(identifiers, resolved_by_group[key])
        for key, identifiers in groups.items()
    }

    out = []
    for item in items:
        key = resolved_for_item.get(item.id)
        entry = labels_by_group.get(key, {}).get(item.identifier) if key else None
        out.append(WatchlistItemOut.of(item, entry))
    return out


def _translate_item_error(exc: UnknownTitleError | UnknownReleaseError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


# ------------------------------------------------------------ generic CRUD


@watchlists.get("", response_model=list[WatchlistSummaryOut])
def list_watchlists(user: RequireUserDep, accounts: AccountsDep) -> list[WatchlistSummaryOut]:
    return [WatchlistSummaryOut.of(w) for w in accounts.list_watchlists(user.id)]


@watchlists.post("", response_model=WatchlistSummaryOut, status_code=201)
def create_watchlist(
    body: WatchlistCreateIn, user: RequireUserDep, accounts: AccountsDep, _csrf: RequireCsrfDep
) -> WatchlistSummaryOut:
    return WatchlistSummaryOut.of(accounts.create_watchlist(user_id=user.id, name=body.name))


@watchlists.delete("/{watchlist_id}", status_code=204)
def delete_watchlist(
    watchlist_id: int, user: RequireUserDep, accounts: AccountsDep, _csrf: RequireCsrfDep
) -> None:
    _owned_watchlist(watchlist_id, user.id, accounts)
    accounts.delete_watchlist(watchlist_id)


@watchlists.get("/{watchlist_id}/items", response_model=WatchlistOut)
def list_items(
    watchlist_id: int, user: RequireUserDep, accounts: AccountsDep, repository: RepositoryDep
) -> WatchlistOut:
    watchlist = _owned_watchlist(watchlist_id, user.id, accounts)
    items = accounts.list_items(watchlist_id)
    return WatchlistOut.of(watchlist, _enrich(items, repository))


@watchlists.post("/{watchlist_id}/items", response_model=WatchlistItemOut, status_code=201)
def add_item(
    watchlist_id: int,
    body: WatchlistItemCreateIn,
    user: RequireUserDep,
    accounts: AccountsDep,
    _csrf: RequireCsrfDep,
) -> WatchlistItemOut:
    return _add_item(watchlist_id, body, user, accounts)


@watchlists.patch("/{watchlist_id}/items/{item_id}", response_model=WatchlistItemOut)
def update_item(
    watchlist_id: int,
    item_id: int,
    body: WatchlistItemUpdateIn,
    user: RequireUserDep,
    accounts: AccountsDep,
    _csrf: RequireCsrfDep,
) -> WatchlistItemOut:
    _owned_item(watchlist_id, item_id, user.id, accounts)
    try:
        item = accounts.update_item(
            item_id, note=body.note, pinned_release_label=body.pinned_release
        )
    except UnknownReleaseError as exc:
        raise _translate_item_error(exc) from exc
    assert item is not None  # ownership just verified the row exists
    return WatchlistItemOut.of(item)


@watchlists.delete("/{watchlist_id}/items/{item_id}", status_code=204)
def delete_item(
    watchlist_id: int,
    item_id: int,
    user: RequireUserDep,
    accounts: AccountsDep,
    _csrf: RequireCsrfDep,
) -> None:
    _owned_item(watchlist_id, item_id, user.id, accounts)
    accounts.delete_item(item_id)


def _add_item(
    watchlist_id: int,
    body: WatchlistItemCreateIn,
    user: UserRef,
    accounts: AccountsRepository,
) -> WatchlistItemOut:
    _owned_watchlist(watchlist_id, user.id, accounts)
    title_num = title_num_from_identifier(body.identifier)
    if title_num is None:
        raise HTTPException(
            status_code=422, detail=f"{body.identifier!r} is not a US Code identifier"
        )
    try:
        item = accounts.add_item(
            watchlist_id=watchlist_id,
            identifier=body.identifier,
            title_num=title_num,
            note=body.note,
            pinned_release_label=body.pinned_release,
        )
    except (UnknownTitleError, UnknownReleaseError) as exc:
        raise _translate_item_error(exc) from exc
    return WatchlistItemOut.of(item)


# --------------------------------------------------- the reader's default list


@default_watchlist.get("", response_model=WatchlistOut)
def get_default_watchlist(
    user: RequireUserDep, accounts: AccountsDep, repository: RepositoryDep
) -> WatchlistOut:
    """"My Provisions": the current user's first watchlist, auto-created."""
    watchlist = _default_watchlist(user.id, accounts)
    items = accounts.list_items(watchlist.id)
    return WatchlistOut.of(watchlist, _enrich(items, repository))


@default_watchlist.post("/items", response_model=WatchlistItemOut, status_code=201)
def add_to_default_watchlist(
    body: WatchlistItemCreateIn,
    user: RequireUserDep,
    accounts: AccountsDep,
    _csrf: RequireCsrfDep,
) -> WatchlistItemOut:
    watchlist = _default_watchlist(user.id, accounts)
    return _add_item(watchlist.id, body, user, accounts)


@default_watchlist.delete("/items/{item_id}", status_code=204)
def remove_from_default_watchlist(
    item_id: int, user: RequireUserDep, accounts: AccountsDep, _csrf: RequireCsrfDep
) -> None:
    item = accounts.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"no item {item_id}")
    _owned_watchlist(item.watchlist_id, user.id, accounts)
    accounts.delete_item(item_id)
