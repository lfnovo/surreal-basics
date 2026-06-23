"""Tests for utility functions."""

import pytest

from surreal_basics import ensure_record_id, parse_record_ids
from surreal_basics.utils import validate_identifier


class MockRecordID:
    """Mock RecordID for testing without SDK dependency."""

    def __init__(self, table: str, id_val: str):
        self.table = table
        self.id_val = id_val

    def __str__(self):
        return f"{self.table}:{self.id_val}"


class TestParseRecordIds:
    """Tests for parse_record_ids function."""

    def test_parse_record_ids_dict(self):
        """Test converting RecordID in dict."""
        # Use actual SDK RecordID if available, otherwise mock
        try:
            from surrealdb import RecordID

            data = {"user": RecordID("user", "123"), "name": "Test"}
            result = parse_record_ids(data)
            assert result["user"] == "user:123"
            assert result["name"] == "Test"
        except ImportError:
            pytest.skip("surrealdb SDK not installed")

    def test_parse_record_ids_list(self):
        """Test converting RecordID in list."""
        try:
            from surrealdb import RecordID

            data = [RecordID("user", "1"), RecordID("user", "2")]
            result = parse_record_ids(data)
            assert result == ["user:1", "user:2"]
        except ImportError:
            pytest.skip("surrealdb SDK not installed")

    def test_parse_record_ids_nested(self):
        """Test converting RecordID in nested structures."""
        try:
            from surrealdb import RecordID

            data = {
                "users": [
                    {"id": RecordID("user", "1"), "name": "User 1"},
                    {"id": RecordID("user", "2"), "name": "User 2"},
                ],
                "meta": {"owner": RecordID("admin", "root")},
            }
            result = parse_record_ids(data)
            assert result["users"][0]["id"] == "user:1"
            assert result["users"][1]["id"] == "user:2"
            assert result["meta"]["owner"] == "admin:root"
        except ImportError:
            pytest.skip("surrealdb SDK not installed")

    def test_parse_record_ids_primitive(self):
        """Test that primitives pass through unchanged."""
        assert parse_record_ids("string") == "string"
        assert parse_record_ids(123) == 123
        assert parse_record_ids(True) is True
        assert parse_record_ids(None) is None

    def test_parse_record_ids_empty(self):
        """Test empty structures."""
        assert parse_record_ids({}) == {}
        assert parse_record_ids([]) == []


class TestEnsureRecordId:
    """Tests for ensure_record_id function."""

    def test_ensure_record_id_string(self):
        """Test converting string to RecordID."""
        try:
            from surrealdb import RecordID

            result = ensure_record_id("user:123")
            assert isinstance(result, RecordID)
            assert result.table_name == "user"
            assert result.id == "123"
        except ImportError:
            pytest.skip("surrealdb SDK not installed")

    def test_ensure_record_id_already(self):
        """Test that RecordID passes through."""
        try:
            from surrealdb import RecordID

            original = RecordID("user", "123")
            result = ensure_record_id(original)
            assert result is original
        except ImportError:
            pytest.skip("surrealdb SDK not installed")


class TestValidateIdentifier:
    """Tests for validate_identifier guard."""

    @pytest.mark.parametrize(
        "value",
        ["user", "user:123", "user:abc_def", "graph:⟨complex-id⟩", "ns_table"],
    )
    def test_safe_identifiers_pass(self, value):
        """Legitimate table/record identifiers pass through unchanged."""
        assert validate_identifier(value, "record_id") == value

    @pytest.mark.parametrize(
        "value",
        [
            "user:1; DROP TABLE user",
            "user\n RETURN 1",
            "user:1 -- comment",
            "user/* */",
            "user:1\x00",
        ],
    )
    def test_unsafe_identifiers_raise(self, value):
        """Statement separators and comment markers are rejected."""
        with pytest.raises(ValueError):
            validate_identifier(value, "record_id")

    def test_record_id_instance_passes(self):
        """RecordID instances are always considered safe."""
        try:
            from surrealdb import RecordID
        except ImportError:
            pytest.skip("surrealdb SDK not installed")

        rid = RecordID("user", "123")
        assert validate_identifier(rid, "record_id") is rid
