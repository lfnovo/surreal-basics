"""Tests for async repository functions."""

import pytest

from surreal_basics import (
    repo_create,
    repo_delete,
    repo_insert,
    repo_query,
    repo_relate,
    repo_select,
    repo_update,
    repo_upsert,
)

TEST_TABLE = "test_table"


@pytest.mark.integration
@pytest.mark.asyncio
class TestRepoAsync:
    """Async repository function tests (require running SurrealDB)."""

    async def test_repo_query(self, surreal_config_ws, cleanup_table, async_cleanup):
        """Test basic query execution."""
        result = await repo_query(f"SELECT * FROM {TEST_TABLE}")
        assert isinstance(result, list)

    async def test_repo_query_with_vars(self, surreal_config_ws, cleanup_table, async_cleanup):
        """Test query with variables."""
        await repo_create(TEST_TABLE, {"name": "Test", "value": 42})
        result = await repo_query(
            f"SELECT * FROM {TEST_TABLE} WHERE value = $val",
            {"val": 42}
        )
        assert len(result) == 1
        assert result[0]["value"] == 42

    async def test_repo_create(self, surreal_config_ws, cleanup_table, async_cleanup):
        """Test record creation with timestamps."""
        record = await repo_create(TEST_TABLE, {"name": "Test User"})
        assert isinstance(record, (dict, list))
        if isinstance(record, list):
            record = record[0]
        assert "id" in record
        assert "created" in record
        assert "updated" in record
        assert record["name"] == "Test User"

    async def test_repo_select_all(self, surreal_config_ws, cleanup_table, async_cleanup):
        """Test selecting all records from table."""
        await repo_create(TEST_TABLE, {"name": "User 1"})
        await repo_create(TEST_TABLE, {"name": "User 2"})

        records = await repo_select(TEST_TABLE)
        assert isinstance(records, list)
        assert len(records) == 2

    async def test_repo_select_by_id(self, surreal_config_ws, cleanup_table, async_cleanup):
        """Test selecting a specific record by ID."""
        created = await repo_create(TEST_TABLE, {"name": "Specific User"})
        if isinstance(created, list):
            created = created[0]
        record_id = created["id"]

        record = await repo_select(record_id)
        # repo_select by ID returns dict directly (not a list)
        assert isinstance(record, dict)
        assert record["name"] == "Specific User"

    async def test_repo_update(self, surreal_config_ws, cleanup_table, async_cleanup):
        """Test record update."""
        created = await repo_create(TEST_TABLE, {"name": "Original"})
        if isinstance(created, list):
            created = created[0]
        record_id = created["id"]

        # Extract just the ID part
        id_part = record_id.split(":")[1] if ":" in record_id else record_id
        result = await repo_update(TEST_TABLE, id_part, {"name": "Updated"})

        assert len(result) == 1
        assert result[0]["name"] == "Updated"

    async def test_repo_upsert_create(self, surreal_config_ws, cleanup_table, async_cleanup):
        """Test upsert creates new record."""
        result = await repo_upsert(
            TEST_TABLE,
            f"{TEST_TABLE}:new_id",
            {"name": "New Record"}
        )
        assert len(result) == 1
        assert result[0]["name"] == "New Record"

    async def test_repo_upsert_update(self, surreal_config_ws, cleanup_table, async_cleanup):
        """Test upsert updates existing record."""
        await repo_upsert(TEST_TABLE, f"{TEST_TABLE}:upsert_test", {"name": "Original"})
        result = await repo_upsert(TEST_TABLE, f"{TEST_TABLE}:upsert_test", {"name": "Updated"})

        assert len(result) == 1
        assert result[0]["name"] == "Updated"

    async def test_repo_delete(self, surreal_config_ws, cleanup_table, async_cleanup):
        """Test record deletion."""
        created = await repo_create(TEST_TABLE, {"name": "To Delete"})
        if isinstance(created, list):
            created = created[0]
        record_id = created["id"]

        await repo_delete(record_id)

        records = await repo_select(TEST_TABLE)
        assert len(records) == 0

    async def test_repo_insert_bulk(self, surreal_config_ws, cleanup_table, async_cleanup):
        """Test bulk insert."""
        data = [
            {"name": "Bulk 1"},
            {"name": "Bulk 2"},
            {"name": "Bulk 3"},
        ]
        result = await repo_insert(TEST_TABLE, data)

        assert len(result) == 3
        records = await repo_select(TEST_TABLE)
        assert len(records) == 3

    async def test_repo_relate(self, surreal_config_ws, cleanup_table, async_cleanup):
        """Test creating relationships."""
        user1 = await repo_create(TEST_TABLE, {"name": "User 1"})
        user2 = await repo_create(TEST_TABLE, {"name": "User 2"})

        if isinstance(user1, list):
            user1 = user1[0]
        if isinstance(user2, list):
            user2 = user2[0]

        result = await repo_relate(
            user1["id"],
            "follows",
            user2["id"],
            {"since": "2024-01-01"}
        )

        assert len(result) == 1
        assert "since" in result[0]

        # Cleanup relationship table
        await repo_query("DELETE follows")
