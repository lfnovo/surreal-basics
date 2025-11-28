"""Tests for sync repository functions."""

import pytest

from surreal_basics import (
    repo_create_sync,
    repo_delete_sync,
    repo_insert_sync,
    repo_query_sync,
    repo_relate_sync,
    repo_select_sync,
    repo_update_sync,
    repo_upsert_sync,
)

TEST_TABLE = "test_table"


@pytest.mark.integration
class TestRepoSync:
    """Sync repository function tests (require running SurrealDB)."""

    def test_repo_query_sync(self, surreal_config_ws, cleanup_table_sync):
        """Test basic query execution."""
        result = repo_query_sync(f"SELECT * FROM {TEST_TABLE}")
        assert isinstance(result, list)

    def test_repo_query_with_vars_sync(self, surreal_config_ws, cleanup_table_sync):
        """Test query with variables."""
        repo_create_sync(TEST_TABLE, {"name": "Test", "value": 42})
        result = repo_query_sync(
            f"SELECT * FROM {TEST_TABLE} WHERE value = $val",
            {"val": 42}
        )
        assert len(result) == 1
        assert result[0]["value"] == 42

    def test_repo_create_sync(self, surreal_config_ws, cleanup_table_sync):
        """Test record creation with timestamps."""
        record = repo_create_sync(TEST_TABLE, {"name": "Test User"})
        assert isinstance(record, (dict, list))
        if isinstance(record, list):
            record = record[0]
        assert "id" in record
        assert "created" in record
        assert "updated" in record
        assert record["name"] == "Test User"

    def test_repo_select_all_sync(self, surreal_config_ws, cleanup_table_sync):
        """Test selecting all records from table."""
        repo_create_sync(TEST_TABLE, {"name": "User 1"})
        repo_create_sync(TEST_TABLE, {"name": "User 2"})

        records = repo_select_sync(TEST_TABLE)
        assert isinstance(records, list)
        assert len(records) == 2

    def test_repo_select_by_id_sync(self, surreal_config_ws, cleanup_table_sync):
        """Test selecting a specific record by ID."""
        created = repo_create_sync(TEST_TABLE, {"name": "Specific User"})
        if isinstance(created, list):
            created = created[0]
        record_id = created["id"]

        record = repo_select_sync(record_id)
        # repo_select by ID returns dict directly (not a list)
        assert isinstance(record, dict)
        assert record["name"] == "Specific User"

    def test_repo_update_sync(self, surreal_config_ws, cleanup_table_sync):
        """Test record update."""
        created = repo_create_sync(TEST_TABLE, {"name": "Original"})
        if isinstance(created, list):
            created = created[0]
        record_id = created["id"]

        # Extract just the ID part
        id_part = record_id.split(":")[1] if ":" in record_id else record_id
        result = repo_update_sync(TEST_TABLE, id_part, {"name": "Updated"})

        assert len(result) == 1
        assert result[0]["name"] == "Updated"

    def test_repo_upsert_create_sync(self, surreal_config_ws, cleanup_table_sync):
        """Test upsert creates new record."""
        result = repo_upsert_sync(
            TEST_TABLE,
            f"{TEST_TABLE}:new_id",
            {"name": "New Record"}
        )
        assert len(result) == 1
        assert result[0]["name"] == "New Record"

    def test_repo_upsert_update_sync(self, surreal_config_ws, cleanup_table_sync):
        """Test upsert updates existing record."""
        repo_upsert_sync(TEST_TABLE, f"{TEST_TABLE}:upsert_test", {"name": "Original"})
        result = repo_upsert_sync(TEST_TABLE, f"{TEST_TABLE}:upsert_test", {"name": "Updated"})

        assert len(result) == 1
        assert result[0]["name"] == "Updated"

    def test_repo_delete_sync(self, surreal_config_ws, cleanup_table_sync):
        """Test record deletion."""
        created = repo_create_sync(TEST_TABLE, {"name": "To Delete"})
        if isinstance(created, list):
            created = created[0]
        record_id = created["id"]

        repo_delete_sync(record_id)

        records = repo_select_sync(TEST_TABLE)
        assert len(records) == 0

    def test_repo_insert_bulk_sync(self, surreal_config_ws, cleanup_table_sync):
        """Test bulk insert."""
        data = [
            {"name": "Bulk 1"},
            {"name": "Bulk 2"},
            {"name": "Bulk 3"},
        ]
        result = repo_insert_sync(TEST_TABLE, data)

        assert len(result) == 3
        records = repo_select_sync(TEST_TABLE)
        assert len(records) == 3

    def test_repo_relate_sync(self, surreal_config_ws, cleanup_table_sync):
        """Test creating relationships."""
        user1 = repo_create_sync(TEST_TABLE, {"name": "User 1"})
        user2 = repo_create_sync(TEST_TABLE, {"name": "User 2"})

        if isinstance(user1, list):
            user1 = user1[0]
        if isinstance(user2, list):
            user2 = user2[0]

        result = repo_relate_sync(
            user1["id"],
            "follows",
            user2["id"],
            {"since": "2024-01-01"}
        )

        assert len(result) == 1
        assert "since" in result[0]

        # Cleanup relationship table
        repo_query_sync("DELETE follows")
