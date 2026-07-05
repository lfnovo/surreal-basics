"""Sync repository functions for SurrealDB operations."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from surrealdb import RecordID, Table  # type: ignore

from ._sdk import is_duplicate_error, translate_errors
from .connection import get_sync_connection
from .exceptions import SurrealDBQueryError
from .retry import surreal_retry
from .utils import ensure_record_id, parse_record_ids, validate_identifier


@surreal_retry
def repo_query_sync(
    query_str: str, vars: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Execute a SurrealQL query and return the results.

    Automatically retries on transient errors (concurrency locks) and timeouts.

    Args:
        query_str: The SurrealQL query to execute
        vars: Optional variables for parameterized queries

    Returns:
        List of result dictionaries

    Raises:
        SurrealDBTransientError: For retryable errors (lock conflicts)
        SurrealDBQueryError: For non-retryable query errors
    """
    with get_sync_connection() as conn:
        with translate_errors():
            result = conn.query(query_str, vars)
        return parse_record_ids(result)


@surreal_retry
def repo_create_sync(
    table: str, data: Dict[str, Any], add_timestamps: bool = False
) -> Dict[str, Any]:
    """
    Create a new record in the specified table.

    Timestamps are best left to the schema (DEFAULT/VALUE time::now());
    SurrealDB 3.x SCHEMAFULL tables reject fields they don't define.

    Args:
        table: The table name
        data: The record data
        add_timestamps: Whether to add 'created' and 'updated' timestamps

    Returns:
        The created record
    """
    data = data.copy()
    data.pop("id", None)
    if add_timestamps:
        data["created"] = datetime.now(timezone.utc)
        data["updated"] = datetime.now(timezone.utc)

    with get_sync_connection() as conn:
        with translate_errors():
            result = conn.insert(table, data)
        return parse_record_ids(result)


@surreal_retry
def repo_upsert_sync(
    table: str,
    record_id: Optional[str],
    data: Dict[str, Any],
    add_timestamp: bool = False,
) -> List[Dict[str, Any]]:
    """
    Create or update a record in the specified table (merge).

    Args:
        table: The table name
        record_id: Optional record ID (e.g., "user:123"). If None, uses table name.
        data: The data to merge
        add_timestamp: Whether to add/update the 'updated' timestamp

    Returns:
        List containing the upserted record
    """
    data = data.copy()
    data.pop("id", None)
    if add_timestamp:
        data["updated"] = datetime.now(timezone.utc)

    # Bind the target as a query variable so the identifier can never alter the
    # query structure. No single SDK method offers UPSERT + MERGE semantics, so
    # this stays a parameterized query rather than a native call.
    if record_id:
        validate_identifier(record_id, "record_id")
        what: Union[RecordID, Table] = ensure_record_id(record_id)
    else:
        validate_identifier(table, "table")
        what = Table(table)

    return repo_query_sync("UPSERT $what MERGE $data;", {"what": what, "data": data})


@surreal_retry
def repo_update_sync(
    table: str,
    record_id: Union[str, RecordID],
    data: Dict[str, Any],
    add_timestamp: bool = False,
) -> List[Dict[str, Any]]:
    """
    Update an existing record by table and id.

    Args:
        table: The table name
        record_id: The record ID (can be just the ID part or full "table:id")
        data: The data to merge
        add_timestamp: Whether to add/update the 'updated' timestamp

    Returns:
        List containing the updated record
    """
    # If id already contains the table name, use it as is
    if isinstance(record_id, RecordID) or (
        ":" in str(record_id) and str(record_id).startswith(f"{table}:")
    ):
        full_id: Union[str, RecordID] = record_id
    else:
        full_id = f"{table}:{record_id}"

    if isinstance(full_id, str):
        validate_identifier(full_id, "record_id")
    rid = ensure_record_id(full_id)

    data = data.copy()
    if add_timestamp:
        data["updated"] = datetime.now(timezone.utc)

    with get_sync_connection() as conn:
        with translate_errors():
            result = conn.merge(rid, data)
    parsed = parse_record_ids(result)
    return [parsed] if isinstance(parsed, dict) else parsed


@surreal_retry
def repo_delete_sync(record_id: Union[str, RecordID]) -> Any:
    """
    Delete a record by record id.

    Args:
        record_id: The full record ID (e.g., "user:123")

    Returns:
        The deleted record or None
    """
    with get_sync_connection() as conn:
        with translate_errors():
            return conn.delete(record_id)


@surreal_retry
def repo_insert_sync(
    table: str, data: List[Dict[str, Any]], ignore_duplicates: bool = False
) -> List[Dict[str, Any]]:
    """
    Bulk insert records into a table.

    Args:
        table: The table name
        data: List of records to insert
        ignore_duplicates: If True, silently ignore duplicate key errors

    Returns:
        List of created records
    """
    with get_sync_connection() as conn:
        try:
            with translate_errors():
                result = conn.insert(table, data)
            return parse_record_ids(result)
        except SurrealDBQueryError as e:
            if ignore_duplicates and is_duplicate_error(e):
                return []
            raise


@surreal_retry
def repo_relate_sync(
    source: str,
    relationship: str,
    target: str,
    data: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Create a relationship between two records.

    Args:
        source: The source record ID
        relationship: The relationship type/table name
        target: The target record ID
        data: Optional data to attach to the relationship

    Returns:
        List containing the created relationship record
    """
    data = dict(data) if data else {}
    validate_identifier(source, "source")
    validate_identifier(relationship, "relationship")
    validate_identifier(target, "target")

    # in/out come last so a stray "in"/"out" in data can't override the
    # validated source/target endpoints.
    payload = {
        **data,
        "in": ensure_record_id(source),
        "out": ensure_record_id(target),
    }
    with get_sync_connection() as conn:
        with translate_errors():
            result = conn.insert_relation(relationship, payload)
    parsed = parse_record_ids(result)
    return [parsed] if isinstance(parsed, dict) else parsed


@surreal_retry
def repo_select_sync(
    table_or_id: Union[str, RecordID],
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Select records from a table or a specific record by ID.

    Args:
        table_or_id: Table name (selects all) or record ID (selects one)

    Returns:
        Single record dict or list of records
    """
    # Convert string ID to RecordID if it contains a colon
    is_single = isinstance(table_or_id, RecordID) or (
        isinstance(table_or_id, str) and ":" in table_or_id
    )
    if isinstance(table_or_id, str) and ":" in table_or_id:
        table_or_id = ensure_record_id(table_or_id)

    with get_sync_connection() as conn:
        with translate_errors():
            result = conn.select(table_or_id)
        parsed = parse_record_ids(result)
        if is_single and isinstance(parsed, list) and len(parsed) == 1:
            return parsed[0]
        return parsed
