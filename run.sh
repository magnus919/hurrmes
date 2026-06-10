#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VENV=.venv

# Create venv if it doesn't exist
if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV"
fi

# Install if not already installed (checks for a sentinel)
if [ ! -f "$VENV/.installed" ]; then
    echo "Installing hurrmes..."
    "$VENV/bin/pip" install -e . > /dev/null
    touch "$VENV/.installed"
fi

exec "$VENV/bin/hurrmes" "$@"
