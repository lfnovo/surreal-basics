# surreal-basics

SurrealDB abstraction library for Python.

## Commands

```bash
uv run pytest                       # run tests
uv run pytest -v                    # verbose tests
uv run python benchmark_library.py  # benchmark
sbl-migrate up                      # run pending migrations
sbl-migrate status                  # show migration status
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
  - `migrate/` - migration system
    - `cli.py` - CLI (sbl-migrate command)
    - `discovery.py` - auto-discovery of .surrealql files
    - `runner.py` - MigrationRunner (sync)
    - `runner_async.py` - AsyncMigrationRunner (async)
    - `models.py` - MigrationFile, MigrationRecord dataclasses

## Best Practices

- WS is 3-6x faster than HTTP
- Always use `reset_connections()` in tests
- "can be retried" errors are lock conflicts - handled automatically
- SDK RecordID must be converted with `parse_record_ids()`
- Migration files follow `NNN_name.surrealql` / `NNN_name_down.surrealql` naming
- Migrations are tracked in `_sbl_migrations` table

## Documentation

- [README](README.md) - quick start and overview
- [docs/](docs/README.md) - complete documentation
- [docs/api-reference.md](docs/api-reference.md) - API reference
- [docs/migrations.md](docs/migrations.md) - migration system guide
