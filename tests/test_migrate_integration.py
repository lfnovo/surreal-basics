"""Integration tests for the migration system against a real SurrealDB."""

import pytest

from surreal_basics import init, repo_query_sync, reset_connections
from surreal_basics.exceptions import SurrealDBMigrationError
from surreal_basics.migrate import MigrationRunner

INTEGRATION_NS = "surreal-basics"
INTEGRATION_DB = "integration-test"


@pytest.fixture(autouse=True)
def setup_connection():
    """Configure connection for integration tests."""
    init(
        host="localhost",
        port=8018,
        namespace=INTEGRATION_NS,
        database=INTEGRATION_DB,
        mode="ws",
    )
    yield
    reset_connections()


@pytest.fixture
def migrations_dir(tmp_path):
    """Create a temporary migrations directory with test migrations."""
    up1 = tmp_path / "001_create_users.surrealql"
    up1.write_text(
        "DEFINE TABLE users SCHEMAFULL;\n"
        "DEFINE FIELD name ON users TYPE string;\n"
        "DEFINE FIELD email ON users TYPE string;\n"
    )
    down1 = tmp_path / "001_create_users_down.surrealql"
    down1.write_text("REMOVE TABLE users;\n")

    up2 = tmp_path / "002_add_index.surrealql"
    up2.write_text("DEFINE INDEX idx_email ON users FIELDS email UNIQUE;\n")
    down2 = tmp_path / "002_add_index_down.surrealql"
    down2.write_text("REMOVE INDEX idx_email ON users;\n")

    return tmp_path


@pytest.fixture(autouse=True)
def cleanup_tracking():
    """Clean up tracking table and test tables before and after each test."""
    _cleanup()
    yield
    _cleanup()


def _cleanup():
    try:
        repo_query_sync("REMOVE TABLE _sbl_migrations;")
    except Exception:
        pass
    try:
        repo_query_sync("REMOVE TABLE users;")
    except Exception:
        pass


class TestMigrationRunnerUp:
    def test_run_up_applies_all(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        applied = runner.run_up()

        assert len(applied) == 2
        assert applied[0].version == 1
        assert applied[1].version == 2

    def test_run_up_creates_table(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        runner.run_up()

        result = repo_query_sync(
            "CREATE users CONTENT { name: 'John', email: 'john@test.com' };"
        )
        assert len(result) == 1
        assert result[0]["name"] == "John"

    def test_run_up_records_in_tracking(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        runner.run_up()

        records = repo_query_sync(
            "SELECT * FROM _sbl_migrations ORDER BY version ASC"
        )
        assert len(records) == 2
        assert records[0]["version"] == 1
        assert records[0]["name"] == "create_users"
        assert records[1]["version"] == 2

    def test_run_up_with_target_version(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        applied = runner.run_up(target_version=1)

        assert len(applied) == 1
        assert applied[0].version == 1

    def test_run_up_idempotent(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        runner.run_up()
        applied = runner.run_up()

        assert len(applied) == 0

    def test_run_up_resumes_from_last(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        runner.run_up(target_version=1)

        applied = runner.run_up()
        assert len(applied) == 1
        assert applied[0].version == 2


class TestMigrationRunnerDown:
    def test_run_down_rollback_last(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        runner.run_up()

        rolled_back = runner.run_down()
        assert len(rolled_back) == 1
        assert rolled_back[0].version == 2

    def test_run_down_rollback_multiple(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        runner.run_up()

        rolled_back = runner.run_down(steps=2)
        assert len(rolled_back) == 2
        assert rolled_back[0].version == 2
        assert rolled_back[1].version == 1

    def test_run_down_removes_tracking_record(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        runner.run_up()
        runner.run_down(steps=1)

        records = repo_query_sync("SELECT * FROM _sbl_migrations")
        assert len(records) == 1
        assert records[0]["version"] == 1

    def test_run_down_actually_removes_schema(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        runner.run_up()
        runner.run_down(steps=2)

        result = repo_query_sync("INFO FOR DB;")
        # INFO FOR DB returns a dict directly
        tables = result.get("tables", {}) if isinstance(result, dict) else result[0].get("tables", {})
        assert "users" not in tables


class TestMigrationRunnerStatus:
    def test_status_empty(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        status = runner.status()

        assert status["current_version"] == 0
        assert len(status["applied"]) == 0
        assert len(status["pending"]) == 2

    def test_status_partial(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        runner.run_up(target_version=1)
        status = runner.status()

        assert status["current_version"] == 1
        assert len(status["applied"]) == 1
        assert len(status["pending"]) == 1

    def test_status_all_applied(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        runner.run_up()
        status = runner.status()

        assert status["current_version"] == 2
        assert len(status["applied"]) == 2
        assert len(status["pending"]) == 0


class TestMigrationRunnerDryRun:
    def test_dry_run_validates_without_applying(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        validated = runner.run_up(dry_run=True)

        assert len(validated) == 2

        # Nothing should be persisted
        records = repo_query_sync("SELECT * FROM _sbl_migrations")
        assert len(records) == 0

    def test_dry_run_does_not_create_table(self, migrations_dir):
        runner = MigrationRunner(migrations_dir)
        runner.run_up(dry_run=True)

        result = repo_query_sync("INFO FOR DB;")
        tables = result.get("tables", {}) if isinstance(result, dict) else result[0].get("tables", {})
        assert "users" not in tables

    def test_dry_run_catches_invalid_sql(self, tmp_path):
        bad_migration = tmp_path / "001_bad.surrealql"
        bad_migration.write_text("THIS IS NOT VALID SQL !!!\n")

        runner = MigrationRunner(tmp_path)
        with pytest.raises(SurrealDBMigrationError, match="failed validation"):
            runner.run_up(dry_run=True)


class TestMigrationRunnerErrors:
    def test_run_up_bad_migration_stops(self, tmp_path):
        good = tmp_path / "001_good.surrealql"
        good.write_text("DEFINE TABLE good_table SCHEMAFULL;\n")

        bad = tmp_path / "002_bad.surrealql"
        bad.write_text("DEFINE FIELD name ON nonexistent TYPE INVALID_TYPE;\n")

        runner = MigrationRunner(tmp_path)
        with pytest.raises(SurrealDBMigrationError):
            runner.run_up()

        # First migration should have been applied
        records = repo_query_sync("SELECT * FROM _sbl_migrations")
        assert len(records) == 1
        assert records[0]["version"] == 1

        # Cleanup
        try:
            repo_query_sync("REMOVE TABLE good_table;")
        except Exception:
            pass

    def test_run_down_no_down_file_raises(self, tmp_path):
        up = tmp_path / "001_create_temp.surrealql"
        up.write_text("DEFINE TABLE temp_table SCHEMAFULL;\n")

        runner = MigrationRunner(tmp_path)
        runner.run_up()

        with pytest.raises(SurrealDBMigrationError, match="No down migration"):
            runner.run_down()

        # Cleanup
        try:
            repo_query_sync("REMOVE TABLE temp_table;")
            repo_query_sync("DELETE _sbl_migrations WHERE version = 1;")
        except Exception:
            pass
