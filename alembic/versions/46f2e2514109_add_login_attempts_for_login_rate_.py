"""add login_attempts for login rate limiting

Revision ID: 46f2e2514109
Revises: c1f9a2b6d3e4
Create Date: 2026-07-28 23:19:02.465432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '46f2e2514109'
down_revision: Union[str, Sequence[str], None] = 'c1f9a2b6d3e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Every read is "this key, within this window" — the window belongs in the
    # index, not in a filter applied after it.
    op.create_index(
        "ix_login_attempts_email_created_at",
        "login_attempts",
        ["email", "created_at"],
    )
    op.create_index(
        "ix_login_attempts_ip_created_at", "login_attempts", ["ip", "created_at"]
    )
    # For the purge, which is by age alone.
    op.create_index("ix_login_attempts_created_at", "login_attempts", ["created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_login_attempts_created_at", table_name="login_attempts")
    op.drop_index("ix_login_attempts_ip_created_at", table_name="login_attempts")
    op.drop_index("ix_login_attempts_email_created_at", table_name="login_attempts")
    op.drop_table("login_attempts")
