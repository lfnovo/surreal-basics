"""Tests for the internal SDK error-translation glue (_sdk)."""

import pytest
from surrealdb.errors import ConnectionUnavailableError, SurrealError

from surreal_basics._sdk import (
    is_auth_rejected_error,
    is_duplicate_error,
    translate_errors,
)
from surreal_basics.exceptions import SurrealDBQueryError, SurrealDBTransientError


class TestTranslateErrors:
    """translate_errors maps surrealdb SDK errors to our hierarchy."""

    def test_retryable_becomes_transient(self):
        with pytest.raises(SurrealDBTransientError):
            with translate_errors():
                raise SurrealError("This transaction can be retried")

    def test_other_server_error_becomes_query_error(self):
        with pytest.raises(SurrealDBQueryError):
            with translate_errors():
                raise SurrealError("The table 'x' does not exist")

    def test_ws_drop_is_reraised_untouched(self):
        # ConnectionUnavailableError is a SurrealError subclass, so this also
        # proves the WS-drop branch runs *before* the generic SurrealError one
        # (otherwise it would be swallowed into SurrealDBQueryError).
        with pytest.raises(ConnectionUnavailableError):
            with translate_errors():
                raise ConnectionUnavailableError("socket gone")

    def test_keyerror_is_reraised_as_ws_drop(self):
        # surrealdb 2.x raises a bare KeyError(request-uuid) when the WS socket
        # drops mid-request; translate_errors must re-raise it (not swallow it)
        # so the ConnectionManager can reset the singleton and retry.
        with pytest.raises(KeyError):
            with translate_errors():
                raise KeyError("00000000-aaaa-bbbb-cccc-000000000000")

    def test_non_surreal_error_passes_through(self):
        with pytest.raises(ValueError):
            with translate_errors():
                raise ValueError("unrelated")


class TestIsDuplicateError:
    @pytest.mark.parametrize(
        "msg",
        [
            "Database record `dup:a` already exists",
            "Found 'x' already contains the value",
        ],
    )
    def test_detects_duplicate(self, msg):
        assert is_duplicate_error(Exception(msg)) is True

    def test_ignores_unrelated(self):
        assert is_duplicate_error(Exception("some other error")) is False


class TestIsAuthRejectedError:
    @pytest.mark.parametrize(
        "msg",
        [
            "IAM error: Not enough permissions to perform this action",
            "There was a problem with authentication",
            "The token has expired",
            "Invalid token",
        ],
    )
    def test_detects_auth_rejection(self, msg):
        assert is_auth_rejected_error(Exception(msg)) is True

    def test_ignores_unrelated(self):
        assert is_auth_rejected_error(Exception("table does not exist")) is False
