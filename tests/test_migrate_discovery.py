"""Tests for migration discovery module (no DB required)."""

import pytest

from surreal_basics.migrate.discovery import (
    discover_migrations,
    parse_sql_file,
    scaffold_migration,
)


def test_discover_empty_directory(tmp_path):
    """Discover returns empty list for empty directory."""
    assert discover_migrations(tmp_path) == []


def test_discover_nonexistent_directory(tmp_path):
    """Discover returns empty list for nonexistent directory."""
    assert discover_migrations(tmp_path / "nope") == []


def test_discover_single_migration(tmp_path):
    """Discover finds a single up migration."""
    (tmp_path / "001_create_users.surrealql").write_text("DEFINE TABLE users;")

    result = discover_migrations(tmp_path)

    assert len(result) == 1
    assert result[0].version == 1
    assert result[0].name == "create_users"
    assert result[0].down_path is None


def test_discover_with_down_migration(tmp_path):
    """Discover pairs up and down migrations."""
    (tmp_path / "001_create_users.surrealql").write_text("DEFINE TABLE users;")
    (tmp_path / "001_create_users_down.surrealql").write_text("REMOVE TABLE users;")

    result = discover_migrations(tmp_path)

    assert len(result) == 1
    assert result[0].down_path is not None
    assert result[0].down_path.name == "001_create_users_down.surrealql"


def test_discover_multiple_sorted(tmp_path):
    """Discover returns migrations sorted by version."""
    (tmp_path / "003_add_indexes.surrealql").write_text("")
    (tmp_path / "001_create_users.surrealql").write_text("")
    (tmp_path / "002_add_fields.surrealql").write_text("")

    result = discover_migrations(tmp_path)

    assert len(result) == 3
    assert [m.version for m in result] == [1, 2, 3]
    assert [m.name for m in result] == ["create_users", "add_fields", "add_indexes"]


def test_discover_duplicate_version_raises(tmp_path):
    """Discover raises ValueError for duplicate versions."""
    (tmp_path / "001_create_users.surrealql").write_text("")
    (tmp_path / "001_other_thing.surrealql").write_text("")

    with pytest.raises(ValueError, match="Duplicate migration version 1"):
        discover_migrations(tmp_path)


def test_discover_ignores_non_matching_files(tmp_path):
    """Discover ignores files that don't match the pattern."""
    (tmp_path / "001_create_users.surrealql").write_text("")
    (tmp_path / "readme.txt").write_text("")
    (tmp_path / "no_number.surrealql").write_text("")

    result = discover_migrations(tmp_path)

    assert len(result) == 1


def test_parse_sql_file(tmp_path):
    """parse_sql_file reads file content."""
    path = tmp_path / "test.surrealql"
    path.write_text("DEFINE TABLE test;\nDEFINE FIELD name ON test TYPE string;")

    content = parse_sql_file(path)

    assert "DEFINE TABLE test;" in content
    assert "DEFINE FIELD name" in content


def test_scaffold_migration_first(tmp_path):
    """scaffold_migration creates the first migration pair."""
    up, down = scaffold_migration(tmp_path, "create_users")

    assert up.name == "001_create_users.surrealql"
    assert down.name == "001_create_users_down.surrealql"
    assert up.exists()
    assert down.exists()
    assert "001" in up.read_text()


def test_scaffold_migration_increments(tmp_path):
    """scaffold_migration increments version from existing migrations."""
    (tmp_path / "001_first.surrealql").write_text("")
    (tmp_path / "002_second.surrealql").write_text("")

    up, down = scaffold_migration(tmp_path, "third")

    assert up.name == "003_third.surrealql"
    assert down.name == "003_third_down.surrealql"


def test_scaffold_migration_creates_directory(tmp_path):
    """scaffold_migration creates the directory if it doesn't exist."""
    new_dir = tmp_path / "new" / "migrations"
    up, down = scaffold_migration(new_dir, "init")

    assert new_dir.exists()
    assert up.exists()
