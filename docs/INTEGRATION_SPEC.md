# MacLua × Steam client — Integration Spec (shared contract)

Reference: LuaTools v1.3.2 (MIT) cloned at `/tmp/LuaTools` (re-clone: `git clone --depth 1 https://github.com/madoiscool/LuaTools /tmp/LuaTools`).
Rule: LuaTools is a **logic reference only**. Everything is re-interpreted and rewritten for MacLua/macOS. No copy-paste blocks. Credit in `CREDITS.md`.
Rule: all LuaTools features and customization options are to be reproduced (adapted), not just a subset; MacLua keeps its own identity (name, palette, DLC-always-integrated rule).

## Architecture
```
Steam (CEF, port 8080 via ~/Library/Application Support/Steam/.cef-enable-remote-debugging)
   ▲  CDP Runtime.evaluate (injected JS: core/steamui/maclua.js + maclua.css)
   │
MacLua bridge  (Python, 127.0.0.1:6767, token auth)  ◄──►  standalone MacLua.app (Swift, same CLI/bridge)
   │
backend core/  (add/download/update/queue/vault/cache…)  →  steamapps + stplug-in + depotcache
```
- Bridge runs as a LaunchAgent (`dev.maclua.bridge`) so it works with MacLua.app closed. Standalone app and Steam UI read the SAME state through the bridge / CLI `--json`.
- Token: random 32 bytes hex at `~/Library/Application Support/MacLua/bridge_token` (0600). Injected JS receives it at injection time (never hardcoded, never in CORS-open endpoints). Requests need header `X-MacLua-Token`. CORS allow-origin only for `https://store.steampowered.com` and `https://steamloopback.host`.
- Reversible: `maclua steam-hook disable` removes marker (only if MacLua created it), LaunchAgent, bridge state, injected assets, and restarts Steam if asked. `maclua steam-hook status --json`. Before/after file manifest recorded in `~/Library/Application Support/MacLua/hook_manifest.json`.

## Bridge HTTP API (JSON, all need token except /health)
| Method | Path | Body / Query | Returns |
|---|---|---|---|
| GET | /health | – | `{ok, version}` |
| GET | /search | `q` | `[{appid,name,price?,image}]` base games only (DLC resolved to parent) |
| GET | /library | – | `[{appid,name,state,installed,updateAvailable,dlcCount,sizeOnDisk,progress?}]` (DLC never listed) |
| GET | /game/{appid} | – | detail + dlc count + applied fixes + vault info |
| POST | /add | `{appid}` | add base game + all DLC (same logic as `cmd_add`), returns status |
| POST | /install | `{appid}` | enqueue download |
| POST | /cancel | `{appid}` | cancel |
| GET | /queue | – | `[{appid,name,state,mb,totalMB,fraction,speed,eta,error?}]` + history |
| POST | /update-check | `{appid?}` | checks base build + new DLC, applies, returns changes |
| POST | /remove | `{appid}` | remove from management |
| GET | /collections | – | LuaTools collections (live, cached fallback, `stale:true` when offline) |
| POST | /collections/add | `{id}` | add all games of a collection (same flow as /add + /install) |
| GET/POST | /settings | – | all user prefs (shared with Swift app, see Settings) |
| POST | /restart-steam | – | restart Steam |
| GET | /events | SSE or long-poll | queue/library change events |

## Backend modules (owner: Backend agent) — `core/`
`bridge.py` (server) · `steamhook.py` (marker, LaunchAgent, CDP injector loop, uninstall/manifest) · `cdp.py` (minimal stdlib websocket client for CDP) · `queue.py` (download queue + history + speed/ETA, persisted) · `appcache.py` (Steam app list/appinfo cache w/ TTL) · `vault.py` (lua vault: backup/restore of installed luas, versions) · `netresil.py` (DoH / fallback DNS + proxy resilience for source requests) · `fixes.py` (applied-fix index) · `updates.py` (auto update: new build / new DLC) · `collections.py` · `settings.py` (shared prefs file `~/Library/Application Support/MacLua/settings.json`). CLI additions in `maclua.py`: `bridge serve|install|uninstall`, `steam-hook enable|disable|status`, `collections list|add`, `queue`, `vault`, `fixes`. Every module gets pytest tests (no network: use local http server mocks). Final bar: `python3 -m pytest tests/` green (≥115 + new).

## Injected UI (owner: Steam-UI agent) — `core/steamui/`
`maclua.js` + `maclua.css`: idempotent (sets `window.__MacLuaReady`), re-injected by the loop on navigation. Store: "Add to MacLua" button on `/app/<id>` pages, header icon, search results badge, download progress toast. Library (tab URL `steamloopback.host`; verify availability on macOS first; fallback documented): MacLua panel/entry with state, install, update, play (`steam://run/<id>`), progress. DLC never shown. Visual style = MacLua's new design language (see UI). Tests: node/jsdom-free unit tests where possible + `scripts/verify_steam_ui.py` that queries `http://127.0.0.1:8080/json` and evaluates `window.__MacLuaReady` in Store and Library tabs.

## Standalone app (owner: Swift agent) — `native/Sources/MacApp/`
1. **Collections** section (live from bridge `/collections`, refresh on open + every N min, offline state, one-click "add all" using the same add+download flow).
2. **UI redesign inspired by LuaTools' look** (richer, more options, more beautiful) while keeping MacLua identity (name, logo, accent system, DLC integrated). 
3. **Customization — replicate ALL LuaTools customization options** (adapted) plus: custom background image **and animated GIF backgrounds** (import from file, copy into `~/Library/Application Support/MacLua/Backgrounds`, animate with ImageIO/`NSImageView`/AVFoundation-free path, blur/dim/opacity sliders, fit modes, pause when window inactive or Low-Power-Mode, reset to default).
4. Settings pages for: Steam integration (enable/disable hook, status, repair, uninstall), queue behavior, DNS mode (Auto/Always/Never), auto-update, vault, fixes, language, launch at login, etc. (mapped from LuaTools `AppSettings`).
5. Downloads page uses bridge `/queue` (single source of truth). Update `native/package.sh` to bundle `core/steamui`.
6. New checks in `Check.swift` for new pure logic. Bar: `MACLUA_CHECK=1 swift run -c release MacApp` green; `native/package.sh` → single Universal `MacLua.app`.

## Analysis (owner: Analyst agent) — `docs/LUATOOLS_COMPARISON.md`, `CREDITS.md`
Feature-by-feature table: LuaTools feature · verdict (adopt / already have / skip) · reason · mapped MacLua module. Also an exhaustive list of LuaTools customization/settings options (from `SettingsService.cs`, `SettingsViewModel`, views, Resources strings) and of the exact collections endpoint/payload of lua.tools (reverse from site JS / network; document shape + fallback). Send the settings list and collections API to Backend and Swift agents as soon as ready.

## Hard constraints
- DLC never a separate entry anywhere (CLI, bridge, Swift, injected UI).
- Games must remain launchable from Steam (`steam://run/<id>`), Mach-O launcher logic in `core/install.py` untouched.
- No regressions: existing 115 pytest + 32 Swift checks stay green.
- Don't edit files owned by another agent; ask via `send_message` instead.
