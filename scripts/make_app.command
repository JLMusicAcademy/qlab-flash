#!/usr/bin/env bash
# Build "QLab Flash.app" — a double-clickable macOS app with a custom icon that
# you can drag to the Dock or Applications folder.
#
# Just double-click this file in Finder, or run:  ./scripts/make_app.command
#
# The app is a thin launcher: it runs this repo's code, so keep the repo where
# it is (don't delete it after building). Re-run this script after a git pull if
# you ever want to rebuild.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$REPO/QLab Flash.app"
ICON_PNG="$REPO/assets/icon.png"

echo "Building QLab Flash.app from: $REPO"

# 1) Make sure the Python environment is installed so first launch is instant.
echo "Preparing Python environment (one-time)…"
"$REPO/run.sh" --setup

# 2) Build the .icns icon from the PNG (needs macOS' sips + iconutil).
echo "Building app icon…"
ICONSET="$(mktemp -d)/AppIcon.iconset"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  sips -z $size $size       "$ICON_PNG" --out "$ICONSET/icon_${size}x${size}.png"   >/dev/null
  sips -z $((size*2)) $((size*2)) "$ICON_PNG" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
ICNS="$(mktemp -d)/AppIcon.icns"
iconutil -c icns "$ICONSET" -o "$ICNS"

# 3) Assemble the .app bundle.
echo "Assembling app bundle…"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$ICNS" "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>            <string>QLab Flash</string>
  <key>CFBundleDisplayName</key>     <string>QLab Flash</string>
  <key>CFBundleIdentifier</key>      <string>com.jlmusicacademy.qlabflash</string>
  <key>CFBundleVersion</key>         <string>1.0.0</string>
  <key>CFBundleShortVersionString</key> <string>1.0.0</string>
  <key>CFBundlePackageType</key>     <string>APPL</string>
  <key>CFBundleExecutable</key>      <string>QLab Flash</string>
  <key>CFBundleIconFile</key>        <string>AppIcon</string>
  <key>NSHighResolutionCapable</key> <true/>
  <key>LSMinimumSystemVersion</key>  <string>10.15</string>
</dict>
</plist>
PLIST

# Launcher: open Terminal for the first-ever setup, otherwise launch silently.
cat > "$APP/Contents/MacOS/QLab Flash" <<LAUNCH
#!/bin/bash
REPO="$REPO"
if [ ! -x "\$REPO/.venv/bin/python" ]; then
  open -a Terminal "\$REPO/run.sh"
else
  exec "\$REPO/.venv/bin/python" "\$REPO/main.py"
fi
LAUNCH
chmod +x "$APP/Contents/MacOS/QLab Flash"

# Refresh Finder/LaunchServices so the icon shows immediately.
touch "$APP"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" 2>/dev/null || true

echo
echo "✅ Done!  Created: $APP"
echo
echo "Next steps:"
echo "  • Double-click 'QLab Flash.app' to launch it."
echo "  • Drag it onto your Dock to keep it there."
echo "  • Or drag it into your Applications folder."
echo
open -R "$APP"   # reveal it in Finder
