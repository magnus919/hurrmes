"""Dashboard panel rendering for hurrmes TUI.

The dashboard lives on the right side of the terminal on wide displays.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DashboardData:
    """All data needed to render the dashboard panel."""

    # System info
    loadavg: str = ""
    datetime: str = ""

    # Working context
    cwd: str = ""
    git_branch: str = ""

    # Token wallet (from Hermes API usage response)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    api_calls: int = 0
    cost_usd: float = 0.0

    # Plan state
    todos: list[TodoItem] = field(default_factory=list)

    # Subagent activity
    subagent_count: int = 0
    subagent_depth: int = 0


@dataclass
class TodoItem:
    content: str
    status: str  # "pending" | "in_progress" | "completed"


def collect_system_info() -> tuple[str, str]:
    """Get loadavg and current date/time string."""
    try:
        load = os.getloadavg()
        load_str = f"{load[0]:.1f} {load[1]:.1f} {load[2]:.1f}"
    except OSError:
        load_str = "--"

    now = time.localtime()
    time_str = time.strftime("%a %b %d %I:%M:%S %p", now)

    return load_str, time_str


def get_git_branch(cwd: str | None = None) -> str:
    """Get current git branch name, or empty string if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd or os.getcwd(),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return ""


def format_cwd(path: str, max_len: int = 40) -> str:
    """Compact working directory display."""
    home = str(Path.home())
    if path.startswith(home):
        path = "~" + path[len(home) :]
    if len(path) > max_len:
        parts = path.split("/")
        if len(parts) > 3:
            path = ".../" + "/".join(parts[-3:])
    return path


def format_tokens(n: int) -> str:
    """Compact token formatting: 12345 -> 12.3K"""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def format_cost(cost: float) -> str:
    """Format dollar cost."""
    if cost >= 1.0:
        return f"${cost:.2f}"
    if cost >= 0.01:
        return f"${cost:.4f}"
    return f"${cost:.6f}"
