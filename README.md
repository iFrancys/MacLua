# MacLua — Native Steam Integration & Game Manager for macOS

[![Platform](https://img.shields.io/badge/Platform-macOS-black?logo=apple)](https://apple.com)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Steam Client](https://img.shields.io/badge/Steam-CEF%20Remote%20Debugging-1b2838?logo=steam)](https://store.steampowered.com/)

**MacLua** is a lightweight, zero-binary-patch game management utility and in-client Steam enhancement designed exclusively for macOS.

It seamlessly integrates with Steam for Mac via local Chromium Embedded Framework (CEF) remote debugging, offline package forging, and direct CDN chunk fetching. MacLua enables users to manage games, offline licenses (`packageinfo.vdf`), depot manifests, and in-place delta updates without touching or modifying the original Steam binary.

---

## 🌟 Key Features

- **🎮 Seamless In-Steam Store & Library Integration**:
  - Injects a native-feeling UI button directly into the official Steam Store header (right beside the Cart button).
  - Inspect depot lists, install states, and trigger in-place updates without ever leaving Steam.
  - Multi-language support (English, Italian, German, Spanish, French).
  - Automatically manages Steam Library entries for managed games.

- **⚡ Plug & Play 1-Step Installation**:
  - Automated `install.sh` handles Python dependencies, LaunchAgent configuration, Steam CEF debugging hooks, and installs a global `maclua` terminal command.

- **🔄 In-Place Delta Updates (No Data Loss)**:
  - Updates games without requiring full redownloads or uninstallation.
  - Compares existing file chunks using Adler32 verification and downloads only modified delta chunks from the Steam CDN, preserving user save data and configuration.

- **🔐 Non-Destructive Offline Licensing**:
  - Dynamically packages app and depot IDs into local `packageinfo.vdf` using binary KeyValues structures with proper terminator padding and SHA-1 re-hashing.
  - Self-healing `ensure` engine keeps licenses intact across Steam client updates.

- **📦 Anonymous Steam CDN Chunk Fetcher**:
  - Downloads encrypted content chunks directly from official Steam CDN endpoints.
  - High-performance AES-256 decryption, multi-format decompression (`VZa`, `VSZa`, `ZIP`), and parallel chunk assembly.

- **🛡️ 100% Safe & Reversible**:
  - Zero modifications to `/Applications/Steam.app` binaries.
  - Easily revert to a 100% stock Steam configuration at any time using `./uninstall.sh`.

---

## 📋 Requirements

- **Operating System**: macOS 11.0 (Big Sur) or newer (Apple Silicon & Intel supported).
- **Python**: Python 3.9 or higher (standard library + `pycryptodome` and `zstandard`).
- **Steam**: Official Steam for macOS installed (`/Applications/Steam.app`).

---

## 🚀 Quick Start (Plug & Play)

### 1. Installation

Clone the repository and run the automated installer:

```bash
git clone https://github.com/iFrancys/MacLua.git
cd MacLua
./install.sh
```

The installer will:
1. Verify macOS and Python 3.9+ environment.
2. Install required Python packages (`pycryptodome`, `zstandard`).
3. Enable Steam CEF debugging mode.
4. Deploy the background bridge daemon (`~/Library/LaunchAgents/dev.maclua.bridge.plist`).
5. Create a global `maclua` CLI command in `~/.local/bin/maclua`.
6. Offer to restart Steam automatically.

### 2. Configure Manifest Source (Optional)

If using a remote manifest repository, configure your access key:

```bash
maclua config set-key
```

*(Keys are stored securely with `0600` permissions in `~/Library/Application Support/MacLua/config.json`).*

---

## 🖥️ In-Steam User Interface

Once installed and Steam is launched:
1. Open any game page in the **Steam Store** (e.g. Stray, Geometry Dash).
2. Look at the top right of the store page, adjacent to the Cart button: you will see the square **MacLua Logo**.
3. Click the icon to open the MacLua in-Steam drawer:
   - View game depots, depot keys, and staged manifests.
   - Click **Install** to register the game with Steam.
   - Click **Update** to perform in-place chunk updates.
   - Click **Repair Library** if games ever need license re-application.

---

## ⌨️ CLI Command Reference

MacLua provides a clean, fully-featured command-line interface:

| Command | Description |
|---|---|
| `maclua search <query>` | Search the Steam catalog for game AppIDs and metadata |
| `maclua add --appid <id>` | Download Lua depot definition and manifests from configured source |
| `maclua add --appid <id> --lua <path>` | Import a game from a local `.lua` file |
| `maclua install <appid>` | Download chunks, verify integrity, and assemble game in `steamapps/common` |
| `maclua update <appid>` | In-place delta update: downloads only modified chunks without reinstalling |
| `maclua verify <appid>` | Adler32 integrity check of all installed depot files on disk |
| `maclua status [appid]` | Display installation status, depot details, and license registration |
| `maclua remove <appid>` | Remove game from MacLua tracking and managed packages |
| `maclua ensure` | Re-apply licenses and manifests to `packageinfo.vdf` (idempotent) |
| `maclua steam-hook status` | Check status of Steam CEF debugging, CDP port (8080), and bridge daemon |
| `maclua steam-hook restart` | Gracefully restart Steam with remote debugging enabled |
| `maclua doctor` | Comprehensive diagnostic check of Steam paths, permissions, and dependencies |

---

## 🏗️ Architecture & How It Works

MacLua operates non-invasively through four core components:

```
┌────────────────────────────────────────────────────────┐
│                      Steam Client                      │
│   ┌───────────────────────┐  ┌───────────────────────┐ │
│   │ Store (CEF Web Page)  │  │ Library (Steam Client)│ │
│   │   [MacLua UI Button]  │  │   [Managed AppIDs]    │ │
│   └───────────▲───────────┘  └───────────▲───────────┘ │
└───────────────┼──────────────────────────┼─────────────┘
                │ Chrome DevTools Protocol │ packageinfo.vdf
                │ (CDP ws://127.0.0.1:8080)│ (Binary KeyValues)
┌───────────────┴──────────────────────────┴─────────────┐
│                   MacLua Core Engine                   │
│                                                        │
│  • core/bridge.py    : Local RPC + CEF Tab Injector    │
│  • core/license.py   : Binary VDF offline packaging    │
│  • core/fetch.py     : Anonymous Steam CDN downloader  │
│  • core/updates.py   : Delta chunk calculator & update │
│  • core/manifest.py  : Depot manifest parser & stager  │
│  • core/steamhook.py : CEF debugging & LaunchAgent mgr │
└────────────────────────────────────────────────────────┘
```

1. **CEF Remote Debugging (`core/steamhook.py`, `core/cdp.py`)**:
   Enables Steam's built-in Chromium remote debugging port (`8080`). The MacLua bridge connects via WebSocket using the Chrome DevTools Protocol (CDP) to inject the custom store UI into storefront views on navigation.
2. **Offline Licensing (`core/license.py`)**:
   Injects managed AppIDs and DepotIDs directly into `package0` in `packageinfo.vdf` and creates synthetic subscription packages. Preserves existing checksums and changenumbers to prevent Steam from invalidating the cache.
3. **Chunk Fetching & Cryptography (`core/fetch.py`)**:
   Fetches encrypted raw chunks directly from `http://content<n>.steampowered.com/depot/<depot_id>/chunk/<sha1>`. Decrypts chunks with depot-specific AES-256 keys, decompresses with Zstandard/ZIP, and validates Adler32 checksums before writing to disk.
4. **Delta Updates (`core/updates.py`)**:
   Parses both the local depot manifest and the target depot manifest. Instead of rewriting unchanged files, it computes chunk-level diffs, downloads only new/modified chunks, and updates the `appmanifest_<appid>.acf` file directly.

---

## 🧹 Uninstallation

To completely remove MacLua and restore Steam to its original state:

```bash
./uninstall.sh
```

Or manually via CLI:
```bash
maclua steam-hook disable
```

This unloads the background LaunchAgent daemon, removes the global CLI launcher, removes CEF debugging flags, and leaves Steam completely unhooked.

---

## 🧪 Testing

MacLua includes a comprehensive test suite covering CLI commands, licensing engine, manifest parsing, CDP injection, and delta updates:

```bash
python3 -m pytest tests/
```

*All unit tests use local mock fixtures and HTTP servers without external network dependencies.*

---

## 📄 License

This project is licensed under the [MIT License](LICENSE) — see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

MacLua is developed for technical research, interoperability, and offline archival management on macOS. Please support game developers by purchasing original titles on Steam.
