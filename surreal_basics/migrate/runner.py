"""Sync migration runner."""

from pathlib import Path

from ..exceptions import SurrealDBMigrationError, SurrealDBQueryError
from ..repo_sync import repo_query_sync
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


class MigrationRunner:
    """Sync migration runner using repo_query_sync."""

    def __init__(self, migrations_dir: str | Path = "migrations"):
        self.migrations_dir = Path(migrations_dir)

    def ensure_tracking_table(self) -> None:
        """Create the tracking table if it doesn't exist."""
        repo_query_sync(_CREATE_TRACKING_TABLE)

    def get_applied_versions(self) -> list[MigrationRecord]:
        """Get all applied migrations ordered by version."""
        self.ensure_tracking_table()
        results = repo_query_sync(
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

    def get_latest_version(self) -> int:
        """Get the latest applied migration version, or 0 if none."""
        applied = self.get_applied_versions()
        return applied[-1].version if applied else 0

    def get_pending(self) -> list[MigrationFile]:
        """Get migrations that haven't been applied yet."""
        all_migrations = discover_migrations(self.migrations_dir)
        applied_versions = {r.version for r in self.get_applied_versions()}
        return [m for m in all_migrations if m.version not in applied_versions]

    def run_up(
        self,
        target_version: int | None = None,
        dry_run: bool = False,
    ) -> list[MigrationFile]:
        """Run all pending migrations, optionally up to a target version.

        Args:
            target_version: If set, only run migrations up to this version.
            dry_run: If True, validate migrations inside a transaction that
                gets cancelled, so nothing is persisted.

        Returns:
            List of migrations that were applied (or validated in dry-run).

        Raises:
            SurrealDBMigrationError: If a migration fails.
        """
        self.ensure_tracking_table()
        pending = self.get_pending()

        if target_version is not None:
            pending = [m for m in pending if m.version <= target_version]

        applied = []
        for migration in pending:
            sql = parse_sql_file(migration.up_path)
            if dry_run:
                dry_sql = f"BEGIN TRANSACTION;\n{sql}\nCANCEL TRANSACTION;"
                try:
                    repo_query_sync(dry_sql)
                except SurrealDBQueryError as e:
                    if "cancelled transaction" in str(e).lower():
                        pass  # Expected: CANCEL TRANSACTION worked
                    else:
                        raise SurrealDBMigrationError(
                            f"Migration {migration.version:03d}_{migration.name} "
                            f"failed validation: {e}"
                        ) from e
                except Exception as e:
                    raise SurrealDBMigrationError(
                        f"Migration {migration.version:03d}_{migration.name} "
                        f"failed validation: {e}"
                    ) from e
            else:
                try:
                    repo_query_sync(sql)
                except Exception as e:
                    raise SurrealDBMigrationError(
                        f"Migration {migration.version:03d}_{migration.name} "
                        f"failed: {e}"
                    ) from e

                repo_query_sync(
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

    def run_down(self, steps: int = 1) -> list[MigrationFile]:
        """Rollback the last N applied migrations.

        Args:
            steps: Number of migrations to rollback.

        Returns:
            List of migrations that were rolled back.

        Raises:
            SurrealDBMigrationError: If a rollback fails or no down file exists.
        """
        self.ensure_tracking_table()
        applied = self.get_applied_versions()
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
                repo_query_sync(sql)
            except Exception as e:
                raise SurrealDBMigrationError(
                    f"Rollback {record.version:03d}_{record.name} failed: {e}"
                ) from e

            repo_query_sync(
                f"DELETE {_TRACKING_TABLE} WHERE version = $version",
                {"version": record.version},
            )
            rolled_back.append(migration)

        return rolled_back

    def status(self) -> dict:
        """Get the current migration status.

        Returns:
            Dict with 'current_version', 'applied', and 'pending' keys.
        """
        applied = self.get_applied_versions()
        all_migrations = discover_migrations(self.migrations_dir)
        applied_versions = {r.version for r in applied}
        pending = [m for m in all_migrations if m.version not in applied_versions]

        return {
            "current_version": applied[-1].version if applied else 0,
            "applied": applied,
            "pending": pending,
        }
