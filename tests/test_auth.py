"""Integration tests for `/api/v1/auth/*` (PLAN §4, Day 5).

Needs a real Postgres — skips via `loaded_database` otherwise, the same bar
`test_api.py` sets, since a session is a real row rather than something a unit
test can stub without reimplementing `PostgresAccounts`. Each test gets its own
`fresh_client` (its own cookie jar) and its own random email, so runs never
collide with each other or with a previous run against the same database.
"""

import datetime
import uuid

import pytest

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"
PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def _clean_login_attempts():
    """Every test here shares one client address, so the per-IP failure counter
    accumulates across tests and across runs within its 15-minute window — a
    test that deliberately fails five logins would otherwise throttle whatever
    ran next. Each test starts from an empty table."""
    from db.base import SessionLocal
    from storage.postgres_accounts import PostgresAccounts

    def purge():
        with SessionLocal() as session:
            PostgresAccounts(session).purge_login_failures(
                before=datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(days=1)
            )

    purge()
    yield
    purge()


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


# ----------------------------------------------------------- rate limiting


def test_repeated_failures_are_throttled_with_429_and_retry_after(fresh_client):
    """ADR-0019. A delay, not a lockout: an account that could be locked by
    guessing badly at its address would make the defence into the attack."""
    _, email, _ = _signup(fresh_client)

    for _ in range(5):
        wrong = fresh_client.post(
            f"{AUTH}/login", json={"email": email, "password": "not the password"}
        )
        assert wrong.status_code == 401

    throttled = fresh_client.post(
        f"{AUTH}/login", json={"email": email, "password": PASSWORD}
    )

    assert throttled.status_code == 429
    assert int(throttled.headers["retry-after"]) > 0


def test_a_successful_login_clears_the_throttle(fresh_client):
    """Someone who mistypes twice and then gets it right is not left throttled."""
    _, email, _ = _signup(fresh_client)
    for _ in range(3):
        fresh_client.post(
            f"{AUTH}/login", json={"email": email, "password": "not the password"}
        )

    assert (
        fresh_client.post(
            f"{AUTH}/login", json={"email": email, "password": PASSWORD}
        ).status_code
        == 200
    )
    # …and the counter is back to zero, so the next slip is not the fifth.
    for _ in range(4):
        assert (
            fresh_client.post(
                f"{AUTH}/login", json={"email": email, "password": "wrong again"}
            ).status_code
            == 401
        )


def test_an_unknown_email_is_throttled_too(fresh_client):
    """Otherwise probing for which addresses exist is free — the throttle has to
    count attempts against addresses that were never registered."""
    unknown = _email()

    for _ in range(5):
        assert (
            fresh_client.post(
                f"{AUTH}/login", json={"email": unknown, "password": PASSWORD}
            ).status_code
            == 401
        )

    assert (
        fresh_client.post(
            f"{AUTH}/login", json={"email": unknown, "password": PASSWORD}
        ).status_code
        == 429
    )


def test_a_forged_x_forwarded_for_does_not_open_a_fresh_throttle_bucket(
    fresh_client, monkeypatch
):
    """ADR-0029. The per-IP limit exists to stop credential stuffing across many
    accounts from one host; a caller who can pick their own bucket by sending a
    header defeats exactly that case and nothing else.

    Each attempt uses a *different* address so the per-email limit (5) cannot be
    what fires, and `MAX_FAILURES_PER_IP` is lowered rather than met 50 times so
    the test costs three argon2 verifies instead of fifty.
    """
    import api.auth

    monkeypatch.setattr(api.auth, "MAX_FAILURES_PER_IP", 3)

    for _ in range(3):
        assert (
            fresh_client.post(
                f"{AUTH}/login", json={"email": _email(), "password": PASSWORD}
            ).status_code
            == 401
        )

    # A rotating header, which is the whole attack: one per attempt, all forged.
    throttled = fresh_client.post(
        f"{AUTH}/login",
        json={"email": _email(), "password": PASSWORD},
        headers={"X-Forwarded-For": "203.0.113.7"},
    )

    assert throttled.status_code == 429
    assert int(throttled.headers["retry-after"]) > 0


def test_the_recorded_address_never_comes_from_a_request_header(fresh_client):
    """The narrower statement behind the test above, asserted directly: nothing
    a caller sends reaches `login_attempts.ip`.

    In production Caddy overwrites X-Forwarded-For with the real peer
    (`deploy/Caddyfile`), and uvicorn's proxy-headers middleware — which is
    server-side, not part of the ASGI app — is what turns that into
    `request.client`. Neither is in the loop here, so what this pins is the
    application's own half: `api.auth._client_ip` reads `request.client` and
    never the raw header, so a forged value cannot become a bucket key or a
    stored row no matter how the proxy is configured.
    """
    from db.base import SessionLocal
    from db.models import LoginAttempt
    from sqlalchemy import select

    email = _email()
    forged = "198.51.100.4, evil.example, " + "A" * 200
    assert (
        fresh_client.post(
            f"{AUTH}/login",
            json={"email": email, "password": PASSWORD},
            headers={"X-Forwarded-For": forged},
        ).status_code
        == 401
    )

    with SessionLocal() as session:
        recorded = session.scalars(
            select(LoginAttempt.ip).where(LoginAttempt.email == email)
        ).all()

    assert recorded, "the failure was not recorded at all"
    for value in recorded:
        assert value != forged
        assert "evil.example" not in (value or "")
        # Whatever the address is, it is bounded — `LoginAttempt.ip` is an
        # unbounded String, so the clip is the storage boundary's job.
        assert len(value or "") <= 45


def test_an_unknown_email_and_a_wrong_password_are_indistinguishable(fresh_client):
    """Same status, same body — and the unknown-email path now runs argon2
    against a dummy hash so it is not measurably faster either."""
    _, email, _ = _signup(fresh_client)

    wrong_password = fresh_client.post(
        f"{AUTH}/login", json={"email": email, "password": "not the password"}
    )
    unknown_email = fresh_client.post(
        f"{AUTH}/login", json={"email": _email(), "password": PASSWORD}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


# --------------------------------------------------------- cookie security


def test_the_session_cookie_is_secure_behind_a_trusted_https_proxy(fresh_client):
    """The deploy bug this closes: `secure` used to come from the scheme uvicorn
    saw, which is http behind Caddy — so a TLS deployment would have shipped
    session cookies without `Secure`."""
    from params import cookie_settings

    original = cookie_settings.usc_cookie_secure
    cookie_settings.usc_cookie_secure = "true"
    try:
        response, _, _ = _signup(fresh_client)
        cookies = response.headers.get_list("set-cookie")
        assert all("Secure" in c for c in cookies), cookies
    finally:
        cookie_settings.usc_cookie_secure = original


def test_cookie_security_is_configuration_not_inference(fresh_client):
    """`auto` is what the tests run under: plain http, so no `Secure` — which is
    exactly why production sets it explicitly rather than trusting inference."""
    from params import cookie_settings

    assert cookie_settings.usc_cookie_secure == "auto"
    response, _, _ = _signup(fresh_client)

    cookies = response.headers.get_list("set-cookie")
    assert not any("Secure" in c for c in cookies)
