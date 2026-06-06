"""Configuration for the hurrmes CLI client.

Reads ~/.hurrmes/config.toml with sensible defaults.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

HURRMES_HOME = Path.home() / ".hurrmes"
DEFAULT_CONFIG_PATH = HURRMES_HOME / "config.toml"


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8642
    api_key: str = ""
    tls: bool = False

    @property
    def base_url(self) -> str:
        scheme = "https" if self.tls else "http"
        return f"{scheme}://{self.host}:{self.port}"


@dataclass
class DisplayConfig:
    dashboard: bool = True
    dashboard_min_width: int = 120
    show_cost: bool = False
    theme: str = "amber"  # amber, dark, light


@dataclass
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    default_model: str = "hermes-agent"
    session_autosave: bool = True

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        cfg = cls()

        path = Path(path) if path else DEFAULT_CONFIG_PATH
        if not path.exists():
            return cfg

        raw = path.read_bytes()
        data = tomllib.loads(raw.decode())

        # Server section
        srv = data.get("server", {})
        cfg.server.host = srv.get("host", cfg.server.host)
        cfg.server.port = srv.get("port", cfg.server.port)
        cfg.server.api_key = srv.get("api_key", cfg.server.api_key)
        cfg.server.tls = srv.get("tls", cfg.server.tls)

        # Display section
        disp = data.get("display", {})
        cfg.display.dashboard = disp.get("dashboard", cfg.display.dashboard)
        cfg.display.dashboard_min_width = disp.get(
            "dashboard_min_width", cfg.display.dashboard_min_width
        )
        cfg.display.show_cost = disp.get("show_cost", cfg.display.show_cost)
        cfg.display.theme = disp.get("theme", cfg.display.theme)

        # Top-level
        cfg.default_model = data.get("default_model", cfg.default_model)
        cfg.session_autosave = data.get("session_autosave", cfg.session_autosave)

        # Env override for API key
        if env_key := os.environ.get("HURRMES_API_KEY"):
            cfg.server.api_key = env_key

        return cfg

    def save(self) -> None:
        HURRMES_HOME.mkdir(parents=True, exist_ok=True)
        lines = [
            "[server]",
            f'host = "{self.server.host}"',
            f"port = {self.server.port}",
            f'tls = {"true" if self.server.tls else "false"}',
            "",
            "[display]",
            f'dashboard = {"true" if self.display.dashboard else "false"}',
            f"dashboard_min_width = {self.display.dashboard_min_width}",
            f'show_cost = {"true" if self.display.show_cost else "false"}',
            f'theme = "{self.display.theme}"',
            "",
            f'default_model = "{self.default_model}"',
            f'session_autosave = {"true" if self.session_autosave else "false"}',
            "",
        ]
        # Don't write the API key — it comes from env or manual config
        DEFAULT_CONFIG_PATH.write_text("\n".join(lines) + "\n")


def ensure_config() -> Config:
    """Load or create default config."""
    cfg = Config.load()
    if not DEFAULT_CONFIG_PATH.exists():
        cfg.save()
    return cfg
