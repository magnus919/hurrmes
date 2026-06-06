"""Theme definitions for hurrmes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Theme:
    """Color theme for the TUI."""

    name: str

    bg: str
    fg: str
    muted: str
    accent: str
    border: str
    status_good: str
    status_warn: str
    status_bad: str

    # Dashboard-specific
    dashboard_bg: str
    dashboard_border: str
    dashboard_label: str
    dashboard_value: str
    dashboard_dim: str

    def ansi(self, color: str) -> str:
        """Return ANSI 256-color code for terminal usage."""
        table = {
            "#1a170f": "233",
            "#d29d00": "178",
            "#eceae5": "255",
            "#8b7355": "101",
            "#6b5b3e": "95",
            "#4a3f2e": "237",
            "#3a3022": "236",
            "#7bc96f": "77",
            "#dd4a3a": "160",
            "#c7a96b": "179",
            "#C0C0C0": "250",
            "#FFD700": "220",
            "#8FBC8F": "108",
            "#FF8C00": "208",
            "#FF6B6B": "203",
            "#151C2F": "234",
            "#C9D1D9": "252",
            "#7EB8F6": "110",
            "#4B5563": "240",
            "#63D0A6": "79",
            "#E6A855": "173",
            "#F7A072": "209",
            "#FF7A7A": "204",
            "#777777": "244",
            "#1F1F1F": "235",
            "#333333": "236",
            "#555555": "240",
        }
        return table.get(color.lower(), "7")


# ── Built-in themes ──────────────────────────────────────────────

AMBER = Theme(
    name="amber",
    bg="#1a170f",
    fg="#eceae5",
    muted="#8b7355",
    accent="#d29d00",
    border="#6b5b3e",
    status_good="#7bc96f",
    status_warn="#c7a96b",
    status_bad="#dd4a3a",
    dashboard_bg="#1a170f",
    dashboard_border="#4a3f2e",
    dashboard_label="#8b7355",
    dashboard_value="#d29d00",
    dashboard_dim="#6b5b3e",
)

DARK = Theme(
    name="dark",
    bg="#1F1F1F",
    fg="#C9D1D9",
    muted="#777777",
    accent="#7EB8F6",
    border="#333333",
    status_good="#63D0A6",
    status_warn="#E6A855",
    status_bad="#F7A072",
    dashboard_bg="#1F1F1F",
    dashboard_border="#333333",
    dashboard_label="#777777",
    dashboard_value="#C9D1D9",
    dashboard_dim="#555555",
)

THEMES = {
    "amber": AMBER,
    "dark": DARK,
}


def get_theme(name: str = "amber") -> Theme:
    return THEMES.get(name, AMBER)
