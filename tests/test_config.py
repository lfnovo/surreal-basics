"""Tests for configuration module."""

import os
import pytest

from surreal_basics import get_config, get_mode, init, set_mode
from surreal_basics.config import SurrealConfig, ConnectionMode


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

    def test_get_url_memory(self, reset_config):
        """Test memory URL generation."""
        config = SurrealConfig()
        config.mode = "memory"
        assert config.get_url() == "mem://"

    def test_get_url_embedded(self, reset_config):
        """Test embedded URL generation with path."""
        config = SurrealConfig()
        config.mode = "embedded"
        config.path = "/tmp/test.db"
        assert config.get_url() == "file:///tmp/test.db"

    def test_get_url_embedded_default_path(self, reset_config):
        """Test embedded URL generation with default path."""
        config = SurrealConfig()
        config.mode = "embedded"
        config.path = None
        assert config.get_url() == "file://./surreal.db"


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

    def test_init_memory_mode(self, reset_config):
        """Test memory mode via init."""
        init(mode="memory")
        assert get_mode() == "memory"
        assert get_config().get_url() == "mem://"

    def test_init_embedded_mode(self, reset_config):
        """Test embedded mode via init."""
        init(mode="embedded", path="/tmp/my.db")
        assert get_mode() == "embedded"
        assert get_config().path == "/tmp/my.db"
        assert get_config().get_url() == "file:///tmp/my.db"

    def test_set_mode_memory(self, reset_config):
        """Test mode change to memory via set_mode."""
        init()
        set_mode("memory")
        assert get_mode() == "memory"

    def test_set_mode_embedded(self, reset_config):
        """Test mode change to embedded via set_mode."""
        init()
        set_mode("embedded")
        assert get_mode() == "embedded"


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
        assert config.tls is True
        assert config.get_url() == "wss://secure.example.com:443/rpc"

    def test_surreal_url_https(self, reset_config, monkeypatch):
        """Test SURREAL_URL parsing for HTTPS."""
        monkeypatch.setenv("SURREAL_URL", "https://secure.example.com:443/rpc")
        config = SurrealConfig()
        assert config.host == "secure.example.com"
        assert config.port == 443
        assert config.mode == "http"
        assert config.tls is True
        assert config.get_url() == "https://secure.example.com:443/rpc"

    def test_surreal_url_wss_no_explicit_port_defaults_to_443(
        self, reset_config, monkeypatch
    ):
        """wss:// without explicit port should default to 443, not 8000."""
        monkeypatch.delenv("SURREAL_PORT", raising=False)
        monkeypatch.setenv("SURREAL_URL", "wss://tenant.aws-use1.surreal.cloud")
        config = SurrealConfig()
        assert config.host == "tenant.aws-use1.surreal.cloud"
        assert config.port == 443
        assert config.mode == "ws"
        assert config.tls is True
        assert (
            config.get_url() == "wss://tenant.aws-use1.surreal.cloud:443/rpc"
        )

    def test_surreal_url_https_no_explicit_port_defaults_to_443(
        self, reset_config, monkeypatch
    ):
        """https:// without explicit port should default to 443."""
        monkeypatch.delenv("SURREAL_PORT", raising=False)
        monkeypatch.setenv("SURREAL_URL", "https://tenant.aws-use1.surreal.cloud")
        config = SurrealConfig()
        assert config.port == 443
        assert config.tls is True
        assert (
            config.get_url()
            == "https://tenant.aws-use1.surreal.cloud:443/rpc"
        )

    def test_surreal_url_ws_no_explicit_port_defaults_to_8000(
        self, reset_config, monkeypatch
    ):
        """Non-TLS ws:// without explicit port should keep 8000 default."""
        monkeypatch.delenv("SURREAL_PORT", raising=False)
        monkeypatch.setenv("SURREAL_URL", "ws://localhost")
        config = SurrealConfig()
        assert config.port == 8000
        assert config.tls is False
        assert config.get_url() == "ws://localhost:8000/rpc"

    def test_surreal_port_env_overrides_url_port(self, reset_config, monkeypatch):
        """SURREAL_PORT should take precedence over URL port (local dev escape hatch)."""
        monkeypatch.setenv("SURREAL_URL", "wss://example.com:443")
        monkeypatch.setenv("SURREAL_PORT", "8018")
        config = SurrealConfig()
        assert config.port == 8018
        assert config.tls is True
        assert config.get_url() == "wss://example.com:8018/rpc"

    def test_surreal_tls_env_overrides_scheme(self, reset_config, monkeypatch):
        """SURREAL_TLS=true should upgrade a ws:// URL to wss://."""
        monkeypatch.delenv("SURREAL_PORT", raising=False)
        monkeypatch.setenv("SURREAL_URL", "ws://example.com:8443")
        monkeypatch.setenv("SURREAL_TLS", "true")
        config = SurrealConfig()
        assert config.tls is True
        assert config.mode == "ws"
        assert config.get_url() == "wss://example.com:8443/rpc"

    def test_surreal_tls_env_false_downgrades(self, reset_config, monkeypatch):
        """SURREAL_TLS=false should downgrade wss:// to ws:// (explicit override)."""
        monkeypatch.setenv("SURREAL_URL", "wss://example.com:8000")
        monkeypatch.setenv("SURREAL_TLS", "false")
        config = SurrealConfig()
        assert config.tls is False
        assert config.get_url() == "ws://example.com:8000/rpc"

    def test_init_tls_flag(self, reset_config):
        """init(tls=True) should flip the TLS flag without changing mode."""
        from surreal_basics import init

        init(mode="ws", host="example.com", port=443, tls=True)
        config = SurrealConfig()
        # init() mutates the global singleton; reset_config gives us a fresh one
        # so we explicitly test the global.
        from surreal_basics import get_config

        cfg = get_config()
        assert cfg.tls is True
        assert cfg.get_url() == "wss://example.com:443/rpc"

    def test_init_tls_recomputes_default_port(self, reset_config, monkeypatch):
        """init(tls=True) without an explicit port should yield :443, not :8000."""
        monkeypatch.delenv("SURREAL_PORT", raising=False)
        monkeypatch.delenv("SURREAL_URL", raising=False)
        from surreal_basics import get_config, init

        init(mode="ws", host="example.com", tls=True)
        cfg = get_config()
        assert cfg.port == 443
        assert cfg.get_url() == "wss://example.com:443/rpc"

    def test_init_tls_false_recomputes_default_port(
        self, reset_config, monkeypatch
    ):
        """init(tls=False) on a config that had implicit :443 should snap back to :8000."""
        monkeypatch.delenv("SURREAL_PORT", raising=False)
        monkeypatch.setenv("SURREAL_URL", "wss://example.com")  # implicit :443
        from surreal_basics import get_config, init

        init(tls=False)
        cfg = get_config()
        assert cfg.port == 8000
        assert cfg.get_url() == "ws://example.com:8000/rpc"

    def test_init_tls_preserves_explicit_port_env(self, reset_config, monkeypatch):
        """SURREAL_PORT should still pin the port even when init(tls=True) is called."""
        monkeypatch.setenv("SURREAL_PORT", "8018")
        monkeypatch.delenv("SURREAL_URL", raising=False)
        from surreal_basics import get_config, init

        init(mode="ws", host="example.com", tls=True)
        cfg = get_config()
        assert cfg.port == 8018
        assert cfg.get_url() == "wss://example.com:8018/rpc"

    def test_init_tls_preserves_explicit_port_arg(self, reset_config, monkeypatch):
        """An explicit port= argument should win over the implicit-default recompute."""
        monkeypatch.delenv("SURREAL_PORT", raising=False)
        monkeypatch.delenv("SURREAL_URL", raising=False)
        from surreal_basics import get_config, init

        init(mode="ws", host="example.com", port=9000, tls=True)
        cfg = get_config()
        assert cfg.port == 9000
        assert cfg.get_url() == "wss://example.com:9000/rpc"

    def test_init_tls_preserves_port_set_by_earlier_init_call(
        self, reset_config, monkeypatch
    ):
        """A port set by an earlier init(port=...) must survive a later init(tls=...)."""
        monkeypatch.delenv("SURREAL_PORT", raising=False)
        monkeypatch.delenv("SURREAL_URL", raising=False)
        from surreal_basics import get_config, init

        init(mode="ws", host="example.com", port=9000)
        init(tls=True)  # separate call — must not overwrite the 9000 above
        cfg = get_config()
        assert cfg.port == 9000
        assert cfg.get_url() == "wss://example.com:9000/rpc"

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

    def test_surreal_url_memory(self, reset_config, monkeypatch):
        """Test SURREAL_URL=memory:// detection."""
        monkeypatch.setenv("SURREAL_URL", "memory://")
        config = SurrealConfig()
        assert config.mode == "memory"
        assert config.get_url() == "mem://"

    def test_surreal_url_mem_scheme(self, reset_config, monkeypatch):
        """Test SURREAL_URL=mem:// detection."""
        monkeypatch.setenv("SURREAL_URL", "mem://")
        config = SurrealConfig()
        assert config.mode == "memory"
        assert config.get_url() == "mem://"

    def test_surreal_url_file(self, reset_config, monkeypatch):
        """Test SURREAL_URL with file:// scheme."""
        monkeypatch.setenv("SURREAL_URL", "file:///data/myapp.db")
        config = SurrealConfig()
        assert config.mode == "embedded"
        assert config.path == "/data/myapp.db"
        assert config.get_url() == "file:///data/myapp.db"

    def test_surreal_mode_env_memory(self, reset_config, monkeypatch):
        """Test SURREAL_MODE=memory env var."""
        monkeypatch.delenv("SURREAL_URL", raising=False)
        monkeypatch.setenv("SURREAL_MODE", "memory")
        config = SurrealConfig()
        assert config.mode == "memory"

    def test_surreal_mode_env_embedded(self, reset_config, monkeypatch):
        """Test SURREAL_MODE=embedded with SURREAL_PATH."""
        monkeypatch.delenv("SURREAL_URL", raising=False)
        monkeypatch.setenv("SURREAL_MODE", "embedded")
        monkeypatch.setenv("SURREAL_PATH", "/tmp/embedded.db")
        config = SurrealConfig()
        assert config.mode == "embedded"
        assert config.path == "/tmp/embedded.db"
        assert config.get_url() == "file:///tmp/embedded.db"

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
