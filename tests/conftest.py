"""Pytest fixtures for surreal_basics tests."""

import os
import pytest
import pytest_asyncio

from surreal_basics import (
    init,
    repo_query,
    repo_query_sync,
    reset_connections,
    reset_connections_async,
)
from surreal_basics.config import _config, SurrealConfig


# Register custom markers
def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration test")


# Test configuration
TEST_HOST = os.getenv("TEST_SURREAL_HOST", "localhost")
TEST_PORT = int(os.getenv("TEST_SURREAL_PORT", "8018"))
TEST_NS = "teste"
TEST_DB = "test_db"
TEST_TABLE = "test_table"


@pytest.fixture
def reset_config():
    """Reset global config before and after test."""
    import surreal_basics.config as config_module

    original = config_module._config
    config_module._config = None
    yield
    config_module._config = original


@pytest.fixture
def surreal_config_ws():
    """Configure surreal_basics for WebSocket testing."""
    init(
        host=TEST_HOST,
        port=TEST_PORT,
        namespace=TEST_NS,
        database=TEST_DB,
        mode="ws",
        persistent=True,
    )
    yield
    reset_connections()


@pytest.fixture
def surreal_config_http():
    """Configure surreal_basics for HTTP testing."""
    init(
        host=TEST_HOST,
        port=TEST_PORT,
        namespace=TEST_NS,
        database=TEST_DB,
        mode="http",
        persistent=True,
    )
    yield
    reset_connections()


@pytest_asyncio.fixture
async def cleanup_table():
    """Cleanup test table before and after each test."""
    # Clean before test
    try:
        await repo_query(f"DELETE {TEST_TABLE}")
    except Exception:
        pass
    yield
    # Clean after test
    try:
        await repo_query(f"DELETE {TEST_TABLE}")
    except Exception:
        pass


@pytest.fixture
def cleanup_table_sync():
    """Cleanup test table before and after each test (sync version)."""
    # Clean before test
    try:
        repo_query_sync(f"DELETE {TEST_TABLE}")
    except Exception:
        pass
    yield
    # Clean after test
    try:
        repo_query_sync(f"DELETE {TEST_TABLE}")
    except Exception:
        pass


@pytest.fixture
def surreal_config_memory():
    """Configure surreal_basics for in-memory testing."""
    init(
        namespace=TEST_NS,
        database=TEST_DB,
        mode="memory",
    )
    yield
    reset_connections()


@pytest_asyncio.fixture
async def async_cleanup():
    """Async cleanup for connections."""
    yield
    await reset_connections_async()
