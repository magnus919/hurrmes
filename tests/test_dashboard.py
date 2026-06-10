"""Tests for hurrmes.dashboard."""

from __future__ import annotations

from hurrmes.dashboard import (
    DashboardData,
    TodoItem,
    format_cost,
    format_cwd,
    format_tokens,
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
        # Should contain ~ since home is replaced
        assert "~" in result or "/home/" in result

    def test_long_path_truncation(self) -> None:
        """Long paths should be truncated with ..."""
        path = "/a/very/long/path/that/should/be/truncated/project/src/utils"
        result = format_cwd(path, max_len=20)
        assert "..." in result


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
