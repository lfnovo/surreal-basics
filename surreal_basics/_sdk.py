"""Internal glue bridging the surrealdb SDK error model to ours.

The surrealdb 2.x SDK raises typed exceptions (``surrealdb.errors.*``) from
``query``/``insert``/``merge``/etc. instead of returning error strings inline as
1.x did. This module centralizes the translation to surreal_basics' own
exception hierarchy and the detection of WebSocket-drop conditions.
"""

import base64
import json
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from surrealdb.errors import (  # type: ignore
    ConnectionUnavailableError,
    SurrealError,
)

from .exceptions import SurrealDBQueryError, SurrealDBTransientError

# Refresh a persistent connection's token this many seconds before it expires.
_TOKEN_REFRESH_MARGIN_SECONDS = 60

try:
    from websockets.exceptions import ConnectionClosed as _WSConnectionClosed
except ImportError:  # pragma: no cover - websockets ships with surrealdb

    class _WSConnectionClosed(Exception):  # type: ignore[no-redef]
        """Fallback when websockets isn't importable; never matches a real drop."""


# Exceptions that signal the persistent WS singleton is dead and must be rebuilt.
# The ConnectionManager catches these (only on the WS path) to reset the
# singleton and surface them as transient errors so the retry layer reconnects
# transparently.
WS_DROPPED_EXCEPTIONS: tuple[type[BaseException], ...] = (
    _WSConnectionClosed,
    ConnectionUnavailableError,
)


def is_dropped_request_keyerror(e: BaseException) -> bool:
    """True for the surrealdb 2.x WS dead-socket symptom.

    When the socket drops mid-request the WS client raises a bare
    ``KeyError(<request-uuid>)``: the receive loop clears the pending-future map
    on close, then the in-flight ``_send`` hits ``del self.qry[query_id]`` on the
    now-missing key. Request ids are ``str(uuid.uuid4())``, so we only treat a
    KeyError whose key parses as a UUID as a drop — a non-SDK KeyError in the
    same code block (e.g. a real ``KeyError('name')``) is left untouched.
    """
    if not isinstance(e, KeyError) or not e.args:
        return False
    key = e.args[0]
    if not isinstance(key, str):
        return False
    try:
        uuid.UUID(key)
        return True
    except ValueError:
        return False


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


def token_expiry(signin_result: Any) -> Optional[float]:
    """Best-effort extract of a JWT ``exp`` (epoch seconds) from a signin result.

    The surrealdb 2.x ``signin()`` returns a ``Tokens`` object whose ``access``
    field holds the JWT; some setups return the token as a plain string. Returns
    ``None`` when the token isn't a decodable JWT (e.g. non-JWT auth), in which
    case proactive refresh is simply skipped for that connection.
    """
    tok = getattr(signin_result, "access", None)
    if tok is None and isinstance(signin_result, str):
        tok = signin_result
    if not isinstance(tok, str) or tok.count(".") != 2:
        return None
    try:
        payload = tok.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        exp = claims.get("exp")
        return float(exp) if exp is not None else None
    except Exception:
        return None


def token_near_expiry(exp: Optional[float]) -> bool:
    """True when a known token expiry is within the refresh margin (or passed)."""
    if exp is None:
        return False
    return time.time() >= exp - _TOKEN_REFRESH_MARGIN_SECONDS
