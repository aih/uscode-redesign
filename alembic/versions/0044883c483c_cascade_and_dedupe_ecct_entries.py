"""cascade and dedupe ecct_entries

Revision ID: 0044883c483c
Revises: 3c8d9ab6d527
Create Date: 2026-08-11 14:22:41.108733

`3c8d9ab6d527` gave `classification_entries` an `ondelete="CASCADE"` foreign key
and `UniqueConstraint(file_id, row_seq)` and gave `ecct_entries` neither, because
the spec specified both for one table and said nothing about the other. The load
policy is wholesale replace per file (ADR-0067 decision 3), which needs both:
without the cascade a deleted registry row leaves orphan ECCT rows, and without
the unique constraint nothing in the database stops a re-load doubling them.

The constraint names are the ones Postgres generates for the unnamed constraints
on the sibling table, so both tables read the same in `\\d`.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0044883c483c'
down_revision: Union[str, Sequence[str], None] = '3c8d9ab6d527'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        "ecct_entries_file_id_row_seq_key", "ecct_entries", ["file_id", "row_seq"]
    )
    op.drop_constraint("ecct_entries_file_id_fkey", "ecct_entries", type_="foreignkey")
    op.create_foreign_key(
        "ecct_entries_file_id_fkey",
        "ecct_entries",
        "classification_files",
        ["file_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ecct_entries_file_id_fkey", "ecct_entries", type_="foreignkey")
    op.create_foreign_key(
        "ecct_entries_file_id_fkey",
        "ecct_entries",
        "classification_files",
        ["file_id"],
        ["id"],
    )
    op.drop_constraint("ecct_entries_file_id_row_seq_key", "ecct_entries", type_="unique")
