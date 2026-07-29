"""Integration tests for `/api/v1/watchlist*` (PLAN §4, Day 5).

Uses `fresh_client` (its own cookie jar, its own random user per test) against
Title 16 loaded at 119-99 and 119-102not101, the same fixture facts
`test_api.py` relies on. `/us/usc/t16/s672` is `omitted` at 119-102not101
(`test_labels_carry_status_so_a_citation_can_be_badged`) — the known-status
section this file uses to prove a watchlist item's badge is real enrichment,
not just echoed input.
"""

import uuid

import pytest

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"
WATCHLIST = "/api/v1/watchlist"
WATCHLISTS = "/api/v1/watchlists"
SECTION = "/us/usc/t16/s45f"
OMITTED_SECTION = "/us/usc/t16/s672"


def _signed_up(client) -> str:
    """Create a fresh user on `client` and return its CSRF token."""
    email = f"watch-test-{uuid.uuid4().hex}@example.com"
    response = client.post(
        f"{AUTH}/signup", json={"email": email, "password": "correct horse battery staple"}
    )
    assert response.status_code == 201
    return client.cookies.get("usc_csrf")


def _csrf_headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


# ------------------------------------------------------------- authorization


def test_watchlist_requires_login(fresh_client):
    assert fresh_client.get(WATCHLIST).status_code == 401


def test_adding_an_item_requires_csrf(fresh_client):
    _signed_up(fresh_client)

    response = fresh_client.post(f"{WATCHLIST}/items", json={"identifier": SECTION})

    assert response.status_code == 403


# ----------------------------------------------------- the default watchlist


def test_default_watchlist_is_auto_created_as_my_provisions(fresh_client):
    _signed_up(fresh_client)

    response = fresh_client.get(WATCHLIST)

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "My Provisions"
    assert body["items"] == []


def test_add_item_then_it_appears_enriched_in_the_default_watchlist(fresh_client):
    csrf = _signed_up(fresh_client)

    added = fresh_client.post(
        f"{WATCHLIST}/items",
        json={"identifier": SECTION, "note": "keeping an eye on this"},
        headers=_csrf_headers(csrf),
    )
    assert added.status_code == 201
    item_id = added.json()["id"]

    listed = fresh_client.get(WATCHLIST).json()
    assert len(listed["items"]) == 1
    item = listed["items"][0]
    assert item["id"] == item_id
    assert item["identifier"] == SECTION
    assert item["note"] == "keeping an eye on this"
    # Enrichment: what the section currently says, not just the stored row.
    assert item["heading"] == "Mineral King Valley addition authorized"
    assert item["num"] == "§ 45f."


def test_watchlist_item_badges_the_sections_current_status(fresh_client):
    """The task this file is really here for: a watched section that has since
    gone repealed/omitted/transferred shows it, because the badge is a live
    `Repository.labels()` lookup, not a copy of the status at add time."""
    csrf = _signed_up(fresh_client)
    fresh_client.post(
        f"{WATCHLIST}/items", json={"identifier": OMITTED_SECTION}, headers=_csrf_headers(csrf)
    )

    listed = fresh_client.get(WATCHLIST).json()

    assert listed["items"][0]["status"] == "omitted"


def test_remove_item_from_default_watchlist(fresh_client):
    csrf = _signed_up(fresh_client)
    added = fresh_client.post(
        f"{WATCHLIST}/items", json={"identifier": SECTION}, headers=_csrf_headers(csrf)
    ).json()

    removed = fresh_client.delete(
        f"{WATCHLIST}/items/{added['id']}", headers=_csrf_headers(csrf)
    )
    assert removed.status_code == 204

    assert fresh_client.get(WATCHLIST).json()["items"] == []


def test_removing_an_item_requires_csrf(fresh_client):
    csrf = _signed_up(fresh_client)
    added = fresh_client.post(
        f"{WATCHLIST}/items", json={"identifier": SECTION}, headers=_csrf_headers(csrf)
    ).json()

    response = fresh_client.delete(f"{WATCHLIST}/items/{added['id']}")

    assert response.status_code == 403


def test_pinned_release_is_returned_and_used_for_enrichment(fresh_client):
    csrf = _signed_up(fresh_client)

    added = fresh_client.post(
        f"{WATCHLIST}/items",
        json={"identifier": SECTION, "pinned_release": "119-99"},
        headers=_csrf_headers(csrf),
    )
    assert added.status_code == 201
    assert added.json()["pinned_release_label"] == "119-99"

    listed = fresh_client.get(WATCHLIST).json()["items"][0]
    assert listed["pinned_release_label"] == "119-99"
    assert listed["heading"] == "Mineral King Valley addition authorized"


def test_add_item_with_unknown_title_is_404(fresh_client):
    csrf = _signed_up(fresh_client)

    response = fresh_client.post(
        f"{WATCHLIST}/items",
        json={"identifier": "/us/usc/t999/s1"},
        headers=_csrf_headers(csrf),
    )

    assert response.status_code == 404


def test_add_item_with_unknown_pinned_release_is_404(fresh_client):
    csrf = _signed_up(fresh_client)

    response = fresh_client.post(
        f"{WATCHLIST}/items",
        json={"identifier": SECTION, "pinned_release": "000-nope"},
        headers=_csrf_headers(csrf),
    )

    assert response.status_code == 404


def test_add_item_with_a_non_us_code_identifier_is_422(fresh_client):
    csrf = _signed_up(fresh_client)

    response = fresh_client.post(
        f"{WATCHLIST}/items", json={"identifier": "not-a-path"}, headers=_csrf_headers(csrf)
    )

    assert response.status_code == 422


# --------------------------------------------------------------- isolation


def test_one_users_watchlist_is_invisible_to_another(fresh_client, client):
    """`client` (the shared, session-scoped fixture) is never logged in by any
    other test in this file, so it stands in for "a second, unrelated user" —
    here, specifically, an anonymous one."""
    csrf = _signed_up(fresh_client)
    fresh_client.post(
        f"{WATCHLIST}/items", json={"identifier": SECTION}, headers=_csrf_headers(csrf)
    )

    # A generic watchlist id, guessed rather than looked up: another user's
    # default list is watchlist id 1 relative to nobody but them, so this just
    # has to be *some* id this test didn't create under `client`'s identity.
    default = fresh_client.get(WATCHLIST).json()
    other_clients_view = client.get(f"{WATCHLISTS}/{default['id']}/items")

    assert other_clients_view.status_code == 401  # `client` isn't logged in at all


# ------------------------------------------------------------ generic CRUD


def test_create_list_and_delete_a_named_watchlist(fresh_client):
    csrf = _signed_up(fresh_client)

    created = fresh_client.post(
        WATCHLISTS, json={"name": "Tax provisions"}, headers=_csrf_headers(csrf)
    )
    assert created.status_code == 201
    watchlist_id = created.json()["id"]

    listed = fresh_client.get(WATCHLISTS).json()
    assert any(w["id"] == watchlist_id and w["name"] == "Tax provisions" for w in listed)

    deleted = fresh_client.delete(f"{WATCHLISTS}/{watchlist_id}", headers=_csrf_headers(csrf))
    assert deleted.status_code == 204

    listed_after = fresh_client.get(WATCHLISTS).json()
    assert all(w["id"] != watchlist_id for w in listed_after)
