# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-03-28

### Added

- Embedded/file-based connection mode (`mode="embedded"`, `path="./data.db"`)
- In-memory connection mode (`mode="memory"`) - no server required
- `path` parameter in `init()` and `SurrealConfig` for embedded file path
- `SURREAL_PATH` environment variable for embedded mode
- Auto-detection of `file://`, `mem://`, `memory://`, `surrealkv://` schemes in `SURREAL_URL`
- GitHub Actions workflows for tag creation and PyPI publishing

### Changed

- Bumped `surrealdb` dependency to `>=1.0.7` (required for embedded support)
- Bumped minimum Python version to `>=3.11`
- `parse_record_ids()` now uses `table_name:id` format instead of `str()` to avoid `⟨⟩` escaping in SDK v1.0.8
- `repo_select()` with a specific record ID returns a `dict` again (SDK v1.0.8 changed to returning a list)

## [0.2.0] - 2026-03-19

### Added

- Migration system for managing SurrealDB schema changes
  - `MigrationRunner` (sync) and `AsyncMigrationRunner` (async) for programmatic usage
  - `sbl-migrate` CLI with `up`, `down`, `status`, and `create` commands
  - Auto-discovery of `.surrealql` migration files with numeric prefix ordering
  - Rollback support via `_down.surrealql` files
  - Migration tracking via `_sbl_migrations` table
  - `python -m surreal_basics.migrate` entry point
- `SurrealDBMigrationError` exception
- `SURREAL_MIGRATIONS_DIR` environment variable for default migrations directory
- Migration documentation (`docs/migrations.md`)

## [0.1.2] - Initial release

### Added

- Async and sync repository functions (`repo_query`, `repo_create`, `repo_select`, etc.)
- WebSocket and HTTP connection management with persistent (singleton) connections
- Automatic retry for transient errors (lock conflicts) via tenacity
- Environment-based configuration (`SURREAL_HOST`, `SURREAL_PORT`, etc.)
- `parse_record_ids` and `ensure_record_id` utilities
- Custom exception hierarchy (`SurrealDBError`, `SurrealDBQueryError`, etc.)
