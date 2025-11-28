"""Tests for configuration module."""

import os
import pytest

from surreal_basics import get_config, get_mode, init, set_mode
from surreal_basics.config import SurrealConfig


class TestSurrealConfig:
    """Tests for SurrealConfig class."""

    def test_default_values(self, reset_config):
        """Test that default values are applied."""
        config = SurrealConfig()
        assert config.host == os.getenv("SURREAL_HOST", "localhost")
        assert config.port == int(os.getenv("SURREAL_PORT", "8000"))
        assert config.mode in ("http", "ws")

    def test_get_url_ws(self, reset_config):
        """Test WebSocket URL generation."""
        config = SurrealConfig()
        config.mode = "ws"
        config.host = "localhost"
        config.port = 8000
        assert config.get_url() == "ws://localhost:8000/rpc"

    def test_get_url_http(self, reset_config):
        """Test HTTP URL generation."""
        config = SurrealConfig()
        config.mode = "http"
        config.host = "localhost"
        config.port = 8000
        assert config.get_url() == "http://localhost:8000/rpc"


class TestConfigFunctions:
    """Tests for config module functions."""

    def test_get_config_creates_singleton(self, reset_config):
        """Test that get_config returns same instance."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_init_overrides_values(self, reset_config):
        """Test that init() overrides config values."""
        init(host="newhost", port=9999, namespace="newns")
        config = get_config()
        assert config.host == "newhost"
        assert config.port == 9999
        assert config.namespace == "newns"

    def test_init_partial_override(self, reset_config):
        """Test that init() only overrides provided values."""
        init(host="first")
        init(port=1234)
        config = get_config()
        assert config.host == "first"
        assert config.port == 1234

    def test_set_mode(self, reset_config):
        """Test mode change via set_mode."""
        init()
        set_mode("http")
        assert get_mode() == "http"
        set_mode("ws")
        assert get_mode() == "ws"

    def test_init_mode(self, reset_config):
        """Test mode change via init."""
        init(mode="http")
        assert get_mode() == "http"
        init(mode="ws")
        assert get_mode() == "ws"

    def test_init_persistent(self, reset_config):
        """Test persistent flag."""
        init(persistent=True)
        assert get_config().persistent is True
        init(persistent=False)
        assert get_config().persistent is False


class TestEnvironmentVariableAliases:
    """Tests for alternative environment variable names."""

    def test_surreal_url_ws(self, reset_config, monkeypatch):
        """Test SURREAL_URL parsing for WebSocket."""
        monkeypatch.setenv("SURREAL_URL", "ws://myhost:8018/rpc")
        config = SurrealConfig()
        assert config.host == "myhost"
        assert config.port == 8018
        assert config.mode == "ws"

    def test_surreal_url_http(self, reset_config, monkeypatch):
        """Test SURREAL_URL parsing for HTTP."""
        monkeypatch.setenv("SURREAL_URL", "http://example.com:9000/rpc")
        config = SurrealConfig()
        assert config.host == "example.com"
        assert config.port == 9000
        assert config.mode == "http"

    def test_surreal_url_wss(self, reset_config, monkeypatch):
        """Test SURREAL_URL parsing for secure WebSocket."""
        monkeypatch.setenv("SURREAL_URL", "wss://secure.example.com:443/rpc")
        config = SurrealConfig()
        assert config.host == "secure.example.com"
        assert config.port == 443
        assert config.mode == "ws"

    def test_surreal_url_https(self, reset_config, monkeypatch):
        """Test SURREAL_URL parsing for HTTPS."""
        monkeypatch.setenv("SURREAL_URL", "https://secure.example.com:443/rpc")
        config = SurrealConfig()
        assert config.host == "secure.example.com"
        assert config.port == 443
        assert config.mode == "http"

    def test_surreal_password_alias(self, reset_config, monkeypatch):
        """Test SURREAL_PASSWORD as alias for SURREAL_PASS."""
        monkeypatch.setenv("SURREAL_PASSWORD", "mypassword")
        monkeypatch.delenv("SURREAL_PASS", raising=False)
        config = SurrealConfig()
        assert config.password == "mypassword"

    def test_surreal_pass_takes_precedence(self, reset_config, monkeypatch):
        """Test SURREAL_PASS takes precedence over SURREAL_PASSWORD."""
        monkeypatch.setenv("SURREAL_PASS", "pass1")
        monkeypatch.setenv("SURREAL_PASSWORD", "pass2")
        config = SurrealConfig()
        assert config.password == "pass1"

    def test_surreal_namespace_alias(self, reset_config, monkeypatch):
        """Test SURREAL_NAMESPACE as alias for SURREAL_NS."""
        monkeypatch.setenv("SURREAL_NAMESPACE", "mynamespace")
        monkeypatch.delenv("SURREAL_NS", raising=False)
        config = SurrealConfig()
        assert config.namespace == "mynamespace"

    def test_surreal_ns_takes_precedence(self, reset_config, monkeypatch):
        """Test SURREAL_NS takes precedence over SURREAL_NAMESPACE."""
        monkeypatch.setenv("SURREAL_NS", "ns1")
        monkeypatch.setenv("SURREAL_NAMESPACE", "ns2")
        config = SurrealConfig()
        assert config.namespace == "ns1"

    def test_surreal_database_alias(self, reset_config, monkeypatch):
        """Test SURREAL_DATABASE as alias for SURREAL_DB."""
        monkeypatch.setenv("SURREAL_DATABASE", "mydatabase")
        monkeypatch.delenv("SURREAL_DB", raising=False)
        config = SurrealConfig()
        assert config.database == "mydatabase"

    def test_surreal_db_takes_precedence(self, reset_config, monkeypatch):
        """Test SURREAL_DB takes precedence over SURREAL_DATABASE."""
        monkeypatch.setenv("SURREAL_DB", "db1")
        monkeypatch.setenv("SURREAL_DATABASE", "db2")
        config = SurrealConfig()
        assert config.database == "db1"

    def test_full_alternative_config(self, reset_config, monkeypatch):
        """Test all alternative env vars together."""
        monkeypatch.setenv("SURREAL_URL", "ws://localhost:8018/rpc")
        monkeypatch.setenv("SURREAL_USER", "root")
        monkeypatch.setenv("SURREAL_PASSWORD", "secret")
        monkeypatch.setenv("SURREAL_NAMESPACE", "investments")
        monkeypatch.setenv("SURREAL_DATABASE", "investments")
        # Clear the short names
        monkeypatch.delenv("SURREAL_PASS", raising=False)
        monkeypatch.delenv("SURREAL_NS", raising=False)
        monkeypatch.delenv("SURREAL_DB", raising=False)

        config = SurrealConfig()
        assert config.host == "localhost"
        assert config.port == 8018
        assert config.mode == "ws"
        assert config.user == "root"
        assert config.password == "secret"
        assert config.namespace == "investments"
        assert config.database == "investments"
