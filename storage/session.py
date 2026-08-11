"""Where a `Repository` comes from.

Storage owns the database session, so `api/` never has to hold one — it depends on
`get_repository` and receives the interface. That is what makes the XCiteDB swap a
one-line change here rather than an edit to every handler.
"""

from __future__ import annotations

from collections.abc import Iterator

from db.base import SessionLocal
from storage.accounts import AccountsRepository
from storage.classification import ClassificationRepository
from storage.postgres import PostgresRepository
from storage.postgres_accounts import PostgresAccounts
from storage.postgres_classification import PostgresClassification
from storage.repository import Repository


def get_repository() -> Iterator[Repository]:
    """Request-scoped repository. Wired into FastAPI as a dependency."""
    with SessionLocal() as session:
        yield PostgresRepository(session)


def get_accounts() -> Iterator[AccountsRepository]:
    """Request-scoped accounts store — users, sessions, watchlists (PLAN §4)."""
    with SessionLocal() as session:
        yield PostgresAccounts(session)


def get_classification() -> Iterator[ClassificationRepository]:
    """Request-scoped classification store — OLRC's Classification Tables (ADR-0067)."""
    with SessionLocal() as session:
        yield PostgresClassification(session)
