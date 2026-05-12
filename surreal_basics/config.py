"""Configuration management for surreal_basics."""

import os
from dataclasses import dataclass, field
from typing import Literal, Optional
from urllib.parse import urlparse

# All supported connection modes
ConnectionMode = Literal["ws", "http", "memory", "embedded"]


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
        mode = "ws"
        tls = False

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


def _get_port() -> int:
    """Get port from SURREAL_PORT, SURREAL_URL, or scheme-aware default.

    Precedence:
        1. SURREAL_PORT env var (explicit override)
        2. Port in SURREAL_URL
        3. 443 if TLS, else 8000
    """
    env_port = os.getenv("SURREAL_PORT")
    if env_port:
        return int(env_port)

    parsed = _parse_surreal_url()
    if parsed and parsed.get("port") is not None:
        return parsed["port"]

    return 443 if _get_tls() else 8000


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
        default_factory=lambda: os.getenv("SURREAL_PASS") or os.getenv("SURREAL_PASSWORD", "root")
    )
    namespace: str = field(
        default_factory=lambda: os.getenv("SURREAL_NS") or os.getenv("SURREAL_NAMESPACE", "test")
    )
    database: str = field(
        default_factory=lambda: os.getenv("SURREAL_DB") or os.getenv("SURREAL_DATABASE", "test")
    )
    mode: ConnectionMode = field(default_factory=_get_mode)
    persistent: bool = field(
        default_factory=lambda: os.getenv("SURREAL_PERSISTENT", "true").lower() == "true"
    )
    path: Optional[str] = field(default_factory=_get_path)
    tls: bool = field(default_factory=_get_tls)

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
    if user is not None:
        config.user = user
    if password is not None:
        config.password = password
    if namespace is not None:
        config.namespace = namespace
    if database is not None:
        config.database = database
    if mode is not None:
        config.mode = mode
    if persistent is not None:
        config.persistent = persistent
    if path is not None:
        config.path = path
    if tls is not None:
        config.tls = tls


def set_mode(mode: ConnectionMode) -> None:
    """Set the connection mode."""
    get_config().mode = mode


def get_mode() -> ConnectionMode:
    """Get the current connection mode."""
    return get_config().mode
