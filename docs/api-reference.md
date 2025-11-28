# API Reference

## Repository Functions

All functions have async and sync versions (suffix `_sync`).

---

### repo_query / repo_query_sync

Execute a SurrealQL query.

```python
async def repo_query(
    query_str: str,
    vars: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]
```

**Parameters:**
- `query_str`: SurrealQL query
- `vars`: Variables for parameterized queries

**Returns:** List of results

**Example:**
```python
# Simple query
users = await repo_query("SELECT * FROM user WHERE active = true")

# Parameterized query
users = await repo_query(
    "SELECT * FROM user WHERE age > $min_age",
    {"min_age": 18}
)
```

---

### repo_create / repo_create_sync

Create a new record. Automatically adds `created` and `updated` timestamps.

```python
async def repo_create(
    table: str,
    data: Dict[str, Any]
) -> Dict[str, Any]
```

**Parameters:**
- `table`: Table name
- `data`: Record data

**Returns:** Created record with ID

**Example:**
```python
user = await repo_create("user", {
    "name": "John",
    "email": "john@test.com",
    "age": 25
})
# Returns: {"id": "user:abc123", "name": "John", ..., "created": ..., "updated": ...}
```

---

### repo_select / repo_select_sync

Select records from a table or a specific record by ID.

```python
async def repo_select(
    table_or_id: Union[str, RecordID]
) -> Union[Dict[str, Any], List[Dict[str, Any]]]
```

**Parameters:**
- `table_or_id`: Table name (returns all) or record ID

**Returns:** Single record or list of records

**Example:**
```python
# All records
all_users = await repo_select("user")

# By ID
user = await repo_select("user:abc123")
```

---

### repo_update / repo_update_sync

Update an existing record (merge). Updates the `updated` timestamp.

```python
async def repo_update(
    table: str,
    record_id: str,
    data: Dict[str, Any]
) -> List[Dict[str, Any]]
```

**Parameters:**
- `table`: Table name
- `record_id`: Record ID (can be "table:id" or just "id")
- `data`: Data to merge

**Returns:** List with updated record

**Example:**
```python
result = await repo_update("user", "abc123", {"name": "John Smith"})
# or
result = await repo_update("user", "user:abc123", {"name": "John Smith"})
```

---

### repo_upsert / repo_upsert_sync

Create or update a record (merge).

```python
async def repo_upsert(
    table: str,
    record_id: Optional[str],
    data: Dict[str, Any],
    add_timestamp: bool = False
) -> List[Dict[str, Any]]
```

**Parameters:**
- `table`: Table name
- `record_id`: Record ID (optional, e.g., "user:123")
- `data`: Data to merge
- `add_timestamp`: If True, updates the `updated` field

**Returns:** List with created/updated record

**Example:**
```python
# Create or update with specific ID
result = await repo_upsert("user", "user:john", {"name": "John", "active": True})

# Use table only (auto-generates ID if not exists)
result = await repo_upsert("config", None, {"theme": "dark"})
```

---

### repo_delete / repo_delete_sync

Delete a record by ID.

```python
async def repo_delete(
    record_id: Union[str, RecordID]
) -> Any
```

**Parameters:**
- `record_id`: Full record ID (e.g., "user:123")

**Returns:** Deleted record or None

**Example:**
```python
deleted = await repo_delete("user:abc123")
```

---

### repo_insert / repo_insert_sync

Bulk insert multiple records.

```python
async def repo_insert(
    table: str,
    data: List[Dict[str, Any]],
    ignore_duplicates: bool = False
) -> List[Dict[str, Any]]
```

**Parameters:**
- `table`: Table name
- `data`: List of records
- `ignore_duplicates`: If True, silently ignores duplicate key errors

**Returns:** List of created records

**Example:**
```python
users = [
    {"name": "User 1", "email": "u1@test.com"},
    {"name": "User 2", "email": "u2@test.com"},
]
created = await repo_insert("user", users)
```

---

### repo_relate / repo_relate_sync

Create a relationship between two records.

```python
async def repo_relate(
    source: str,
    relationship: str,
    target: str,
    data: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]
```

**Parameters:**
- `source`: Source record ID
- `relationship`: Relationship type/table name
- `target`: Target record ID
- `data`: Optional relationship data

**Returns:** Created relationship record

**Example:**
```python
# User follows another user
result = await repo_relate("user:1", "follows", "user:2")

# With relationship data
result = await repo_relate(
    "user:1",
    "purchased",
    "product:abc",
    {"quantity": 2, "price": 29.90}
)
```

---

## Utilities

### parse_record_ids

Convert RecordID to strings in nested structures.

```python
def parse_record_ids(obj: Any) -> Any
```

**Example:**
```python
from surreal_basics import parse_record_ids

data = {"user": RecordID("user", "123"), "items": [RecordID("item", "1")]}
result = parse_record_ids(data)
# {"user": "user:123", "items": ["item:1"]}
```

### ensure_record_id

Ensure a value is a RecordID.

```python
def ensure_record_id(value: Union[str, RecordID]) -> RecordID
```

**Example:**
```python
from surreal_basics import ensure_record_id

rid = ensure_record_id("user:123")  # Returns RecordID
rid = ensure_record_id(rid)  # Returns same RecordID
```

---

## Exceptions

| Exception | Description | Retry |
|-----------|-------------|-------|
| `SurrealDBError` | Base for all exceptions | - |
| `SurrealDBConnectionError` | Failed to connect to SurrealDB | No |
| `SurrealDBQueryError` | Query error (syntax, etc) | No |
| `SurrealDBTransientError` | Transient error (lock conflict) | Yes (3x) |

**Example:**
```python
from surreal_basics import (
    SurrealDBConnectionError,
    SurrealDBQueryError,
    SurrealDBTransientError,
)

try:
    result = await repo_query("SELECT * FROM user")
except SurrealDBTransientError as e:
    # Already retried 3x with automatic retry
    print(f"Error after retries: {e}")
except SurrealDBQueryError as e:
    print(f"Invalid query: {e}")
except SurrealDBConnectionError as e:
    print(f"Connection failed: {e}")
```
