"""Connection management for SurrealDB."""

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, Optional

from surrealdb import AsyncSurreal, Surreal  # type: ignore

from .config import get_config
from .exceptions import SurrealDBConnectionError


class ConnectionManager:
    """
    Manages SurrealDB connections.

    - WebSocket: Always uses persistent singleton connection (better performance)
    - HTTP: Configurable - persistent (default) or per-operation
    - Memory/Embedded: Always uses persistent singleton connection

    This design allows easy extension to connection pooling in the future.
    """

    _ws_sync_connection: Optional[Surreal] = None
    _ws_async_connection: Optional[AsyncSurreal] = None
    _http_sync_connection: Optional[Surreal] = None
    _http_async_connection: Optional[AsyncSurreal] = None
    _embedded_sync_connection: Optional[Surreal] = None
    _embedded_async_connection: Optional[AsyncSurreal] = None
    _ws_sync_connected: bool = False
    _ws_async_connected: bool = False
    _http_sync_connected: bool = False
    _http_async_connected: bool = False
    _embedded_sync_connected: bool = False
    _embedded_async_connected: bool = False

    @classmethod
    def _get_credentials(cls) -> dict:
        """Get authentication credentials."""
        config = get_config()
        return {"username": config.user, "password": config.password}

    @classmethod
    def _get_ns_db(cls) -> tuple[str, str]:
        """Get namespace and database."""
        config = get_config()
        return config.namespace, config.database

    @classmethod
    def reset(cls) -> None:
        """Reset all connections. Useful for testing or reconfiguration."""
        if cls._ws_sync_connection is not None:
            try:
                cls._ws_sync_connection.close()
            except Exception:
                pass
            cls._ws_sync_connection = None
            cls._ws_sync_connected = False

        if cls._ws_async_connection is not None:
            # Note: async close should be called from async context
            cls._ws_async_connection = None
            cls._ws_async_connected = False

        if cls._http_sync_connection is not None:
            try:
                cls._http_sync_connection.close()
            except Exception:
                pass
            cls._http_sync_connection = None
            cls._http_sync_connected = False

        if cls._http_async_connection is not None:
            cls._http_async_connection = None
            cls._http_async_connected = False

        if cls._embedded_sync_connection is not None:
            try:
                cls._embedded_sync_connection.close()
            except Exception:
                pass
            cls._embedded_sync_connection = None
            cls._embedded_sync_connected = False

        if cls._embedded_async_connection is not None:
            cls._embedded_async_connection = None
            cls._embedded_async_connected = False

    @classmethod
    async def reset_async(cls) -> None:
        """Reset async connections properly."""
        if cls._ws_async_connection is not None:
            try:
                await cls._ws_async_connection.close()
            except Exception:
                pass
            cls._ws_async_connection = None
            cls._ws_async_connected = False

        if cls._http_async_connection is not None:
            try:
                await cls._http_async_connection.close()
            except Exception:
                pass
            cls._http_async_connection = None
            cls._http_async_connected = False

        if cls._embedded_async_connection is not None:
            try:
                await cls._embedded_async_connection.close()
            except Exception:
                pass
            cls._embedded_async_connection = None
            cls._embedded_async_connected = False

    @classmethod
    @asynccontextmanager
    async def get_async_connection(cls) -> AsyncGenerator[AsyncSurreal, None]:
        """
        Get an async connection to SurrealDB.

        For WebSocket mode: Always uses persistent singleton connection.
        For HTTP mode: Persistent if config.persistent=True, otherwise new connection per call.
        For Memory/Embedded mode: Always uses persistent singleton connection.
        """
        config = get_config()

        if config.mode in ("memory", "embedded"):
            # Memory/Embedded: always use persistent connection (no signin needed)
            if cls._embedded_async_connection is None or not cls._embedded_async_connected:
                try:
                    cls._embedded_async_connection = AsyncSurreal(config.get_url())
                    ns, db = cls._get_ns_db()
                    await cls._embedded_async_connection.use(ns, db)
                    cls._embedded_async_connected = True
                except Exception as e:
                    cls._embedded_async_connection = None
                    cls._embedded_async_connected = False
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e

            yield cls._embedded_async_connection

        elif config.mode == "ws":
            # WebSocket: always use persistent connection
            if cls._ws_async_connection is None or not cls._ws_async_connected:
                try:
                    cls._ws_async_connection = AsyncSurreal(config.get_url())
                    await cls._ws_async_connection.signin(cls._get_credentials())
                    ns, db = cls._get_ns_db()
                    await cls._ws_async_connection.use(ns, db)
                    cls._ws_async_connected = True
                except Exception as e:
                    cls._ws_async_connection = None
                    cls._ws_async_connected = False
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e

            yield cls._ws_async_connection

        elif config.persistent:
            # HTTP with persistent connection
            if cls._http_async_connection is None or not cls._http_async_connected:
                try:
                    cls._http_async_connection = AsyncSurreal(config.get_url())
                    await cls._http_async_connection.signin(cls._get_credentials())
                    ns, db = cls._get_ns_db()
                    await cls._http_async_connection.use(ns, db)
                    cls._http_async_connected = True
                except Exception as e:
                    cls._http_async_connection = None
                    cls._http_async_connected = False
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e

            yield cls._http_async_connection

        else:
            # HTTP: create new connection each time (stateless mode)
            async with AsyncSurreal(config.get_url()) as conn:
                try:
                    await conn.signin(cls._get_credentials())
                    ns, db = cls._get_ns_db()
                    await conn.use(ns, db)
                    yield conn
                except Exception as e:
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e

    @classmethod
    @contextmanager
    def get_sync_connection(cls) -> Generator[Surreal, None, None]:
        """
        Get a sync connection to SurrealDB.

        For WebSocket mode: Always uses persistent singleton connection.
        For HTTP mode: Persistent if config.persistent=True, otherwise new connection per call.
        For Memory/Embedded mode: Always uses persistent singleton connection.
        """
        config = get_config()

        if config.mode in ("memory", "embedded"):
            # Memory/Embedded: always use persistent connection (no signin needed)
            if cls._embedded_sync_connection is None or not cls._embedded_sync_connected:
                try:
                    cls._embedded_sync_connection = Surreal(config.get_url())
                    ns, db = cls._get_ns_db()
                    cls._embedded_sync_connection.use(ns, db)
                    cls._embedded_sync_connected = True
                except Exception as e:
                    cls._embedded_sync_connection = None
                    cls._embedded_sync_connected = False
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e

            yield cls._embedded_sync_connection

        elif config.mode == "ws":
            # WebSocket: always use persistent connection
            if cls._ws_sync_connection is None or not cls._ws_sync_connected:
                try:
                    cls._ws_sync_connection = Surreal(config.get_url())
                    cls._ws_sync_connection.signin(cls._get_credentials())
                    ns, db = cls._get_ns_db()
                    cls._ws_sync_connection.use(ns, db)
                    cls._ws_sync_connected = True
                except Exception as e:
                    cls._ws_sync_connection = None
                    cls._ws_sync_connected = False
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e

            yield cls._ws_sync_connection

        elif config.persistent:
            # HTTP with persistent connection
            if cls._http_sync_connection is None or not cls._http_sync_connected:
                try:
                    cls._http_sync_connection = Surreal(config.get_url())
                    cls._http_sync_connection.signin(cls._get_credentials())
                    ns, db = cls._get_ns_db()
                    cls._http_sync_connection.use(ns, db)
                    cls._http_sync_connected = True
                except Exception as e:
                    cls._http_sync_connection = None
                    cls._http_sync_connected = False
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e

            yield cls._http_sync_connection

        else:
            # HTTP: create new connection each time (stateless mode)
            with Surreal(config.get_url()) as conn:
                try:
                    conn.signin(cls._get_credentials())
                    ns, db = cls._get_ns_db()
                    conn.use(ns, db)
                    yield conn
                except Exception as e:
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e


# Convenience aliases
get_async_connection = ConnectionManager.get_async_connection
get_sync_connection = ConnectionManager.get_sync_connection
reset_connections = ConnectionManager.reset
reset_connections_async = ConnectionManager.reset_async
