# surreal-basics

SurrealDB abstraction library for Python.

## Commands

```bash
uv run pytest                       # run tests
uv run pytest -v                    # verbose tests
uv run python benchmark_library.py  # benchmark
```

## Structure

- `surreal_basics/` - library code
  - `config.py` - configuration (env vars, init())
  - `connection.py` - connection management (singleton WS, HTTP)
  - `repo.py` - async functions
  - `repo_sync.py` - sync functions
  - `retry.py` - retry with tenacity
  - `exceptions.py` - custom exceptions
  - `utils.py` - parse_record_ids, ensure_record_id

## Best Practices

- WS is 3-6x faster than HTTP
- Always use `reset_connections()` in tests
- "can be retried" errors are lock conflicts - handled automatically
- SDK RecordID must be converted with `parse_record_ids()`

## Documentation

- [README](README.md) - quick start and overview
- [docs/](docs/README.md) - complete documentation
- [docs/api-reference.md](docs/api-reference.md) - API reference
