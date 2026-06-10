"""hurrmes — main TUI application.

A custom CLI client for the Hermes Agent API Server with
a persistent right-side dashboard on wide terminals.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import ANSI, to_formatted_text
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
from rich.console import Console as RichConsole
from rich.markdown import Markdown as RichMarkdown
from rich.syntax import Syntax as RichSyntax

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

# ── Structured transcript entry ────────────────────────────────

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_ERROR = "error"
ROLE_SYSTEM = "system"


@dataclass
class TranscriptEntry:
    """A single entry in the conversation transcript."""

    role: str
    content: str
    rendered: list[tuple[str, str]] | None = None


# ── Spinner characters ─────────────────────────────────────────

_SPINNER_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


# ── Markdown rendering ─────────────────────────────────────────


def _render_rich_markdown(text: str, width: int) -> list[tuple[str, str]]:
    try:
        buf = io.StringIO()
        console = RichConsole(
            width=width,
            force_terminal=True,
            color_system="truecolor",
            file=buf,
            legacy_windows=False,
        )
        console.print(RichMarkdown(text))
        ansi_output = buf.getvalue()
        if ansi_output.strip():
            return cast("list[tuple[str, str]]", to_formatted_text(ANSI(ansi_output)))
    except Exception:
        pass
    return [("", text)]


def _render_rich_code_block(code: str, lang: str, width: int) -> list[tuple[str, str]]:
    try:
        buf = io.StringIO()
        console = RichConsole(
            width=width,
            force_terminal=True,
            color_system="truecolor",
            file=buf,
            legacy_windows=False,
        )
        console.print(RichSyntax(code, lang or "text", background_color="default"))
        ansi_output = buf.getvalue()
        if ansi_output.strip():
            return cast("list[tuple[str, str]]", to_formatted_text(ANSI(ansi_output)))
    except Exception:
        pass
    return [("", code)]


# ── Slash commands ─────────────────────────────────────────────


async def _handle_slash_command(app: HurrmesApp, text: str) -> bool:
    """Handle a slash command. Returns True if the command was handled."""
    parts = text[1:].split()
    if not parts:
        return False
    cmd = parts[0].lower()
    args = parts[1:]

    if cmd == "clear":
        app.transcript.clear()
        app.messages.clear()
        app.dashboard.prompt_tokens = 0
        app.dashboard.completion_tokens = 0
        app.dashboard.total_tokens = 0
        app.dashboard.api_calls = 0
        app.dashboard.cost_usd = 0.0
        app._invalidate()
        return True

    if cmd in ("help", "?"):
        app.transcript.append(
            TranscriptEntry(
                role=ROLE_SYSTEM,
                content=(
                    "Available commands:\n"
                    "  /help, /?   — Show this help\n"
                    "  /clear      — Clear the conversation\n"
                    "  /models     — List available models (requires API)\n"
                    "  /config     — Show current config\n"
                    "  /export     — Export conversation as markdown\n"
                    "  /cost       — Toggle cost display\n"
                    "  /theme      — Switch theme (amber, dark)"
                ),
            )
        )
        app._invalidate()
        return True

    if cmd == "models":
        app.transcript.append(
            TranscriptEntry(
                role=ROLE_SYSTEM,
                content=f"Connected to: {app.config.server.base_url}\nDefault model: {app.config.default_model}",
            )
        )
        app._invalidate()
        return True

    if cmd == "config":
        cfg_lines = [
            f"Server: {app.config.server.base_url}",
            f"API Key: {'***' if app.config.server.api_key else '(not set)'}",
            f"Dashboard: {app.config.display.dashboard}",
            f"Theme: {app.config.display.theme}",
            f"Model: {app.config.default_model}",
        ]
        app.transcript.append(TranscriptEntry(role=ROLE_SYSTEM, content="\n".join(cfg_lines)))
        app._invalidate()
        return True

    if cmd == "export":
        lines = ["# hurrmes — Conversation Export\n"]
        for entry in app.transcript:
            if entry.role == ROLE_USER:
                lines.append(f"## You\n\n{entry.content}\n")
            elif entry.role == ROLE_ASSISTANT:
                lines.append(f"## Hermes\n\n{entry.content}\n")
            elif entry.role == ROLE_ERROR:
                lines.append(f"## Error\n\n{entry.content}\n")
        export_text = "\n".join(lines)
        # Store in a transcript entry for display
        app.transcript.append(
            TranscriptEntry(
                role=ROLE_SYSTEM,
                content=f"Exported {len([e for e in app.transcript if e.role in (ROLE_USER, ROLE_ASSISTANT)])} messages.\n\n```\n{export_text[:1000]}\n```",
            )
        )
        app._invalidate()
        return True

    if cmd == "cost":
        app.config.display.show_cost = not app.config.display.show_cost
        app.transcript.append(
            TranscriptEntry(
                role=ROLE_SYSTEM,
                content=f"Cost display: {'on' if app.config.display.show_cost else 'off'}",
            )
        )
        app._invalidate()
        return True

    if cmd == "theme":
        if args:
            from hurrmes.theme import THEMES

            if args[0] in THEMES:
                app.config.display.theme = args[0]
                app.theme = get_theme(args[0])
                app._rebuild_style()
                app.transcript.append(
                    TranscriptEntry(role=ROLE_SYSTEM, content=f"Theme changed to: {args[0]}")
                )
            else:
                app.transcript.append(
                    TranscriptEntry(
                        role=ROLE_ERROR,
                        content=f"Unknown theme: {args[0]}. Available: {', '.join(THEMES)}",
                    )
                )
        else:
            from hurrmes.theme import THEMES

            app.transcript.append(
                TranscriptEntry(
                    role=ROLE_SYSTEM,
                    content=f"Available themes: {', '.join(THEMES)}\nCurrent: {app.config.display.theme}",
                )
            )
        app._invalidate()
        return True

    return False


# ── Main application class ─────────────────────────────────────


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
        self._spinner_idx = 0

        # Structured transcript
        self.transcript: list[TranscriptEntry] = []

        # Build the UI
        self._build_ui()

    def _rebuild_style(self) -> None:
        """Rebuild the style dict after a theme change."""
        style = Style.from_dict(
            {
                "status-bar": f"bg:{self.theme.dashboard_border} fg:{self.theme.accent}",
                "status-bar.key": f"bg:{self.theme.dashboard_border} fg:{self.theme.muted}",
                "dashboard-label": f"fg:{self.theme.dashboard_label}",
                "dashboard-value": f"fg:{self.theme.dashboard_value}",
                "dashboard-dim": f"fg:{self.theme.dashboard_dim}",
                "dashboard-section": f"fg:{self.theme.accent} bold",
                "transcript-user": f"bold fg:{self.theme.accent}",
                "transcript-assistant": f"fg:{self.theme.fg}",
                "transcript-error": f"bold fg:{self.theme.status_bad}",
                "transcript-system": f"fg:{self.theme.muted} italic",
                "transcript-divider": f"fg:{self.theme.border}",
                "transcript-header": f"fg:{self.theme.accent} bold",
            }
        )
        self.app.style = style

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

        # ── Input buffer (multiline) ──────────────────────────
        self.input_buffer = Buffer(
            multiline=True,
            on_text_changed=self._on_input_changed,
        )
        input_window = Window(
            content=BufferControl(
                buffer=self.input_buffer,
                focusable=True,
            ),
            height=Dimension(min=1, max=8),
            dont_extend_height=False,
            wrap_lines=True,
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
            self.transcript.clear()
            self._invalidate()

        # Enter submits, Alt+Enter inserts newline
        @kb.add("enter")
        async def _(_event: object) -> None:
            text = self.input_buffer.text
            if text.strip():
                self.input_buffer.text = ""
                await self._submit_message(text)

        @kb.add("escape", "enter")
        def _(_event: object) -> None:
            self.input_buffer.insert_text("\n")

        # ── Style ─────────────────────────────────────────────
        base_style = Style.from_dict(
            {
                "status-bar": f"bg:{self.theme.dashboard_border} fg:{self.theme.accent}",
                "status-bar.key": f"bg:{self.theme.dashboard_border} fg:{self.theme.muted}",
                "dashboard-label": f"fg:{self.theme.dashboard_label}",
                "dashboard-value": f"fg:{self.theme.dashboard_value}",
                "dashboard-dim": f"fg:{self.theme.dashboard_dim}",
                "dashboard-section": f"fg:{self.theme.accent} bold",
                "transcript-user": f"bold fg:{self.theme.accent}",
                "transcript-assistant": f"fg:{self.theme.fg}",
                "transcript-error": f"bold fg:{self.theme.status_bad}",
                "transcript-system": f"fg:{self.theme.muted} italic",
                "transcript-divider": f"fg:{self.theme.border}",
                "transcript-header": f"fg:{self.theme.accent} bold",
            }
        )

        self.app: Application[Any] = Application(
            layout=Layout(root, focused_element=self.input_buffer),
            key_bindings=kb,
            style=base_style,
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
        _ = buf  # unused

    def _invalidate(self) -> None:
        """Request a UI redraw."""
        self.app.invalidate()

    # ── Message handling ──────────────────────────────────────

    async def _submit_message(self, text: str) -> None:
        """Send a user message and stream the response."""
        # Handle slash commands
        if text.startswith("/"):
            handled = await _handle_slash_command(self, text)
            if handled:
                return

        # Store user message
        self.messages.append({"role": "user", "content": text})
        self.transcript.append(TranscriptEntry(role=ROLE_USER, content=text))

        self._is_streaming = True
        self._accumulated = ""
        self._spinner_idx = 0
        self._invalidate()

        try:
            async for event in self.client.chat_stream(self.messages):
                if event["type"] == "delta":
                    self._accumulated += event["content"]
                    self._spinner_idx = (self._spinner_idx + 1) % len(_SPINNER_CHARS)
                    self._tick_dashboard()
                    self._invalidate()
                elif event["type"] == "done":
                    if self._accumulated:
                        self.messages.append({"role": "assistant", "content": self._accumulated})
                        entry = TranscriptEntry(role=ROLE_ASSISTANT, content=self._accumulated)
                        self.transcript.append(entry)
                        self._accumulated = ""

                    usage = event.get("usage", {})
                    if usage:
                        self.dashboard.prompt_tokens = usage.get("prompt_tokens", 0)
                        self.dashboard.completion_tokens = usage.get("completion_tokens", 0)
                        self.dashboard.total_tokens = usage.get("total_tokens", 0)
                        self.dashboard.api_calls += 1
                    self._is_streaming = False
                    self._invalidate()
                elif event["type"] == "error":
                    self.transcript.append(
                        TranscriptEntry(role=ROLE_ERROR, content=event["content"])
                    )
                    self._is_streaming = False
                    self._invalidate()
        except Exception as e:
            self.transcript.append(TranscriptEntry(role=ROLE_ERROR, content=str(e)))
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
        fragments: list[tuple[str, str]] = []

        # Header
        fragments.append(("class:transcript-header", "  hurrmes — Hermes TUI Client"))
        fragments.append(("", "\n"))
        fragments.append(("class:transcript-divider", f"  {'─' * (width - 4)}"))
        fragments.append(("", "\n"))

        for entry in self.transcript:
            if entry.role == ROLE_USER:
                fragments.append(("class:transcript-divider", ""))
                fragments.append(("class:transcript-user", "  \u25b6  You"))
                fragments.append(("", "\n"))
                fragments.append(("class:transcript-user", f"  {entry.content[: width - 4]}"))
                fragments.append(("", "\n\n"))

            elif entry.role == ROLE_ASSISTANT:
                fragments.append(("class:transcript-divider", f"  {'─' * (width - 4)}"))
                fragments.append(("", "\n"))
                fragments.append(("class:transcript-assistant", "  \u25b6  Hermes"))
                fragments.append(("", "\n"))
                # Render markdown
                rendered = _render_rich_markdown(entry.content, width - 4)
                for style_str, text in rendered:
                    fragments.append((style_str, text))
                fragments.append(("", "\n\n"))

            elif entry.role == ROLE_ERROR:
                fragments.append(
                    ("class:transcript-error", f"  \u2716  {entry.content[: width - 4]}")
                )
                fragments.append(("", "\n"))

            elif entry.role == ROLE_SYSTEM:
                fragments.append(("class:transcript-system", f"  {entry.content[: width - 4]}"))
                fragments.append(("", "\n"))

        # Streaming content with spinner
        if self._accumulated:
            spinner = _SPINNER_CHARS[self._spinner_idx % len(_SPINNER_CHARS)]
            fragments.append(("class:transcript-divider", f"  {'─' * (width - 4)}"))
            fragments.append(("", "\n"))
            fragments.append(("class:transcript-assistant", f"  {spinner}  Hermes"))
            fragments.append(("", "\n"))
            fragments.append(("", f"  {self._accumulated}"))
            fragments.append(("", "\n"))

        return fragments

    def _get_statusbar_fragments(self) -> list[tuple[str, str]]:
        """Generate formatted text for the bottom status bar."""
        cols = self.app.output.get_size().columns if self.app.output else 80
        model = self.config.default_model
        model_short = model.split("/")[-1] if "/" in model else model
        msgs = sum(1 for e in self.transcript if e.role in (ROLE_USER, ROLE_ASSISTANT)) // 2
        dur = datetime.now().strftime("%H:%M")

        if self._is_streaming:
            spinner = _SPINNER_CHARS[self._spinner_idx % len(_SPINNER_CHARS)]
            status = f"{spinner} streaming"
        else:
            status = "\u25cf idle"

        left = f"  {status}  {model_short}  {msgs} exchanges  {dur} "

        if self.config.display.show_cost and self.dashboard.total_tokens > 0:
            cost_str = format_cost(self.dashboard.cost_usd)
            left += f"  {cost_str} "

        right = "  /help  "
        if not self._dashboard_visible():
            right = "  /help  /dashboard  "

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
        self.transcript.append(
            TranscriptEntry(
                role=ROLE_SYSTEM,
                content=(
                    f"Connected to {self.config.server.base_url}\n"
                    f"Model: {self.config.default_model}\n"
                    "Type a message and press Enter to chat.\n"
                    "  /help         — Show available commands\n"
                    "  Enter         — Send message\n"
                    "  Alt+Enter     — New line\n"
                    "  Ctrl+D        — Quit\n"
                    "  Ctrl+L        — Clear screen"
                ),
            )
        )

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
