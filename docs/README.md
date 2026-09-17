# Documentation - surreal-basics

## Contents

- [Configuration](configuration.md) - Environment variables, init() and connection modes
- [API Reference](api-reference.md) - Complete documentation of all functions
- [Migrations](migrations.md) - Schema migration system
- [Targets](targets.md) - Several namespaces, databases or users from one process

## Main Features

### Connections

| Mode | Characteristics |
|------|-----------------|
| **WebSocket** | Persistent connection, best performance, ideal for long-running applications |
| **HTTP** | Stateless or persistent, ideal for serverless/lambdas |

### CRUD Operations

- `repo_create` / `repo_create_sync` - Create records (opt-in timestamps via `add_timestamps=True`)
- `repo_select` / `repo_select_sync` - Fetch by table or specific ID
- `repo_update` / `repo_update_sync` - Update existing record
- `repo_upsert` / `repo_upsert_sync` - Create or update (merge)
- `repo_delete` / `repo_delete_sync` - Delete record

### Advanced Operations

- `repo_query` / `repo_query_sync` - Custom SurrealQL queries
- `repo_insert` / `repo_insert_sync` - Bulk insert
- `repo_relate` / `repo_relate_sync` - Create relationships between records

### Targets

- `Target` - Namespace, database and credential for one call (`using=`)
- `use_target()` - Bind a target for a block, per task/thread
- One persistent connection per target, idle ones capped by `ConnectionManager.max_connections`

### Migrations

- `MigrationRunner` / `AsyncMigrationRunner` - Run and rollback migrations programmatically
- `discover_migrations()` - Auto-discover `.surrealql` migration files
- `scaffold_migration()` - Create new migration file pairs
- `sbl-migrate` CLI - Command-line interface for migrations

### Utilities

- `parse_record_ids()` - Convert RecordID to strings in nested structures
- `ensure_record_id()` - Ensure a value is a RecordID
- `reset_connections()` - Reset connections (useful for testing)

## Quick Links

- [Main README](../README.md) - Quick start and overview
- [Benchmark](../benchmark_library.py) - Performance comparison
