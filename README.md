# surreal-basics

[![PyPI version](https://img.shields.io/pypi/v/surreal-basics.svg)](https://pypi.org/project/surreal-basics/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

Simple and transparent SurrealDB connection abstraction for Python.

## Why surreal-basics?

When working with SurrealDB, you need to manage connections, authentication, and namespaces for each operation. `surreal-basics` abstracts this complexity, offering:

- **Automatic connection**: Configure once, use anywhere
- **Optimized performance**: Persistent (singleton) connections for WebSocket and HTTP
- **Smart retry**: Automatic handling of transient errors (lock conflicts)
- **Consistent API**: `repo_*` functions for async and `repo_*_sync` for sync

## Installation

```bash
pip install surreal-basics
```

Or with uv:

```bash
uv add surreal-basics
```

## Quick Start

### Configuration via environment variables

```bash
export SURREAL_HOST=localhost
export SURREAL_PORT=8000
export SURREAL_USER=root
export SURREAL_PASS=root
export SURREAL_NS=test
export SURREAL_DB=test
export SURREAL_MODE=ws  # or "http"
```

### Basic usage

```python
from surreal_basics import repo_query, repo_create, repo_select

# Simple query
results = await repo_query("SELECT * FROM user WHERE active = true")

# Create record (automatic timestamps)
user = await repo_create("user", {"name": "John", "email": "john@test.com"})

# Select by ID
user = await repo_select("user:123")
```

### Synchronous mode

```python
from surreal_basics import repo_query_sync, repo_create_sync

# Same operations, without async/await
results = repo_query_sync("SELECT * FROM user")
user = repo_create_sync("user", {"name": "Mary"})
```

### Programmatic configuration

```python
import surreal_basics

# Configure connection
surreal_basics.init(
    host="localhost",
    port=8000,
    namespace="my_ns",
    database="my_db",
    mode="ws",  # "ws" or "http"
    persistent=True,  # persistent connection (recommended)
)

# Or just change the mode
surreal_basics.mode = "http"
```

## Performance

Benchmarks with 1000 operations each (localhost):

| Operation | HTTP Sync | HTTP Async | WS Sync | WS Async |
|-----------|-----------|------------|---------|----------|
| CREATE    | ~130 ops/s | ~180 ops/s | ~650 ops/s | ~750 ops/s |
| SELECT    | ~150 ops/s | ~200 ops/s | ~800 ops/s | ~3500 ops/s |
| UPDATE    | ~130 ops/s | ~170 ops/s | ~600 ops/s | ~2800 ops/s |
| DELETE    | ~140 ops/s | ~190 ops/s | ~700 ops/s | ~3000 ops/s |

**Recommendation**: Use WebSocket (`mode="ws"`) for best performance. HTTP is useful for serverless environments or when WebSocket is not available.

## API Reference

### Async Functions

| Function | Description |
|----------|-------------|
| `repo_query(query, vars)` | Execute SurrealQL query |
| `repo_create(table, data)` | Create record with timestamps |
| `repo_select(table_or_id)` | Select records or by ID |
| `repo_update(table, id, data)` | Update existing record |
| `repo_upsert(table, id, data)` | Create or update (merge) |
| `repo_delete(record_id)` | Delete record |
| `repo_insert(table, data_list)` | Bulk insert |
| `repo_relate(source, rel, target)` | Create relationship |

### Sync Functions

All async functions have sync equivalents with `_sync` suffix:
- `repo_query_sync`, `repo_create_sync`, etc.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SURREAL_HOST` | localhost | SurrealDB host |
| `SURREAL_PORT` | 8000 | Port |
| `SURREAL_USER` | root | Username |
| `SURREAL_PASS` | root | Password |
| `SURREAL_NS` | test | Namespace |
| `SURREAL_DB` | test | Database |
| `SURREAL_MODE` | ws | Mode: "ws" or "http" |
| `SURREAL_PERSISTENT` | true | Persistent connection |

## Error Handling

```python
from surreal_basics import (
    SurrealDBConnectionError,  # Connection failed
    SurrealDBQueryError,       # Query error (no retry)
    SurrealDBTransientError,   # Transient error (automatic retry)
)

try:
    result = await repo_query("SELECT * FROM user")
except SurrealDBConnectionError as e:
    print(f"Connection failed: {e}")
except SurrealDBQueryError as e:
    print(f"Query error: {e}")
```

## Documentation

See [docs/](docs/) for complete documentation including:
- [Configuration](docs/configuration.md) - Environment variables, init() and connection modes
- [API Reference](docs/api-reference.md) - Complete documentation of all functions

## Development

```bash
# Clone and install
git clone https://github.com/lfnovo/surreal-basics.git
cd surreal-basics
uv sync

# Run tests
uv run pytest

# Run benchmark
uv run python benchmark_library.py
```

## License

MIT
