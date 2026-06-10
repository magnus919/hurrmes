"""Tests for hurrmes.__main__."""

from __future__ import annotations

from unittest.mock import patch


class TestMain:
    """Tests for the __main__ entry point."""

    def test_help_flag(self) -> None:
        """--help should print docstring and return."""
        with patch("sys.argv", ["hurrmes", "--help"]), patch("builtins.print") as mock_print:
            from hurrmes.__main__ import main

            main()
            mock_print.assert_called_once()
            assert "Usage" in mock_print.call_args[0][0]

    def test_short_help_flag(self) -> None:
        """-h should print docstring and return."""
        with patch("sys.argv", ["hurrmes", "-h"]), patch("builtins.print") as mock_print:
            from hurrmes.__main__ import main

            main()
            mock_print.assert_called_once()

    def test_config_flag(self) -> None:
        """--config should print config path."""
        with patch("sys.argv", ["hurrmes", "--config"]), patch("builtins.print") as mock_print:
            from hurrmes.__main__ import main

            main()
            assert mock_print.call_count >= 2

    def test_default_starts_tui(self) -> None:
        """No flags should launch the TUI main."""
        with patch("sys.argv", ["hurrmes"]), patch("hurrmes.cli.main") as mock_tui:
            from hurrmes.__main__ import main

            main()
            mock_tui.assert_called_once()
