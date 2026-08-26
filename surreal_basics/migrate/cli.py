"""CLI for surreal-basics migrations."""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from ..config import get_config
from ..exceptions import SurrealDBMigrationError
from .discovery import scaffold_migration
from .runner import MigrationRunner


def _get_default_dir() -> str:
    return os.environ.get("SURREAL_MIGRATIONS_DIR", "./migrations")


def _expectation(args: argparse.Namespace, attr: str, env_var: str) -> Optional[str]:
    """Resolve one expectation, flag first, then env var.

    Only an absent value (``None``) means "not stated". An empty string is a
    stated expectation that can never match a real target, so it fails closed
    rather than silently disabling the guard.
    """
    from_flag = getattr(args, attr, None)
    if from_flag is not None:
        return from_flag
    return os.environ.get(env_var)


def _env_flag(name: str) -> bool:
    """True when the env var is set to a truthy value."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def assert_expected_target(args: argparse.Namespace) -> None:
    """Abort when the resolved target doesn't match what the caller expects.

    Several environments often share one SurrealDB instance under different
    namespaces, where a stale ``SURREAL_NAMESPACE`` is enough to migrate the
    wrong one. ``--expect-ns``/``--expect-db`` (or ``SBL_EXPECT_NS``/
    ``SBL_EXPECT_DB`` for CI, where threading flags through is awkward) make
    the caller state the target up front. Checked by ``up``, ``down`` and
    ``status`` — the read-only command earns it too, since knowing which
    target you are reading is the point. The flag wins over the env var, and
    with neither set nothing is checked, so existing setups are unaffected.

    Raises:
        SurrealDBMigrationError: If a stated expectation doesn't match.
    """
    config = get_config()
    checks = (
        (
            "namespace",
            _expectation(args, "expect_ns", "SBL_EXPECT_NS"),
            config.namespace,
            "--expect-ns",
        ),
        (
            "database",
            _expectation(args, "expect_db", "SBL_EXPECT_DB"),
            config.database,
            "--expect-db",
        ),
    )

    for label, expected, actual, flag in checks:
        if expected is not None and expected != actual:
            raise SurrealDBMigrationError(
                f"ABORT: target {label} is {actual!r}, but {flag} is "
                f"{expected!r}. No SQL was executed."
            )


def assert_baselined(runner: MigrationRunner, args: argparse.Namespace) -> None:
    """Abort when --require-baseline is set and the tracking table is empty.

    An empty table is ambiguous: it is either a fresh database that should run
    the whole history, or an existing one that was never baselined and would
    have that history replayed against it. The library cannot tell them apart,
    so the caller states which it expects. Off by default — a first run on a
    new database is the normal case and must keep working. Not checked for a
    dry-run, which applies nothing.

    Raises:
        SurrealDBMigrationError: If the tracking table has no rows.
    """
    if not (
        getattr(args, "require_baseline", False) or _env_flag("SBL_REQUIRE_BASELINE")
    ):
        return
    if runner.get_applied_versions():
        return
    raise SurrealDBMigrationError(
        "ABORT: --require-baseline is set but no migration is recorded as "
        "applied. Running now would apply the full history to this database. "
        "If its schema is already up to date, run `sbl-migrate baseline` "
        "first. No SQL was executed."
    )


def cmd_up(args: argparse.Namespace) -> None:
    """Run pending migrations."""
    assert_expected_target(args)
    runner = MigrationRunner(args.dir)
    target = args.to if hasattr(args, "to") and args.to else None
    dry_run = args.dry_run

    # A dry-run persists nothing, so the guard has nothing to protect and its
    # message would be untrue. Validating pending migrations stays available on
    # a database that was never baselined.
    if not dry_run:
        assert_baselined(runner, args)

    applied = runner.run_up(target_version=target, dry_run=dry_run)

    if not applied:
        print("No pending migrations.")
        return

    label = "VALID" if dry_run else "APPLIED"
    for m in applied:
        print(f"  [{label}] {m.version:03d}_{m.name}")

    if dry_run:
        print(f"\n{len(applied)} migration(s) validated (dry-run, nothing applied).")
    else:
        print(f"\n{len(applied)} migration(s) applied.")


def cmd_down(args: argparse.Namespace) -> None:
    """Rollback migrations."""
    assert_expected_target(args)
    runner = MigrationRunner(args.dir)
    steps = args.steps if hasattr(args, "steps") and args.steps else 1

    rolled_back = runner.run_down(steps=steps)

    if not rolled_back:
        print("No migrations to rollback.")
        return

    for m in rolled_back:
        print(f"  [ROLLED BACK] {m.version:03d}_{m.name}")
    print(f"\n{len(rolled_back)} migration(s) rolled back.")


def cmd_status(args: argparse.Namespace) -> None:
    """Show migration status."""
    assert_expected_target(args)
    runner = MigrationRunner(args.dir)
    status = runner.status()

    print(f"Current version: {status['current_version']}")
    print()

    if status["applied"]:
        for r in status["applied"]:
            print(f"  [APPLIED] {r.version:03d}_{r.name} (at {r.applied_at})")

    if status["pending"]:
        for m in status["pending"]:
            print(f"  [PENDING] {m.version:03d}_{m.name}")

    if not status["applied"] and not status["pending"]:
        print("  No migrations found.")


def cmd_baseline(args: argparse.Namespace) -> None:
    """Record pending migrations as applied, without running them."""
    assert_expected_target(args)
    runner = MigrationRunner(args.dir)
    target = args.to if hasattr(args, "to") and args.to else None

    recorded = runner.baseline(target_version=target)

    if not recorded:
        print("Nothing to baseline: every migration is already recorded.")
        return

    for m in recorded:
        print(f"  [BASELINED] {m.version:03d}_{m.name}")
    print(f"\n{len(recorded)} migration(s) recorded as applied. No SQL was run.")


def cmd_create(args: argparse.Namespace) -> None:
    """Create a new migration."""
    directory = Path(args.dir)
    up_path, down_path = scaffold_migration(directory, args.name)

    print("Created migration files:")
    print(f"  {up_path}")
    print(f"  {down_path}")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="sbl-migrate",
        description="SurrealDB migration tool for surreal-basics",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # up
    up_parser = subparsers.add_parser("up", help="Run pending migrations")
    up_parser.add_argument(
        "--to", type=int, default=None, help="Run migrations up to this version"
    )
    up_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate migrations without applying (uses BEGIN/CANCEL TRANSACTION)",
    )
    up_parser.add_argument(
        "--dir", default=_get_default_dir(), help="Migrations directory"
    )
    up_parser.add_argument(
        "--require-baseline",
        action="store_true",
        default=False,
        help=(
            "Abort if no migration is recorded yet, instead of applying the "
            "full history to a database that was never baselined "
            "(env: SBL_REQUIRE_BASELINE)"
        ),
    )
    up_parser.add_argument(
        "--expect-ns",
        default=None,
        help="Abort unless the target namespace matches (env: SBL_EXPECT_NS)",
    )
    up_parser.add_argument(
        "--expect-db",
        default=None,
        help="Abort unless the target database matches (env: SBL_EXPECT_DB)",
    )
    up_parser.set_defaults(func=cmd_up)

    # down
    down_parser = subparsers.add_parser("down", help="Rollback migrations")
    down_parser.add_argument(
        "--steps", type=int, default=1, help="Number of migrations to rollback"
    )
    down_parser.add_argument(
        "--dir", default=_get_default_dir(), help="Migrations directory"
    )
    down_parser.add_argument(
        "--expect-ns",
        default=None,
        help="Abort unless the target namespace matches (env: SBL_EXPECT_NS)",
    )
    down_parser.add_argument(
        "--expect-db",
        default=None,
        help="Abort unless the target database matches (env: SBL_EXPECT_DB)",
    )
    down_parser.set_defaults(func=cmd_down)

    # status
    status_parser = subparsers.add_parser("status", help="Show migration status")
    status_parser.add_argument(
        "--dir", default=_get_default_dir(), help="Migrations directory"
    )
    status_parser.add_argument(
        "--expect-ns",
        default=None,
        help="Abort unless the target namespace matches (env: SBL_EXPECT_NS)",
    )
    status_parser.add_argument(
        "--expect-db",
        default=None,
        help="Abort unless the target database matches (env: SBL_EXPECT_DB)",
    )
    status_parser.set_defaults(func=cmd_status)

    # baseline
    baseline_parser = subparsers.add_parser(
        "baseline",
        help="Record migrations as applied without running them",
    )
    baseline_parser.add_argument(
        "--to",
        type=int,
        default=None,
        help="Only record migrations up to this version",
    )
    baseline_parser.add_argument(
        "--dir", default=_get_default_dir(), help="Migrations directory"
    )
    baseline_parser.add_argument(
        "--expect-ns",
        default=None,
        help="Abort unless the target namespace matches (env: SBL_EXPECT_NS)",
    )
    baseline_parser.add_argument(
        "--expect-db",
        default=None,
        help="Abort unless the target database matches (env: SBL_EXPECT_DB)",
    )
    baseline_parser.set_defaults(func=cmd_baseline)

    # create
    create_parser = subparsers.add_parser("create", help="Create a new migration")
    create_parser.add_argument("name", help="Migration name (e.g., create_users)")
    create_parser.add_argument(
        "--dir", default=_get_default_dir(), help="Migrations directory"
    )
    create_parser.set_defaults(func=cmd_create)

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        args.func(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
