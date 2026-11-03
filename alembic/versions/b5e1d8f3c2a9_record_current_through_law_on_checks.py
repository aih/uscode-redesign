"""Record the public law the source says the Code is current through.

`source_checks` gains `current_through_law` and `current_through_date`, read from
the sentence "The United States Code Online is current through Public Law
119-136 (October 22, 2026)." on the release-point pages. It can name a law
later than the newest release point when the laws after it changed no title.
Existing rows get NULL.

Revision ID: b5e1d8f3c2a9
Revises: e7a4b2c9d1f5
Create Date: 2026-11-03
"""

import sqlalchemy as sa

from alembic import op

revision = "b5e1d8f3c2a9"
down_revision = "e7a4b2c9d1f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_checks", sa.Column("current_through_law", sa.String(), nullable=True))
    op.add_column("source_checks", sa.Column("current_through_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("source_checks", "current_through_date")
    op.drop_column("source_checks", "current_through_law")
