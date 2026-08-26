"""Async migration runner."""

from pathlib import Path

from .._sdk import is_duplicate_error
from ..exceptions import SurrealDBMigrationError, SurrealDBQueryError
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

    async def run_up(
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
        await self.ensure_tracking_table()
        pending = await self.get_pending()

        if target_version is not None:
            pending = [m for m in pending if m.version <= target_version]

        applied = []
        for migration in pending:
            sql = parse_sql_file(migration.up_path)
            if dry_run:
                dry_sql = f"BEGIN TRANSACTION;\n{sql}\nCANCEL TRANSACTION;"
                try:
                    await repo_query(dry_sql)
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
                    await repo_query(sql)
                except Exception as e:
                    raise SurrealDBMigrationError(
                        f"Migration {migration.version:03d}_{migration.name} "
                        f"failed: {e}"
                    ) from e

                await self._record_applied(migration)
            applied.append(migration)

        return applied

    async def baseline(self, target_version: int | None = None) -> list[MigrationFile]:
        """Record pending migrations as applied, without executing their SQL.

        For adopting migration tracking on a database whose schema already
        matches the migrations on disk. Without it the tracking table starts
        empty, every migration looks pending, and the next ``run_up`` replays
        the whole history against a database that already has it — harmless for
        ``IF NOT EXISTS`` DDL, destructive for anything that deletes or rebuilds.

        Only ever call this on a database you know is already at that state.

        Args:
            target_version: If set, only record migrations up to this version,
                leaving later ones pending. For a database that is mid-history.

        Returns:
            List of migrations that were recorded. Already-recorded versions are
            skipped, so calling this twice is a no-op the second time.
        """
        await self.ensure_tracking_table()
        pending = await self.get_pending()

        if target_version is not None:
            pending = [m for m in pending if m.version <= target_version]

        for migration in pending:
            await self._record_applied(migration)

        return pending

    async def _record_applied(self, migration: MigrationFile) -> None:
        """Record a migration as applied, tolerating concurrent writers.

        Uses an UPSERT against a deterministic record id so two replicas
        recording the same version collapse into a single row instead of
        hitting the UNIQUE index on ``version``. The id is interpolated
        rather than built with ``type::thing``, which SurrealDB 3 renamed
        to ``type::record``; ``version`` is an int parsed from the file
        name, so there is nothing to inject. Rows written by older
        versions of this library used a random record id, so during a rollout
        an overlapping replica can still trip the index; a duplicate error
        means the version is already recorded and is safe to swallow.
        """
        try:
            await repo_query(
                f"UPSERT {_TRACKING_TABLE}:{migration.version} "
                f"SET version = $version, name = $name",
                {"version": migration.version, "name": migration.name},
            )
        except Exception as e:
            if not is_duplicate_error(e):
                raise

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
