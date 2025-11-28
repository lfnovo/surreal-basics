# Configuration

## Environment Variables

The library automatically loads configuration via environment variables:

```bash
SURREAL_HOST=localhost       # SurrealDB host
SURREAL_PORT=8000            # Port
SURREAL_USER=root            # Authentication username
SURREAL_PASS=root            # Password
SURREAL_NS=test              # Namespace
SURREAL_DB=test              # Database
SURREAL_MODE=ws              # "ws" (WebSocket) or "http"
SURREAL_PERSISTENT=true      # Persistent connection (true/false)
```

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
)
```

Only the provided parameters are changed - others keep their current value.

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
        port=8018,  # test port
        namespace="test_ns",
        database="test_db",
        mode="ws",
    )
    yield
    reset_connections()
```
