#!/usr/bin/env bash
# Launch QLab Flash on macOS.
#
# First run creates a local virtual environment and installs PySide6.
# Subsequent runs reuse it and start instantly.
#
#   ./run.sh           # connect to a real QLab on your network
#   ./run.sh --demo    # explore the UI with a simulated QLab (no QLab needed)

set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "Setting up QLab Flash (one-time)…"
  "$PYTHON" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
  "$VENV_DIR/bin/pip" install -r requirements.txt
fi

exec "$VENV_DIR/bin/python" main.py "$@"
