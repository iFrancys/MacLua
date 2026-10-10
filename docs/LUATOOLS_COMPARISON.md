# LuaTools vs MacLua: Architectural Comparison & Feature Adaptation

Reference: [LuaTools v1.3.2](https://github.com/madoiscool/LuaTools) (MIT License, © 2026 LuaTools).

| Feature / Area | LuaTools (C# / Windows) | MacLua Existing (Swift / Python) | Verdict | MacLua Target Implementation |
|---|---|---|---|---|
| **In-Steam CEF Injection** | `.cef-enable-remote-debugging` junction + CDP port 8080 WebSocket `Runtime.evaluate` of `luatools.js` | None (standalone app only) | **ADOPT** | `core/cdp.py`, `core/steamhook.py`, `core/steamui/maclua.js`, `maclua.css`. Reversible via `maclua steam-hook enable/disable`. |
| **Local Bridge Server** | `HttpServerService` on `http://127.0.0.1:6767/`, unauthenticated | Bridge via direct CLI subprocess invocation (`MacLuaBridge.swift`) | **ADOPT & HARDEN** | `core/bridge.py` on `127.0.0.1:6767` with random token auth (`~/Library/Application Support/MacLua/bridge_token`), CORS origin restriction, SSE `/events`. |
| **DLC Handling** | Can display and handle individual DLCs | Strictly integrates DLCs into base game; DLCs are never separate cards | **KEEP MACLUA (SUPERIOR)** | Base game always bundles all current & future DLCs automatically. |
| **Game Launching on macOS** | Windows-centric (`.exe` launching, Steamless, AutoCrack) | Universal Mach-O wrapper binary + `steam://run/<id>` | **KEEP MACLUA (SUPERIOR)** | Preserves Mach-O directory fixer in `core/install.py` for flawless Steam client tracking & overlay. |
| **Collections** | Browser link to `lua.tools/collections` | None | **ADOPT** | `core/collections.py` (live Next.js scraper + offline cache) + `CollectionsView.swift` in standalone app + in-Steam shortcut. |
| **Download Queue** | `DownloadQueue.cs` with concurrent jobs, progress, speed, ETA, history | Single active download in `Downloader.swift` | **ADOPT** | `core/queue.py` multi-job download queue with speed calculation, ETA, retry, and history. |
| **DNS-over-HTTPS (DoH)** | `DohResolver.cs` using Cloudflare (1.1.1.1) | System default DNS resolver | **ADOPT** | `core/netresil.py` supporting DoH (Cloudflare 1.1.1.1 & Google 8.8.8.8) with Auto/Always/Never modes. |
| **Lua Vault (Backups)** | `LuaVault.cs` with versioned archives of `.lua` files | Plain file overwrite in `stplug-in/` | **ADOPT** | `core/vault.py` automatic snapshots, version comparison, and instant rollback. |
| **Applied Fixes Index** | `AppliedFixIndexService.cs` tracking fix IDs | None | **ADOPT** | `core/fixes.py` logging game-specific Mach-O wrappers and depot patch states. |
| **AppInfo & AppList Cache** | `SteamAppInfoCache.cs` + `SteamAppListCache.cs` with TTL | Basic memory cache in `catalog.py` | **ADOPT** | `core/appcache.py` persistent disk cache with TTL for Steam names, headers, and appinfo. |
| **Updates Detection** | Checks manifest build IDs | CLI `update <appid>` manual | **ADOPT** | `core/updates.py` background detection of newer base game builds + newly released DLCs. |
| **UI Aesthetics & Customization** | WPF XAML dark interface, settings page | Native SwiftUI app | **ADOPT & ENHANCE** | Complete UI redesign with glassmorphism, accent colors, theme presets, plus **Animated GIF / Custom Image backgrounds** with blur and opacity controls. |

## Collections Data Contract
- **Source URL**: `https://lua.tools/collections`
- **Item URL**: `https://lua.tools/c/<slug>`
- **Payload Shape**:
  ```json
  [
    {
      "id": "e4f40c3c-friendslop",
      "title": "Friendslop Co-op Pack",
      "cover": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1966720/header.jpg",
      "appCount": 20,
      "apps": [1966720, 2881650, 3643170]
    }
  ]
  ```
- **Fallback**: Cached locally in `~/Library/Application Support/MacLua/collections_cache.json` with a bundle of curated collections when offline.
