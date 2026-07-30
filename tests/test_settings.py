"""Integration tests for `/api/v1/settings` (per-user preferences).

Uses `fresh_client` (its own cookie jar, its own random user per test) — same
fixture `test_watchlists.py` relies on for isolation, since a shared `client`
would let one test's saved preference leak into another's assertions.
"""

import uuid

import pytest

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"
SETTINGS = "/api/v1/settings"


def _signed_up(client) -> str:
    """Create a fresh user on `client` and return its CSRF token."""
    email = f"settings-test-{uuid.uuid4().hex}@example.com"
    response = client.post(
        f"{AUTH}/signup", json={"email": email, "password": "correct horse battery staple"}
    )
    assert response.status_code == 201
    return client.cookies.get("usc_csrf")


def _csrf_headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


# ------------------------------------------------------------- authorization


def test_get_settings_requires_login(fresh_client):
    assert fresh_client.get(SETTINGS).status_code == 401


def test_update_settings_requires_csrf(fresh_client):
    _signed_up(fresh_client)

    response = fresh_client.put(SETTINGS, json={"open_links_in_new_tab": False})

    assert response.status_code == 403


# -------------------------------------------------------------------- defaults


def test_defaults_are_returned_when_no_row_exists(fresh_client):
    _signed_up(fresh_client)

    response = fresh_client.get(SETTINGS)

    assert response.status_code == 200
    assert response.json() == {"open_links_in_new_tab": True}


def test_reading_settings_does_not_create_a_row(fresh_client):
    """`get_settings` must not write — a user who never changes anything should
    cost no row (storage/accounts.py's documented contract)."""
    from db.base import SessionLocal
    from db.models import UserSettings
    from sqlalchemy import func, select

    email = f"settings-test-{uuid.uuid4().hex}@example.com"
    signup = fresh_client.post(
        f"{AUTH}/signup", json={"email": email, "password": "correct horse battery staple"}
    )
    user_id = uuid.UUID(signup.json()["id"])

    fresh_client.get(SETTINGS)

    with SessionLocal() as session:
        count = session.scalar(
            select(func.count()).select_from(UserSettings).where(UserSettings.user_id == user_id)
        )
    assert count == 0


# --------------------------------------------------------- update then re-read


def test_update_then_read_back(fresh_client):
    csrf = _signed_up(fresh_client)

    updated = fresh_client.put(
        SETTINGS, json={"open_links_in_new_tab": False}, headers=_csrf_headers(csrf)
    )
    assert updated.status_code == 200
    assert updated.json() == {"open_links_in_new_tab": False}

    reread = fresh_client.get(SETTINGS)
    assert reread.json() == {"open_links_in_new_tab": False}


def test_update_is_a_true_upsert_second_call_also_works(fresh_client):
    csrf = _signed_up(fresh_client)

    fresh_client.put(SETTINGS, json={"open_links_in_new_tab": False}, headers=_csrf_headers(csrf))
    second = fresh_client.put(
        SETTINGS, json={"open_links_in_new_tab": True}, headers=_csrf_headers(csrf)
    )

    assert second.status_code == 200
    assert second.json() == {"open_links_in_new_tab": True}


# ------------------------------------------------------------------- validation


def test_update_rejects_a_non_boolean_body(fresh_client):
    csrf = _signed_up(fresh_client)

    response = fresh_client.put(
        SETTINGS, json={"open_links_in_new_tab": "not a bool"}, headers=_csrf_headers(csrf)
    )

    assert response.status_code == 422


# ----------------------------------------------------------------------- caching


def test_settings_responses_are_never_cached(fresh_client):
    csrf = _signed_up(fresh_client)

    get_response = fresh_client.get(SETTINGS)
    put_response = fresh_client.put(
        SETTINGS, json={"open_links_in_new_tab": False}, headers=_csrf_headers(csrf)
    )

    for response in (get_response, put_response):
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["vary"] == "Cookie"


def test_the_401_is_uncacheable_too(fresh_client):
    """The error path, which is the one that gets missed.

    `no_store` is a router dependency, and it writes to a response a raised
    `HTTPException` never returns — so a 401 leaves the router's header behind
    and is re-stamped by the handler in `main.py` from `params.PRIVATE_PREFIXES`.
    That tuple is a hand-maintained list of path prefixes, so a new private
    router is private only if someone remembered to add it. `/api/v1/settings`
    was not on it when the routes were written, and every assertion above still
    passed: they all check a 200.

    A cached 401 in a shared cache is served to the next reader, who is then
    told they are signed out while holding a valid session.
    """
    response = fresh_client.get(SETTINGS)

    assert response.status_code == 401
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Cookie"


# --------------------------------------------------------------------- isolation


def test_one_users_settings_are_invisible_to_another(fresh_client, client):
    """`client` (the shared, session-scoped fixture) is never logged in by any
    other test in this file, so it stands in for "a second, unrelated user" —
    here, specifically, an anonymous one."""
    csrf = _signed_up(fresh_client)
    fresh_client.put(SETTINGS, json={"open_links_in_new_tab": False}, headers=_csrf_headers(csrf))

    assert client.get(SETTINGS).status_code == 401  # `client` isn't logged in at all
