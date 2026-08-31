"""add version change annotations

Revision ID: b6e1f0a2c9d4
Revises: 0044883c483c
Create Date: 2026-08-30

Phase V1 of docs/version-semantics-spec.md (ADR-0074): two nullable hash
columns on the content-deduped `section_versions` row — nullable so this
migration is trivial and existing rows are back-fillable by
`python -m ingest version-changes` — plus the two derived tables that classify
every version transition (`section_version_changes`) and attribute text
changes to Public Laws (`section_version_change_laws`). The dedupe key
(ADR-0007) is untouched.

`section_version_change_laws` deliberately carries no foreign key into
`classification_entries`, whose rows are deleted and re-inserted wholesale
when a source file changes.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

# revision identifiers, used by Alembic.
revision: str = 'b6e1f0a2c9d4'
down_revision: Union[str, Sequence[str], None] = '0044883c483c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "section_versions", sa.Column("text_hash", sa.LargeBinary(), nullable=True)
    )
    op.add_column(
        "section_versions", sa.Column("notes_hash", sa.LargeBinary(), nullable=True)
    )

    op.create_table(
        "section_version_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("sections.id"), nullable=False),
        sa.Column(
            "to_version_id",
            sa.Integer(),
            sa.ForeignKey("section_versions.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "from_version_id",
            sa.Integer(),
            sa.ForeignKey("section_versions.id"),
            nullable=True,
        ),
        sa.Column(
            "window_from_release_id",
            sa.Integer(),
            sa.ForeignKey("release_points.id"),
            nullable=True,
        ),
        sa.Column(
            "window_to_release_id",
            sa.Integer(),
            sa.ForeignKey("release_points.id"),
            nullable=False,
        ),
        sa.Column("change_kind", sa.String(), nullable=False),
        sa.Column("text_changed", sa.Boolean(), nullable=False),
        sa.Column("notes_changed", sa.Boolean(), nullable=False),
        sa.Column("heading_changed", sa.Boolean(), nullable=False),
        sa.Column("status_changed", sa.Boolean(), nullable=False),
        sa.Column("concurrent", sa.Boolean(), nullable=False),
        sa.Column("attribution", sa.String(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_section_version_changes_section_id", "section_version_changes", ["section_id"]
    )

    op.create_table(
        "section_version_change_laws",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "change_id",
            sa.Integer(),
            sa.ForeignKey("section_version_changes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pl_congress", sa.Integer(), nullable=False),
        sa.Column("pl_num", sa.Integer(), nullable=False),
        sa.Column("in_classification", sa.Boolean(), nullable=False),
        sa.Column("is_note_classification", sa.Boolean(), nullable=False),
        sa.Column("in_source_credit", sa.Boolean(), nullable=False),
        sa.Column("classification_actions", ARRAY(sa.String()), nullable=False),
        sa.UniqueConstraint("change_id", "pl_congress", "pl_num"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("section_version_change_laws")
    op.drop_index(
        "ix_section_version_changes_section_id", table_name="section_version_changes"
    )
    op.drop_table("section_version_changes")
    op.drop_column("section_versions", "notes_hash")
    op.drop_column("section_versions", "text_hash")
