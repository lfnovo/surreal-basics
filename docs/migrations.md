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
