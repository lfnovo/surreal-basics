"""Tests for the internal SDK error-translation glue (_sdk)."""

import base64
import json
from types import SimpleNamespace

import pytest
from surrealdb.errors import ConnectionUnavailableError, SurrealError

from surreal_basics._sdk import (
    first_statement_result,
    is_auth_rejected_error,
    is_dropped_request_keyerror,
    is_duplicate_error,
    token_expiry,
    token_near_expiry,
    translate_errors,
)
from surreal_basics.exceptions import SurrealDBQueryError, SurrealDBTransientError


def _make_jwt(exp: int) -> str:
    def seg(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    return f"{seg({'alg': 'HS512'})}.{seg({'exp': exp, 'iat': exp - 3600})}.sig"


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

    def test_keyerror_passes_through(self):
        # translate_errors only maps SurrealError; a KeyError (the WS dead-socket
        # symptom) must propagate untouched so the ConnectionManager can handle it.
        with pytest.raises(KeyError):
            with translate_errors():
                raise KeyError("00000000-aaaa-bbbb-cccc-000000000000")


class TestFirstStatementResult:
    """first_statement_result checks every statement of a query_raw response.

    The SDK's query() only looks at result[0], which hides failures in later
    statements — an aborted transaction was recorded as applied (#35).
    """

    @staticmethod
    def _ok(result=None):
        return {"status": "OK", "result": result, "time": "0ns"}

    @staticmethod
    def _err(message):
        return {"status": "ERR", "result": message, "time": "0ns"}

    def test_returns_first_statement_result_when_all_ok(self):
        response = {"result": [self._ok([{"id": "t:1"}]), self._ok([])]}
        assert first_statement_result(response) == [{"id": "t:1"}]

    def test_empty_result_list_returns_none(self):
        # e.g. "BEGIN; COMMIT;" on a 2.x server yields no statement results.
        assert first_statement_result({"result": []}) is None

    def test_top_level_rpc_error_raises(self):
        response = {"error": {"code": -32000, "message": "Parse error: boom"}}
        with pytest.raises(SurrealError, match="Parse error"):
            first_statement_result(response)

    def test_missing_result_key_raises(self):
        with pytest.raises(SurrealError, match="no result"):
            first_statement_result({"id": "x"})

    def test_failure_after_ok_first_statement_raises(self):
        response = {"result": [self._ok(), self._err("An error occurred: boom")]}
        with pytest.raises(SurrealError, match="boom"):
            first_statement_result(response)

    def test_aborted_transaction_raises_the_real_cause(self):
        # Shape SurrealDB 3.x returns for BEGIN; DEFINE ...; THROW 'stop'; COMMIT;
        response = {
            "result": [
                self._ok(),
                self._err("The query was not executed due to a failed transaction"),
                self._err("An error occurred: stop"),
                self._err(
                    "Cannot COMMIT: the transaction was aborted due to a prior error"
                ),
            ]
        }
        with pytest.raises(SurrealError, match="stop"):
            first_statement_result(response)

    def test_only_echoes_raises_the_echo(self):
        # A dry-run's CANCEL TRANSACTION: every statement is a "not executed"
        # echo and there is no more specific error to prefer.
        response = {
            "result": [
                self._ok(),
                self._err("The query was not executed due to a cancelled transaction"),
                self._ok(),
            ]
        }
        with pytest.raises(SurrealError, match="cancelled transaction"):
            first_statement_result(response)

    def test_retryable_later_statement_becomes_transient(self):
        response = {
            "result": [
                self._ok(),
                self._err(
                    "Failed to commit transaction due to a read or write conflict. This transaction can be retried"
                ),
            ]
        }
        with pytest.raises(SurrealDBTransientError):
            with translate_errors():
                first_statement_result(response)


class TestIsDroppedRequestKeyError:
    def test_uuid_keyerror_is_a_drop(self):
        assert is_dropped_request_keyerror(
            KeyError("00000000-aaaa-bbbb-cccc-000000000000")
        )

    @pytest.mark.parametrize("key", ["name", "id", "user_id", "0"])
    def test_non_uuid_keyerror_is_not_a_drop(self, key):
        assert is_dropped_request_keyerror(KeyError(key)) is False

    def test_non_keyerror_is_not_a_drop(self):
        assert is_dropped_request_keyerror(ValueError("x")) is False

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


class TestTokenExpiry:
    def test_decodes_tokens_object(self):
        # signin() returns a Tokens object whose `access` field holds the JWT.
        tok = SimpleNamespace(access=_make_jwt(1_900_000_000), refresh=None)
        assert token_expiry(tok) == 1_900_000_000.0

    def test_decodes_plain_string(self):
        assert token_expiry(_make_jwt(1_800_000_000)) == 1_800_000_000.0

    @pytest.mark.parametrize("value", ["not-a-jwt", "", "a.b"])
    def test_non_jwt_returns_none(self, value):
        assert token_expiry(value) is None

    def test_missing_access_returns_none(self):
        assert token_expiry(SimpleNamespace(access=None)) is None


class TestTokenNearExpiry:
    def test_past_is_near(self):
        assert token_near_expiry(1_000_000_000.0) is True

    def test_far_future_is_not_near(self):
        assert token_near_expiry(99_000_000_000.0) is False

    def test_none_is_not_near(self):
        assert token_near_expiry(None) is False
