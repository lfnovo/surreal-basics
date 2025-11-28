"""Tests for retry mechanism."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from surreal_basics.exceptions import SurrealDBQueryError, SurrealDBTransientError
from surreal_basics.retry import surreal_retry, surreal_retry_async


class TestRetrySync:
    """Tests for sync retry decorator."""

    def test_retry_on_transient_error(self):
        """Test that retry happens on transient errors."""
        call_count = 0

        @surreal_retry
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise SurrealDBTransientError("can be retried")
            return "success"

        result = flaky_function()
        assert result == "success"
        assert call_count == 3

    def test_no_retry_on_query_error(self):
        """Test that no retry happens on query errors."""
        call_count = 0

        @surreal_retry
        def query_error_function():
            nonlocal call_count
            call_count += 1
            raise SurrealDBQueryError("invalid query")

        with pytest.raises(SurrealDBQueryError):
            query_error_function()

        assert call_count == 1  # No retry

    def test_retry_max_attempts(self):
        """Test that retry stops after max attempts."""
        call_count = 0

        @surreal_retry
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise SurrealDBTransientError("always fails")

        with pytest.raises(SurrealDBTransientError):
            always_fails()

        assert call_count == 3  # Default max attempts

    def test_success_no_retry(self):
        """Test that successful calls don't retry."""
        call_count = 0

        @surreal_retry
        def success_function():
            nonlocal call_count
            call_count += 1
            return "success"

        result = success_function()
        assert result == "success"
        assert call_count == 1


@pytest.mark.asyncio
class TestRetryAsync:
    """Tests for async retry decorator."""

    async def test_retry_on_transient_error_async(self):
        """Test that retry happens on transient errors (async)."""
        call_count = 0

        @surreal_retry_async
        async def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise SurrealDBTransientError("can be retried")
            return "success"

        result = await flaky_function()
        assert result == "success"
        assert call_count == 3

    async def test_no_retry_on_query_error_async(self):
        """Test that no retry happens on query errors (async)."""
        call_count = 0

        @surreal_retry_async
        async def query_error_function():
            nonlocal call_count
            call_count += 1
            raise SurrealDBQueryError("invalid query")

        with pytest.raises(SurrealDBQueryError):
            await query_error_function()

        assert call_count == 1  # No retry

    async def test_retry_max_attempts_async(self):
        """Test that retry stops after max attempts (async)."""
        call_count = 0

        @surreal_retry_async
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise SurrealDBTransientError("always fails")

        with pytest.raises(SurrealDBTransientError):
            await always_fails()

        assert call_count == 3  # Default max attempts

    async def test_success_no_retry_async(self):
        """Test that successful calls don't retry (async)."""
        call_count = 0

        @surreal_retry_async
        async def success_function():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await success_function()
        assert result == "success"
        assert call_count == 1
