"""Connection management for SurrealDB."""

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, Optional

from surrealdb import AsyncSurreal, Surreal  # type: ignore
from surrealdb.errors import SurrealError  # type: ignore

from ._sdk import (
    WS_DROPPED_EXCEPTIONS,
    is_auth_rejected_error,
    is_dropped_request_keyerror,
    token_expiry,
    token_near_expiry,
)
from .config import get_config
from .exceptions import (
    SurrealDBConnectionError,
    SurrealDBQueryError,
    SurrealDBTransientError,
)

# Errors that, on a persistent connection, mean the cached auth token was
# rejected — caught after WS-drop/KeyError so genuine query errors fall through.
# Covers both the translated form (repo_* path) and the raw SDK form (callers
# using the connection directly, who have no translate_errors/retry wrapper).
_AUTH_REJECTION_TYPES: tuple[type[BaseException], ...] = (
    SurrealDBQueryError,
    SurrealError,
)


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
    # Auth-token expiry (epoch seconds) per persistent singleton, for proactive
    # refresh. None when unknown (non-JWT token) or not yet signed in.
    _ws_sync_token_exp: Optional[float] = None
    _ws_async_token_exp: Optional[float] = None
    _http_sync_token_exp: Optional[float] = None
    _http_async_token_exp: Optional[float] = None

    @classmethod
    def _get_credentials(cls) -> dict:
        """Get authentication credentials for the configured auth scope.

        Root signs in with username/password only. Namespace/database scopes
        additionally bind the signin to the configured namespace (and
        database), as required for DEFINE USER ... ON NAMESPACE/DATABASE.
        """
        config = get_config()
        credentials = {"username": config.user, "password": config.password}
        if config.auth_scope in ("namespace", "database"):
            credentials["namespace"] = config.namespace
        if config.auth_scope == "database":
            credentials["database"] = config.database
        return credentials

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
            cls._ws_sync_token_exp = None

        if cls._ws_async_connection is not None:
            # Note: async close should be called from async context
            cls._ws_async_connection = None
            cls._ws_async_connected = False
            cls._ws_async_token_exp = None

        if cls._http_sync_connection is not None:
            try:
                cls._http_sync_connection.close()
            except Exception:
                pass
            cls._http_sync_connection = None
            cls._http_sync_connected = False
            cls._http_sync_token_exp = None

        if cls._http_async_connection is not None:
            cls._http_async_connection = None
            cls._http_async_connected = False
            cls._http_async_token_exp = None

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
            cls._ws_async_token_exp = None

        if cls._http_async_connection is not None:
            try:
                await cls._http_async_connection.close()
            except Exception:
                pass
            cls._http_async_connection = None
            cls._http_async_connected = False
            cls._http_async_token_exp = None

        if cls._embedded_async_connection is not None:
            try:
                await cls._embedded_async_connection.close()
            except Exception:
                pass
            cls._embedded_async_connection = None
            cls._embedded_async_connected = False

    @staticmethod
    async def _close_quietly_async(conn: Optional[AsyncSurreal]) -> None:
        """Best-effort close of a discarded connection (e.g. after a rejected
        auth token, where the socket is still open and must not leak)."""
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass

    @staticmethod
    def _close_quietly_sync(conn: Optional[Surreal]) -> None:
        """Best-effort close of a discarded connection (sync)."""
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

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
            if (
                cls._embedded_async_connection is None
                or not cls._embedded_async_connected
            ):
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
            existing = cls._ws_async_connection
            needs_new = existing is None or not cls._ws_async_connected
            if (
                existing is not None
                and not needs_new
                and token_near_expiry(cls._ws_async_token_exp)
            ):
                # Proactively refresh the token before it lapses, so every caller
                # (repo_* and direct conn.query()) gets a valid-auth connection.
                try:
                    tok = await existing.signin(cls._get_credentials())
                    cls._ws_async_token_exp = token_expiry(tok)
                except Exception:
                    # Refresh failed — close the stale client before rebuilding.
                    await cls._close_quietly_async(existing)
                    needs_new = True
            if needs_new:
                try:
                    cls._ws_async_connection = AsyncSurreal(config.get_url())
                    tok = await cls._ws_async_connection.signin(cls._get_credentials())
                    cls._ws_async_token_exp = token_expiry(tok)
                    ns, db = cls._get_ns_db()
                    await cls._ws_async_connection.use(ns, db)
                    cls._ws_async_connected = True
                except Exception as e:
                    cls._ws_async_connection = None
                    cls._ws_async_connected = False
                    cls._ws_async_token_exp = None
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e

            try:
                yield cls._ws_async_connection
            except WS_DROPPED_EXCEPTIONS as e:
                # Underlying socket died (idle timeout, network drop, server close).
                # Drop the singleton so the next attempt rebuilds it, and surface as
                # a transient error so surreal_retry_async retries the operation.
                cls._ws_async_connection = None
                cls._ws_async_connected = False
                cls._ws_async_token_exp = None
                raise SurrealDBTransientError(
                    f"WebSocket connection dropped: {e}"
                ) from e
            except KeyError as e:
                # surrealdb 2.x dead-socket symptom: KeyError(<request-uuid>).
                # Non-UUID KeyErrors are real logic errors and re-raised as-is.
                if not is_dropped_request_keyerror(e):
                    raise
                cls._ws_async_connection = None
                cls._ws_async_connected = False
                cls._ws_async_token_exp = None
                raise SurrealDBTransientError(
                    f"WebSocket connection dropped (request {e})"
                ) from e
            except _AUTH_REJECTION_TYPES as e:
                # Auth/IAM error on a still-open socket = the cached token was
                # rejected. Rebuild so the next call re-signs in; non-auth errors
                # (and raw SDK errors from direct callers) re-raise untouched.
                if is_auth_rejected_error(e):
                    conn = cls._ws_async_connection
                    cls._ws_async_connection = None
                    cls._ws_async_connected = False
                    cls._ws_async_token_exp = None
                    await cls._close_quietly_async(conn)
                    raise SurrealDBTransientError(
                        f"Auth token rejected; reconnecting: {e}"
                    ) from e
                raise

        elif config.persistent:
            # HTTP with persistent connection
            existing = cls._http_async_connection
            needs_new = existing is None or not cls._http_async_connected
            if (
                existing is not None
                and not needs_new
                and token_near_expiry(cls._http_async_token_exp)
            ):
                try:
                    tok = await existing.signin(cls._get_credentials())
                    cls._http_async_token_exp = token_expiry(tok)
                except Exception:
                    await cls._close_quietly_async(existing)
                    needs_new = True
            if needs_new:
                try:
                    cls._http_async_connection = AsyncSurreal(config.get_url())
                    tok = await cls._http_async_connection.signin(
                        cls._get_credentials()
                    )
                    cls._http_async_token_exp = token_expiry(tok)
                    ns, db = cls._get_ns_db()
                    await cls._http_async_connection.use(ns, db)
                    cls._http_async_connected = True
                except Exception as e:
                    cls._http_async_connection = None
                    cls._http_async_connected = False
                    cls._http_async_token_exp = None
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e

            try:
                yield cls._http_async_connection
            except _AUTH_REJECTION_TYPES as e:
                if is_auth_rejected_error(e):
                    conn = cls._http_async_connection
                    cls._http_async_connection = None
                    cls._http_async_connected = False
                    cls._http_async_token_exp = None
                    await cls._close_quietly_async(conn)
                    raise SurrealDBTransientError(
                        f"Auth token rejected; reconnecting: {e}"
                    ) from e
                raise

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
            if (
                cls._embedded_sync_connection is None
                or not cls._embedded_sync_connected
            ):
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
            existing = cls._ws_sync_connection
            needs_new = existing is None or not cls._ws_sync_connected
            if (
                existing is not None
                and not needs_new
                and token_near_expiry(cls._ws_sync_token_exp)
            ):
                try:
                    tok = existing.signin(cls._get_credentials())
                    cls._ws_sync_token_exp = token_expiry(tok)
                except Exception:
                    # Refresh failed — close the stale client before rebuilding.
                    cls._close_quietly_sync(existing)
                    needs_new = True
            if needs_new:
                try:
                    cls._ws_sync_connection = Surreal(config.get_url())
                    tok = cls._ws_sync_connection.signin(cls._get_credentials())
                    cls._ws_sync_token_exp = token_expiry(tok)
                    ns, db = cls._get_ns_db()
                    cls._ws_sync_connection.use(ns, db)
                    cls._ws_sync_connected = True
                except Exception as e:
                    cls._ws_sync_connection = None
                    cls._ws_sync_connected = False
                    cls._ws_sync_token_exp = None
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e

            try:
                yield cls._ws_sync_connection
            except WS_DROPPED_EXCEPTIONS as e:
                # Underlying socket died (idle timeout, network drop, server close).
                # Drop the singleton so the next attempt rebuilds it, and surface as
                # a transient error so surreal_retry retries the operation.
                cls._ws_sync_connection = None
                cls._ws_sync_connected = False
                cls._ws_sync_token_exp = None
                raise SurrealDBTransientError(
                    f"WebSocket connection dropped: {e}"
                ) from e
            except KeyError as e:
                # surrealdb 2.x dead-socket symptom: KeyError(<request-uuid>).
                # Non-UUID KeyErrors are real logic errors and re-raised as-is.
                if not is_dropped_request_keyerror(e):
                    raise
                cls._ws_sync_connection = None
                cls._ws_sync_connected = False
                cls._ws_sync_token_exp = None
                raise SurrealDBTransientError(
                    f"WebSocket connection dropped (request {e})"
                ) from e
            except _AUTH_REJECTION_TYPES as e:
                # Auth/IAM error on a still-open socket = the cached token was
                # rejected. Rebuild so the next call re-signs in; non-auth errors
                # (and raw SDK errors from direct callers) re-raise untouched.
                if is_auth_rejected_error(e):
                    conn = cls._ws_sync_connection
                    cls._ws_sync_connection = None
                    cls._ws_sync_connected = False
                    cls._ws_sync_token_exp = None
                    cls._close_quietly_sync(conn)
                    raise SurrealDBTransientError(
                        f"Auth token rejected; reconnecting: {e}"
                    ) from e
                raise

        elif config.persistent:
            # HTTP with persistent connection
            existing = cls._http_sync_connection
            needs_new = existing is None or not cls._http_sync_connected
            if (
                existing is not None
                and not needs_new
                and token_near_expiry(cls._http_sync_token_exp)
            ):
                try:
                    tok = existing.signin(cls._get_credentials())
                    cls._http_sync_token_exp = token_expiry(tok)
                except Exception:
                    cls._close_quietly_sync(existing)
                    needs_new = True
            if needs_new:
                try:
                    cls._http_sync_connection = Surreal(config.get_url())
                    tok = cls._http_sync_connection.signin(cls._get_credentials())
                    cls._http_sync_token_exp = token_expiry(tok)
                    ns, db = cls._get_ns_db()
                    cls._http_sync_connection.use(ns, db)
                    cls._http_sync_connected = True
                except Exception as e:
                    cls._http_sync_connection = None
                    cls._http_sync_connected = False
                    cls._http_sync_token_exp = None
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e

            try:
                yield cls._http_sync_connection
            except _AUTH_REJECTION_TYPES as e:
                if is_auth_rejected_error(e):
                    conn = cls._http_sync_connection
                    cls._http_sync_connection = None
                    cls._http_sync_connected = False
                    cls._http_sync_token_exp = None
                    cls._close_quietly_sync(conn)
                    raise SurrealDBTransientError(
                        f"Auth token rejected; reconnecting: {e}"
                    ) from e
                raise

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
