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
        # SurrealDB 3.x errors on reads of an undefined table; create one first.
        await repo_create(TEST_TABLE, {"name": "seed"})
        result = await repo_query(f"SELECT * FROM {TEST_TABLE}")
        assert isinstance(result, list)

    async def test_repo_query_with_vars(
        self, surreal_config_ws, cleanup_table, async_cleanup
    ):
        """Test query with variables."""
        await repo_create(TEST_TABLE, {"name": "Test", "value": 42})
        result = await repo_query(
            f"SELECT * FROM {TEST_TABLE} WHERE value = $val", {"val": 42}
        )
        assert len(result) == 1
        assert result[0]["value"] == 42

    async def test_repo_create(self, surreal_config_ws, cleanup_table, async_cleanup):
        """Test record creation does not inject timestamps by default."""
        record = await repo_create(TEST_TABLE, {"name": "Test User"})
        assert isinstance(record, (dict, list))
        if isinstance(record, list):
            record = record[0]
        assert "id" in record
        assert "created" not in record
        assert "updated" not in record
        assert record["name"] == "Test User"

    async def test_repo_create_with_timestamps(
        self, surreal_config_ws, cleanup_table, async_cleanup
    ):
        """Test record creation with opt-in timestamps."""
        record = await repo_create(
            TEST_TABLE, {"name": "Test User"}, add_timestamps=True
        )
        if isinstance(record, list):
            record = record[0]
        assert "created" in record
        assert "updated" in record

    async def test_repo_create_strips_id(
        self, surreal_config_ws, cleanup_table, async_cleanup
    ):
        """Test that an 'id' key in data is stripped before insert."""
        record = await repo_create(TEST_TABLE, {"id": "ignored", "name": "No ID"})
        if isinstance(record, list):
            record = record[0]
        assert record["name"] == "No ID"
        assert str(record["id"]) != f"{TEST_TABLE}:ignored"

    async def test_repo_select_all(
        self, surreal_config_ws, cleanup_table, async_cleanup
    ):
        """Test selecting all records from table."""
        await repo_create(TEST_TABLE, {"name": "User 1"})
        await repo_create(TEST_TABLE, {"name": "User 2"})

        records = await repo_select(TEST_TABLE)
        assert isinstance(records, list)
        assert len(records) == 2

    async def test_repo_select_by_id(
        self, surreal_config_ws, cleanup_table, async_cleanup
    ):
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

    async def test_repo_upsert_create(
        self, surreal_config_ws, cleanup_table, async_cleanup
    ):
        """Test upsert creates new record."""
        result = await repo_upsert(
            TEST_TABLE, f"{TEST_TABLE}:new_id", {"name": "New Record"}
        )
        assert len(result) == 1
        assert result[0]["name"] == "New Record"

    async def test_repo_upsert_update(
        self, surreal_config_ws, cleanup_table, async_cleanup
    ):
        """Test upsert updates existing record."""
        await repo_upsert(TEST_TABLE, f"{TEST_TABLE}:upsert_test", {"name": "Original"})
        result = await repo_upsert(
            TEST_TABLE, f"{TEST_TABLE}:upsert_test", {"name": "Updated"}
        )

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

    async def test_repo_insert_bulk(
        self, surreal_config_ws, cleanup_table, async_cleanup
    ):
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
            user1["id"], "follows", user2["id"], {"since": "2024-01-01"}
        )

        assert len(result) == 1
        assert "since" in result[0]

        # Cleanup relationship table
        await repo_query("DELETE follows")

    async def test_repo_relate_data_cannot_override_endpoints(
        self, surreal_config_ws, cleanup_table, async_cleanup
    ):
        """data must not be able to override the validated in/out endpoints."""
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
            {"in": "evil:hacker", "out": "evil:target"},
        )

        assert len(result) == 1
        assert result[0]["in"] == user1["id"]
        assert result[0]["out"] == user2["id"]

        await repo_query("DELETE follows")

    async def test_ws_drop_keyerror_reconnects(
        self, surreal_config_ws, cleanup_table, async_cleanup
    ):
        """A dropped-WS KeyError (the surrealdb 2.x dead-socket symptom) must
        reset the singleton and surface as transient, so the next call
        transparently reconnects."""
        from surreal_basics import get_async_connection
        from surreal_basics.connection import ConnectionManager
        from surreal_basics.exceptions import SurrealDBTransientError

        # Prime the persistent WS singleton.
        await repo_create(TEST_TABLE, {"name": "seed"})
        assert ConnectionManager._ws_async_connected

        # Simulate the 2.x symptom: an in-flight request raising KeyError(uuid).
        with pytest.raises(SurrealDBTransientError):
            async with get_async_connection():
                raise KeyError("00000000-aaaa-bbbb-cccc-000000000000")

        # Singleton was dropped → the next operation rebuilds and succeeds.
        assert not ConnectionManager._ws_async_connected
        result = await repo_query(f"SELECT * FROM {TEST_TABLE}")
        assert isinstance(result, list)

    async def test_ws_auth_rejected_reconnects(
        self, surreal_config_ws, cleanup_table, async_cleanup
    ):
        """An auth/IAM error on a warm socket (e.g. expired JWT) must reset the
        singleton and surface as transient, so the retry re-signs in."""
        from surreal_basics import get_async_connection
        from surreal_basics.connection import ConnectionManager
        from surreal_basics.exceptions import (
            SurrealDBQueryError,
            SurrealDBTransientError,
        )

        await repo_create(TEST_TABLE, {"name": "seed"})
        assert ConnectionManager._ws_async_connected

        # Simulate the expired-token symptom: a permission error over a still-open
        # socket (translate_errors maps the SDK error to SurrealDBQueryError).
        with pytest.raises(SurrealDBTransientError):
            async with get_async_connection():
                raise SurrealDBQueryError(
                    "IAM error: Not enough permissions to perform this action"
                )

        assert not ConnectionManager._ws_async_connected
        result = await repo_query(f"SELECT * FROM {TEST_TABLE}")
        assert isinstance(result, list)

    async def test_ws_direct_raw_auth_error_reconnects(
        self, surreal_config_ws, cleanup_table, async_cleanup
    ):
        """Direct conn callers raise the *raw* SDK error (no translate_errors).
        The persistent path must still treat a raw auth error as a dead singleton
        (#15)."""
        from surrealdb.errors import SurrealError

        from surreal_basics import get_async_connection
        from surreal_basics.connection import ConnectionManager
        from surreal_basics.exceptions import SurrealDBTransientError

        await repo_create(TEST_TABLE, {"name": "seed"})
        assert ConnectionManager._ws_async_connected

        with pytest.raises(SurrealDBTransientError):
            async with get_async_connection():
                raise SurrealError(
                    "IAM error: Not enough permissions to perform this action"
                )

        assert not ConnectionManager._ws_async_connected
        result = await repo_query(f"SELECT * FROM {TEST_TABLE}")
        assert isinstance(result, list)

    async def test_ws_proactive_token_refresh(
        self, surreal_config_ws, cleanup_table, async_cleanup
    ):
        """When the token is near expiry, the next checkout refreshes it in place
        so even a direct conn.query() gets a valid-auth connection (#15)."""
        import time

        from surreal_basics import get_async_connection
        from surreal_basics.connection import ConnectionManager

        await repo_create(TEST_TABLE, {"name": "seed"})
        conn_before = id(ConnectionManager._ws_async_connection)

        # Pretend the cached token just lapsed; the next checkout must refresh.
        ConnectionManager._ws_async_token_exp = time.time() - 1
        async with get_async_connection() as db:
            result = await db.query(f"SELECT * FROM {TEST_TABLE}")

        assert isinstance(result, list)
        # Refreshed in place on the same warm socket (no full rebuild needed).
        assert id(ConnectionManager._ws_async_connection) == conn_before
