"""Async migration runner."""

from pathlib import Path

from ..exceptions import SurrealDBMigrationError
from ..repo import repo_query
from .discovery import discover_migrations, parse_sql_file
from .models import MigrationFile, MigrationRecord

_TRACKING_TABLE = "_sbl_migrations"

_CREATE_TRACKING_TABLE = f"""
DEFINE TABLE IF NOT EXISTS {_TRACKING_TABLE} SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS version ON {_TRACKING_TABLE} TYPE int;
DEFINE FIELD IF NOT EXISTS name ON {_TRACKING_TABLE} TYPE string;
DEFINE FIELD IF NOT EXISTS applied_at ON {_TRACKING_TABLE} TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS idx_version ON {_TRACKING_TABLE} FIELDS version UNIQUE;
"""


class AsyncMigrationRunner:
    """Async migration runner using repo_query."""

    def __init__(self, migrations_dir: str | Path = "migrations"):
        self.migrations_dir = Path(migrations_dir)

    async def ensure_tracking_table(self) -> None:
        """Create the tracking table if it doesn't exist."""
        await repo_query(_CREATE_TRACKING_TABLE)

    async def get_applied_versions(self) -> list[MigrationRecord]:
        """Get all applied migrations ordered by version."""
        await self.ensure_tracking_table()
        results = await repo_query(
            f"SELECT * FROM {_TRACKING_TABLE} ORDER BY version ASC"
        )
        return [
            MigrationRecord(
                version=r["version"],
                name=r["name"],
                applied_at=str(r["applied_at"]),
            )
            for r in results
        ]

    async def get_latest_version(self) -> int:
        """Get the latest applied migration version, or 0 if none."""
        applied = await self.get_applied_versions()
        return applied[-1].version if applied else 0

    async def get_pending(self) -> list[MigrationFile]:
        """Get migrations that haven't been applied yet."""
        all_migrations = discover_migrations(self.migrations_dir)
        applied_versions = {r.version for r in await self.get_applied_versions()}
        return [m for m in all_migrations if m.version not in applied_versions]

    async def run_up(self, target_version: int | None = None) -> list[MigrationFile]:
        """Run all pending migrations, optionally up to a target version.

        Args:
            target_version: If set, only run migrations up to this version.

        Returns:
            List of migrations that were applied.

        Raises:
            SurrealDBMigrationError: If a migration fails.
        """
        await self.ensure_tracking_table()
        pending = await self.get_pending()

        if target_version is not None:
            pending = [m for m in pending if m.version <= target_version]

        applied = []
        for migration in pending:
            sql = parse_sql_file(migration.up_path)
            try:
                await repo_query(sql)
            except Exception as e:
                raise SurrealDBMigrationError(
                    f"Migration {migration.version:03d}_{migration.name} failed: {e}"
                ) from e

            await repo_query(
                f"CREATE {_TRACKING_TABLE} CONTENT $data",
                {
                    "data": {
                        "version": migration.version,
                        "name": migration.name,
                    }
                },
            )
            applied.append(migration)

        return applied

    async def run_down(self, steps: int = 1) -> list[MigrationFile]:
        """Rollback the last N applied migrations.

        Args:
            steps: Number of migrations to rollback.

        Returns:
            List of migrations that were rolled back.

        Raises:
            SurrealDBMigrationError: If a rollback fails or no down file exists.
        """
        await self.ensure_tracking_table()
        applied = await self.get_applied_versions()
        all_migrations = discover_migrations(self.migrations_dir)
        migration_map = {m.version: m for m in all_migrations}

        to_rollback = list(reversed(applied))[:steps]
        rolled_back = []

        for record in to_rollback:
            migration = migration_map.get(record.version)
            if migration is None:
                raise SurrealDBMigrationError(
                    f"Migration file for version {record.version} not found"
                )

            if migration.down_path is None:
                raise SurrealDBMigrationError(
                    f"No down migration for {record.version:03d}_{record.name}"
                )

            sql = parse_sql_file(migration.down_path)
            try:
                await repo_query(sql)
            except Exception as e:
                raise SurrealDBMigrationError(
                    f"Rollback {record.version:03d}_{record.name} failed: {e}"
                ) from e

            await repo_query(
                f"DELETE {_TRACKING_TABLE} WHERE version = $version",
                {"version": record.version},
            )
            rolled_back.append(migration)

        return rolled_back

    async def status(self) -> dict:
        """Get the current migration status.

        Returns:
            Dict with 'current_version', 'applied', and 'pending' keys.
        """
        applied = await self.get_applied_versions()
        all_migrations = discover_migrations(self.migrations_dir)
        applied_versions = {r.version for r in applied}
        pending = [m for m in all_migrations if m.version not in applied_versions]

        return {
            "current_version": applied[-1].version if applied else 0,
            "applied": applied,
            "pending": pending,
        }
