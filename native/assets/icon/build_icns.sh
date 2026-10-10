#!/bin/zsh
# Rigenera assets/AppIcon.icns da assets/icon/MacLuaLogo.png.
set -euo pipefail
cd "$(dirname "$0")"
SRC="${1:-MacLuaLogo.png}"
swift make_icon.swift "$SRC" icon_1024.png
SET=$(mktemp -d)/AppIcon.iconset
mkdir -p "$SET"
for s in 16 32 128 256 512; do
  sips -z $s $s icon_1024.png --out "$SET/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2))
  sips -z $d $d icon_1024.png --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o ../AppIcon.icns
echo "ok ../AppIcon.icns"
