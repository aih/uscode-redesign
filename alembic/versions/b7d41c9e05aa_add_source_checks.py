"""add source_checks

Revision ID: b7d41c9e05aa
Revises: a2f0edc8f5e2
Create Date: 2026-08-02 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b7d41c9e05aa'
down_revision: Union[str, Sequence[str], None] = 'a2f0edc8f5e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # One row per poll of uscode.house.gov, written whether the poll succeeded
    # or not — see db.models.SourceCheck for why the failures are the point.
    op.create_table(
        "source_checks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("release_points_seen", sa.Integer(), nullable=True),
        sa.Column(
            "new_labels",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("latest_label", sa.String(), nullable=True),
        sa.Column("latest_currency_date", sa.Date(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Every read is "the most recent one", so the ordering column is the index.
    op.create_index("ix_source_checks_checked_at", "source_checks", ["checked_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_source_checks_checked_at", table_name="source_checks")
    op.drop_table("source_checks")
