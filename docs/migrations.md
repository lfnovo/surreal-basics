# Migrations

`surreal-basics` includes a migration system for managing SurrealDB schema changes incrementally and reversibly.

## File Naming Convention

Migration files use numeric prefixes for ordering:

```
migrations/
  001_create_users.surrealql          # up migration
  001_create_users_down.surrealql     # down migration (rollback)
  002_add_indexes.surrealql
  002_add_indexes_down.surrealql
```

- **Up files**: `NNN_name.surrealql` - contain the forward migration SQL
- **Down files**: `NNN_name_down.surrealql` - contain the rollback SQL (optional)

## CLI Usage

The `sbl-migrate` command is available after installing the package.

### Create a migration

```bash
sbl-migrate create create_users
# Creates:
#   migrations/001_create_users.surrealql
#   migrations/001_create_users_down.surrealql
```

### Check status

```bash
sbl-migrate status
# Current version: 1
#
#   [APPLIED] 001_create_users (at 2025-01-15T10:30:00Z)
#   [PENDING] 002_add_indexes
```

### Apply migrations

```bash
# Apply all pending
sbl-migrate up

# Apply up to a specific version
sbl-migrate up --to 2
```

### Dry-run (validate without applying)

```bash
# Validate all pending migrations without applying
sbl-migrate up --dry-run

# Validate up to a specific version
sbl-migrate up --to 2 --dry-run
```

Each migration is wrapped in `BEGIN TRANSACTION; ... CANCEL TRANSACTION;`, so SurrealDB parses and validates the SQL but rolls back all changes. If a migration has invalid syntax or references non-existent fields/tables, the dry-run will catch it.

### Guard against the wrong target

When several environments share one SurrealDB instance under different
namespaces, a stale `SURREAL_NAMESPACE` is enough to migrate the wrong one.
`up`, `down` and `status` accept optional `--expect-ns` / `--expect-db`,
which abort before any SQL runs if the resolved target doesn't match:

```bash
sbl-migrate up --expect-ns acme-prod --expect-db app

# Error: ABORT: target namespace is 'acme-stg', but --expect-ns is
# 'acme-prod'. No SQL was executed.
```

In CI, where threading flags through is awkward, set `SBL_EXPECT_NS` /
`SBL_EXPECT_DB` instead — the flags take precedence over them. With neither
set nothing is checked, so single-environment setups are unaffected.

### Adopt tracking on an existing database

A database that predates this library has no tracking table. Start using
migrations on it and every migration looks pending, so the next `up` replays
the whole history against a database that already has it. That is harmless for
`IF NOT EXISTS` DDL and destructive for anything that deletes or rebuilds.

`baseline` records migrations as applied without running their SQL:

```bash
sbl-migrate baseline --expect-ns acme-prod

#   [BASELINED] 001_create_users
#   [BASELINED] 002_add_indexes
#
# 2 migration(s) recorded as applied. No SQL was run.
```

Only run this against a database whose schema already matches those files.
If it is mid-history, `--to` records up to a version and leaves the rest
pending:

```bash
sbl-migrate baseline --to 2      # 003 onwards stays pending
```

It is a one-shot per database, and safe to repeat: already-recorded versions
are skipped.

### Refuse to migrate a database that was never baselined

An empty tracking table is ambiguous — either a fresh database that should run
the whole history, or an existing one that someone forgot to baseline. The
library cannot tell them apart, so `up` takes `--require-baseline` (or
`SBL_REQUIRE_BASELINE=1`) for the caller to say which it expects:

```bash
sbl-migrate up --require-baseline

# Error: ABORT: --require-baseline is set but no migration is recorded as
# applied. Running now would apply the full history to this database. If its
# schema is already up to date, run `sbl-migrate baseline` first. No SQL was
# executed.
```

Worth setting in a deploy pipeline that migrates an environment that already
exists: the failure mode it prevents is a full replay against production. It
is off by default, so a first run on a new database keeps working, and it is
not checked for `--dry-run`, which applies nothing.

### Rollback

```bash
# Rollback last migration
sbl-migrate down

# Rollback last 3 migrations
sbl-migrate down --steps 3
```

### Custom directory

All commands accept `--dir` to specify the migrations directory:

```bash
sbl-migrate status --dir ./db/migrations
```

Default directory: `SURREAL_MIGRATIONS_DIR` env var, or `./migrations/`.

### Running via Python module

```bash
python -m surreal_basics.migrate up
python -m surreal_basics.migrate status
```

## Programmatic Usage

### Sync

```python
from surreal_basics.migrate import MigrationRunner

runner = MigrationRunner("./migrations")

# Apply all pending migrations
applied = runner.run_up()
for m in applied:
    print(f"Applied {m.version:03d}_{m.name}")

# Apply up to a specific version
runner.run_up(target_version=3)

# Dry-run: validate without applying
runner.run_up(dry_run=True)

# Rollback last migration
runner.run_down()

# Rollback last N migrations
runner.run_down(steps=2)

# Get status
status = runner.status()
print(f"Current version: {status['current_version']}")
print(f"Pending: {len(status['pending'])}")
```

### Async

```python
from surreal_basics.migrate import AsyncMigrationRunner

runner = AsyncMigrationRunner("./migrations")

applied = await runner.run_up()
await runner.run_down(steps=1)
status = await runner.status()
```

### Discovery

```python
from pathlib import Path
from surreal_basics.migrate import discover_migrations, scaffold_migration

# List all migration files
migrations = discover_migrations(Path("./migrations"))
for m in migrations:
    print(f"{m.version:03d}_{m.name} (down: {'yes' if m.down_path else 'no'})")

# Create a new migration pair
up_path, down_path = scaffold_migration(Path("./migrations"), "add_email_field")
```

## Tracking

Applied migrations are tracked in the `_sbl_migrations` table in your SurrealDB database. This table is created automatically on first use with the following schema:

| Field | Type | Description |
|-------|------|-------------|
| `version` | int | Migration version number (unique) |
| `name` | string | Migration name |
| `applied_at` | datetime | When the migration was applied |

## Concurrent Replicas

If several replicas of your app run migrations at startup, they can all see the
same migration as pending and execute it before any of them records it.

Recording is safe: the tracking record is written with an `UPSERT` against a
deterministic record id, so a second replica recording the same version is a
no-op rather than a unique-index violation.

Execution is not serialized, so **write your migrations idempotently** —
prefer `DEFINE ... IF NOT EXISTS` and avoid statements that break when replayed:

```sql
DEFINE TABLE IF NOT EXISTS users SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS email ON users TYPE string;
DEFINE INDEX IF NOT EXISTS idx_email ON users FIELDS email UNIQUE;
```

## Error Handling

If a migration fails, it is **not** recorded in the tracking table. Execution stops immediately and a `SurrealDBMigrationError` is raised.

```python
from surreal_basics import SurrealDBMigrationError
from surreal_basics.migrate import MigrationRunner

runner = MigrationRunner("./migrations")
try:
    runner.run_up()
except SurrealDBMigrationError as e:
    print(f"Migration failed: {e}")
```

## Configuration

The migration system uses the same connection configuration as the rest of `surreal-basics` (env vars `SURREAL_HOST`, `SURREAL_PORT`, etc.). See [Configuration](configuration.md) for details.

| Variable | Default | Description |
|----------|---------|-------------|
| `SURREAL_MIGRATIONS_DIR` | `./migrations` | Default migrations directory for CLI |
| `SBL_EXPECT_NS` | _(unset)_ | Abort `up`/`down`/`status` unless the target namespace matches |
| `SBL_EXPECT_DB` | _(unset)_ | Abort `up`/`down`/`status` unless the target database matches |
| `SBL_REQUIRE_BASELINE` | _(unset)_ | Abort `up` unless at least one migration is recorded as applied |
