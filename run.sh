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

# On Apple Silicon, build a NATIVE (arm64) environment. Otherwise an Intel
# Python (e.g. an x86_64 Homebrew in /usr/local) runs under Rosetta and macOS
# warns that "Intel-based" components will stop working in a future release.
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
  is_arm64_py() {
    command -v "$1" >/dev/null 2>&1 && \
      "$1" -c 'import platform,sys; sys.exit(0 if platform.machine()=="arm64" else 1)' >/dev/null 2>&1
  }
  if ! is_arm64_py "$PYTHON"; then
    for cand in /opt/homebrew/bin/python3 /usr/bin/python3; do
      if is_arm64_py "$cand"; then
        echo "Using native Apple Silicon Python: $cand"
        PYTHON="$cand"
        break
      fi
    done
  fi
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "Setting up QLab Flash (one-time)…"
  "$PYTHON" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
  "$VENV_DIR/bin/pip" install -r requirements.txt
fi

# `--setup` just prepares the environment (used by the .app installer) and exits.
if [ "${1:-}" = "--setup" ]; then
  echo "QLab Flash is ready."
  exit 0
fi

exec "$VENV_DIR/bin/python" main.py "$@"
