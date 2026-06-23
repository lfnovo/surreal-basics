# Configuration

## Environment Variables

The library automatically loads configuration from environment variables.

### Discrete variables

```bash
SURREAL_HOST=localhost       # SurrealDB host
SURREAL_PORT=8000            # Port (defaults to 443 when TLS is enabled)
SURREAL_USER=root            # Authentication username
SURREAL_PASS=root            # Password (alias: SURREAL_PASSWORD)
SURREAL_NS=test              # Namespace (alias: SURREAL_NAMESPACE)
SURREAL_DB=test              # Database (alias: SURREAL_DATABASE)
SURREAL_MODE=ws              # ws | http | memory | embedded
SURREAL_PERSISTENT=true      # Persistent connection (true/false)
SURREAL_TLS=false            # Use wss:// / https:// (true/false)
SURREAL_PATH=./surreal.db    # File path for embedded mode
```

### Single URL

Alternatively, set `SURREAL_URL` and the scheme selects the mode. When set, the
URL is **authoritative** — its host, port, and TLS take precedence over the
discrete variables above (so a local `SURREAL_PORT` can't leak into a cloud
connection).

```bash
SURREAL_URL=ws://localhost:8000/rpc      # WebSocket
SURREAL_URL=wss://tenant.surreal.cloud   # WebSocket + TLS (port defaults to 443)
SURREAL_URL=http://localhost:8000        # HTTP
SURREAL_URL=https://tenant.surreal.cloud # HTTP + TLS
SURREAL_URL=mem://                       # In-memory
SURREAL_URL=file://./surreal.db          # Embedded (also: surrealkv://)
```

An unsupported scheme raises a `ValueError` at config time rather than silently
falling back. `SURREAL_TLS` can still override the scheme-derived TLS flag (e.g.
upgrade a `ws://` URL to `wss://`).

## Programmatic Configuration

### init()

Use `init()` to override environment values:

```python
import surreal_basics

surreal_basics.init(
    host="localhost",
    port=8000,
    user="root",
    password="root",
    namespace="my_ns",
    database="my_db",
    mode="ws",
    persistent=True,
    tls=False,
    path=None,        # embedded mode only
)
```

Only the provided parameters are changed - others keep their current value.
Calling `init(tls=True)` without an explicit port recomputes the default port to
443 (and back to 8000 for `tls=False`), unless a port was pinned explicitly.

### Mode Switching

```python
import surreal_basics

# Via module property
surreal_basics.mode = "http"

# Via function
surreal_basics.set_mode("ws")

# Check current mode
current = surreal_basics.get_mode()
```

## Connection Modes

### WebSocket (recommended)

```python
surreal_basics.init(mode="ws")
```

- **Persistent connection**: A single connection is maintained (singleton)
- **Performance**: 3-6x faster than HTTP
- **Ideal for**: Long-running applications, backends, workers

### HTTP

```python
# HTTP with persistent connection (default)
surreal_basics.init(mode="http", persistent=True)

# HTTP stateless (new connection per operation)
surreal_basics.init(mode="http", persistent=False)
```

- **persistent=True**: Keeps connection open for reuse
- **persistent=False**: New connection per operation (useful for lambdas)
- **Ideal for**: Serverless, environments without WebSocket support

### Memory

```python
surreal_basics.init(mode="memory")
```

- **In-process, ephemeral**: data lives only for the process lifetime
- **Ideal for**: tests, quick experiments, examples

### Embedded

```python
surreal_basics.init(mode="embedded", path="./surreal.db")
```

- **On-disk, no server**: persists to a local SurrealKV file
- **Ideal for**: single-node apps, CLIs, local-first tools

> Memory and embedded modes require the `surrealdb` SDK extras for the embedded
> engine. Install them if you hit an import error for these modes.

## TLS

```python
# Explicit flag
surreal_basics.init(mode="ws", host="tenant.surreal.cloud", tls=True)

# Or via a secure URL scheme
# SURREAL_URL=wss://tenant.surreal.cloud
```

When TLS is enabled and no port is set, the default becomes 443. URLs generate
`wss://` / `https://` accordingly.

## Connection Management

### Reset

Useful for testing or reconfiguration:

```python
from surreal_basics import reset_connections, reset_connections_async

# Sync
reset_connections()

# Async (properly closes async connections)
await reset_connections_async()
```

### Direct Access (advanced)

For special cases, access the connection manager:

```python
from surreal_basics import get_async_connection, get_sync_connection

# Use as context manager
async with get_async_connection() as conn:
    result = await conn.query("SELECT * FROM user")

with get_sync_connection() as conn:
    result = conn.query("SELECT * FROM user")
```

## Test Configuration

```python
import pytest
from surreal_basics import init, reset_connections

@pytest.fixture
def surreal_config():
    init(
        host="localhost",
        port=8000,  # test port
        namespace="test_ns",
        database="test_db",
        mode="ws",
    )
    yield
    reset_connections()
```
