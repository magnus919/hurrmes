# hurrmes — a custom TUI for the Hermes Agent API Server

A standalone CLI/TUI client that connects to the Hermes Agent API Server
and provides a custom conversation interface with a persistent right-side
dashboard panel.

## Quick Start

```bash
# Install
pip install -e .

# Run
hurrmes

# Or
python -m hurrmes
```

## Config

`~/.hurrmes/config.toml`:

```toml
[server]
host = "127.0.0.1"
port = 8642

[display]
dashboard = true
dashboard_min_width = 120
show_cost = false
theme = "amber"
```

API key via `HURRMES_API_KEY` env var or in config file.

## Architecture

- `hurrmes/cli.py` — Main TUI application (prompt_toolkit)
- `hurrmes/client.py` — Hermes API Server HTTP client
- `hurrmes/config.py` — Configuration management
- `hurrmes/dashboard.py` — Dashboard data collection and formatting
- `hurrmes/theme.py` — Color themes

The Hermes API Server must be running (`hermes gateway run` with
`API_SERVER_ENABLED=true`).
