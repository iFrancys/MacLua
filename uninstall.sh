#!/bin/bash
# ==============================================================================
# MacLua - Clean Uninstaller for macOS
# ==============================================================================
# Completely disables Steam CEF hook, unloads LaunchAgent, removes symlinks,
# and restores Steam to 100% vanilla state.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACLUA_BIN="$SCRIPT_DIR/maclua.py"

BOLD="\033[1m"
GREEN="\033[32m"
BLUE="\033[34m"
YELLOW="\033[33m"
RESET="\033[0m"

echo -e "${YELLOW}${BOLD}[MacLua] Uninstalling MacLua...${RESET}"

# 1. Disable Steam Hook and remove LaunchAgent
if [ -f "$MACLUA_BIN" ]; then
    python3 "$MACLUA_BIN" steam-hook disable || true
fi

# 2. Remove LaunchAgent plist if still present
PLIST="$HOME/Library/LaunchAgents/dev.maclua.bridge.plist"
if [ -f "$PLIST" ]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
fi

# 3. Remove CLI symlink
rm -f "$HOME/.local/bin/maclua"
if [ -w "/usr/local/bin" ]; then
    rm -f "/usr/local/bin/maclua" 2>/dev/null || true
fi

echo -e "${GREEN}${BOLD}[MacLua] ✓ MacLua successfully uninstalled.${RESET}"
echo "Steam has been restored to vanilla state."
