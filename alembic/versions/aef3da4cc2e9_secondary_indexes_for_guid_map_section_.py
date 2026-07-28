"""secondary indexes for guid_map, section_release_map, section_versions

Revision ID: aef3da4cc2e9
Revises: fce3a6c7a647
Create Date: 2026-07-27 21:22:06.790535

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aef3da4cc2e9'
down_revision: Union[str, Sequence[str], None] = 'fce3a6c7a647'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Reverse lookup: provision @ release point -> guid.
    op.create_index(
        "ix_guid_map_release_id_identifier",
        "guid_map",
        ["release_id", "identifier"],
    )
    # "Everything at this RP" scans. release_id is not the leading column of the
    # section_release_map PK, so it needs its own index.
    op.create_index(
        "ix_section_release_map_release_id",
        "section_release_map",
        ["release_id"],
    )
    # Version-timeline queries. The (section_id, content_hash, first_release_id)
    # unique constraint's index has content_hash between the two columns this
    # needs, so it doesn't serve (section_id, first_release_id) lookups.
    op.create_index(
        "ix_section_versions_section_id_first_release_id",
        "section_versions",
        ["section_id", "first_release_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_section_versions_section_id_first_release_id",
        table_name="section_versions",
    )
    op.drop_index("ix_section_release_map_release_id", table_name="section_release_map")
    op.drop_index("ix_guid_map_release_id_identifier", table_name="guid_map")
