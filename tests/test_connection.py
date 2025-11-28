"""Tests for connection management."""

import pytest
import pytest_asyncio

from surreal_basics import (
    init,
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
        ConnectionManager._ws_sync_connected = True
        ConnectionManager._ws_async_connected = True
        ConnectionManager._http_sync_connected = True
        ConnectionManager._http_async_connected = True

        ConnectionManager.reset()

        assert ConnectionManager._ws_sync_connection is None
        assert ConnectionManager._ws_async_connection is None
        assert ConnectionManager._http_sync_connection is None
        assert ConnectionManager._http_async_connection is None
        assert ConnectionManager._ws_sync_connected is False
        assert ConnectionManager._ws_async_connected is False
        assert ConnectionManager._http_sync_connected is False
        assert ConnectionManager._http_async_connected is False


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
