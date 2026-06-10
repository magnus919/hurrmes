"""Tests for hurrmes.config."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hurrmes.config import (
    Config,
    DisplayConfig,
    ServerConfig,
)


class TestConfig:
    """Tests for the Config dataclass and loading."""

    def test_server_config_defaults(self) -> None:
        """ServerConfig should use sensible defaults."""
        cfg = ServerConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8642
        assert cfg.api_key == ""
        assert cfg.tls is False

    def test_server_config_base_url_http(self) -> None:
        """base_url should use http when tls is False."""
        cfg = ServerConfig(host="localhost", port=8080, tls=False)
        assert cfg.base_url == "http://localhost:8080"

    def test_server_config_base_url_https(self) -> None:
        """base_url should use https when tls is True."""
        cfg = ServerConfig(host="localhost", port=443, tls=True)
        assert cfg.base_url == "https://localhost:443"

    def test_display_config_defaults(self) -> None:
        """DisplayConfig should use sensible defaults."""
        cfg = DisplayConfig()
        assert cfg.dashboard is True
        assert cfg.dashboard_min_width == 120
        assert cfg.show_cost is False
        assert cfg.theme == "amber"

    def test_config_defaults(self) -> None:
        """Config should initialize with default sub-configs."""
        cfg = Config()
        assert cfg.default_model == "hermes-agent"
        assert cfg.session_autosave is True
        assert cfg.server.host == "127.0.0.1"
        assert cfg.display.theme == "amber"

    def test_config_load_returns_defaults_when_no_file(self) -> None:
        """Config.load() should return defaults when config file doesn't exist."""
        cfg = Config.load(path="/nonexistent/path/config.toml")
        assert cfg.server.host == "127.0.0.1"
        assert cfg.display.dashboard is True

    @pytest.mark.asyncio
    async def test_config_load_does_not_raise(self) -> None:
        """Config.load() should not raise for any valid path."""
        # Just verify the method doesn't crash with a non-existent path
        cfg = Config.load(path="/tmp/__hurrmes_test_nonexistent/config.toml")
        assert isinstance(cfg, Config)


class TestConfigEnvOverride:
    """Tests for environment variable overrides."""

    def test_api_key_from_env(self, tmp_path: Path) -> None:
        """HURRMES_API_KEY environment variable should override config."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("[server]\nhost = 'localhost'\n")
        with patch("hurrmes.config.os.environ", {"HURRMES_API_KEY": "test-key-123"}):
            cfg = Config.load(path=str(config_path))
            assert cfg.server.api_key == "test-key-123"

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        """Config.save() should create the config directory."""
        dest_dir = tmp_path / ".hurrmes"
        dest = dest_dir / "config.toml"
        cfg = Config()
        with (
            patch("hurrmes.config.DEFAULT_CONFIG_PATH", dest),
            patch("hurrmes.config.HURRMES_HOME", dest_dir),
        ):
            cfg.save()
            assert dest.exists()
            content = dest.read_text()
            assert "[server]" in content
            assert "[display]" in content
