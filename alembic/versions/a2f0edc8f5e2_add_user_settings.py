"""add user settings

Revision ID: a2f0edc8f5e2
Revises: 46f2e2514109
Create Date: 2026-07-30 16:41:57.403922

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2f0edc8f5e2'
down_revision: Union[str, Sequence[str], None] = '46f2e2514109'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # `user_id` is the primary key, not a separate id — this table only ever
    # has one row per user, so a surrogate id would carry no information the
    # foreign key doesn't already. CASCADE so deleting an account doesn't leave
    # an orphaned preferences row behind for `verify` to explain later.
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("open_links_in_new_tab", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("user_settings")
