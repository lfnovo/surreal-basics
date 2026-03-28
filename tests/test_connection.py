"""Tests for connection management."""

import pytest
import pytest_asyncio

from surreal_basics import (
    init,
    repo_query,
    repo_query_sync,
    reset_connections,
    reset_connections_async,
)
from surreal_basics.connection import ConnectionManager


class TestConnectionManager:
    """Tests for ConnectionManager."""

    def test_reset_clears_connections(self, reset_config):
        """Test that reset clears all connection references."""
        ConnectionManager._ws_sync_connection = "mock"
        ConnectionManager._ws_async_connection = "mock"
        ConnectionManager._http_sync_connection = "mock"
        ConnectionManager._http_async_connection = "mock"
        ConnectionManager._embedded_sync_connection = "mock"
        ConnectionManager._embedded_async_connection = "mock"
        ConnectionManager._ws_sync_connected = True
        ConnectionManager._ws_async_connected = True
        ConnectionManager._http_sync_connected = True
        ConnectionManager._http_async_connected = True
        ConnectionManager._embedded_sync_connected = True
        ConnectionManager._embedded_async_connected = True

        ConnectionManager.reset()

        assert ConnectionManager._ws_sync_connection is None
        assert ConnectionManager._ws_async_connection is None
        assert ConnectionManager._http_sync_connection is None
        assert ConnectionManager._http_async_connection is None
        assert ConnectionManager._embedded_sync_connection is None
        assert ConnectionManager._embedded_async_connection is None
        assert ConnectionManager._ws_sync_connected is False
        assert ConnectionManager._ws_async_connected is False
        assert ConnectionManager._http_sync_connected is False
        assert ConnectionManager._http_async_connected is False
        assert ConnectionManager._embedded_sync_connected is False
        assert ConnectionManager._embedded_async_connected is False


@pytest.mark.integration
class TestConnectionIntegration:
    """Integration tests for connections (require running SurrealDB)."""

    def test_ws_sync_connection_persistent(self, surreal_config_ws):
        """Test that WS sync connections are persistent (singleton)."""
        with ConnectionManager.get_sync_connection() as conn1:
            pass
        with ConnectionManager.get_sync_connection() as conn2:
            pass
        # Should be same connection object
        assert ConnectionManager._ws_sync_connection is not None

    def test_http_sync_connection_persistent(self, surreal_config_http):
        """Test that HTTP sync connections are persistent when configured."""
        init(persistent=True)
        with ConnectionManager.get_sync_connection() as conn1:
            pass
        with ConnectionManager.get_sync_connection() as conn2:
            pass
        # Should be same connection object
        assert ConnectionManager._http_sync_connection is not None

    @pytest.mark.asyncio
    async def test_ws_async_connection_persistent(self, surreal_config_ws, async_cleanup):
        """Test that WS async connections are persistent (singleton)."""
        async with ConnectionManager.get_async_connection() as conn1:
            pass
        async with ConnectionManager.get_async_connection() as conn2:
            pass
        # Should be same connection object
        assert ConnectionManager._ws_async_connection is not None

    @pytest.mark.asyncio
    async def test_http_async_connection_persistent(self, surreal_config_http, async_cleanup):
        """Test that HTTP async connections are persistent when configured."""
        init(persistent=True)
        async with ConnectionManager.get_async_connection() as conn1:
            pass
        async with ConnectionManager.get_async_connection() as conn2:
            pass
        # Should be same connection object
        assert ConnectionManager._http_async_connection is not None


class TestMemoryConnection:
    """Tests for in-memory connections (no server required)."""

    def test_memory_sync_connection(self, surreal_config_memory):
        """Test sync connection in memory mode."""
        with ConnectionManager.get_sync_connection() as conn:
            assert conn is not None
        assert ConnectionManager._embedded_sync_connected is True

    def test_memory_sync_connection_persistent(self, surreal_config_memory):
        """Test that memory sync connections are persistent (singleton)."""
        with ConnectionManager.get_sync_connection() as conn1:
            pass
        with ConnectionManager.get_sync_connection() as conn2:
            pass
        assert ConnectionManager._embedded_sync_connection is not None

    @pytest.mark.asyncio
    async def test_memory_async_connection(self, surreal_config_memory, async_cleanup):
        """Test async connection in memory mode."""
        async with ConnectionManager.get_async_connection() as conn:
            assert conn is not None
        assert ConnectionManager._embedded_async_connected is True

    @pytest.mark.asyncio
    async def test_memory_async_connection_persistent(self, surreal_config_memory, async_cleanup):
        """Test that memory async connections are persistent (singleton)."""
        async with ConnectionManager.get_async_connection() as conn1:
            pass
        async with ConnectionManager.get_async_connection() as conn2:
            pass
        assert ConnectionManager._embedded_async_connection is not None

    def test_memory_sync_query(self, surreal_config_memory):
        """Test running a query via sync memory connection."""
        result = repo_query_sync("RETURN 1 + 1")
        assert result is not None

    @pytest.mark.asyncio
    async def test_memory_async_query(self, surreal_config_memory, async_cleanup):
        """Test running a query via async memory connection."""
        result = await repo_query("RETURN 1 + 1")
        assert result is not None

    def test_memory_sync_crud(self, surreal_config_memory):
        """Test basic CRUD operations via sync memory connection."""
        # Create
        repo_query_sync("CREATE test_mem SET name = 'test', value = 1")
        # Read
        result = repo_query_sync("SELECT * FROM test_mem")
        assert len(result) > 0
        assert result[0]["name"] == "test"
        # Update
        repo_query_sync("UPDATE test_mem SET value = 2 WHERE name = 'test'")
        result = repo_query_sync("SELECT * FROM test_mem WHERE name = 'test'")
        assert result[0]["value"] == 2
        # Delete
        repo_query_sync("DELETE test_mem")
        result = repo_query_sync("SELECT * FROM test_mem")
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_memory_async_crud(self, surreal_config_memory, async_cleanup):
        """Test basic CRUD operations via async memory connection."""
        # Create
        await repo_query("CREATE test_mem_async SET name = 'test', value = 1")
        # Read
        result = await repo_query("SELECT * FROM test_mem_async")
        assert len(result) > 0
        assert result[0]["name"] == "test"
        # Update
        await repo_query("UPDATE test_mem_async SET value = 2 WHERE name = 'test'")
        result = await repo_query("SELECT * FROM test_mem_async WHERE name = 'test'")
        assert result[0]["value"] == 2
        # Delete
        await repo_query("DELETE test_mem_async")
        result = await repo_query("SELECT * FROM test_mem_async")
        assert len(result) == 0
