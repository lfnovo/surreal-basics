"""Data models for the migration system."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class MigrationFile:
    """Represents a migration file pair (up + optional down)."""

    version: int
    name: str
    up_path: Path
    down_path: Optional[Path]


@dataclass
class MigrationRecord:
    """Represents a migration record stored in the tracking table."""

    version: int
    name: str
    applied_at: str
