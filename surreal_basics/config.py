"""Configuration management for surreal_basics."""

import os
from dataclasses import dataclass, field
from typing import Literal, Optional, Tuple, Union
from urllib.parse import urlparse

# All supported connection modes
ConnectionMode = Literal["ws", "http", "memory", "embedded"]


def _parse_surreal_url() -> (
    Optional[Union[Tuple[str, int, Literal["http", "ws"]], Tuple[str, Literal["memory", "embedded"]]]]
):
    """Parse SURREAL_URL if set.

    Returns:
        - (host, port, mode) for ws/http URLs
        - (path, mode) for file:// URLs
        - ("memory", "memory") for memory URLs
        - None if SURREAL_URL is not set
    """
    url = os.getenv("SURREAL_URL")
    if not url:
        return None

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    # Handle memory schemes
    if scheme in ("mem", "memory"):
        return ("memory", "memory")

    # Handle file:// scheme -> embedded mode
    if scheme in ("file", "surrealkv"):
        path = parsed.path or parsed.netloc + parsed.path
        return (path, "embedded")

    # Determine mode from scheme
    if scheme in ("ws", "wss"):
        mode: Literal["http", "ws"] = "ws"
    elif scheme in ("http", "https"):
        mode = "http"
    else:
        mode = "ws"  # default to ws

    host = parsed.hostname or "localhost"
    port = parsed.port or 8000

    return (host, port, mode)


def _get_host() -> str:
    """Get host from SURREAL_URL or SURREAL_HOST."""
    parsed = _parse_surreal_url()
    if parsed and len(parsed) == 3:
        return parsed[0]
    return os.getenv("SURREAL_HOST", "localhost")


def _get_port() -> int:
    """Get port from SURREAL_URL or SURREAL_PORT."""
    parsed = _parse_surreal_url()
    if parsed and len(parsed) == 3:
        return parsed[1]
    return int(os.getenv("SURREAL_PORT", "8000"))


def _get_mode() -> ConnectionMode:
    """Get mode from SURREAL_URL or SURREAL_MODE."""
    parsed = _parse_surreal_url()
    if parsed:
        if len(parsed) == 2:
            return parsed[1]
        return parsed[2]
    return os.getenv("SURREAL_MODE", "ws")  # type: ignore


def _get_path() -> Optional[str]:
    """Get path from SURREAL_URL or SURREAL_PATH."""
    parsed = _parse_surreal_url()
    if parsed and len(parsed) == 2 and parsed[1] == "embedded":
        return parsed[0]
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

    def get_url(self) -> str:
        """Get the connection URL based on current mode."""
        if self.mode == "memory":
            return "mem://"
        if self.mode == "embedded":
            path = self.path or "./surreal.db"
            return f"file://{path}"
        prefix = "ws" if self.mode == "ws" else "http"
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
) -> None:
    """
    Initialize or update the global configuration.

    Args:
        host: SurrealDB host (default: env SURREAL_HOST or "localhost")
        port: SurrealDB port (default: env SURREAL_PORT or 8000)
        user: Username (default: env SURREAL_USER or "root")
        password: Password (default: env SURREAL_PASS or "root")
        namespace: Namespace (default: env SURREAL_NS or "test")
        database: Database (default: env SURREAL_DB or "test")
        mode: Connection mode - "ws", "http", "memory", or "embedded" (default: env SURREAL_MODE or "ws")
        persistent: Use persistent connection (default: True for ws, configurable for http)
        path: File path for embedded mode (default: env SURREAL_PATH or "./surreal.db")
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


def set_mode(mode: ConnectionMode) -> None:
    """Set the connection mode."""
    get_config().mode = mode


def get_mode() -> ConnectionMode:
    """Get the current connection mode."""
    return get_config().mode
