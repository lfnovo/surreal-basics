"""Internal glue bridging the surrealdb SDK error model to ours.

The surrealdb 2.x SDK raises typed exceptions (``surrealdb.errors.*``) from
``query``/``insert``/``merge``/etc. instead of returning error strings inline as
1.x did. This module centralizes the translation to surreal_basics' own
exception hierarchy and the detection of WebSocket-drop conditions.
"""

from contextlib import contextmanager
from typing import Iterator

from surrealdb.errors import (  # type: ignore
    ConnectionUnavailableError,
    SurrealError,
)

from .exceptions import SurrealDBQueryError, SurrealDBTransientError

try:
    from websockets.exceptions import ConnectionClosed as _WSConnectionClosed
except ImportError:  # pragma: no cover - websockets ships with surrealdb

    class _WSConnectionClosed(Exception):  # type: ignore[no-redef]
        """Fallback when websockets isn't importable; never matches a real drop."""


# Exceptions that signal the persistent WS singleton is dead and must be rebuilt.
# The ConnectionManager catches these (only on the WS path) to reset the
# singleton and surface them as transient errors so the retry layer reconnects
# transparently.
#
# KeyError is included because the surrealdb 2.x async/blocking WS clients raise
# a bare KeyError(<request-uuid>) when the socket drops mid-request: the receive
# loop clears the pending-future map on close, then the in-flight `_send` hits
# `del self.qry[query_id]` on the now-missing key. It is the 2.x dead-socket
# symptom, not a logic error.
WS_DROPPED_EXCEPTIONS: tuple[type[BaseException], ...] = (
    _WSConnectionClosed,
    ConnectionUnavailableError,
    KeyError,
)

# Substring SurrealDB uses to flag a transaction/lock conflict as retryable.
_RETRYABLE_MARKER = "can be retried"


@contextmanager
def translate_errors() -> Iterator[None]:
    """Map surrealdb SDK errors raised inside the block to our exception types.

    - WebSocket-drop errors are re-raised untouched so the ConnectionManager can
      reset the singleton (enabling reconnect).
    - A retryable lock/transaction conflict becomes ``SurrealDBTransientError``.
    - Any other server/query error becomes ``SurrealDBQueryError``.

    Works in both sync and async call sites — wrap a block containing an
    ``await`` and the translation still applies.
    """
    try:
        yield
    except WS_DROPPED_EXCEPTIONS:
        raise
    except SurrealError as e:
        msg = str(e)
        if _RETRYABLE_MARKER in msg.lower():
            raise SurrealDBTransientError(msg) from e
        raise SurrealDBQueryError(msg) from e


def is_duplicate_error(e: BaseException) -> bool:
    """True when an exception represents a duplicate-record/insert conflict.

    Covers both the 2.x message ("already exists") and the legacy 1.x wording
    ("already contains").
    """
    msg = str(e).lower()
    return "already exists" in msg or "already contains" in msg


# Markers for a rejected/expired auth token on an otherwise-open connection
# (e.g. SurrealDB Cloud's 60-minute JWT lapsing on a warm persistent socket).
_AUTH_REJECTED_MARKERS = (
    "not enough permissions",
    "iam error",
    "problem with authentication",
    "token has expired",
    "token is expired",
    "invalid token",
)


def is_auth_rejected_error(e: BaseException) -> bool:
    """True when an error looks like a rejected/expired authentication token.

    A persistent connection signs in once and caches the token; against a
    backend with a time-limited token, queries start failing with an IAM /
    permission error once it lapses, *without* the socket dropping. Treating
    that as "the singleton is dead" lets the connection be rebuilt with a fresh
    signin. Note this cannot distinguish an expired token from a genuine
    permission denial, so genuine denials are retried before surfacing.
    """
    msg = str(e).lower()
    return any(m in msg for m in _AUTH_REJECTED_MARKERS)
