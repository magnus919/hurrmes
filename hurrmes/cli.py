"""hurrmes — main TUI application.

A custom CLI client for the Hermes Agent API Server with
a persistent right-side dashboard on wide terminals.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import time
from datetime import datetime
from typing import Any

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    Dimension,
    FloatContainer,
    FormattedTextControl,
    HSplit,
    Layout,
    VSplit,
    Window,
)
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.styles import Style
from prompt_toolkit.utils import get_cwidth

from hurrmes.client import HermesClient
from hurrmes.config import ensure_config
from hurrmes.dashboard import (
    DashboardData,
    collect_system_info,
    format_cost,
    format_cwd,
    format_tokens,
    get_git_branch,
)
from hurrmes.theme import get_theme


class HurrmesApp:
    """The hurrmes TUI application."""

    def __init__(self) -> None:
        self.config = ensure_config()
        self.theme = get_theme(self.config.display.theme)
        self.client = HermesClient(self.config)

        # Session state
        self.messages: list[dict[str, Any]] = []
        self.dashboard = DashboardData()
        self._is_streaming = False
        self._accumulated = ""
        self._last_tick = 0.0

        # Conversation history buffer
        self.conversation_lines: list[str] = []
        self._rendered_history: list[str] = []

        # Build the UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Construct the prompt_toolkit UI layout."""

        # ── Conversation transcript ───────────────────────────
        self.transcript_control = FormattedTextControl(
            text=self._get_transcript_fragments,
            show_cursor=False,
        )
        transcript_window = Window(
            content=self.transcript_control,
            wrap_lines=True,
            always_hide_cursor=True,
        )

        # ── Input buffer ──────────────────────────────────────
        self.input_buffer = Buffer(
            multiline=False,
            on_text_changed=self._on_input_changed,
        )
        input_window = Window(
            content=BufferControl(
                buffer=self.input_buffer,
                focusable=True,
            ),
            height=Dimension(min=1, max=3),
            dont_extend_height=False,
        )

        # ── Status bar ────────────────────────────────────────
        self.status_control = FormattedTextControl(
            text=self._get_statusbar_fragments,
            show_cursor=False,
        )
        status_window = Window(
            content=self.status_control,
            height=1,
            style=f"bg:{self.theme.dashboard_border}",
        )

        # ── Dashboard panel ───────────────────────────────────
        self.dash_control = FormattedTextControl(
            text=self._get_dashboard_fragments,
            show_cursor=False,
        )
        dashboard_window = ConditionalContainer(
            content=Window(
                content=self.dash_control,
                width=Dimension.exact(36),
                wrap_lines=True,
                style=f"bg:{self.theme.dashboard_bg}",
            ),
            filter=Condition(self._dashboard_visible),
        )

        # ── Main layout ───────────────────────────────────────
        # Split: transcript fills, dashboard on right when wide
        main_area = VSplit(
            [
                HSplit([transcript_window, input_window]),
                dashboard_window,
            ]
        )

        root = FloatContainer(
            content=HSplit(
                [
                    main_area,
                    status_window,
                ]
            ),
            floats=[],
        )

        # ── Key bindings ──────────────────────────────────────
        kb = KeyBindings()

        @kb.add("c-c")
        def _(event: object) -> None:
            if self._is_streaming:
                self._is_streaming = False
            else:
                event.app.exit()  # type: ignore[attr-defined]

        @kb.add("c-d")
        def _(event: object) -> None:
            event.app.exit()  # type: ignore[attr-defined]

        @kb.add("c-l")
        def _(_event: object) -> None:
            self.conversation_lines.clear()
            self._invalidate()

        @kb.add("enter")
        async def _(_event: object) -> None:
            text = self.input_buffer.text.strip()
            if text:
                self.input_buffer.text = ""
                await self._submit_message(text)

        # ── Style ─────────────────────────────────────────────
        style = Style.from_dict(
            {
                "status-bar": f"bg:{self.theme.dashboard_border} fg:{self.theme.accent}",
                "status-bar.key": f"bg:{self.theme.dashboard_border} fg:{self.theme.muted}",
                "dashboard-label": f"fg:{self.theme.dashboard_label}",
                "dashboard-value": f"fg:{self.theme.dashboard_value}",
                "dashboard-dim": f"fg:{self.theme.dashboard_dim}",
                "dashboard-section": f"fg:{self.theme.accent} bold",
            }
        )

        self.app: Application[Any] = Application(
            layout=Layout(root, focused_element=self.input_buffer),
            key_bindings=kb,
            style=style,
            full_screen=True,
            mouse_support=True,
        )

    # ── Layout helpers ─────────────────────────────────────────

    def _dashboard_visible(self) -> bool:
        """Whether the dashboard panel should be shown."""
        if not self.config.display.dashboard:
            return False
        cols = self.app.output.get_size().columns if self.app.output else 80
        return cols >= self.config.display.dashboard_min_width

    def _on_input_changed(self, buf: Buffer) -> None:
        """Callback when input text changes."""
        pass

    def _invalidate(self) -> None:
        """Request a UI redraw."""
        self.app.invalidate()

    # ── Message handling ──────────────────────────────────────

    async def _submit_message(self, text: str) -> None:
        """Send a user message and stream the response."""
        self.messages.append({"role": "user", "content": text})
        self.conversation_lines.append(f">>> {text}")

        self._is_streaming = True
        self._accumulated = ""
        self._invalidate()

        try:
            async for event in self.client.chat_stream(self.messages):
                if event["type"] == "delta":
                    self._accumulated += event["content"]
                    # Update dashboard periodically
                    self._tick_dashboard()
                    self._invalidate()
                elif event["type"] == "done":
                    if self._accumulated:
                        self.messages.append({"role": "assistant", "content": self._accumulated})
                        self.conversation_lines.append(self._accumulated)
                        self._accumulated = ""

                    # Update token wallet from usage
                    usage = event.get("usage", {})
                    if usage:
                        self.dashboard.prompt_tokens = usage.get("prompt_tokens", 0)
                        self.dashboard.completion_tokens = usage.get("completion_tokens", 0)
                        self.dashboard.total_tokens = usage.get("total_tokens", 0)
                        self.dashboard.api_calls += 1
                    self._is_streaming = False
                    self._invalidate()
                elif event["type"] == "error":
                    self.conversation_lines.append(f"[error] {event['content']}")
                    self._is_streaming = False
                    self._invalidate()
        except Exception as e:
            self.conversation_lines.append(f"[error] {e}")
            self._is_streaming = False
            self._invalidate()

    def _tick_dashboard(self) -> None:
        """Periodically refresh dashboard system info."""
        now = time.monotonic()
        if now - self._last_tick < 2.0:
            return
        self._last_tick = now
        load, dt = collect_system_info()
        self.dashboard.loadavg = load
        self.dashboard.datetime = dt
        cwd = os.getcwd()
        self.dashboard.cwd = format_cwd(cwd)
        self.dashboard.git_branch = get_git_branch(cwd)

    # ── Text fragment generators ──────────────────────────────

    def _get_transcript_width(self) -> int:
        """Available width for transcript content."""
        cols = self.app.output.get_size().columns if self.app.output else 80
        if self._dashboard_visible():
            cols -= 38  # dashboard width + border + padding
        return max(cols - 2, 40)

    def _get_transcript_fragments(self) -> list[tuple[str, str]]:
        """Generate formatted text for the conversation transcript."""
        width = self._get_transcript_width()
        fragments = []
        fragments.append(("class:status-bar", "  hurrmes — Hermes TUI Client\n"))
        fragments.append(("", "\n"))

        for line in self.conversation_lines:
            if line.startswith(">>> "):
                fragments.append(("bold fg:#d29d00", line[:width]))
                fragments.append(("", "\n"))
            elif line.startswith("[error]"):
                fragments.append(("bold fg:#dd4a3a", line[:width]))
                fragments.append(("", "\n"))
            else:
                fragments.append(("", line[:width]))
                fragments.append(("", "\n"))

        if self._accumulated:
            fragments.append(("fg:#eceae5", self._accumulated[: width * 3]))

        return fragments

    def _get_statusbar_fragments(self) -> list[tuple[str, str]]:
        """Generate formatted text for the bottom status bar."""
        cols = self.app.output.get_size().columns if self.app.output else 80
        model = self.config.default_model
        model_short = model.split("/")[-1] if "/" in model else model
        msgs = len(self.messages) // 2
        status = "⚡ streaming" if self._is_streaming else "● idle"
        dur = datetime.now().strftime("%H:%M")

        left = f"  {status}  {model_short}  {msgs} exchanges  {dur} "

        if self.config.display.show_cost and self.dashboard.total_tokens > 0:
            cost_str = format_cost(self.dashboard.cost_usd)
            left += f"  {cost_str} "

        right = ""
        if self._dashboard_visible():
            right = " Ctrl+D quit  Ctrl+L clear  "
        else:
            right = " Ctrl+D quit  Ctrl+L clear  /dashboard  "

        # Pad the middle so right aligns
        avail = max(cols - get_cwidth(left) - get_cwidth(right) - 2, 1)
        middle = " " * avail

        return [
            ("class:status-bar", left),
            ("", middle),
            ("class:status-bar", right),
        ]

    def _get_dashboard_fragments(self) -> list[tuple[str, str]]:
        """Generate formatted text for the right-side dashboard panel."""
        dash_w = 34  # inner width
        f: list[tuple[str, str]] = []

        def sep() -> None:
            f.append(("class:dashboard-dim", f"{'─' * dash_w}"))

        def section(title: str) -> None:
            f.append(("class:dashboard-section", f"  {title}"))
            f.append(("", "\n"))

        def label_value(label: str, value: str, value_style: str = "class:dashboard-value") -> None:
            label_t = f"{label}:".ljust(12)
            f.append(("class:dashboard-label", f"  {label_t}"))
            f.append((value_style, value))
            f.append(("", "\n"))

        def sub_text(text: str) -> None:
            f.append(("class:dashboard-dim", f"  {text}"))
            f.append(("", "\n"))

        # ── Header ──
        f.append(("class:dashboard-section", f"  ─── Dashboard {'─' * (dash_w - 14)}"))
        f.append(("", "\n"))

        # ── System ──
        section("System")
        load, dt = self.dashboard.loadavg, self.dashboard.datetime
        if not load:
            load, dt = collect_system_info()
            self.dashboard.loadavg = load
            self.dashboard.datetime = dt
        label_value("loadavg", load)
        label_value("time", dt)

        sep()
        f.append(("", "\n"))

        # ── Session ──
        section("Session")
        cwd = self.dashboard.cwd or format_cwd(os.getcwd())
        branch = self.dashboard.git_branch or get_git_branch()
        self.dashboard.cwd = cwd
        self.dashboard.git_branch = branch
        label_value("cwd", cwd[: dash_w - 16])
        if branch:
            label_value("branch", branch)

        sep()
        f.append(("", "\n"))

        # ── Tokens ──
        section("Token Wallet")
        label_value("prompt", format_tokens(self.dashboard.prompt_tokens))
        label_value("output", format_tokens(self.dashboard.completion_tokens))
        label_value("total", format_tokens(self.dashboard.total_tokens))
        label_value("calls", str(self.dashboard.api_calls))
        if self.config.display.show_cost:
            label_value("cost", format_cost(self.dashboard.cost_usd))

        sep()
        f.append(("", "\n"))

        # ── Plan ──
        section("Todo")
        todos = self.dashboard.todos
        if not todos:
            sub_text("no active plan")
        else:
            for t in todos:
                icon = "☐" if t.status == "pending" else "◐" if t.status == "in_progress" else "☑"
                label_value(f"{icon}", t.content[: dash_w - 16])

        sep()
        f.append(("", "\n"))

        # ── Subagents ──
        section("Subagents")
        if self.dashboard.subagent_count:
            label_value(
                "active",
                f"{self.dashboard.subagent_count}  depth: {self.dashboard.subagent_depth}",
            )
        else:
            sub_text("none active")

        # ── Footer ──
        f.append(("class:dashboard-dim", f"  ─{'─' * (dash_w - 2)}─"))

        return f

    # ── Run ────────────────────────────────────────────────────

    async def run(self) -> None:
        """Start the application."""
        # Welcome message
        self.conversation_lines.append("Connected to Hermes API at " + self.config.server.base_url)
        self.conversation_lines.append("Type a message and press Enter to chat.")
        self.conversation_lines.append("")

        # Collect initial dashboard data
        self._tick_dashboard()

        await self.app.run_async()


def main() -> None:
    """Entry point."""
    app: HurrmesApp = HurrmesApp()

    def handle_sigint(_sig: int, _frame: object | None) -> None:
        if app._is_streaming:
            app._is_streaming = False
        else:
            sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(app.run())


if __name__ == "__main__":
    main()
