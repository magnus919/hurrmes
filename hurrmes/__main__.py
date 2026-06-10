#!/usr/bin/env python3
"""hurrmes — a custom TUI client for the Hermes Agent API Server.

Usage:
    hurrmes                  Start the TUI
    hurrmes --config         Print config path
    hurrmes --help           This help
"""

from __future__ import annotations

import sys


def main() -> None:
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return
    if "--config" in sys.argv:
        from hurrmes.config import DEFAULT_CONFIG_PATH, HURRMES_HOME

        from_path = DEFAULT_CONFIG_PATH
        print(f"HURRMES_HOME: {HURRMES_HOME}")
        print(f"Config: {from_path}")
        return

    from hurrmes.cli import main as tui_main

    tui_main()


if __name__ == "__main__":
    main()
