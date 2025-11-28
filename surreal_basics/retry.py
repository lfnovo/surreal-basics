"""Retry decorators using tenacity."""

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .exceptions import SurrealDBTransientError

# Retry decorator for transient errors (lock conflicts, etc.)
# Retries up to 3 times with exponential backoff: 0.5s, 1s, 2s
surreal_retry = retry(
    retry=retry_if_exception_type(SurrealDBTransientError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
    reraise=True,
)

# Async version of the retry decorator
surreal_retry_async = retry(
    retry=retry_if_exception_type(SurrealDBTransientError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
    reraise=True,
)
