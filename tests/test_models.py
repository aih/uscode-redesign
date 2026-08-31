from sqlalchemy import ARRAY, Integer, String

from db.models import Base

EXPECTED_TABLES = {
    "release_points",
    "titles",
    "title_versions",
    "sections",
    "structure_nodes",
    "section_versions",
    "section_version_changes",
    "section_version_change_laws",
    "section_release_map",
    "guid_map",
    "users",
    "watchlists",
    "watchlist_items",
    "auth_sessions",
    "login_attempts",
    "user_settings",
    "source_checks",
    "classification_files",
    "classification_entries",
    "ecct_entries",
    "classification_source_checks",
}

CLASSIFICATION_TABLES = {
    "classification_files",
    "classification_entries",
    "ecct_entries",
    "classification_source_checks",
}


def _unique_column_sets(table_name: str) -> set[tuple[str, ...]]:
    table = Base.metadata.tables[table_name]
    return {tuple(c.columns.keys()) for c in table.constraints if hasattr(c, "columns")}


def _index_columns(table_name: str) -> dict[str, tuple[str, ...]]:
    table = Base.metadata.tables[table_name]
    return {ix.name: tuple(ix.columns.keys()) for ix in table.indexes}


def test_all_plan_tables_registered() -> None:
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES


def test_sections_identifier_is_cross_release_identity() -> None:
    sections = Base.metadata.tables["sections"]
    assert "identifier" in sections.columns
    unique_cols = {tuple(c.columns.keys()) for c in sections.constraints if hasattr(c, "columns")}
    assert ("title_id", "identifier") in unique_cols


def test_guid_map_guid_is_primary_key() -> None:
    guid_map = Base.metadata.tables["guid_map"]
    assert [c.name for c in guid_map.primary_key.columns] == ["guid"]


# --- classification tables (docs/classification-spec.md §2) ---


def test_classification_files_has_the_specified_columns() -> None:
    columns = Base.metadata.tables["classification_files"].columns
    assert set(columns.keys()) == {
        "id",
        "kind",
        "congress",
        "session",
        "source_url",
        "source_filename",
        "covered_laws_text",
        "covered_ranges",
        "first_law",
        "last_law",
        "prepared_date",
        "stat_volume",
        "content_hash",
        "fetched_at",
        "row_count",
        "skipped_lines",
    }


def test_classification_files_is_unique_per_kind_congress_session() -> None:
    """A re-fetch updates the registry row in place, so (kind, congress,
    session) has to identify one — including the 104th, whose whole-congress
    file uses session 0 rather than NULL so the unique index can see it."""
    assert ("kind", "congress", "session") in _unique_column_sets("classification_files")
    session = Base.metadata.tables["classification_files"].columns["session"]
    assert not session.nullable


def test_classification_files_covered_ranges_is_an_array() -> None:
    covered = Base.metadata.tables["classification_files"].columns["covered_ranges"]
    assert isinstance(covered.type, ARRAY)
    assert isinstance(covered.type.item_type, String)


def test_classification_files_nullable_where_the_source_is_silent() -> None:
    columns = Base.metadata.tables["classification_files"].columns
    # ECCT files carry no covered-law header; the 104th's header names no volume.
    assert columns["covered_laws_text"].nullable
    assert columns["stat_volume"].nullable
    assert columns["prepared_date"].nullable
    assert not columns["content_hash"].nullable


def test_classification_entries_has_the_specified_columns() -> None:
    columns = Base.metadata.tables["classification_entries"].columns
    assert set(columns.keys()) == {
        "id",
        "file_id",
        "row_seq",
        "raw_line",
        "title_raw",
        "title_num",
        "is_appendix",
        "section_raw",
        "section_norm",
        "description_raw",
        "is_note",
        "action",
        "transfer_counterpart",
        "act_name",
        "usc_identifier",
        "pl_congress",
        "pl_num",
        "pl_section_raw",
        "new_section_quote",
        "stat_volume",
        "stat_pages",
        "stat_page_labels",
    }


def test_classification_entries_cascade_from_their_file() -> None:
    """Load policy is wholesale replace per file, so dropping a registry row
    must take its rows with it rather than orphaning them."""
    file_id = Base.metadata.tables["classification_entries"].columns["file_id"]
    fk = next(iter(file_id.foreign_keys))
    assert fk.column.table.name == "classification_files"
    assert fk.ondelete == "CASCADE"


def test_classification_entries_row_seq_is_unique_within_a_file() -> None:
    assert ("file_id", "row_seq") in _unique_column_sets("classification_entries")


def test_classification_entries_indexes_serve_the_three_lookup_shapes() -> None:
    assert _index_columns("classification_entries") == {
        "ix_classification_entries_pl_congress_pl_num_row_seq": (
            "pl_congress",
            "pl_num",
            "row_seq",
        ),
        "ix_classification_entries_title_num_section_norm": ("title_num", "section_norm"),
        "ix_classification_entries_usc_identifier": ("usc_identifier",),
    }


def test_classification_entries_title_num_is_a_string() -> None:
    """Gotcha 16: '5a' is a title and '5' is a different one, so a title number
    is never an integer and never an ORDER BY of its own."""
    title_num = Base.metadata.tables["classification_entries"].columns["title_num"]
    assert isinstance(title_num.type, String)
    assert not isinstance(title_num.type, Integer)


def test_classification_entries_keep_rows_that_did_not_fully_parse() -> None:
    """A row whose Pub. L. cell fails to parse is kept and warned about, and an
    appendix row derives no identifier by rule — both need a nullable column to
    land in."""
    columns = Base.metadata.tables["classification_entries"].columns
    assert columns["pl_congress"].nullable
    assert columns["pl_num"].nullable
    assert columns["usc_identifier"].nullable
    assert columns["action"].nullable


def test_classification_entries_raw_cells_are_not_null() -> None:
    """The raw cells are the source verbatim: a blank Description means
    'amended' and a blank Sec. means 'the whole law', so they are stored as ''
    rather than as NULL."""
    columns = Base.metadata.tables["classification_entries"].columns
    for name in ("raw_line", "title_raw", "section_raw", "description_raw", "pl_section_raw"):
        assert not columns[name].nullable, name


def test_classification_entries_stat_pages_is_an_integer_array() -> None:
    stat_pages = Base.metadata.tables["classification_entries"].columns["stat_pages"]
    assert isinstance(stat_pages.type, ARRAY)
    assert isinstance(stat_pages.type.item_type, Integer)


def test_classification_entries_keep_the_stat_cells_tokens_as_written() -> None:
    """110 Stat. 1321-9 is one page and not a number, and 1,658 of the 104th's
    11,737 rows cite one — so `stat_pages` alone loses their citation."""
    labels = Base.metadata.tables["classification_entries"].columns["stat_page_labels"]
    assert isinstance(labels.type, ARRAY)
    assert isinstance(labels.type.item_type, String)
    assert labels.nullable is False


def test_ecct_entries_has_the_specified_columns() -> None:
    columns = Base.metadata.tables["ecct_entries"].columns
    assert set(columns.keys()) == {
        "id",
        "file_id",
        "row_seq",
        "former_raw",
        "former_title_num",
        "former_section_norm",
        "former_is_note",
        "new_raw",
        "new_title_num",
        "new_section_norm",
        "new_is_note",
        "provision_affected",
        "provision_prompting",
        "affected_pl_congress",
        "affected_pl_num",
        "prompting_pl_congress",
        "prompting_pl_num",
    }


def test_ecct_entries_are_indexed_from_both_ends() -> None:
    assert _index_columns("ecct_entries") == {
        "ix_ecct_entries_former_title_num_former_section_norm": (
            "former_title_num",
            "former_section_norm",
        ),
        "ix_ecct_entries_new_title_num_new_section_norm": (
            "new_title_num",
            "new_section_norm",
        ),
    }


def test_ecct_entries_belong_to_a_classification_file() -> None:
    """The same two constraints `classification_entries` carries, for the same
    reason: the load policy is wholesale replace per file, so a re-load must not
    be able to double these rows and a deleted registry row must not orphan
    them (migration 0044883c483c)."""
    file_id = Base.metadata.tables["ecct_entries"].columns["file_id"]
    fk = next(iter(file_id.foreign_keys))
    assert fk.column.table.name == "classification_files"
    assert fk.ondelete == "CASCADE"
    assert ("file_id", "row_seq") in _unique_column_sets("ecct_entries")


def test_classification_source_checks_is_a_sibling_of_source_checks() -> None:
    """`last_source_check()` takes the newest `source_checks` row regardless of
    `source_url`, so classification polls get their own table rather than making
    /api/v1/status's corpus-freshness answer flap between two sources."""
    classification = Base.metadata.tables["classification_source_checks"]
    corpus = Base.metadata.tables["source_checks"]
    assert classification is not corpus
    assert set(classification.columns.keys()) == {
        "id",
        "checked_at",
        "source_url",
        "ok",
        "files_seen",
        "changed_files",
        "latest_covered_text",
        "error",
    }


def test_classification_source_checks_records_failures_too() -> None:
    columns = Base.metadata.tables["classification_source_checks"].columns
    # NULL on a failed check — the page never parsed, so there is no count.
    assert columns["files_seen"].nullable
    assert columns["error"].nullable
    assert not columns["ok"].nullable


def test_classification_source_checks_is_indexed_by_recency() -> None:
    assert _index_columns("classification_source_checks") == {
        "ix_classification_source_checks_checked_at": ("checked_at",),
    }


def test_classification_indexes_follow_the_house_naming_convention() -> None:
    for table_name in CLASSIFICATION_TABLES:
        for name, columns in _index_columns(table_name).items():
            assert name == f"ix_{table_name}_{'_'.join(columns)}", name
