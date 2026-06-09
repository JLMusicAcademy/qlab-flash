#!/usr/bin/env bash
# QLab Flash installer / updater.
#
# Downloads the latest QLab Flash, builds a native (Apple Silicon) app with its
# icon, and puts "QLab Flash.app" in your Applications folder. Run it again any
# time to update. No git, no GitHub login, no Python setup required.
#
# Usage (paste into Terminal):
#   T="$(mktemp -d)" && curl -fsSL \
#     https://github.com/JLMusicAcademy/qlab-flash/archive/refs/heads/claude/youthful-darwin-10q5dl.tar.gz \
#     | tar xz -C "$T" && bash "$T"/*/scripts/install.sh

set -euo pipefail

TARBALL="https://github.com/JLMusicAcademy/qlab-flash/archive/refs/heads/claude/youthful-darwin-10q5dl.tar.gz"
INSTALL_DIR="${QLABFLASH_DIR:-$HOME/qlab-flash}"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This installer is for macOS." >&2
  exit 1
fi

echo "==> Installing QLab Flash to: $INSTALL_DIR"

# Find the source: either the repo this script was unpacked into, or download.
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd || true)"
if [ -n "$SELF_DIR" ] && [ -f "$SELF_DIR/main.py" ]; then
  SRC="$SELF_DIR"
else
  echo "==> Downloading latest QLab Flash…"
  TMP="$(mktemp -d)"
  curl -fsSL "$TARBALL" | tar xz -C "$TMP"
  SRC="$(echo "$TMP"/*/)"
fi

# Copy the code into place, leaving any existing virtualenv and git data alone.
mkdir -p "$INSTALL_DIR"
if [ "$SRC" -ef "$INSTALL_DIR" ]; then
  echo "==> Using existing files in place."
else
  echo "==> Updating files…"
  rsync -a --exclude ".venv" --exclude ".git" "$SRC"/ "$INSTALL_DIR"/
fi

cd "$INSTALL_DIR"
chmod +x run.sh scripts/*.command scripts/*.sh 2>/dev/null || true

# Build the app (this also creates the native Python environment).
echo "==> Building the app…"
./scripts/make_app.command

# Try to drop it into /Applications for convenience.
APP="$INSTALL_DIR/QLab Flash.app"
if [ -d "$APP" ]; then
  if cp -R "$APP" "/Applications/" 2>/dev/null; then
    echo "==> Installed to /Applications/QLab Flash.app"
    open "/Applications/QLab Flash.app" 2>/dev/null || true
  else
    echo "==> App built at: $APP"
    echo "    (Drag it into Applications, then to your Dock.)"
  fi
fi

echo
echo "✅ Done. Launch 'QLab Flash' from Applications or Spotlight."
