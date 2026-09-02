"""record editorial reclassifications on attributed laws

Revision ID: c7e2a9f4b1d0
Revises: b6e1f0a2c9d4
Create Date: 2026-09-02

ADR-0077: `section_version_change_laws` gains two columns so a law the
Editorial Classification Change Table records as prompting a move into or out
of a section can be attributed to the transition that move produced. Both are
additive and derivable: `python -m ingest version-changes --reattribute`
fills them from the stored ECCT rows.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7e2a9f4b1d0'
down_revision: Union[str, Sequence[str], None] = 'b6e1f0a2c9d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "section_version_change_laws",
        sa.Column("in_ecct", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "section_version_change_laws",
        sa.Column("ecct_move", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("section_version_change_laws", "ecct_move")
    op.drop_column("section_version_change_laws", "in_ecct")
