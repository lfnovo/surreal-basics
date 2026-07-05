"""Configuration management for surreal_basics."""

import os
from dataclasses import dataclass, field
from typing import Literal, Optional
from urllib.parse import urlparse

# All supported connection modes
ConnectionMode = Literal["ws", "http", "memory", "embedded"]

# Authentication scope for signin. Root signs in with username/password only;
# namespace/database additionally bind the signin to the configured
# namespace (and database), enabling DEFINE USER ... ON NAMESPACE/DATABASE.
AuthScope = Literal["root", "namespace", "database"]

_AUTH_SCOPES = ("root", "namespace", "database")


def _get_auth_scope() -> AuthScope:
    """Get auth scope from SURREAL_AUTH_SCOPE, failing fast on bad values."""
    raw = os.getenv("SURREAL_AUTH_SCOPE", "root").strip().lower()
    if raw not in _AUTH_SCOPES:
        raise ValueError(
            f"SURREAL_AUTH_SCOPE must be one of {_AUTH_SCOPES}, got {raw!r}."
        )
    return raw  # type: ignore[return-value]


def _parse_surreal_url() -> Optional[dict]:
    """Parse SURREAL_URL if set.

    Returns a dict with any of the following keys depending on the scheme:
        - mode: ConnectionMode
        - host: str (ws/http modes only)
        - port: Optional[int] — None when the URL has no explicit port
        - tls: bool (ws/http modes only)
        - path: str (embedded mode only)

    Returns None if SURREAL_URL is not set.
    """
    url = os.getenv("SURREAL_URL")
    if not url:
        return None

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    # Memory schemes
    if scheme in ("mem", "memory"):
        return {"mode": "memory"}

    # file:// / surrealkv:// -> embedded
    if scheme in ("file", "surrealkv"):
        path = parsed.path or parsed.netloc + parsed.path
        return {"mode": "embedded", "path": path}

    # Network schemes
    if scheme in ("ws", "wss"):
        mode: ConnectionMode = "ws"
        tls = scheme == "wss"
    elif scheme in ("http", "https"):
        mode = "http"
        tls = scheme == "https"
    else:
        raise ValueError(
            f"Unsupported SURREAL_URL scheme {scheme!r} (from {url!r}). "
            "Supported schemes: ws, wss, http, https, mem, memory, file, surrealkv."
        )

    return {
        "mode": mode,
        "host": parsed.hostname or "localhost",
        "port": parsed.port,  # None if not explicit in URL
        "tls": tls,
    }


def _env_bool(name: str) -> Optional[bool]:
    """Parse a boolean env var. Returns None if unset."""
    raw = os.getenv(name)
    if raw is None:
        return None
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _get_host() -> str:
    """Get host from SURREAL_URL or SURREAL_HOST."""
    parsed = _parse_surreal_url()
    if parsed and "host" in parsed:
        return parsed["host"]
    return os.getenv("SURREAL_HOST", "localhost")


def _get_tls() -> bool:
    """Get TLS flag from SURREAL_TLS or SURREAL_URL scheme."""
    env_tls = _env_bool("SURREAL_TLS")
    if env_tls is not None:
        return env_tls
    parsed = _parse_surreal_url()
    if parsed and "tls" in parsed:
        return parsed["tls"]
    return False


def _default_port_for(tls: bool) -> int:
    return 443 if tls else 8000


def _port_is_implicit() -> bool:
    """True when no explicit port was provided.

    Mirrors the precedence in `_get_port`: when SURREAL_URL is set, the URL
    is authoritative and SURREAL_PORT is ignored. Otherwise SURREAL_PORT
    counts as explicit.
    """
    parsed = _parse_surreal_url()
    if parsed and "host" in parsed:
        return parsed.get("port") is None
    return os.getenv("SURREAL_PORT") is None


def _get_port() -> int:
    """Get port using URL-first precedence.

    Precedence:
        1. If SURREAL_URL is set (network scheme), the URL is authoritative:
            a. URL has an explicit port → use it
            b. URL has no port → scheme default (443 for wss/https, 8000 for ws/http)
           SURREAL_PORT is intentionally ignored in this branch so that a
           sourced local-dev .env (SURREAL_PORT=8018) doesn't leak into a
           SURREAL_URL=wss://... cloud connection.
        2. If SURREAL_URL is not set:
            a. SURREAL_PORT env → use it
            b. Otherwise → scheme default
    """
    parsed = _parse_surreal_url()
    if parsed and "host" in parsed:
        if parsed.get("port") is not None:
            return parsed["port"]
        return _default_port_for(_get_tls())

    env_port = os.getenv("SURREAL_PORT")
    if env_port:
        try:
            return int(env_port)
        except ValueError as e:
            raise ValueError(
                f"SURREAL_PORT must be an integer, got {env_port!r}."
            ) from e

    return _default_port_for(_get_tls())


def _get_mode() -> ConnectionMode:
    """Get mode from SURREAL_URL or SURREAL_MODE."""
    parsed = _parse_surreal_url()
    if parsed:
        return parsed["mode"]
    return os.getenv("SURREAL_MODE", "ws")  # type: ignore


def _get_path() -> Optional[str]:
    """Get path from SURREAL_URL or SURREAL_PATH."""
    parsed = _parse_surreal_url()
    if parsed and parsed.get("mode") == "embedded":
        return parsed["path"]
    return os.getenv("SURREAL_PATH")


@dataclass
class SurrealConfig:
    """Configuration for SurrealDB connections."""

    host: str = field(default_factory=_get_host)
    port: int = field(default_factory=_get_port)
    user: str = field(default_factory=lambda: os.getenv("SURREAL_USER", "root"))
    password: str = field(
        default_factory=lambda: (
            os.getenv("SURREAL_PASS") or os.getenv("SURREAL_PASSWORD") or "root"
        )
    )
    namespace: str = field(
        default_factory=lambda: (
            os.getenv("SURREAL_NS") or os.getenv("SURREAL_NAMESPACE") or "test"
        )
    )
    database: str = field(
        default_factory=lambda: (
            os.getenv("SURREAL_DB") or os.getenv("SURREAL_DATABASE") or "test"
        )
    )
    auth_scope: AuthScope = field(default_factory=_get_auth_scope)
    mode: ConnectionMode = field(default_factory=_get_mode)
    persistent: bool = field(
        default_factory=lambda: (
            os.getenv("SURREAL_PERSISTENT", "true").lower() == "true"
        )
    )
    path: Optional[str] = field(default_factory=_get_path)
    tls: bool = field(default_factory=_get_tls)
    # Internal: True when the port came from an explicit source (SURREAL_PORT,
    # URL port, or init(port=...)). Used to decide whether init(tls=...) is
    # allowed to recompute the implicit scheme-aware default.
    _port_explicit: bool = field(
        default_factory=lambda: not _port_is_implicit(), repr=False
    )

    def get_url(self) -> str:
        """Get the connection URL based on current mode."""
        if self.mode == "memory":
            return "mem://"
        if self.mode == "embedded":
            path = self.path or "./surreal.db"
            return f"file://{path}"
        if self.mode == "ws":
            prefix = "wss" if self.tls else "ws"
        else:
            prefix = "https" if self.tls else "http"
        return f"{prefix}://{self.host}:{self.port}/rpc"


# Global config instance
_config: Optional[SurrealConfig] = None


def get_config() -> SurrealConfig:
    """Get the global config, creating it if needed."""
    global _config
    if _config is None:
        _config = SurrealConfig()
    return _config


def init(
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    namespace: Optional[str] = None,
    database: Optional[str] = None,
    auth_scope: Optional[AuthScope] = None,
    mode: Optional[ConnectionMode] = None,
    persistent: Optional[bool] = None,
    path: Optional[str] = None,
    tls: Optional[bool] = None,
) -> None:
    """
    Initialize or update the global configuration.

    Args:
        host: SurrealDB host (default: env SURREAL_HOST or "localhost")
        port: SurrealDB port (default: env SURREAL_PORT or 8000, or 443 when tls=True)
        user: Username (default: env SURREAL_USER or "root")
        password: Password (default: env SURREAL_PASS or "root")
        namespace: Namespace (default: env SURREAL_NS or "test")
        database: Database (default: env SURREAL_DB or "test")
        auth_scope: Signin scope - "root", "namespace", or "database"
            (default: env SURREAL_AUTH_SCOPE or "root"). Namespace/database
            scopes bind the signin to the configured namespace (and database),
            for users defined with DEFINE USER ... ON NAMESPACE/DATABASE.
        mode: Connection mode - "ws", "http", "memory", or "embedded" (default: env SURREAL_MODE or "ws")
        persistent: Use persistent connection (default: True for ws, configurable for http)
        path: File path for embedded mode (default: env SURREAL_PATH or "./surreal.db")
        tls: Use TLS (wss://, https://). Derived from SURREAL_URL scheme by default;
            can be overridden via SURREAL_TLS env var or this argument.
    """
    global _config
    config = get_config()

    if host is not None:
        config.host = host
    if port is not None:
        config.port = port
        config._port_explicit = True
    if user is not None:
        config.user = user
    if password is not None:
        config.password = password
    if namespace is not None:
        config.namespace = namespace
    if database is not None:
        config.database = database
    if auth_scope is not None:
        if auth_scope not in _AUTH_SCOPES:
            raise ValueError(
                f"auth_scope must be one of {_AUTH_SCOPES}, got {auth_scope!r}."
            )
        config.auth_scope = auth_scope
    if mode is not None:
        config.mode = mode
    if persistent is not None:
        config.persistent = persistent
    if path is not None:
        config.path = path
    if tls is not None:
        config.tls = tls
        # Recompute the implicit port default when the user flips TLS without
        # specifying a port — e.g. init(tls=True) on a fresh config should
        # yield :443, not the non-TLS default of :8000. Preserve any port the
        # user already pinned via SURREAL_PORT, URL, or a prior init(port=...).
        if port is None and not config._port_explicit:
            config.port = _default_port_for(tls)


def set_mode(mode: ConnectionMode) -> None:
    """Set the connection mode."""
    get_config().mode = mode


def get_mode() -> ConnectionMode:
    """Get the current connection mode."""
    return get_config().mode
