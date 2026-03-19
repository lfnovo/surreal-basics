"""CLI for surreal-basics migrations."""

import argparse
import os
import sys
from pathlib import Path

from .discovery import scaffold_migration
from .runner import MigrationRunner


def _get_default_dir() -> str:
    return os.environ.get("SURREAL_MIGRATIONS_DIR", "./migrations")


def cmd_up(args: argparse.Namespace) -> None:
    """Run pending migrations."""
    runner = MigrationRunner(args.dir)
    target = args.to if hasattr(args, "to") and args.to else None
    dry_run = args.dry_run

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


def cmd_create(args: argparse.Namespace) -> None:
    """Create a new migration."""
    directory = Path(args.dir)
    up_path, down_path = scaffold_migration(directory, args.name)

    print(f"Created migration files:")
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
    up_parser.set_defaults(func=cmd_up)

    # down
    down_parser = subparsers.add_parser("down", help="Rollback migrations")
    down_parser.add_argument(
        "--steps", type=int, default=1, help="Number of migrations to rollback"
    )
    down_parser.add_argument(
        "--dir", default=_get_default_dir(), help="Migrations directory"
    )
    down_parser.set_defaults(func=cmd_down)

    # status
    status_parser = subparsers.add_parser("status", help="Show migration status")
    status_parser.add_argument(
        "--dir", default=_get_default_dir(), help="Migrations directory"
    )
    status_parser.set_defaults(func=cmd_status)

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
