"""Pytest fixtures for surreal_basics tests."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import pytest_asyncio

from surreal_basics import (
    init,
    repo_query,
    repo_query_sync,
    reset_connections,
    reset_connections_async,
)

# The `integration` marker is registered in pyproject.toml
# ([tool.pytest.ini_options] markers).

# Test configuration
TEST_HOST = os.getenv("TEST_SURREAL_HOST", "localhost")
TEST_PORT = int(os.getenv("TEST_SURREAL_PORT", "8000"))
TEST_NS = "teste"
TEST_DB = "test_db"
TEST_TABLE = "test_table"

_COMPOSE_FILE = Path(__file__).resolve().parent.parent / "docker-compose.yml"


@pytest.fixture(scope="session")
def surrealdb_service():
    """Start SurrealDB via docker compose for the integration suite.

    Only the WS/HTTP fixtures depend on this, so it is started lazily — running
    `pytest -m "not integration"` never touches Docker. The container is torn
    down at the end of the session.

    Set ``SBL_TEST_DOCKER=0`` to use an externally managed instance instead
    (e.g. when pointing TEST_SURREAL_HOST/PORT at an existing server).
    """
    if os.getenv("SBL_TEST_DOCKER", "1") == "0":
        yield
        return

    if shutil.which("docker") is None:
        pytest.skip(
            "docker not available; cannot start SurrealDB for integration tests"
        )

    subprocess.run(
        ["docker", "compose", "-f", str(_COMPOSE_FILE), "up", "-d", "--wait"],
        check=True,
    )
    try:
        yield
    finally:
        subprocess.run(
            ["docker", "compose", "-f", str(_COMPOSE_FILE), "down", "-v"],
            check=False,
        )


@pytest.fixture
def reset_config():
    """Reset global config before and after test."""
    import surreal_basics.config as config_module

    original = config_module._config
    config_module._config = None
    yield
    config_module._config = original


@pytest.fixture
def surreal_config_ws(surrealdb_service):
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
def surreal_config_http(surrealdb_service):
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
