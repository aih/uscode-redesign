"""add classification tables

Revision ID: 3c8d9ab6d527
Revises: d5c81f27a930
Create Date: 2026-08-11 09:55:54.884943

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3c8d9ab6d527'
down_revision: Union[str, Sequence[str], None] = 'd5c81f27a930'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # OLRC's Classification Tables: which provision of which public law was
    # classified to which Code section. Four tables, all new, nothing existing
    # touched — see docs/classification-spec.md §2 and db.models.

    # One registry row per source document. (kind, congress, session) is unique
    # so a re-fetch updates in place; the 104th's whole-congress file uses
    # session 0 rather than NULL, which a unique index would not see.
    op.create_table(
        "classification_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("congress", sa.Integer(), nullable=False),
        sa.Column("session", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("source_filename", sa.String(), nullable=False),
        sa.Column("covered_laws_text", sa.Text(), nullable=True),
        sa.Column(
            "covered_ranges",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("first_law", sa.Integer(), nullable=True),
        sa.Column("last_law", sa.Integer(), nullable=True),
        sa.Column("prepared_date", sa.Date(), nullable=True),
        sa.Column("stat_volume", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("skipped_lines", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "congress", "session"),
    )

    # One poll of the tables index page, written on success and on failure. A
    # sibling of source_checks rather than a reuse: last_source_check() takes
    # the newest row regardless of source_url and feeds /api/v1/status.
    op.create_table(
        "classification_source_checks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("files_seen", sa.Integer(), nullable=True),
        sa.Column(
            "changed_files",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("latest_covered_text", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Every read is "the most recent one", so the ordering column is the index.
    op.create_index(
        "ix_classification_source_checks_checked_at",
        "classification_source_checks",
        ["checked_at"],
    )

    # One table row: a public-law provision and where it landed in the Code.
    # ondelete CASCADE because the load policy is wholesale replace per file.
    op.create_table(
        "classification_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("row_seq", sa.Integer(), nullable=False),
        sa.Column("raw_line", sa.Text(), nullable=False),
        sa.Column("title_raw", sa.String(), nullable=False),
        sa.Column("title_num", sa.String(), nullable=False),
        sa.Column("is_appendix", sa.Boolean(), nullable=False),
        sa.Column("section_raw", sa.String(), nullable=False),
        sa.Column("section_norm", sa.String(), nullable=False),
        sa.Column("description_raw", sa.String(), nullable=False),
        sa.Column("is_note", sa.Boolean(), nullable=False),
        sa.Column("action", sa.String(), nullable=True),
        sa.Column("transfer_counterpart", sa.String(), nullable=True),
        sa.Column("act_name", sa.String(), nullable=True),
        sa.Column("usc_identifier", sa.String(), nullable=True),
        sa.Column("pl_congress", sa.Integer(), nullable=True),
        sa.Column("pl_num", sa.Integer(), nullable=True),
        sa.Column("pl_section_raw", sa.String(), nullable=False),
        sa.Column("new_section_quote", sa.String(), nullable=True),
        sa.Column("stat_volume", sa.Integer(), nullable=True),
        sa.Column(
            "stat_pages",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'::integer[]"),
            nullable=False,
        ),
        # Verbatim tokens beside the integers: 110 Stat. 1321-9 is one page and not
        # a number, and 1,658 of the 104th's rows cite one.
        sa.Column(
            "stat_page_labels",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::character varying[]"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["file_id"], ["classification_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id", "row_seq"),
    )
    # "Everything Public Law 118-33 classified", in source order.
    op.create_index(
        "ix_classification_entries_pl_congress_pl_num_row_seq",
        "classification_entries",
        ["pl_congress", "pl_num", "row_seq"],
    )
    # "Everything ever classified to 42 U.S.C. 254c-15" — also the ?title=/
    # ?section= filters and the leading columns of the `code` sort.
    op.create_index(
        "ix_classification_entries_title_num_section_norm",
        "classification_entries",
        ["title_num", "section_norm"],
    )
    # The by-identifier route: a lookup on the derived path alone, which the
    # composite index above cannot serve.
    op.create_index(
        "ix_classification_entries_usc_identifier",
        "classification_entries",
        ["usc_identifier"],
    )

    # The Editorial Classification Change Table: a provision OLRC moved without
    # Congress amending it.
    op.create_table(
        "ecct_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("row_seq", sa.Integer(), nullable=False),
        sa.Column("former_raw", sa.String(), nullable=False),
        sa.Column("former_title_num", sa.String(), nullable=True),
        sa.Column("former_section_norm", sa.String(), nullable=True),
        sa.Column("former_is_note", sa.Boolean(), nullable=False),
        sa.Column("new_raw", sa.String(), nullable=False),
        sa.Column("new_title_num", sa.String(), nullable=True),
        sa.Column("new_section_norm", sa.String(), nullable=True),
        sa.Column("new_is_note", sa.Boolean(), nullable=False),
        sa.Column("provision_affected", sa.Text(), nullable=False),
        sa.Column("provision_prompting", sa.Text(), nullable=False),
        sa.Column("affected_pl_congress", sa.Integer(), nullable=True),
        sa.Column("affected_pl_num", sa.Integer(), nullable=True),
        sa.Column("prompting_pl_congress", sa.Integer(), nullable=True),
        sa.Column("prompting_pl_num", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["file_id"], ["classification_files.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # "What happened to this section", from either end of the move.
    op.create_index(
        "ix_ecct_entries_former_title_num_former_section_norm",
        "ecct_entries",
        ["former_title_num", "former_section_norm"],
    )
    op.create_index(
        "ix_ecct_entries_new_title_num_new_section_norm",
        "ecct_entries",
        ["new_title_num", "new_section_norm"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_ecct_entries_new_title_num_new_section_norm", table_name="ecct_entries"
    )
    op.drop_index(
        "ix_ecct_entries_former_title_num_former_section_norm", table_name="ecct_entries"
    )
    op.drop_table("ecct_entries")
    op.drop_index(
        "ix_classification_entries_usc_identifier", table_name="classification_entries"
    )
    op.drop_index(
        "ix_classification_entries_title_num_section_norm",
        table_name="classification_entries",
    )
    op.drop_index(
        "ix_classification_entries_pl_congress_pl_num_row_seq",
        table_name="classification_entries",
    )
    op.drop_table("classification_entries")
    op.drop_index(
        "ix_classification_source_checks_checked_at",
        table_name="classification_source_checks",
    )
    op.drop_table("classification_source_checks")
    op.drop_table("classification_files")
