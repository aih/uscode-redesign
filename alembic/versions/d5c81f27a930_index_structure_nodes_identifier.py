"""index structure_nodes.identifier

Every spine query that resolves a path — `get_section`, both `get_toc` paths and
`resolve_id` — looks a node up by `identifier` alone. The only index that
covered the column was the `(title_id, identifier)` unique constraint, and a
composite index cannot serve a predicate on its second column, so each of those
lookups sequentially scanned the whole table.

Measured on the deployed corpus before this migration
(`docs/verification/spine-explain.json`, task B3): a Seq Scan over 9,916 rows at
1.3 ms, which was 80% of `get_section`'s 1.6 ms of database time and recurred
two or three times per section view.

Revision ID: d5c81f27a930
Revises: b7d41c9e05aa
Create Date: 2026-08-04

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5c81f27a930"
down_revision: Union[str, Sequence[str], None] = "b7d41c9e05aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_structure_nodes_identifier",
        "structure_nodes",
        ["identifier"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_structure_nodes_identifier", table_name="structure_nodes")
