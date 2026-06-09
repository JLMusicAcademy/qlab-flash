#!/usr/bin/env bash
# Use your own image as the QLab Flash app icon.
#
# Usage (in Terminal, from the repo):
#   ./scripts/set_icon.command /path/to/your-logo.png
#
# Tip: type "./scripts/set_icon.command " then DRAG your image file onto the
# Terminal window to fill in the path, then press Return.
#
# It writes assets/icon.png (square, 1024x1024). After running it, rebuild the
# app with ./scripts/make_app.command so the new icon takes effect.

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO/assets/icon.png"

SRC="${1:-}"
if [ -z "$SRC" ] || [ ! -f "$SRC" ]; then
  echo "Usage: $0 /path/to/your-image.(png|jpg|jpeg|heic)"
  echo "Tip: drag the image onto the Terminal window to fill in the path."
  exit 1
fi

# Convert to PNG.
sips -s format png "$SRC" --out "$OUT" >/dev/null

# Pad to a square (so it isn't distorted), then size to 1024x1024.
W=$(sips -g pixelWidth  "$OUT" | awk '/pixelWidth/{print $2}')
H=$(sips -g pixelHeight "$OUT" | awk '/pixelHeight/{print $2}')
M=$(( W > H ? W : H ))
# Pad with white to match a logo on a white background; change FFFFFF if your
# art has a different background colour.
sips --padToHeightWidth "$M" "$M" --padColor FFFFFF "$OUT" --out "$OUT" >/dev/null
sips -z 1024 1024 "$OUT" --out "$OUT" >/dev/null

echo "✅ Saved $OUT (1024x1024)."
echo "Now rebuild the app:  ./scripts/make_app.command"
