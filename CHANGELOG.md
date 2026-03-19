# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
