"""
surreal_basics - Simple and transparent SurrealDB connection management.

Usage:
    import surreal_basics

    # Configure (optional - env vars work automatically)
    surreal_basics.init(host="localhost", port=8000, mode="ws")

    # Or just change mode
    surreal_basics.mode = "http"

    # Async operations
    from surreal_basics import repo_query, repo_create
    results = await repo_query("SELECT * FROM user")

    # Sync operations
    from surreal_basics import repo_query_sync, repo_create_sync
    results = repo_query_sync("SELECT * FROM user")
"""

from .config import get_config, get_mode, init, set_mode

# Async repository functions
from .repo import (
    repo_create,
    repo_delete,
    repo_insert,
    repo_query,
    repo_relate,
    repo_select,
    repo_update,
    repo_upsert,
)

# Sync repository functions
from .repo_sync import (
    repo_create_sync,
    repo_delete_sync,
    repo_insert_sync,
    repo_query_sync,
    repo_relate_sync,
    repo_select_sync,
    repo_update_sync,
    repo_upsert_sync,
)

# Utilities
from .utils import ensure_record_id, parse_record_ids

# Exceptions
from .exceptions import (
    SurrealDBConnectionError,
    SurrealDBError,
    SurrealDBQueryError,
    SurrealDBTransientError,
)

# Connection management (for advanced use)
from .connection import (
    ConnectionManager,
    get_async_connection,
    get_sync_connection,
    reset_connections,
    reset_connections_async,
)

# Re-export RecordID for convenience
from surrealdb import RecordID  # type: ignore


# Module-level property for easy mode access
class _ModuleProxy:
    """Proxy to allow module-level property access."""

    @property
    def mode(self) -> str:
        return get_mode()

    @mode.setter
    def mode(self, value: str) -> None:
        set_mode(value)  # type: ignore


import sys

# Replace module with proxy for property support
_proxy = _ModuleProxy()


def __getattr__(name: str):
    if name == "mode":
        return _proxy.mode
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __setattr__(name: str, value):
    if name == "mode":
        _proxy.mode = value
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Config
    "init",
    "get_config",
    "get_mode",
    "set_mode",
    # Async repo functions
    "repo_query",
    "repo_create",
    "repo_upsert",
    "repo_update",
    "repo_delete",
    "repo_insert",
    "repo_relate",
    "repo_select",
    # Sync repo functions
    "repo_query_sync",
    "repo_create_sync",
    "repo_upsert_sync",
    "repo_update_sync",
    "repo_delete_sync",
    "repo_insert_sync",
    "repo_relate_sync",
    "repo_select_sync",
    # Utilities
    "parse_record_ids",
    "ensure_record_id",
    "RecordID",
    # Exceptions
    "SurrealDBError",
    "SurrealDBTransientError",
    "SurrealDBQueryError",
    "SurrealDBConnectionError",
    # Connection management
    "ConnectionManager",
    "get_async_connection",
    "get_sync_connection",
    "reset_connections",
    "reset_connections_async",
]
