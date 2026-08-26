"""Tests for the --expect-ns / --expect-db target guard."""

import pytest

from surreal_basics import init
from surreal_basics.exceptions import SurrealDBMigrationError
from surreal_basics.migrate.cli import (
    assert_baselined,
    assert_expected_target,
    build_parser,
)


@pytest.fixture(autouse=True)
def target(reset_config, monkeypatch):
    """Pin the resolved target and the ambient expectation env vars.

    A developer or CI shell may well have SBL_EXPECT_* exported — that is the
    point of the feature — so the tests clear them and set their own.
    """
    monkeypatch.delenv("SBL_EXPECT_NS", raising=False)
    monkeypatch.delenv("SBL_EXPECT_DB", raising=False)
    monkeypatch.delenv("SBL_REQUIRE_BASELINE", raising=False)
    init(namespace="acme-prod", database="app")


def _args(argv):
    return build_parser().parse_args(argv)


class TestFlags:
    def test_matching_namespace_passes(self):
        assert_expected_target(_args(["up", "--expect-ns", "acme-prod"]))

    def test_mismatched_namespace_aborts(self):
        with pytest.raises(SurrealDBMigrationError, match="namespace"):
            assert_expected_target(_args(["up", "--expect-ns", "acme-stg"]))

    def test_mismatched_database_aborts(self):
        with pytest.raises(SurrealDBMigrationError, match="database"):
            assert_expected_target(_args(["up", "--expect-db", "other"]))

    def test_both_checked_together(self):
        assert_expected_target(
            _args(["up", "--expect-ns", "acme-prod", "--expect-db", "app"])
        )

    def test_guard_available_on_down(self):
        with pytest.raises(SurrealDBMigrationError):
            assert_expected_target(_args(["down", "--expect-ns", "acme-stg"]))

    def test_guard_available_on_status(self):
        with pytest.raises(SurrealDBMigrationError):
            assert_expected_target(_args(["status", "--expect-ns", "acme-stg"]))

    def test_no_expectation_is_a_noop(self):
        assert_expected_target(_args(["up"]))


class TestEnvVars:
    def test_env_var_aborts(self, monkeypatch):
        monkeypatch.setenv("SBL_EXPECT_NS", "acme-stg")
        with pytest.raises(SurrealDBMigrationError, match="namespace"):
            assert_expected_target(_args(["up"]))

    def test_env_var_matching_passes(self, monkeypatch):
        monkeypatch.setenv("SBL_EXPECT_NS", "acme-prod")
        monkeypatch.setenv("SBL_EXPECT_DB", "app")
        assert_expected_target(_args(["up"]))

    def test_flag_wins_over_env_var(self, monkeypatch):
        monkeypatch.setenv("SBL_EXPECT_NS", "acme-stg")
        assert_expected_target(_args(["up", "--expect-ns", "acme-prod"]))

    def test_empty_env_var_fails_closed(self, monkeypatch):
        """An empty value is a stated expectation, not an absent one."""
        monkeypatch.setenv("SBL_EXPECT_NS", "")
        with pytest.raises(SurrealDBMigrationError, match="namespace"):
            assert_expected_target(_args(["up"]))

    def test_empty_flag_does_not_fall_through_to_env_var(self, monkeypatch):
        """An explicit empty flag wins over the env var and still aborts."""
        monkeypatch.setenv("SBL_EXPECT_NS", "acme-prod")
        with pytest.raises(SurrealDBMigrationError, match="namespace"):
            assert_expected_target(_args(["up", "--expect-ns", ""]))

    def test_expect_db_env_var_aborts(self, monkeypatch):
        monkeypatch.setenv("SBL_EXPECT_DB", "other")
        with pytest.raises(SurrealDBMigrationError, match="database"):
            assert_expected_target(_args(["up"]))


class TestMessage:
    def test_message_names_both_sides(self):
        with pytest.raises(SurrealDBMigrationError) as exc:
            assert_expected_target(_args(["up", "--expect-ns", "acme-stg"]))

        message = str(exc.value)
        assert "acme-prod" in message
        assert "acme-stg" in message
        assert "No SQL was executed" in message


class TestRequireBaseline:
    """The --require-baseline guard on `up`.

    Off by default: a first run on a brand-new database is the normal case and
    must keep working. On, an empty tracking table means the database was never
    baselined, and applying the full history to it is the accident to prevent.
    """

    class _Runner:
        def __init__(self, applied):
            self._applied = applied

        def get_applied_versions(self):
            return self._applied

    def test_off_by_default_with_empty_tracking(self):
        assert_baselined(self._Runner([]), _args(["up"]))

    def test_empty_tracking_aborts_when_required(self):
        with pytest.raises(SurrealDBMigrationError, match="baseline"):
            assert_baselined(self._Runner([]), _args(["up", "--require-baseline"]))

    def test_passes_when_something_is_recorded(self):
        assert_baselined(self._Runner(["001"]), _args(["up", "--require-baseline"]))

    def test_env_var_enables_the_guard(self, monkeypatch):
        monkeypatch.setenv("SBL_REQUIRE_BASELINE", "true")
        with pytest.raises(SurrealDBMigrationError, match="baseline"):
            assert_baselined(self._Runner([]), _args(["up"]))

    def test_env_var_falsy_leaves_it_off(self, monkeypatch):
        monkeypatch.setenv("SBL_REQUIRE_BASELINE", "no")
        assert_baselined(self._Runner([]), _args(["up"]))


class TestBaselineCommandGuard:
    def test_baseline_honours_expect_ns(self):
        with pytest.raises(SurrealDBMigrationError, match="namespace"):
            assert_expected_target(_args(["baseline", "--expect-ns", "acme-stg"]))

    def test_baseline_matching_namespace_passes(self):
        assert_expected_target(_args(["baseline", "--expect-ns", "acme-prod"]))
