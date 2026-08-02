from db.models import Base

EXPECTED_TABLES = {
    "release_points",
    "titles",
    "title_versions",
    "sections",
    "structure_nodes",
    "section_versions",
    "section_release_map",
    "guid_map",
    "users",
    "watchlists",
    "watchlist_items",
    "auth_sessions",
    "login_attempts",
    "user_settings",
    "source_checks",
}


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
