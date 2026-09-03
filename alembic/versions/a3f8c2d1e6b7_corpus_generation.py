"""A corpus generation counter, bumped by triggers on every corpus table.

One row in `corpus_state`, and a statement-level `AFTER INSERT OR UPDATE OR
DELETE OR TRUNCATE` trigger on each table the API reads for corpus data. The
bump runs inside the writer's own transaction, so it commits with the write or
not at all — the property ADR-0078's cache keys rest on. Ingest needs no code
change: the database itself is the ledger.

The account tables (`users`, `auth_sessions`, `watchlists`, `watchlist_items`,
`user_settings`, `login_attempts`) are deliberately absent — everything behind
them is `no-store` and never cached, and their writes are per-request, which
would empty the cache on every login.

Revision ID: a3f8c2d1e6b7
Revises: b6e1f0a2c9d4
Create Date: 2026-09-02
"""

from alembic import op

revision = "a3f8c2d1e6b7"
down_revision = "b6e1f0a2c9d4"
branch_labels = None
depends_on = None

# Every table `PostgresRepository` and `PostgresClassification` read. A table
# added later must be added here (or in a successor migration) the moment a
# cached route reads it.
CORPUS_TABLES = (
    "release_points",
    "source_checks",
    "titles",
    "title_versions",
    "sections",
    "section_versions",
    "section_release_map",
    "guid_map",
    "structure_nodes",
    "section_version_changes",
    "section_version_change_laws",
    "classification_files",
    "classification_entries",
    "ecct_entries",
    "classification_source_checks",
)


def upgrade() -> None:
    op.execute(
        "CREATE TABLE corpus_state ("
        "  id integer PRIMARY KEY CHECK (id = 1),"
        "  generation bigint NOT NULL"
        ")"
    )
    op.execute("INSERT INTO corpus_state (id, generation) VALUES (1, 1)")
    op.execute(
        "CREATE OR REPLACE FUNCTION usc_bump_corpus_generation()"
        " RETURNS trigger LANGUAGE plpgsql AS $$"
        " BEGIN"
        "   UPDATE corpus_state SET generation = generation + 1 WHERE id = 1;"
        "   RETURN NULL;"
        " END $$"
    )
    for table in CORPUS_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_bumps_corpus_generation"
            f" AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON {table}"
            f" FOR EACH STATEMENT EXECUTE FUNCTION usc_bump_corpus_generation()"
        )


def downgrade() -> None:
    for table in CORPUS_TABLES:
        op.execute(
            f"DROP TRIGGER IF EXISTS {table}_bumps_corpus_generation ON {table}"
        )
    op.execute("DROP FUNCTION IF EXISTS usc_bump_corpus_generation()")
    op.execute("DROP TABLE corpus_state")
