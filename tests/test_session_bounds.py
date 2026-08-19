"""The API's database sessions are bounded; ingest's are not (ADR-0073).

On 2026-08-19 the site served nothing for about ten hours. The cause was not
load in any interesting sense — the box was at load average 0.73 and Postgres
was doing no work at all. It was that all fifteen connections in the pool were
held by backends sitting `idle in transaction` on `ClientRead`, for requests
whose clients had gone. Postgres will hold that state forever, so the pool
never recovered and every later request waited out `pool_timeout` and failed.

These tests are the bounds that end that state, and the boundary they respect:
ingest shares the same engine module in its own process and holds one
transaction open across minutes of parsing by design, so the bounds have to be
scoped to the transaction rather than set on the connection or the engine.
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from db.base import SessionLocal, engine
from db.config import settings
from storage.session import bounded_session


def _database_or_skip() -> None:
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
    except Exception as exc:  # pragma: no cover - depends on the machine
        from tests.conftest import _unavailable

        _unavailable(f"no database to bound a session against: {exc}")


@pytest.fixture()
def database() -> None:
    _database_or_skip()


def _settings_of(session) -> tuple[str, str]:
    return session.execute(
        text(
            "select current_setting('statement_timeout'),"
            "       current_setting('idle_in_transaction_session_timeout')"
        )
    ).one()


def test_an_api_session_carries_both_bounds(database: None) -> None:
    with bounded_session() as session:
        statement, idle = _settings_of(session)
    assert statement == f"{settings.db_statement_timeout_ms // 1000}s"
    assert idle == f"{settings.db_idle_in_transaction_timeout_ms // 1000}s"


def test_ingest_keeps_the_unbounded_budget_its_loads_need(database: None) -> None:
    """`db.base.SessionLocal` is ingest's door and must stay unbounded.

    A 20-second statement timeout on a bulk load is a corpus that will not
    load; the whole reason these bounds live in `storage/session.py` rather
    than on the engine is that the two callers want opposite things.
    """
    with SessionLocal() as session:
        assert _settings_of(session) == ("0", "0")


def test_the_bounds_do_not_follow_the_connection_back_into_the_pool(database: None) -> None:
    """`set_config(..., true)` is `SET LOCAL` — scoped to the transaction.

    Set on the connection instead, the first bounded request would silently
    bound every later ingest job that drew the same pooled connection.
    """
    with bounded_session() as session:
        _settings_of(session)
    with SessionLocal() as session:
        assert _settings_of(session) == ("0", "0")


def test_a_query_that_runs_too_long_is_cancelled(database: None) -> None:
    """The mechanism, against a bound short enough to wait for.

    The configured 20 seconds is asserted above; what this adds is that the
    setting is in force rather than merely reported, and it overrides the value
    locally so `make test` does not spend twenty seconds proving it.
    """
    with pytest.raises(DBAPIError, match="statement timeout"):
        with bounded_session() as session:
            session.execute(text("set local statement_timeout = '200ms'"))
            session.execute(text("select pg_sleep(5)"))


def test_a_transaction_left_idle_is_ended_by_postgres(database: None) -> None:
    """The failure of 2026-08-19, reproduced against a one-second bound.

    The real bound is 30 seconds and this test will not wait for it, so it
    overrides the setting inside the transaction the same way the listener
    does. What it proves is the mechanism: a session that queries and then
    stops does not keep its backend, and the next use of it raises rather
    than hanging.
    """
    with pytest.raises(DBAPIError, match="idle-in-transaction"):
        with bounded_session() as session:
            session.execute(text("set local idle_in_transaction_session_timeout = '200ms'"))
            session.execute(text("select 1"))
            time.sleep(1)
            session.execute(text("select 1"))


def test_the_pool_sheds_rather_than_queues(database: None) -> None:
    """A request that cannot get a connection fails fast.

    SQLAlchemy's default is a 30-second wait, which is longer than the proxy
    will hold a request open — so under exhaustion the site produced requests
    that occupied a worker thread for half a minute on behalf of a client that
    had already been given up on.
    """
    assert settings.db_pool_timeout <= 5
    assert engine.pool._timeout <= 5


def test_a_pool_timeout_becomes_a_storage_error(database: None) -> None:
    """Storage owns SQLAlchemy, so the surfaces never name its exceptions.

    `tests/test_architecture.py` enforces the import rule; this asserts the
    translation that makes obeying it possible.
    """
    from sqlalchemy.exc import TimeoutError as PoolTimeout

    from storage import RepositoryUnavailableError

    manager = bounded_session()
    manager.__enter__()
    with pytest.raises(RepositoryUnavailableError):
        manager.__exit__(PoolTimeout, PoolTimeout("QueuePool limit of size 10 overflow 20 reached"), None)


def test_pool_exhaustion_answers_503_rather_than_500() -> None:
    """Busy is not broken (ADR-0073).

    Unhandled, this is a 500 — which tells a caller the site is faulty when what
    is true is that it is full, and carries no `Retry-After`, so the caller's
    only guide is how long it feels like waiting.
    """
    from fastapi.testclient import TestClient

    from main import app
    from storage import RepositoryUnavailableError, get_repository

    def exhausted() -> None:
        raise RepositoryUnavailableError("QueuePool limit of size 10 overflow 20 reached")

    app.dependency_overrides[get_repository] = exhausted
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/us/usc/t16/s45f")
    finally:
        del app.dependency_overrides[get_repository]

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert "busy" in response.json()["detail"].lower()


def test_the_translation_reaches_the_handler_through_fastapi() -> None:
    """The join between the two tests above, asserted rather than assumed.

    The pool times out on the first query, which is inside the handler — so the
    exception has to travel *back* into the dependency's `yield`, be translated
    there, and then continue out to the app's exception handler. That FastAPI
    propagates an endpoint's exception into a yield-dependency, and routes what
    that dependency re-raises to `app.exception_handler`, is behaviour of the
    framework rather than of this code, and a version bump could take it away
    silently — leaving the 503 a 500 with every test above still green.
    """
    from contextlib import contextmanager

    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import TimeoutError as PoolTimeout

    from main import repository_unavailable
    from storage import RepositoryUnavailableError

    @contextmanager
    def bounded():
        try:
            yield "session"
        except PoolTimeout as exc:
            raise RepositoryUnavailableError(str(exc)) from exc

    def dependency():
        with bounded() as session:
            yield session

    app = FastAPI()
    app.add_exception_handler(RepositoryUnavailableError, repository_unavailable)

    @app.get("/boom")
    def boom(session: str = Depends(dependency)) -> None:
        raise PoolTimeout("QueuePool limit of size 10 overflow 20 reached")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
