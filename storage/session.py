"""Where a `Repository` comes from.

Storage owns the database session, so `api/` never has to hold one — it depends on
`get_repository` and receives the interface. That is what makes the XCiteDB swap a
one-line change here rather than an edit to every handler.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event, text
from sqlalchemy.orm import Session, sessionmaker

from db.base import engine
from db.config import settings
from storage.accounts import AccountsRepository
from storage.classification import ClassificationRepository
from storage.postgres import PostgresRepository
from storage.postgres_accounts import PostgresAccounts
from storage.postgres_classification import PostgresClassification
from storage.repository import Repository

# A sessionmaker of storage's own, over `db.base`'s engine. It exists to carry
# the listener below and nothing else: `db.base.SessionLocal` is what ingest
# uses, and ingest must not inherit these bounds — its bulk loads hold one
# transaction open across minutes of parsing by design (ADR-0073).
ApiSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# One round trip, two bounds, both scoped to the transaction rather than the
# connection — `set_config(..., true)` is `SET LOCAL`, so Postgres reverts them
# when the transaction ends and the connection goes back to the pool carrying
# nothing.
_BOUNDS = text(
    "SELECT set_config('statement_timeout', :statement, true),"
    "       set_config('idle_in_transaction_session_timeout', :idle, true)"
)


@event.listens_for(ApiSessionLocal, "after_begin")
def _bound_the_transaction(session: Session, transaction: object, connection: object) -> None:
    """Bound each transaction as it opens.

    `after_begin` and not the session's construction, because SQLAlchemy
    connects lazily and that laziness is worth keeping: a request the route
    rejects before it queries anything — an over-long `/api/v1/labels` batch,
    a malformed identifier — should not cost a connection to refuse.
    """
    connection.execute(  # type: ignore[attr-defined]
        _BOUNDS,
        {
            "statement": f"{settings.db_statement_timeout_ms}ms",
            "idle": f"{settings.db_idle_in_transaction_timeout_ms}ms",
        },
    )


@contextmanager
def bounded_session() -> Iterator[Session]:
    """A request-scoped session that cannot hold a connection indefinitely.

    The site went down on 2026-08-19 with fifteen Postgres backends — the whole
    pool — sitting `idle in transaction` on `ClientRead`, held by requests whose
    clients had long since gone. Nothing timed them out, so nothing recovered:
    each new request waited the pool's full timeout and then failed, for ten
    hours. `idle_in_transaction_session_timeout` is what ends that state, and
    `statement_timeout` is the same bound one step earlier, on a query that runs
    long rather than a transaction that stops running at all.
    """
    with ApiSessionLocal() as session:
        yield session


def get_repository() -> Iterator[Repository]:
    """Request-scoped repository. Wired into FastAPI as a dependency."""
    with bounded_session() as session:
        yield PostgresRepository(session)


def get_accounts() -> Iterator[AccountsRepository]:
    """Request-scoped accounts store — users, sessions, watchlists (PLAN §4)."""
    with bounded_session() as session:
        yield PostgresAccounts(session)


def get_classification() -> Iterator[ClassificationRepository]:
    """Request-scoped classification store — OLRC's Classification Tables (ADR-0067)."""
    with bounded_session() as session:
        yield PostgresClassification(session)
