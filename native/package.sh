#!/bin/zsh
# Impacchetta MacLua.app universale (Apple Silicon arm64 + Intel x86_64).
# Esegue verifiche, build release universale, firma e installazione pulita.
set -euo pipefail
cd "$(dirname "$0")"

echo "== verifiche interne =="
MACLUA_CHECK=1 swift run -c release MacApp | tail -n 3

echo "== build release universale (arm64 + x86_64) =="
echo "-> Compilazione per Apple Silicon (arm64)..."
swift build -c release --triple arm64-apple-macosx14.0
cp .build/release/MacApp /tmp/MacApp_arm64

echo "-> Compilazione per chip Intel (x86_64)..."
swift build -c release --triple x86_64-apple-macosx14.0
cp .build/release/MacApp /tmp/MacApp_x86_64

APP="$PWD/MacLua.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$APP/Contents/Resources/backend"

echo "-> Unione in binario Mach-O universale con lipo..."
lipo -create /tmp/MacApp_arm64 /tmp/MacApp_x86_64 -output "$APP/Contents/MacOS/MacLua"
rm -f /tmp/MacApp_arm64 /tmp/MacApp_x86_64

cp assets/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"

# Backend Python: unica fonte di verità, impacchettato insieme all'app.
cp ../maclua.py "$APP/Contents/Resources/backend/maclua.py"
cp -R ../core "$APP/Contents/Resources/backend/core"
find "$APP/Contents/Resources/backend" -name '__pycache__' -type d -prune -exec rm -rf {} +

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>MacLua</string>
  <key>CFBundleDisplayName</key><string>MacLua</string>
  <key>CFBundleIdentifier</key><string>dev.maclua.app</string>
  <key>CFBundleVersion</key><string>0.1.0</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>MacLua</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSMultipleInstancesProhibited</key><true/>
</dict>
</plist>
PLIST

codesign --force --deep --sign - "$APP" >/dev/null

echo "== installazione pulita =="
ROOT_APP="$PWD/../MacLua.app"
rm -rf "$ROOT_APP"
cp -R "$APP" "$ROOT_APP"

if [ -w "/Applications" ]; then
    rm -rf /Applications/MacLua.app
    cp -R "$APP" /Applications/MacLua.app 2>/dev/null || true
fi

# Rimuovi il bundle duplicato in native/ per evitare doppie voci in Spotlight
rm -rf "$APP"

echo "OK: $ROOT_APP (Universal arm64 + x86_64)"
