"""Tests for the --expect-ns / --expect-db target guard."""

import pytest

from surreal_basics import init
from surreal_basics.exceptions import SurrealDBMigrationError
from surreal_basics.migrate.cli import assert_expected_target, build_parser


@pytest.fixture(autouse=True)
def target(reset_config):
    """Point the resolved config at a known namespace/database."""
    init(namespace="jota-prod", database="app")


def _args(argv):
    return build_parser().parse_args(argv)


class TestFlags:
    def test_matching_namespace_passes(self):
        assert_expected_target(_args(["up", "--expect-ns", "jota-prod"]))

    def test_mismatched_namespace_aborts(self):
        with pytest.raises(SurrealDBMigrationError, match="namespace"):
            assert_expected_target(_args(["up", "--expect-ns", "jota-stg"]))

    def test_mismatched_database_aborts(self):
        with pytest.raises(SurrealDBMigrationError, match="database"):
            assert_expected_target(_args(["up", "--expect-db", "other"]))

    def test_both_checked_together(self):
        assert_expected_target(
            _args(["up", "--expect-ns", "jota-prod", "--expect-db", "app"])
        )

    def test_guard_available_on_down(self):
        with pytest.raises(SurrealDBMigrationError):
            assert_expected_target(_args(["down", "--expect-ns", "jota-stg"]))

    def test_no_expectation_is_a_noop(self):
        assert_expected_target(_args(["up"]))


class TestEnvVars:
    def test_env_var_aborts(self, monkeypatch):
        monkeypatch.setenv("SBL_EXPECT_NS", "jota-stg")
        with pytest.raises(SurrealDBMigrationError, match="namespace"):
            assert_expected_target(_args(["up"]))

    def test_env_var_matching_passes(self, monkeypatch):
        monkeypatch.setenv("SBL_EXPECT_NS", "jota-prod")
        monkeypatch.setenv("SBL_EXPECT_DB", "app")
        assert_expected_target(_args(["up"]))

    def test_flag_wins_over_env_var(self, monkeypatch):
        monkeypatch.setenv("SBL_EXPECT_NS", "jota-stg")
        assert_expected_target(_args(["up", "--expect-ns", "jota-prod"]))

    def test_expect_db_env_var_aborts(self, monkeypatch):
        monkeypatch.setenv("SBL_EXPECT_DB", "other")
        with pytest.raises(SurrealDBMigrationError, match="database"):
            assert_expected_target(_args(["up"]))


class TestMessage:
    def test_message_names_both_sides(self):
        with pytest.raises(SurrealDBMigrationError) as exc:
            assert_expected_target(_args(["up", "--expect-ns", "jota-stg"]))

        message = str(exc.value)
        assert "jota-prod" in message
        assert "jota-stg" in message
        assert "No SQL was executed" in message
