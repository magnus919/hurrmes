"""Tests for hurrmes.dashboard."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from hurrmes.dashboard import (
    DashboardData,
    TodoItem,
    collect_system_info,
    format_cost,
    format_cwd,
    format_tokens,
    get_git_branch,
)


class TestFormatTokens:
    """Tests for format_tokens utility."""

    def test_zero(self) -> None:
        assert format_tokens(0) == "0"

    def test_small_number(self) -> None:
        assert format_tokens(42) == "42"

    def test_thousands(self) -> None:
        assert format_tokens(1234) == "1.2K"

    def test_millions(self) -> None:
        assert format_tokens(2_500_000) == "2.5M"

    def test_rounding(self) -> None:
        assert format_tokens(999) == "999"
        assert format_tokens(1000) == "1.0K"


class TestFormatCost:
    """Tests for format_cost utility."""

    def test_micro_dollars(self) -> None:
        result = format_cost(0.000001)
        assert result.startswith("$0.")
        assert len(result) >= 8

    def test_cents(self) -> None:
        assert format_cost(0.05) == "$0.0500"

    def test_dollars(self) -> None:
        assert format_cost(1.50) == "$1.50"

    def test_large_amount(self) -> None:
        assert format_cost(123.45) == "$123.45"


class TestFormatCwd:
    """Tests for format_cwd utility."""

    def test_short_path_stays_unchanged(self) -> None:
        result = format_cwd("/tmp", max_len=40)
        assert result == "/tmp"

    def test_home_replacement(self) -> None:
        """Home directory should be replaced with ~."""
        result = format_cwd("/home/user/projects/hurrmes", max_len=100)
        assert "~" in result or "/home/" in result

    def test_long_path_truncation(self) -> None:
        """Long paths should be truncated with ..."""
        path = "/a/very/long/path/that/should/be/truncated/project/src/utils"
        result = format_cwd(path, max_len=20)
        assert "..." in result

    def test_home_replacement_then_truncation(self) -> None:
        """Home path that truncates after replacement."""
        with patch("pathlib.Path.home", return_value="/home/user"):
            result = format_cwd(
                "/home/user/very/long/nested/directory/structure/project/src", max_len=20
            )
            assert "..." in result


class TestCollectSystemInfo:
    """Tests for collect_system_info."""

    def test_returns_load_and_time(self) -> None:
        """collect_system_info should return loadavg string and time string."""
        load_str, time_str = collect_system_info()
        assert isinstance(load_str, str)
        assert isinstance(time_str, str)
        assert time_str != ""

    def test_load_format(self) -> None:
        """Loadavg should contain three space-separated numbers."""
        load_str, _ = collect_system_info()
        parts = load_str.split()
        assert len(parts) == 3
        for p in parts:
            float(p)  # should not raise

    @patch("os.getloadavg", side_effect=OSError)
    def test_load_error_fallback(self, _: object) -> None:
        """When getloadavg raises OSError, should return --."""
        load_str, _ = collect_system_info()
        assert load_str == "--"


class TestGetGitBranch:
    """Tests for get_git_branch."""

    def test_in_git_repo(self) -> None:
        """Should return current branch name when in a git repo."""
        branch = get_git_branch()
        assert isinstance(branch, str)
        assert branch != ""

    def test_non_git_directory(self) -> None:
        """Should return empty string when not in a git repo."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 128
            mock_run.return_value.stdout = ""
            branch = get_git_branch(cwd="/tmp")
            assert branch == ""

    def test_file_not_found(self) -> None:
        """Should return empty string when git is not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            branch = get_git_branch()
            assert branch == ""

    def test_subprocess_error(self) -> None:
        """Should return empty string on subprocess error."""
        with patch("subprocess.run", side_effect=subprocess.SubprocessError):
            branch = get_git_branch()
            assert branch == ""


class TestDashboardData:
    """Tests for DashboardData dataclass."""

    def test_default_values(self) -> None:
        """DashboardData should initialize with sensible defaults."""
        data = DashboardData()
        assert data.loadavg == ""
        assert data.datetime == ""
        assert data.prompt_tokens == 0
        assert data.completion_tokens == 0
        assert data.total_tokens == 0
        assert data.api_calls == 0
        assert data.cost_usd == 0.0
        assert data.todos == []
        assert data.subagent_count == 0
        assert data.subagent_depth == 0

    def test_todo_item_defaults(self) -> None:
        """TodoItem should store content and status."""
        item = TodoItem(content="test task", status="pending")
        assert item.content == "test task"
        assert item.status == "pending"

    def test_token_tracking(self) -> None:
        """DashboardData should track token usage."""
        data = DashboardData()
        data.prompt_tokens = 100
        data.completion_tokens = 50
        data.total_tokens = 150
        data.api_calls = 3
        assert data.total_tokens == data.prompt_tokens + data.completion_tokens
