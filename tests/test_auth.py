"""Integration tests for `/api/v1/auth/*` (PLAN §4, Day 5).

Needs a real Postgres — skips via `loaded_database` otherwise, the same bar
`test_api.py` sets, since a session is a real row rather than something a unit
test can stub without reimplementing `PostgresAccounts`. Each test gets its own
`fresh_client` (its own cookie jar) and its own random email, so runs never
collide with each other or with a previous run against the same database.
"""

import uuid

import pytest

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"
PASSWORD = "correct horse battery staple"


def _email() -> str:
    return f"auth-test-{uuid.uuid4().hex}@example.com"


def _signup(client, email=None, password=PASSWORD):
    email = email or _email()
    response = client.post(f"{AUTH}/signup", json={"email": email, "password": password})
    return response, email, password


# ------------------------------------------------------------------- signup


def test_signup_creates_a_user_and_starts_a_session(fresh_client):
    response, email, _ = _signup(fresh_client)

    assert response.status_code == 201
    assert response.json()["email"] == email
    assert uuid.UUID(response.json()["id"])  # a real user id, not echoed input


def test_signup_session_cookie_is_httponly_and_csrf_cookie_is_not(fresh_client):
    response, _, _ = _signup(fresh_client)

    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("usc_session="))
    csrf_cookie = next(c for c in cookies if c.startswith("usc_csrf="))

    assert "HttpOnly" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert fresh_client.cookies.get("usc_session")
    assert fresh_client.cookies.get("usc_csrf")


def test_signup_with_a_taken_email_is_409(fresh_client):
    _, email, _ = _signup(fresh_client)

    second = fresh_client.post(
        f"{AUTH}/signup", json={"email": email, "password": "a different password"}
    )

    assert second.status_code == 409


def test_signup_rejects_a_malformed_email(fresh_client):
    response = fresh_client.post(
        f"{AUTH}/signup", json={"email": "not-an-email", "password": PASSWORD}
    )
    assert response.status_code == 422


def test_signup_rejects_a_short_password(fresh_client):
    response = fresh_client.post(
        f"{AUTH}/signup", json={"email": _email(), "password": "short"}
    )
    assert response.status_code == 422


# -------------------------------------------------------------------- login


def test_login_with_correct_credentials_starts_a_session(fresh_client):
    _, email, password = _signup(fresh_client)
    fresh_client.cookies.clear()

    response = fresh_client.post(f"{AUTH}/login", json={"email": email, "password": password})

    assert response.status_code == 200
    assert response.json()["email"] == email
    assert fresh_client.cookies.get("usc_session")


def test_login_with_wrong_password_is_401(fresh_client):
    _, email, _ = _signup(fresh_client)
    fresh_client.cookies.clear()

    response = fresh_client.post(
        f"{AUTH}/login", json={"email": email, "password": "not the password"}
    )

    assert response.status_code == 401


def test_login_with_unknown_email_is_401_not_404(fresh_client):
    """Same status as a wrong password — confirming an email doesn't exist is a
    account-enumeration leak this API doesn't need to offer."""
    response = fresh_client.post(
        f"{AUTH}/login", json={"email": _email(), "password": PASSWORD}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------- me


def test_me_requires_a_session(fresh_client):
    assert fresh_client.get(f"{AUTH}/me").status_code == 401


def test_me_reflects_the_logged_in_user(fresh_client):
    _, email, _ = _signup(fresh_client)

    response = fresh_client.get(f"{AUTH}/me")

    assert response.status_code == 200
    assert response.json()["email"] == email


# -------------------------------------------------------------------- logout


def test_logout_requires_csrf_header(fresh_client):
    _signup(fresh_client)

    response = fresh_client.post(f"{AUTH}/logout")

    assert response.status_code == 403


def test_logout_revokes_the_session(fresh_client):
    _signup(fresh_client)
    csrf = fresh_client.cookies.get("usc_csrf")

    logout = fresh_client.post(f"{AUTH}/logout", headers={"X-CSRF-Token": csrf})
    assert logout.status_code == 204

    assert fresh_client.get(f"{AUTH}/me").status_code == 401


def test_logout_with_the_wrong_csrf_token_is_403(fresh_client):
    _signup(fresh_client)

    response = fresh_client.post(f"{AUTH}/logout", headers={"X-CSRF-Token": "not-the-token"})

    assert response.status_code == 403
    # the session survives a rejected logout
    assert fresh_client.get(f"{AUTH}/me").status_code == 200
