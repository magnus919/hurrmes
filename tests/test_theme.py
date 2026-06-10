"""Tests for hurrmes.theme."""

from __future__ import annotations

from hurrmes.theme import AMBER, DARK, Theme, get_theme


class TestTheme:
    """Tests for Theme dataclass."""

    def test_amber_theme_values(self) -> None:
        """AMBER theme should have expected color values."""
        assert AMBER.name == "amber"
        assert AMBER.bg == "#1a170f"
        assert AMBER.accent == "#d29d00"

    def test_dark_theme_values(self) -> None:
        """DARK theme should have expected color values."""
        assert DARK.name == "dark"
        assert DARK.bg == "#1F1F1F"
        assert DARK.accent == "#7EB8F6"

    def test_get_theme_amber(self) -> None:
        """get_theme('amber') should return the AMBER theme."""
        theme = get_theme("amber")
        assert theme is AMBER

    def test_get_theme_dark(self) -> None:
        """get_theme('dark') should return the DARK theme."""
        theme = get_theme("dark")
        assert theme is DARK

    def test_get_theme_unknown_falls_back_to_amber(self) -> None:
        """get_theme with unknown name should return AMBER."""
        theme = get_theme("nonexistent")
        assert theme is AMBER

    def test_get_theme_default(self) -> None:
        """get_theme() without args should return AMBER."""
        theme = get_theme()
        assert theme is AMBER

    def test_ansi_color_lookup(self) -> None:
        """ansi() should return correct ANSI codes."""
        assert AMBER.ansi("#d29d00") == "178"
        assert AMBER.ansi("#1a170f") == "233"
        assert AMBER.ansi("#unknown") == "7"

    def test_theme_is_dataclass(self) -> None:
        """Theme should be instantiable with all fields."""
        theme = Theme(
            name="test",
            bg="#000",
            fg="#fff",
            muted="#888",
            accent="#ff0",
            border="#333",
            status_good="#0f0",
            status_warn="#ff0",
            status_bad="#f00",
            dashboard_bg="#111",
            dashboard_border="#222",
            dashboard_label="#aaa",
            dashboard_value="#fff",
            dashboard_dim="#666",
        )
        assert theme.name == "test"
        assert theme.bg == "#000"
