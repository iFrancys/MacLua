#!/bin/bash
# ==============================================================================
# MacLua - Automated Plug & Play Installer for macOS
# ==============================================================================
# Sets up dependencies, Steam CEF integration, LaunchAgent daemon, and CLI tool.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACLUA_BIN="$SCRIPT_DIR/maclua.py"

# Colors for terminal output
BOLD="\033[1m"
GREEN="\033[32m"
BLUE="\033[34m"
YELLOW="\033[33m"
RED="\033[31m"
CYAN="\033[36m"
RESET="\033[0m"

log_info() {
    echo -e "${BLUE}${BOLD}[MacLua]${RESET} $1"
}

log_success() {
    echo -e "${GREEN}${BOLD}[MacLua] ✓${RESET} $1"
}

log_warn() {
    echo -e "${YELLOW}${BOLD}[MacLua] ⚠${RESET} $1"
}

log_error() {
    echo -e "${RED}${BOLD}[MacLua] ✗${RESET} $1" >&2
}

echo -e "${CYAN}${BOLD}"
echo "  __  __            _               "
echo " |  \/  |          | |              "
echo " | \  / | __ _  ___| |    _   _  __ "
echo " | |\/| |/ _\` |/ __| |   | | | |/ _\`|"
echo " | |  | | (_| | (__| |___| |_| | (_| |"
echo " |_|  |_|\__,_|\___|______\__,_|\__,_|"
echo -e "${RESET}"
echo -e "${BOLD}Native Steam Integration & Game Manager for macOS${RESET}\n"

# 1. Verify macOS
OS_NAME="$(uname -s)"
if [ "$OS_NAME" != "Darwin" ]; then
    log_error "MacLua is designed exclusively for macOS. Detected: $OS_NAME"
    exit 1
fi
ARCH="$(uname -m)"
log_success "Operating System: macOS ($ARCH)"

# 2. Check Python 3
log_info "Checking Python 3 environment..."
if ! command -v python3 &>/dev/null; then
    log_error "Python 3 is required but not found."
    echo "Install it via Xcode Command Line Tools ('xcode-select --install') or Homebrew ('brew install python3')."
    exit 1
fi

PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="$(python3 -c 'import sys; print(sys.version_info.major)')"
PY_MINOR="$(python3 -c 'import sys; print(sys.version_info.minor)')"

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]); then
    log_error "Python 3.9 or higher is required. Found Python $PY_VER"
    exit 1
fi
log_success "Found Python $PY_VER ($(which python3))"

# 3. Install Python Dependencies
log_info "Installing Python dependencies (pycryptodome, zstandard)..."
PIP_ARGS=()
if python3 -m pip install --help 2>&1 | grep -q -- "--break-system-packages"; then
    PIP_ARGS+=("--break-system-packages")
fi

if python3 -m pip install -r "$SCRIPT_DIR/requirements.txt" "${PIP_ARGS[@]}" &>/dev/null; then
    log_success "Python dependencies verified."
else
    log_warn "Standard pip install failed. Retrying with --user..."
    python3 -m pip install --user -r "$SCRIPT_DIR/requirements.txt" "${PIP_ARGS[@]}"
    log_success "Python dependencies installed in user site-packages."
fi

# 4. Check Steam Installation
log_info "Checking Steam installation..."
STEAM_APP="/Applications/Steam.app"
STEAM_USER_DIR="$HOME/Library/Application Support/Steam"

if [ ! -d "$STEAM_APP" ] && [ ! -d "$STEAM_USER_DIR" ]; then
    log_warn "Steam installation was not found in default locations (/Applications/Steam.app)."
    log_warn "Please ensure Steam for macOS is installed before using in-client features."
else
    log_success "Steam for macOS detected."
fi

# 5. Make maclua.py executable
chmod +x "$MACLUA_BIN"

# 6. Enable Steam Integration (CEF Debugging Marker & LaunchAgent Daemon)
log_info "Configuring Steam integration & LaunchAgent daemon..."
python3 "$MACLUA_BIN" steam-hook enable
python3 "$MACLUA_BIN" ensure
log_success "Steam hook enabled and LaunchAgent active."

# 7. Setup CLI Global Symlink
log_info "Setting up 'maclua' terminal command..."
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
SYMLINK_PATH="$BIN_DIR/maclua"

cat << EOF > "$SYMLINK_PATH"
#!/bin/bash
exec python3 "$MACLUA_BIN" "\$@"
EOF
chmod +x "$SYMLINK_PATH"
log_success "Created CLI launcher at: $SYMLINK_PATH"

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    SHELL_RC=""
    if [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    elif [ -f "$HOME/.bash_profile" ]; then
        SHELL_RC="$HOME/.bash_profile"
    elif [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
    fi

    if [ -n "$SHELL_RC" ] && ! grep -q 'HOME/.local/bin' "$SHELL_RC"; then
        echo -e '\n# MacLua CLI\nexport PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        log_success "Added ~/.local/bin to PATH in $(basename "$SHELL_RC")"
    fi
fi

# Also create symlink in /usr/local/bin if writable without sudo
if [ -w "/usr/local/bin" ]; then
    ln -sf "$SYMLINK_PATH" "/usr/local/bin/maclua" 2>/dev/null || true
fi

# 8. Complete Verification
echo ""
log_info "Running system doctor check..."
python3 "$MACLUA_BIN" doctor

echo ""
echo -e "${GREEN}${BOLD}==============================================================================${RESET}"
echo -e "${GREEN}${BOLD}                🎉 MacLua Successfully Installed! (Plug & Play)                ${RESET}"
echo -e "${GREEN}${BOLD}==============================================================================${RESET}"
echo ""
echo -e "You can now control MacLua directly from ${CYAN}${BOLD}Steam${RESET} or via terminal with ${CYAN}${BOLD}maclua${RESET}."
echo ""
echo -e "${BOLD}Quick Next Steps:${RESET}"
echo -e "  1. ${CYAN}Restart Steam${RESET} with remote debugging enabled:"
echo -e "     ${BOLD}maclua steam-hook restart${RESET}  (or use 'python3 maclua.py steam-hook restart')"
echo -e "  2. Open Steam and browse to any game in the ${CYAN}Store${RESET}."
echo -e "     Look for the square ${CYAN}MacLua Logo${RESET} right next to the Cart icon!"
echo -e "  3. Use the CLI anytime:"
echo -e "     ${BOLD}maclua search <game>${RESET}    # Search games"
echo -e "     ${BOLD}maclua status${RESET}            # Check managed games & license status"
echo -e "     ${BOLD}maclua update <appid>${RESET}    # In-place delta update without data loss"
echo ""

# Interactive prompt to restart Steam now
read -r -p "Would you like to restart Steam now to activate in-client UI? [Y/n] " response || response="y"
response="${response:-y}"
if [[ "$response" =~ ^[Yy]$ ]]; then
    log_info "Restarting Steam with CEF remote debugging enabled..."
    python3 "$MACLUA_BIN" steam-hook restart
    log_success "Steam restarted. Enjoy MacLua!"
else
    log_info "Steam was not restarted. Remember to restart it via 'maclua steam-hook restart' or when you next open Steam."
fi
