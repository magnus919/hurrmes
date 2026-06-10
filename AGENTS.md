# hurrmes — Agent Guide

## Overview

A standalone CLI/TUI client that connects to the Hermes Agent API Server
and provides a custom conversation interface with a persistent right-side
dashboard panel.

## Quick Start

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run the app
hurrmes

# Or
python -m hurrmes
```

## Development Commands

```bash
# Lint all Python code
ruff check .

# Auto-fix lint issues
ruff check --fix .

# Format code
ruff format .

# Type-check all code
mypy hurrmes/

# Run all tests
pytest

# Run tests with coverage
pytest --cov=hurrmes

# Run pre-commit hooks on all files
pre-commit run --all-files

# Install pre-commit hooks (runs automatically on git commit)
pre-commit install
```

## Project Structure

```
hurrmes/
  __init__.py    — Package init
  __main__.py    — CLI entry point
  cli.py         — Main TUI application (prompt_toolkit)
  client.py      — Hermes API Server HTTP client
  config.py      — Configuration management
  dashboard.py   — Dashboard data collection and formatting
  theme.py       — Color themes
tests/
  test_*.py      — Pytest test files
```

## Dependencies

- `prompt-toolkit>=3.0.50` — Terminal UI framework
- `httpx>=0.28.0` — Async HTTP client
- `rich>=13.0.0` — Rich text formatting

## Coding Conventions

- **Python**: 3.11+, with `from __future__ import annotations`
- **Formatter**: ruff (line length 100, double quotes)
- **Linter**: ruff with pycodestyle, pyflakes, isort, pep8-naming, bugbear
- **Type hints**: Required for all function signatures (mypy strict mode)
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_CASE` for constants
- **Tests**: pytest with `test_*.py` naming, asyncio mode auto

## Configuration

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

API key via `HURRMES_API_KEY` env var.

The Hermes API Server must be running (`hermes gateway run` with
`API_SERVER_ENABLED=true`).
