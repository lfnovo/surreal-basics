"""Custom exceptions for surreal_basics."""


class SurrealDBError(Exception):
    """Base exception for SurrealDB errors."""

    pass


class SurrealDBTransientError(SurrealDBError):
    """Transient error that can be retried (e.g., lock conflicts)."""

    pass


class SurrealDBQueryError(SurrealDBError):
    """Non-retryable query error."""

    pass


class SurrealDBConnectionError(SurrealDBError):
    """Connection-related error."""

    pass
