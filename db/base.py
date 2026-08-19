from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from db.config import settings

# `pool_pre_ping` is not optional now that the API asks Postgres to terminate
# backends that sit idle in a transaction (ADR-0073): a terminated backend
# leaves a dead connection in the pool, and without the ping the next request
# to draw it is the one that discovers it. The ping costs a round trip on
# checkout and turns that into a transparent reconnect.
#
# `pool_recycle` bounds how long a connection lives at all, which is the
# ordinary defence against a connection killed by something further away than
# Postgres — a NAT table, a restarted database.
engine = create_engine(
    settings.database_url,
    future=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
