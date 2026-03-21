"""Auto-discovery and parsing of .surrealql migration files."""

import re
from pathlib import Path

from .models import MigrationFile

_MIGRATION_PATTERN = re.compile(r"^(\d+)_(.+)\.surrealql$")


def discover_migrations(directory: Path) -> list[MigrationFile]:
    """Discover and parse migration files from a directory.

    Files must follow the naming convention: NNN_name.surrealql
    Down migrations are optional: NNN_name_down.surrealql

    Args:
        directory: Path to the migrations directory.

    Returns:
        List of MigrationFile sorted by version.

    Raises:
        ValueError: If duplicate versions are found.
    """
    if not directory.is_dir():
        return []

    up_files: dict[int, tuple[str, Path]] = {}

    for path in sorted(directory.glob("*.surrealql")):
        filename = path.name
        if filename.endswith("_down.surrealql"):
            continue

        match = _MIGRATION_PATTERN.match(filename)
        if not match:
            continue

        version = int(match.group(1))
        name = match.group(2)

        if version in up_files:
            existing_name = up_files[version][0]
            raise ValueError(
                f"Duplicate migration version {version}: "
                f"'{existing_name}' and '{name}'"
            )

        up_files[version] = (name, path)

    migrations = []
    for version in sorted(up_files):
        name, up_path = up_files[version]
        down_path = up_path.parent / f"{version:03d}_{name}_down.surrealql"
        migrations.append(
            MigrationFile(
                version=version,
                name=name,
                up_path=up_path,
                down_path=down_path if down_path.exists() else None,
            )
        )

    return migrations


def parse_sql_file(path: Path) -> str:
    """Read a .surrealql file and return its content.

    Args:
        path: Path to the SQL file.

    Returns:
        The file content as a string.
    """
    return path.read_text(encoding="utf-8")


def scaffold_migration(directory: Path, name: str) -> tuple[Path, Path]:
    """Create the next migration file pair.

    Args:
        directory: Path to the migrations directory.
        name: Descriptive name for the migration (e.g., 'create_users').

    Returns:
        Tuple of (up_path, down_path).
    """
    directory.mkdir(parents=True, exist_ok=True)

    existing = discover_migrations(directory)
    next_version = (existing[-1].version + 1) if existing else 1

    up_path = directory / f"{next_version:03d}_{name}.surrealql"
    down_path = directory / f"{next_version:03d}_{name}_down.surrealql"

    up_path.write_text(
        f"-- Migration {next_version:03d}: {name}\n\n", encoding="utf-8"
    )
    down_path.write_text(
        f"-- Rollback {next_version:03d}: {name}\n\n", encoding="utf-8"
    )

    return up_path, down_path
