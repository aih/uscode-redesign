"""Where a `Repository` comes from.

Storage owns the database session, so `api/` never has to hold one — it depends on
`get_repository` and receives the interface. That is what makes the XCiteDB swap a
one-line change here rather than an edit to every handler.
"""

from __future__ import annotations

from collections.abc import Iterator

from db.base import SessionLocal
from storage.postgres import PostgresRepository
from storage.repository import Repository


def get_repository() -> Iterator[Repository]:
    """Request-scoped repository. Wired into FastAPI as a dependency."""
    with SessionLocal() as session:
        yield PostgresRepository(session)
