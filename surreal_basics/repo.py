"""Async repository functions for SurrealDB operations."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from surrealdb import RecordID  # type: ignore

from .connection import get_async_connection
from .exceptions import SurrealDBQueryError, SurrealDBTransientError
from .retry import surreal_retry_async
from .utils import ensure_record_id, parse_record_ids


@surreal_retry_async
async def repo_query(
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
    async with get_async_connection() as conn:
        result = parse_record_ids(await conn.query(query_str, vars))
        if isinstance(result, str):
            if "can be retried" in result:
                raise SurrealDBTransientError(result)
            else:
                raise SurrealDBQueryError(result)
        return result


@surreal_retry_async
async def repo_create(table: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new record in the specified table.

    Automatically adds 'created' and 'updated' timestamps.

    Args:
        table: The table name
        data: The record data

    Returns:
        The created record
    """
    data = data.copy()
    data["created"] = datetime.now(timezone.utc)
    data["updated"] = datetime.now(timezone.utc)

    async with get_async_connection() as conn:
        result = await conn.insert(table, data)
        return parse_record_ids(result)


@surreal_retry_async
async def repo_upsert(
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

    target = record_id if record_id else table
    query = f"UPSERT {target} MERGE $data;"
    return await repo_query(query, {"data": data})


@surreal_retry_async
async def repo_update(
    table: str, record_id: str, data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Update an existing record by table and id.

    Automatically updates the 'updated' timestamp.

    Args:
        table: The table name
        record_id: The record ID (can be just the ID part or full "table:id")
        data: The data to merge

    Returns:
        List containing the updated record
    """
    # If id already contains the table name, use it as is
    if isinstance(record_id, RecordID) or (
        ":" in str(record_id) and str(record_id).startswith(f"{table}:")
    ):
        full_id = record_id
    else:
        full_id = f"{table}:{record_id}"

    data = data.copy()
    data["updated"] = datetime.now(timezone.utc)
    query = f"UPDATE {full_id} MERGE $data;"
    result = await repo_query(query, {"data": data})
    return parse_record_ids(result)


@surreal_retry_async
async def repo_delete(record_id: Union[str, RecordID]) -> Any:
    """
    Delete a record by record id.

    Args:
        record_id: The full record ID (e.g., "user:123")

    Returns:
        The deleted record or None
    """
    async with get_async_connection() as conn:
        return await conn.delete(record_id)


@surreal_retry_async
async def repo_insert(
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
    async with get_async_connection() as conn:
        try:
            result = await conn.insert(table, data)
            return parse_record_ids(result)
        except Exception as e:
            if ignore_duplicates and "already contains" in str(e):
                return []
            raise


@surreal_retry_async
async def repo_relate(
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
    if data is None:
        data = {}
    query = f"RELATE {source}->{relationship}->{target} CONTENT $data;"
    return await repo_query(query, {"data": data})


@surreal_retry_async
async def repo_select(
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
    if isinstance(table_or_id, str) and ":" in table_or_id:
        table_or_id = ensure_record_id(table_or_id)

    async with get_async_connection() as conn:
        result = await conn.select(table_or_id)
        return parse_record_ids(result)
