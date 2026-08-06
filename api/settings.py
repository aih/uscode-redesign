"""Per-user preferences: `/api/v1/settings` (PLAN §4).

One setting today — whether links open in a new tab — stored so it follows a
signed-in reader across devices instead of living in that device's
`localStorage` alone. Mirrors `api/watchlists.py`'s shape exactly: both routes
require a session (`RequireUserDep`), the state-changing one also requires the
double-submit CSRF header (`RequireCsrfDep`), and the router carries `no_store`
as a whole rather than per-route so a route added later cannot forget it — a
shared cache holding one reader's preferences and handing them to the next
reader is the same failure `params.no_store`'s docstring names for watchlists.

No `db.*` import, no SQL (CLAUDE.md architecture rule 1) — everything here goes
through `AccountsRepository` (storage/accounts.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import AccountsDep, RequireCsrfDep, RequireUserDep
from params import no_store
from storage.accounts import UserSettingsRef

settings = APIRouter(
    prefix="/api/v1/settings", tags=["settings"], dependencies=[Depends(no_store)]
)


class SettingsOut(BaseModel):
    open_links_in_new_tab: bool

    @classmethod
    def of(cls, ref: UserSettingsRef) -> "SettingsOut":
        return cls(open_links_in_new_tab=ref.open_links_in_new_tab)


class SettingsUpdateIn(BaseModel):
    open_links_in_new_tab: bool


@settings.get(
    "",
    response_model=SettingsOut,
    summary="This account's reading preferences",
)
def get_settings(user: RequireUserDep, accounts: AccountsDep) -> SettingsOut:
    """Defaults for a user who has never saved a preference — `get_settings`
    does not write, so reading this costs no row (storage/accounts.py)."""
    return SettingsOut.of(accounts.get_settings(user.id))


@settings.put(
    "",
    response_model=SettingsOut,
    summary="Change this account's reading preferences",
)
def update_settings(
    body: SettingsUpdateIn, user: RequireUserDep, accounts: AccountsDep, _csrf: RequireCsrfDep
) -> SettingsOut:
    return SettingsOut.of(
        accounts.update_settings(user.id, open_links_in_new_tab=body.open_links_in_new_tab)
    )
