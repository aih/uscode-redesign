"""Move seq_in_title and parent_identifier onto section_release_map

Reading order and parenthood are facts about (section, release point), not about
the text. `section_versions` is deduped on content (ADR-0007), so a row created at
one release point is reused by later ones — which froze both facts at the release
the text first appeared in. See ADR-0008.

The data moves with the columns rather than being rebuilt by re-ingest, so this
upgrade is safe on a populated database.

Revision ID: 9b1ce4ea7ddf
Revises: 1a045cde2094
Create Date: 2026-07-27 22:53:05.791958

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b1ce4ea7ddf'
down_revision: Union[str, Sequence[str], None] = '1a045cde2094'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("section_release_map", sa.Column("seq_in_title", sa.Integer(), nullable=True))
    op.add_column(
        "section_release_map", sa.Column("parent_identifier", sa.String(), nullable=True)
    )
    op.execute(
        """
        UPDATE section_release_map AS m
           SET seq_in_title = v.seq_in_title,
               parent_identifier = v.parent_identifier
          FROM section_versions AS v
         WHERE v.id = m.section_version_id
        """
    )
    op.alter_column("section_release_map", "seq_in_title", nullable=False)

    op.drop_index(op.f("ix_section_release_map_release_id"), table_name="section_release_map")
    op.create_index(
        "ix_section_release_map_release_id_seq",
        "section_release_map",
        ["release_id", "seq_in_title"],
    )
    op.create_index(
        "ix_section_release_map_parent",
        "section_release_map",
        ["release_id", "parent_identifier", "seq_in_title"],
    )

    op.drop_index(
        op.f("ix_section_versions_parent_identifier_seq"), table_name="section_versions"
    )
    op.drop_column("section_versions", "seq_in_title")
    op.drop_column("section_versions", "parent_identifier")


def downgrade() -> None:
    """Downgrade schema.

    Lossy by nature: one `section_versions` row is published by many release points
    with potentially different placements, and the old schema had room for one. The
    earliest release point's placement is restored — what the pre-migration ingest
    would have written.
    """
    op.add_column("section_versions", sa.Column("seq_in_title", sa.Integer(), nullable=True))
    op.add_column(
        "section_versions", sa.Column("parent_identifier", sa.String(), nullable=True)
    )
    op.execute(
        """
        UPDATE section_versions AS v
           SET seq_in_title = placement.seq_in_title,
               parent_identifier = placement.parent_identifier
          FROM (
            SELECT DISTINCT ON (m.section_version_id)
                   m.section_version_id, m.seq_in_title, m.parent_identifier
              FROM section_release_map AS m
              JOIN release_points AS r ON r.id = m.release_id
             ORDER BY m.section_version_id, r.seq
          ) AS placement
         WHERE placement.section_version_id = v.id
        """
    )
    op.execute("UPDATE section_versions SET seq_in_title = 0 WHERE seq_in_title IS NULL")
    op.alter_column("section_versions", "seq_in_title", nullable=False)
    op.create_index(
        op.f("ix_section_versions_parent_identifier_seq"),
        "section_versions",
        ["parent_identifier", "seq_in_title"],
    )

    op.drop_index("ix_section_release_map_parent", table_name="section_release_map")
    op.drop_index("ix_section_release_map_release_id_seq", table_name="section_release_map")
    op.create_index(
        op.f("ix_section_release_map_release_id"), "section_release_map", ["release_id"]
    )
    op.drop_column("section_release_map", "parent_identifier")
    op.drop_column("section_release_map", "seq_in_title")
