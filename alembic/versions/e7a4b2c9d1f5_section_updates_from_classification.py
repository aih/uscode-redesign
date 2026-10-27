"""Record title-releases built section by section from the classification tables.

`title_versions` gains `load_method` — `release-point` for a load of the title's
file, `sections` for one assembled by `python -m ingest sections-update` — and
`base_release_id`, the release point a `sections` load carried the unchanged
sections forward from (ADR-0095). Every existing row is a `release-point` load.

`section_update_items` is one row per (release point, section, public law) such a
load fetched: the classification or ECCT row that named the section, and what the
fetch found.

Revision ID: e7a4b2c9d1f5
Revises: c4d9e2f7a1b3
Create Date: 2026-10-27
"""

import sqlalchemy as sa

from alembic import op

revision = "e7a4b2c9d1f5"
down_revision = "c4d9e2f7a1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "title_versions",
        sa.Column(
            "load_method",
            sa.String(),
            nullable=False,
            server_default="release-point",
        ),
    )
    op.add_column(
        "title_versions",
        sa.Column(
            "base_release_id",
            sa.Integer(),
            sa.ForeignKey("release_points.id"),
            nullable=True,
        ),
    )
    op.create_table(
        "section_update_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("release_id", sa.Integer(), sa.ForeignKey("release_points.id"), nullable=False),
        sa.Column("title_id", sa.Integer(), sa.ForeignKey("titles.id"), nullable=False),
        sa.Column("identifier", sa.String(), nullable=False),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("sections.id"), nullable=True),
        sa.Column("pl_congress", sa.Integer(), nullable=True),
        sa.Column("pl_num", sa.Integer(), nullable=True),
        sa.Column("basis", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=True),
        sa.Column("is_note", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column(
            "section_version_id",
            sa.Integer(),
            sa.ForeignKey("section_versions.id"),
            nullable=True,
        ),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_section_update_items_release_title",
        "section_update_items",
        ["release_id", "title_id"],
    )
    op.create_index(
        "ix_section_update_items_law",
        "section_update_items",
        ["pl_congress", "pl_num"],
    )
    # A corpus table: a write moves the corpus generation (ADR-0078).
    op.execute(
        "CREATE TRIGGER section_update_items_bumps_corpus_generation"
        " AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON section_update_items"
        " FOR EACH STATEMENT EXECUTE FUNCTION usc_bump_corpus_generation()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS section_update_items_bumps_corpus_generation"
        " ON section_update_items"
    )
    op.drop_index("ix_section_update_items_law", table_name="section_update_items")
    op.drop_index("ix_section_update_items_release_title", table_name="section_update_items")
    op.drop_table("section_update_items")
    op.drop_column("title_versions", "base_release_id")
    op.drop_column("title_versions", "load_method")
