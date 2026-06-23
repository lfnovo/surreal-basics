"""Utility functions for surreal_basics."""

import re
from typing import Any, Union

from surrealdb import RecordID  # type: ignore

# Characters/sequences that have no place in a bare table or record identifier
# and signal an attempt to break out of a SurrealQL clause.
_UNSAFE_IDENTIFIER = re.compile(r"[;\n\r\x00]|--|/\*|\*/")


def validate_identifier(value: Any, name: str = "identifier") -> Any:
    """Basic guard against SurrealQL injection in interpolated identifiers.

    This is a lightweight check, **not** a substitute for parameterized queries.
    It rejects statement separators and comment markers that have no legitimate
    place in a bare table or record reference. ``RecordID`` instances are always
    considered safe and pass through unchanged.

    Args:
        value: The table name or record identifier to check.
        name: Label used in the error message.

    Returns:
        The original value, unchanged, when it is safe.

    Raises:
        ValueError: If the value contains unsafe characters/sequences.
    """
    if isinstance(value, RecordID):
        return value
    if isinstance(value, str) and _UNSAFE_IDENTIFIER.search(value):
        raise ValueError(
            f"{name} contains characters not allowed in a table/record "
            f"identifier: {value!r}"
        )
    return value


def parse_record_ids(obj: Any) -> Any:
    """Recursively parse and convert RecordIDs into strings."""
    if isinstance(obj, dict):
        return {k: parse_record_ids(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [parse_record_ids(item) for item in obj]
    elif isinstance(obj, RecordID):
        return f"{obj.table_name}:{obj.id}"
    return obj


def ensure_record_id(value: Union[str, RecordID]) -> RecordID:
    """Ensure a value is a RecordID."""
    if isinstance(value, RecordID):
        return value
    return RecordID.parse(value)
