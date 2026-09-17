"""Connection management for SurrealDB."""

import asyncio
import threading
from collections import OrderedDict
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Generator, Optional

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
from .target import ResolvedTarget, Target, resolve_target

# Errors that, on a persistent connection, mean the cached auth token was
# rejected — caught after WS-drop/KeyError so genuine query errors fall through.
# Covers both the translated form (repo_* path) and the raw SDK form (callers
# using the connection directly, who have no translate_errors/retry wrapper).
_AUTH_REJECTION_TYPES: tuple[type[BaseException], ...] = (
    SurrealDBQueryError,
    SurrealError,
)


@dataclass(eq=False)
class _Slot:
    """One persistent network connection, bound to a single target.

    ``users`` counts open checkouts, so a connection is never closed in the
    middle of someone's query: eviction skips it, and a slot taken out of
    rotation while held is only ``retired`` and closed on its last release.
    ``loop`` is the event loop that owns an async connection: the SDK binds
    futures to it, so the connection is unusable from any other loop (e.g.
    after one ``asyncio.run()`` per operation) and must be closed on it.
    """

    conn: Any
    target: ResolvedTarget
    token_exp: Optional[float] = None
    loop: Optional[asyncio.AbstractEventLoop] = None
    users: int = 0
    retired: bool = False


@dataclass(eq=False)
class _Engine:
    """One in-process engine (memory/embedded mode) and its current binding.

    Unlike a server, a second ``mem://`` handle is a separate, empty database,
    so every target shares this engine and switches it with ``use()``. The
    binding is per engine, which is why two targets cannot hold it at once.
    """

    conn: Any
    ns_db: Optional[tuple[str, str]] = None
    users: int = 0
    # True while an async checkout is still running use() for ``ns_db``.
    binding: bool = False


class ConnectionManager:
    """
    Manages SurrealDB connections.

    - WebSocket: persistent connections, one per target
    - HTTP: persistent (default) or per-operation, one per target when persistent
    - Memory/Embedded: one engine per URL, switched between targets

    A target is the (namespace, database, credential) an operation runs
    against: the global config by default, or a ``Target`` passed as
    ``using=`` or bound with ``use_target()``. At most ``max_connections``
    idle persistent connections are kept; the least recently used idle one is
    closed beyond that. Connections that are checked out are never closed, so
    the cap is soft under load.

    A connection that has to be replaced while others hold it (a rejected or
    unrefreshable token) is taken out of rotation at once and closed when its
    last holder releases it. ``reset()`` is the exception: it closes
    everything immediately.
    """

    max_connections: int = 32

    _sync_slots: "OrderedDict[tuple, _Slot]" = OrderedDict()
    _async_slots: "OrderedDict[tuple, _Slot]" = OrderedDict()
    _sync_engines: dict[str, _Engine] = {}
    _async_engines: dict[str, _Engine] = {}
    # Guards the sync maps: sync callers may share connections across threads.
    _sync_lock = threading.RLock()

    @classmethod
    def _get_credentials(cls, using: Optional[Target] = None) -> dict:
        """Signin payload for a target (the global config by default).

        Root signs in with username/password only. Namespace/database scopes
        additionally bind the signin to the target's namespace (and database),
        as required for DEFINE USER ... ON NAMESPACE/DATABASE.
        """
        return resolve_target(using).credentials or {}

    @classmethod
    def _get_ns_db(cls, using: Optional[Target] = None) -> tuple[str, str]:
        """Namespace and database for a target (the global config by default)."""
        resolved = resolve_target(using)
        return resolved.namespace, resolved.database

    @classmethod
    def _async_slot_for(cls, using: Optional[Target] = None) -> Optional[_Slot]:
        """The open async connection for a target on the running loop, if any."""
        key = cls._async_key(resolve_target(using), asyncio.get_running_loop())
        return cls._async_slots.get(key)

    @classmethod
    def _sync_slot_for(cls, using: Optional[Target] = None) -> Optional[_Slot]:
        """The open sync connection for a target, if any."""
        return cls._sync_slots.get(resolve_target(using).key)

    # ------------------------------------------------------------------ reset

    @classmethod
    def reset(cls) -> None:
        """Reset all connections. Useful for testing or reconfiguration."""
        with cls._sync_lock:
            for slot in cls._sync_slots.values():
                cls._close_quietly_sync(slot.conn)
            cls._sync_slots.clear()
            for engine in cls._sync_engines.values():
                cls._close_quietly_sync(engine.conn)
            cls._sync_engines.clear()
        # Async close needs the owning event loop; drop the references and let
        # reset_async() handle a clean close from async code.
        cls._async_slots.clear()
        cls._async_engines.clear()

    @classmethod
    async def reset_async(cls) -> None:
        """Reset async connections properly."""
        loop = asyncio.get_running_loop()
        slots = list(cls._async_slots.values())
        engines = list(cls._async_engines.values())
        cls._async_slots.clear()
        cls._async_engines.clear()
        for slot in slots:
            await cls._close_slot_async(slot, loop)
        for engine in engines:
            await cls._close_quietly_async(engine.conn)

    @staticmethod
    async def _close_quietly_async(conn: Any) -> None:
        """Best-effort close of a discarded connection (e.g. after a rejected
        auth token, where the socket is still open and must not leak)."""
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass

    @staticmethod
    def _close_quietly_sync(conn: Any) -> None:
        """Best-effort close of a discarded connection (sync)."""
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    # ------------------------------------------------------------ async path

    @staticmethod
    def _async_key(target: ResolvedTarget, loop: asyncio.AbstractEventLoop) -> tuple:
        return (id(loop), *target.key)

    @staticmethod
    async def _open_async(conn: Any, target: ResolvedTarget) -> Optional[float]:
        """Authenticate and select the target; returns the token expiry."""
        if target.token is not None:
            await conn.authenticate(target.token)
            exp = token_expiry(target.token)
        else:
            exp = token_expiry(await conn.signin(target.credentials))
        await conn.use(target.namespace, target.database)
        return exp

    @classmethod
    def _drop_async(cls, key: tuple, slot: _Slot) -> None:
        """Forget a dead slot, unless it was already replaced."""
        if cls._async_slots.get(key) is slot:
            del cls._async_slots[key]

    @classmethod
    async def _close_slot_async(
        cls, slot: _Slot, current: asyncio.AbstractEventLoop
    ) -> None:
        """Close an async connection on the event loop that owns it."""
        owner = slot.loop
        if owner is None or owner is current:
            await cls._close_quietly_async(slot.conn)
        elif not owner.is_closed():
            # Owned by a loop running in another thread: close it there.
            asyncio.run_coroutine_threadsafe(cls._close_quietly_async(slot.conn), owner)
        # A closed owner can't run the close; the socket died with it.

    @classmethod
    async def _retire_async(cls, key: tuple, slot: _Slot) -> None:
        """Take a slot out of rotation, closing it once nobody holds it."""
        cls._drop_async(key, slot)
        slot.retired = True
        if not slot.users:
            await cls._close_slot_async(slot, asyncio.get_running_loop())

    @classmethod
    async def _release_async(cls, slot: _Slot) -> None:
        slot.users -= 1
        if slot.retired and not slot.users:
            await cls._close_slot_async(slot, asyncio.get_running_loop())

    @classmethod
    async def _evict_async(cls, loop: asyncio.AbstractEventLoop) -> None:
        """Close least recently used idle connections beyond the cap."""
        for key, slot in list(cls._async_slots.items()):
            if slot.loop is not None and slot.loop.is_closed():
                # Left behind by a finished asyncio.run(); it can't be closed
                # from here, and nothing can use it again.
                cls._drop_async(key, slot)
        excess = len(cls._async_slots) - cls.max_connections
        for key, slot in list(cls._async_slots.items()):
            if excess <= 0:
                break
            if slot.users or cls._async_slots.get(key) is not slot:
                continue
            del cls._async_slots[key]
            excess -= 1
            await cls._close_slot_async(slot, loop)

    @classmethod
    async def _checkout_async(cls, target: ResolvedTarget) -> tuple[tuple, _Slot]:
        loop = asyncio.get_running_loop()
        key = cls._async_key(target, loop)
        slot = cls._async_slots.get(key)
        if slot is not None and slot.loop is not loop:
            # A previous loop with a recycled id; its futures are unusable.
            cls._drop_async(key, slot)
            slot = None
        if (
            slot is not None
            and target.token is None
            and token_near_expiry(slot.token_exp)
        ):
            # Proactively refresh the token before it lapses, so every caller
            # (repo_* and direct conn.query()) gets a valid-auth connection.
            # A caller-supplied token cannot be refreshed here.
            try:
                slot.token_exp = token_expiry(
                    await slot.conn.signin(target.credentials)
                )
            except Exception:
                # Refresh failed — retire the stale client and rebuild. Other
                # holders finish on it; it is closed on the last release.
                await cls._retire_async(key, slot)
                slot = None

        created = False
        if slot is None:
            conn = AsyncSurreal(target.url)
            try:
                exp = await cls._open_async(conn, target)
            except Exception as e:
                await cls._close_quietly_async(conn)
                raise SurrealDBConnectionError(f"Failed to connect: {e}") from e
            existing = cls._async_slots.get(key)
            if existing is not None and existing.loop is loop:
                # Another task connected the same target while we awaited.
                await cls._close_quietly_async(conn)
                slot = existing
            else:
                slot = _Slot(conn, target, exp, loop)
                cls._async_slots[key] = slot
                created = True

        slot.users += 1
        cls._async_slots.move_to_end(key)
        if created:
            await cls._evict_async(loop)
        return key, slot

    @classmethod
    async def _checkout_engine_async(cls, target: ResolvedTarget) -> _Engine:
        want = (target.namespace, target.database)
        engine = cls._async_engines.get(target.url)
        if engine is None:
            conn = AsyncSurreal(target.url)
            engine = cls._async_engines.setdefault(target.url, _Engine(conn))
            if engine.conn is not conn:
                await cls._close_quietly_async(conn)
        return await cls._bind_engine_async(engine, want, target.url)

    @classmethod
    async def _bind_engine_async(
        cls, engine: _Engine, want: tuple[str, str], url: str
    ) -> _Engine:
        while engine.ns_db == want and engine.binding:
            # Same target, but another task is still selecting it.
            await asyncio.sleep(0)
        if engine.ns_db == want:
            engine.users += 1
            return engine
        if engine.users:
            raise cls._engine_busy(engine, want)
        # Claim the binding before awaiting, so a concurrent checkout for a
        # different target sees it as taken, and one for the same target waits.
        previous = engine.ns_db
        engine.ns_db = want
        engine.binding = True
        engine.users += 1
        try:
            await engine.conn.use(*want)
        except Exception as e:
            engine.users -= 1
            engine.ns_db = previous
            if previous is None and cls._async_engines.get(url) is engine:
                del cls._async_engines[url]
            raise SurrealDBConnectionError(f"Failed to connect: {e}") from e
        finally:
            engine.binding = False
        return engine

    @staticmethod
    def _engine_busy(engine: _Engine, want: tuple[str, str]) -> Exception:
        ns, db = engine.ns_db or ("?", "?")
        return SurrealDBConnectionError(
            f"The in-process engine is serving namespace {ns!r} / database "
            f"{db!r} and cannot switch to {want[0]!r} / {want[1]!r} while that "
            "connection is in use. Memory and embedded modes serve one target "
            "at a time."
        )

    @classmethod
    @asynccontextmanager
    async def get_async_connection(
        cls, *, using: Optional[Target] = None
    ) -> AsyncGenerator[AsyncSurreal, None]:
        """
        Get an async connection to SurrealDB.

        Args:
            using: Target to connect to. Defaults to the one bound with
                ``use_target()``, then to the global config.

        For WebSocket mode: persistent connection per target.
        For HTTP mode: persistent per target if config.persistent=True,
            otherwise a new connection per call.
        For Memory/Embedded mode: one persistent engine, switched per target.
        """
        config = get_config()
        target = resolve_target(using, config)

        if config.mode in ("memory", "embedded"):
            # In-process engine: no signin needed.
            engine = await cls._checkout_engine_async(target)
            try:
                yield engine.conn
            finally:
                engine.users -= 1
            return

        if config.mode != "ws" and not config.persistent:
            # HTTP: create new connection each time (stateless mode)
            async with AsyncSurreal(target.url) as conn:
                try:
                    await cls._open_async(conn, target)
                    yield conn
                except Exception as e:
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e
            return

        key, slot = await cls._checkout_async(target)
        try:
            yield slot.conn
        except WS_DROPPED_EXCEPTIONS as e:
            if config.mode != "ws":
                raise
            # Underlying socket died (idle timeout, network drop, server close).
            # Drop the slot so the next attempt rebuilds it, and surface as a
            # transient error so surreal_retry_async retries the operation.
            cls._drop_async(key, slot)
            raise SurrealDBTransientError(f"WebSocket connection dropped: {e}") from e
        except KeyError as e:
            # surrealdb 2.x dead-socket symptom: KeyError(<request-uuid>).
            # Non-UUID KeyErrors are real logic errors and re-raised as-is.
            if config.mode != "ws" or not is_dropped_request_keyerror(e):
                raise
            cls._drop_async(key, slot)
            raise SurrealDBTransientError(
                f"WebSocket connection dropped (request {e})"
            ) from e
        except _AUTH_REJECTION_TYPES as e:
            # Auth/IAM error on a still-open socket = the cached token was
            # rejected. Rebuild so the next call re-authenticates; non-auth
            # errors (and raw SDK errors from direct callers) re-raise untouched.
            if not is_auth_rejected_error(e):
                raise
            await cls._retire_async(key, slot)
            raise SurrealDBTransientError(
                f"Auth token rejected; reconnecting: {e}"
            ) from e
        finally:
            await cls._release_async(slot)

    # ------------------------------------------------------------- sync path

    @staticmethod
    def _open_sync(conn: Any, target: ResolvedTarget) -> Optional[float]:
        """Authenticate and select the target; returns the token expiry."""
        if target.token is not None:
            conn.authenticate(target.token)
            exp = token_expiry(target.token)
        else:
            exp = token_expiry(conn.signin(target.credentials))
        conn.use(target.namespace, target.database)
        return exp

    @classmethod
    def _drop_sync(cls, key: tuple, slot: _Slot) -> None:
        with cls._sync_lock:
            if cls._sync_slots.get(key) is slot:
                del cls._sync_slots[key]

    @classmethod
    def _retire_sync(cls, key: tuple, slot: _Slot) -> None:
        """Take a slot out of rotation, closing it once nobody holds it."""
        with cls._sync_lock:
            if cls._sync_slots.get(key) is slot:
                del cls._sync_slots[key]
            slot.retired = True
            close_now = not slot.users
        if close_now:
            cls._close_quietly_sync(slot.conn)

    @classmethod
    def _release_sync(cls, slot: _Slot) -> None:
        with cls._sync_lock:
            slot.users -= 1
            close_now = slot.retired and not slot.users
        if close_now:
            cls._close_quietly_sync(slot.conn)

    @classmethod
    def _evict_sync(cls) -> None:
        """Close least recently used idle connections beyond the cap.

        Caller holds ``_sync_lock``.
        """
        excess = len(cls._sync_slots) - cls.max_connections
        for key, slot in list(cls._sync_slots.items()):
            if excess <= 0:
                break
            if slot.users:
                continue
            del cls._sync_slots[key]
            excess -= 1
            cls._close_quietly_sync(slot.conn)

    @classmethod
    def _checkout_sync(cls, target: ResolvedTarget) -> tuple[tuple, _Slot]:
        key = target.key
        with cls._sync_lock:
            slot = cls._sync_slots.get(key)
            if (
                slot is not None
                and target.token is None
                and token_near_expiry(slot.token_exp)
            ):
                try:
                    slot.token_exp = token_expiry(slot.conn.signin(target.credentials))
                except Exception:
                    # Refresh failed — retire the stale client and rebuild.
                    # Other holders finish on it; it is closed on the last
                    # release.
                    cls._retire_sync(key, slot)
                    slot = None

            created = False
            if slot is None:
                conn = Surreal(target.url)
                try:
                    exp = cls._open_sync(conn, target)
                except Exception as e:
                    cls._close_quietly_sync(conn)
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e
                slot = _Slot(conn, target, exp)
                cls._sync_slots[key] = slot
                created = True

            slot.users += 1
            cls._sync_slots.move_to_end(key)
            if created:
                cls._evict_sync()
            return key, slot

    @classmethod
    def _checkout_engine_sync(cls, target: ResolvedTarget) -> _Engine:
        want = (target.namespace, target.database)
        with cls._sync_lock:
            engine = cls._sync_engines.get(target.url)
            if engine is None:
                engine = _Engine(Surreal(target.url))
                cls._sync_engines[target.url] = engine
            if engine.ns_db == want:
                engine.users += 1
                return engine
            if engine.users:
                raise cls._engine_busy(engine, want)
            try:
                engine.conn.use(*want)
            except Exception as e:
                if engine.ns_db is None:
                    del cls._sync_engines[target.url]
                raise SurrealDBConnectionError(f"Failed to connect: {e}") from e
            engine.ns_db = want
            engine.users += 1
            return engine

    @classmethod
    @contextmanager
    def get_sync_connection(
        cls, *, using: Optional[Target] = None
    ) -> Generator[Surreal, None, None]:
        """
        Get a sync connection to SurrealDB.

        Args:
            using: Target to connect to. Defaults to the one bound with
                ``use_target()``, then to the global config.

        For WebSocket mode: persistent connection per target.
        For HTTP mode: persistent per target if config.persistent=True,
            otherwise a new connection per call.
        For Memory/Embedded mode: one persistent engine, switched per target.
        """
        config = get_config()
        target = resolve_target(using, config)

        if config.mode in ("memory", "embedded"):
            # In-process engine: no signin needed.
            engine = cls._checkout_engine_sync(target)
            try:
                yield engine.conn
            finally:
                with cls._sync_lock:
                    engine.users -= 1
            return

        if config.mode != "ws" and not config.persistent:
            # HTTP: create new connection each time (stateless mode)
            with Surreal(target.url) as conn:
                try:
                    cls._open_sync(conn, target)
                    yield conn
                except Exception as e:
                    raise SurrealDBConnectionError(f"Failed to connect: {e}") from e
            return

        key, slot = cls._checkout_sync(target)
        try:
            yield slot.conn
        except WS_DROPPED_EXCEPTIONS as e:
            if config.mode != "ws":
                raise
            # Underlying socket died (idle timeout, network drop, server close).
            # Drop the slot so the next attempt rebuilds it, and surface as a
            # transient error so surreal_retry retries the operation.
            cls._drop_sync(key, slot)
            raise SurrealDBTransientError(f"WebSocket connection dropped: {e}") from e
        except KeyError as e:
            # surrealdb 2.x dead-socket symptom: KeyError(<request-uuid>).
            # Non-UUID KeyErrors are real logic errors and re-raised as-is.
            if config.mode != "ws" or not is_dropped_request_keyerror(e):
                raise
            cls._drop_sync(key, slot)
            raise SurrealDBTransientError(
                f"WebSocket connection dropped (request {e})"
            ) from e
        except _AUTH_REJECTION_TYPES as e:
            # Auth/IAM error on a still-open socket = the cached token was
            # rejected. Rebuild so the next call re-authenticates; non-auth
            # errors (and raw SDK errors from direct callers) re-raise untouched.
            if not is_auth_rejected_error(e):
                raise
            cls._retire_sync(key, slot)
            raise SurrealDBTransientError(
                f"Auth token rejected; reconnecting: {e}"
            ) from e
        finally:
            cls._release_sync(slot)


# Convenience aliases
get_async_connection = ConnectionManager.get_async_connection
get_sync_connection = ConnectionManager.get_sync_connection
reset_connections = ConnectionManager.reset
reset_connections_async = ConnectionManager.reset_async
