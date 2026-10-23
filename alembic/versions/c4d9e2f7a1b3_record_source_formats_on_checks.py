"""Record the format each source page was served in on every check row.

`source_checks` and `classification_source_checks` gain `source_formats`, the
`ingest.source_formats` id of each page the check read (ADR-0094). Existing
rows get an empty list: nothing recorded which markup they read.

Revision ID: c4d9e2f7a1b3
Revises: a3f8c2d1e6b7
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c4d9e2f7a1b3"
down_revision = "a3f8c2d1e6b7"
branch_labels = None
depends_on = None

TABLES = ("source_checks", "classification_source_checks")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "source_formats",
                postgresql.ARRAY(sa.String()),
                nullable=False,
                server_default="{}",
            ),
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "source_formats")
