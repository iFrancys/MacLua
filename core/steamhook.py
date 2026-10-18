"""Management of native in-client Steam integration.
Activates CEF debugging (port 8080) and injects MacLua interface (JS/CSS) into Store and Library tabs.
Guarantees full reversibility (clean uninstall with before/after manifests).
"""
import os
import re
import sys
import json
import secrets
import urllib.request
from core import paths, cdp
from core.atomic import atomic_write

HOOK_DIR = os.path.expanduser("~/Library/Application Support/MacLua")
TOKEN_FILE = os.path.join(HOOK_DIR, "bridge_token")
MANIFEST_FILE = os.path.join(HOOK_DIR, "hook_manifest.json")
CDP_URL = "http://127.0.0.1:8080/json"


def is_cdp_available(timeout=0.2):
    """Quickly checks via TCP socket whether CDP port 8080 is open (latency < 1ms)."""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(("127.0.0.1", 8080))
        s.close()
        return True
    except Exception:
        return False


def get_or_create_token():
    """Generates or retrieves unique cryptographic token for local bridge."""
    os.makedirs(HOOK_DIR, exist_ok=True)
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                t = f.read().strip()
            if len(t) >= 32:
                return t
        except Exception:
            pass

    token = secrets.token_hex(32)
    atomic_write(TOKEN_FILE, token, mode=0o600)
    return token


def _candidate_markers(home=None):
    home = home or os.path.expanduser("~")
    steam_dir = paths.steam_root(home)
    return [
        os.path.join(steam_dir, ".cef-enable-remote-debugging"),
        os.path.join(steam_dir, "Steam.AppBundle", "Steam", "Contents", "MacOS", ".cef-enable-remote-debugging"),
        os.path.join(home, ".steam", "steam", ".cef-enable-remote-debugging"),
        "/Applications/Steam.app/Contents/MacOS/.cef-enable-remote-debugging",
    ]


def enable_hook(home=None):
    """Enables Steam integration by creating CEF markers in all known locations, installing LaunchAgent, and recording manifest."""
    home = home or os.path.expanduser("~")
    os.makedirs(HOOK_DIR, exist_ok=True)
    created_markers = []
    existed_markers = []

    for marker in _candidate_markers(home):
        parent_dir = os.path.dirname(marker)
        if os.path.exists(parent_dir) and os.access(parent_dir, os.W_OK):
            if os.path.exists(marker):
                existed_markers.append(marker)
            else:
                try:
                    with open(marker, "w") as f:
                        pass
                    created_markers.append(marker)
                except OSError:
                    pass

    # Ensure bridge daemon is always running and registered as LaunchAgent
    agent_info = install_bridge_agent(home=home)

    manifest = {
        "enabled": True,
        "created_markers": created_markers,
        "existed_markers": existed_markers,
        "bridge_agent": agent_info.get("path") if agent_info.get("ok") else None,
    }
    atomic_write(MANIFEST_FILE, json.dumps(manifest, indent=2))

    return {
        "ok": True,
        "created": created_markers,
        "existed": existed_markers,
        "agent": agent_info
    }


def disable_hook(home=None):
    """Removes Steam integration, uninstalls LaunchAgent, and restores previous state."""
    home = home or os.path.expanduser("~")
    manifest = {}
    if os.path.exists(MANIFEST_FILE):
        try:
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            pass

    to_remove = manifest.get("created_markers") or []
    if not to_remove:
        # Fallback for older manifest
        p = manifest.get("marker_path")
        if p and manifest.get("marker_created_by_maclua", True):
            to_remove = [p]

    removed = []
    for marker in to_remove:
        if os.path.exists(marker):
            try:
                os.remove(marker)
                removed.append(marker)
            except OSError:
                pass

    # Remove and unload bridge LaunchAgent
    agent_removed = remove_bridge_agent(home=home)

    manifest["enabled"] = False
    manifest["bridge_agent"] = None
    atomic_write(MANIFEST_FILE, json.dumps(manifest, indent=2))

    return {"ok": True, "removed": removed, "agent_removed": agent_removed}


def restart_steam():
    """Restarts Steam ensuring it opens with CEF debugging enabled (-cef-enable-debugging)."""
    import subprocess
    import time

    # Ensure debug markers are present on disk
    enable_hook()

    # Request Steam to quit cleanly to save state
    subprocess.run(["/usr/bin/osascript", "-e", 'tell application "Steam" to quit'], capture_output=True)

    # Wait for process to actually terminate
    for _ in range(35):
        p1 = subprocess.run(["/usr/bin/pgrep", "-f", "Steam.AppBundle"], capture_output=True)
        p2 = subprocess.run(["/usr/bin/pgrep", "-x", "Steam"], capture_output=True)
        p3 = subprocess.run(["/usr/bin/pgrep", "steam_osx"], capture_output=True)
        if p1.returncode != 0 and p2.returncode != 0 and p3.returncode != 0:
            break
        time.sleep(0.2)
    else:
        # If not closed within 7s, force termination
        subprocess.run(["/usr/bin/killall", "Steam"], capture_output=True)
        subprocess.run(["/usr/bin/killall", "steam_osx"], capture_output=True)
        for _ in range(15):
            p1 = subprocess.run(["/usr/bin/pgrep", "-f", "Steam.AppBundle"], capture_output=True)
            if p1.returncode != 0:
                break
            time.sleep(0.2)
        else:
            subprocess.run(["/usr/bin/killall", "-9", "Steam"], capture_output=True)
            subprocess.run(["/usr/bin/killall", "-9", "steam_osx"], capture_output=True)
            time.sleep(0.5)

    # Before reopening Steam (while completely closed and unable to overwrite
    # packageinfo.vdf on exit), reconcile licenses and keys.
    try:
        import maclua
        maclua._ensure(os.path.expanduser("~"))
    except Exception:
        pass

    time.sleep(0.5)
    subprocess.Popen(["/usr/bin/open", "-a", "Steam", "--args", "-cef-enable-debugging"])
    return {"ok": True, "restarted": True}


def notify_macos(title, message):
    """Displays a native macOS notification (used to alert user that Steam needs to restart for licenses)."""
    import subprocess
    t = str(title).replace("\\", "").replace('"', "'")
    m = str(message).replace("\\", "").replace('"', "'")
    try:
        subprocess.run(
            ["/usr/bin/osascript", "-e", f'display notification "{m}" with title "{t}"'],
            capture_output=True, timeout=5
        )
        return True
    except Exception:
        return False


def client_app_licensed(appid, timeout=2):
    """Queries running Steam client (SharedJSContext) for app ownership.
    Returns True/False, or None if client unreachable (no CDP or Steam closed)."""
    try:
        req = urllib.request.Request(CDP_URL, headers={"User-Agent": "MacLua"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            tabs = json.loads(resp.read().decode("utf-8"))

        shared_tab = next((t for t in tabs if t.get("title") == "SharedJSContext"), None)
        if not shared_tab or not shared_tab.get("webSocketDebuggerUrl"):
            return None

        client = cdp.CDPClient(shared_tab["webSocketDebuggerUrl"], timeout=timeout)
        try:
            res = client.evaluate(
                f"(async () => {{ if (!window.appStore || window.appStore.m_bIsInitialized !== true) return 'none'; return String(await SteamClient.Apps.GetIsSubscribedApp({int(appid)})); }})()"
            )
            if res == "true":
                return True
            if res == "false":
                return False
            return None
        finally:
            client.close()
    except Exception:
        return None


def running_managed_appids(home=None):
    """AppIDs of managed games with a running process (avoids restarting
    Steam while gaming).

    Robust macOS heuristic: the game process contains the path
    `steamapps/common/<installdir>` in its command line. When in doubt
    (invalid pgrep pattern), be conservative and treat game as active.
    """
    import subprocess
    home = home or os.path.expanduser("~")
    steamapps_dir = paths.steamapps(home)
    stplug = paths.stplug_in(home)
    running = []
    try:
        names = os.listdir(steamapps_dir)
    except OSError:
        return running
    for fn in names:
        if not (fn.startswith("appmanifest_") and fn.endswith(".acf")):
            continue
        try:
            appid = int(fn[len("appmanifest_"):-len(".acf")])
        except ValueError:
            continue
        if not os.path.exists(os.path.join(stplug, f"{appid}.lua")):
            continue
        try:
            with open(os.path.join(steamapps_dir, fn), encoding="utf-8",
                      errors="replace") as f:
                txt = f.read()
        except OSError:
            continue
        m_dir = re.search(r'"installdir"\s+"([^"]+)"', txt)
        if not m_dir:
            continue
        target = os.path.join("steamapps", "common", m_dir.group(1))
        try:
            r = subprocess.run(["/usr/bin/pgrep", "-f", target],
                               capture_output=True, timeout=5)
        except Exception:
            continue
        if r.returncode == 0:
            running.append(appid)
        elif r.returncode not in (0, 1):
            # Non-interpretable pattern: be conservative, treat as active.
            running.append(appid)
    return running


def get_status(home=None):
    """Checks activation status, Steam presence, and CDP port availability."""
    home = home or os.path.expanduser("~")
    steam_dir = paths.steam_root(home)
    marker = os.path.join(steam_dir, ".cef-enable-remote-debugging")

    marker_present = os.path.exists(marker)
    cdp_available = False
    tabs = []

    if is_cdp_available():
        try:
            req = urllib.request.Request(CDP_URL, headers={"User-Agent": "MacLua"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                cdp_available = True
                tabs = [
                    {"title": t.get("title"), "url": t.get("url"), "id": t.get("id")}
                    for t in data
                    if t.get("webSocketDebuggerUrl")
                ]
        except Exception:
            pass

    return {
        "marker_present": marker_present,
        "cdp_available": cdp_available,
        "tabs_count": len(tabs),
        "tabs": tabs,
        "agent_installed": is_bridge_agent_installed(home)
    }


def handle_rpc_request(path, method="GET", data=None):
    """Handles RPC calls locally originating from the in-Steam script via CDP."""
    home = os.path.expanduser("~")
    data = data or {}
    path = (path or "").rstrip("/")

    if path.startswith("/game/"):
        try:
            aid = int(path.split("/")[-1])
        except ValueError:
            return {"error": "Invalid AppID"}
        from core import catalog, install
        name = catalog.name_of(aid) or f"Game {aid}"
        installed = install.is_game_installed(aid, home)
        managed = os.path.exists(os.path.join(paths.stplug_in(home), f"{aid}.lua"))
        return {
            "appid": aid,
            "name": name,
            "installed": installed,
            "managed": managed,
            "cover": f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg"
        }

    elif path == "/add":
        aid = data.get("appid")
        if not aid:
            return {"ok": False, "error": "Missing AppID"}
        try:
            aid = int(aid)
        except ValueError:
            return {"ok": False, "error": "Invalid AppID"}

        from core import appinfo as ai, catalog, config, source, install, vault, settings
        p_id = ai.parent(aid)
        if p_id is None:
            p_id, _ = catalog.parent_of(aid)
        target_id = p_id if p_id else aid

        key = config.get_key(home) or settings.get("hubcap_key", "")
        pref = settings.get("preferred_source", "auto")
        auto_up = settings.get("auto_update_apps", True)

        try:
            fetched = source.fetch_from_sources(target_id, key=key, preferred_source=pref, auto_update=auto_up)
            install.import_lua(target_id, fetched["lua"], fetched["manifests"], home)

            # Clean up potential stale ghost appmanifests (StateFlags 2 with size 0)
            steamapps_dir = paths.steamapps(home)
            install.cleanup_broken_appmanifests(steamapps_dir)

            from maclua import _ensure
            _ensure(home)

            vault.snapshot(target_id, fetched["lua"], note="Added from Steam")
            game_name = catalog.name_of(target_id) or f"Game {target_id}"

            try:
                broadcast_library_refresh(home)
            except Exception:
                pass

            return {
                "ok": True,
                "appid": target_id,
                "name": game_name,
                "source": fetched.get("source"),
                "message": f"Added {game_name}!"
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    elif path == "/settings":
        from core import settings
        if method == "POST":
            for k, v in data.items():
                settings.set_val(k, v)
            return {"ok": True, "settings": settings.get_all()}
        else:
            return {"ok": True, "settings": settings.get_all()}

    elif path == "/api-list":
        return {
            "ok": True,
            "sources": [
                {"id": "auto", "name": "Auto (Sushi -> Ryuu -> Hubcap)", "requires_key": False},
                {"id": "sushi", "name": "Sushi (GitHub Raw - Free)", "requires_key": False},
                {"id": "ryuu", "name": "Ryuu (Anonymous - Free)", "requires_key": False},
                {"id": "hubcap", "name": "Hubcap / Morrenus (Requires API Key)", "requires_key": True}
            ]
        }

    elif path.startswith("/check-sources"):
        try:
            aid = int(path.split("/")[-1]) if "/" in path[1:] else int(data.get("appid", 0))
        except ValueError:
            return {"ok": False, "error": "Invalid AppID"}
        from core import source
        ryuu_avail = source.check_ryuu(aid)
        sushi_avail = False
        try:
            source.fetch_from_sushi(aid, timeout=5)
            sushi_avail = True
        except Exception:
            pass
        return {
            "ok": True,
            "appid": aid,
            "sources": {
                "sushi": sushi_avail,
                "ryuu": ryuu_avail,
                "hubcap": True
            }
        }

    elif path == "/cleanup-manifests":
        from core import install
        steamapps_dir = paths.steamapps(home)
        cleaned = install.cleanup_broken_appmanifests(steamapps_dir)
        reconciled = install.reconcile_installed_appmanifests(steamapps_dir, home=home)
        try:
            sync_library_in_steam(home)
        except Exception:
            pass
        return {"ok": True, "cleaned": cleaned, "reconciled": reconciled, "count": len(cleaned) + len(reconciled)}

    elif path == "/update":
        aid = data.get("appid")
        if not aid:
            return {"ok": False, "error": "Missing AppID"}
        try:
            aid = int(aid)
        except ValueError:
            return {"ok": False, "error": "Invalid AppID"}
        from core import updates
        # Tracked update: the real outcome is stored in updates.json
        # (visible via /update-status), avoiding silent failures.
        try:
            return updates.request_update(aid, home=home)
        except Exception as e:
            return {"ok": False, "error": f"Update error: {e}"}

    elif path == "/update-status":
        from core import updates
        return {"ok": True, "status": updates.load_status(home)}

    elif path == "/library":
        from core import catalog, install, appinfo as ai, updates
        stplug = paths.stplug_in(home)
        games = []
        if os.path.exists(stplug):
            for fn in sorted(os.listdir(stplug)):
                if fn.endswith(".lua"):
                    try:
                        aid = int(fn[:-4])
                        p_id = ai.parent(aid)
                        if p_id is not None and p_id != aid:
                            continue
                        name = catalog.name_of(aid) or f"Game {aid}"
                        installed = install.is_game_installed(aid, home)
                        up_status = updates.get_status(aid, home) if installed else None
                        if installed and not up_status:
                            try:
                                chk = updates.check_updates(aid, home=home)
                                if chk:
                                    up_status = updates.set_status(aid, {
                                        "status": "pending" if (chk.get("has_update") and not chk.get("manifest_ready")) else ("ok" if not chk.get("has_update") else "pending"),
                                        "checked_at": int(time.time()),
                                        "current_buildid": chk.get("current_buildid"),
                                        "latest_buildid": chk.get("latest_buildid"),
                                        "has_update": bool(chk.get("has_update")),
                                        "message": "Updated to latest version available." if not chk.get("has_update") else "Update available.",
                                    }, home=home)
                            except Exception:
                                pass
                        games.append({
                            "appid": aid,
                            "name": name,
                            "installed": installed,
                            "update": up_status,
                            "cover": f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg"
                        })
                    except Exception:
                        pass
        return {"ok": True, "games": games}

    elif path == "/remove":
        aid = data.get("appid")
        if not aid:
            return {"ok": False, "error": "Missing AppID"}
        try:
            aid = int(aid)
        except ValueError:
            return {"ok": False, "error": "Invalid AppID"}

        from core import appinfo as ai, catalog, install
        p_id = ai.parent(aid)
        if p_id is None:
            p_id, _ = catalog.parent_of(aid)
        target_id = p_id if p_id else aid

        lua_path = os.path.join(paths.stplug_in(home), f"{target_id}.lua")
        if os.path.exists(lua_path):
            try:
                os.remove(lua_path)
            except OSError:
                pass

        if not install.is_game_installed(target_id, home):
            acf_path = os.path.join(paths.steamapps(home), f"appmanifest_{target_id}.acf")
            if os.path.exists(acf_path):
                try:
                    os.remove(acf_path)
                except OSError:
                    pass

        from maclua import _ensure
        _ensure(home)

        try:
            remove_from_steam_library(target_id, home)
            broadcast_library_refresh(home)
        except Exception:
            pass

        g_name = catalog.name_of(target_id) or f"App {target_id}"
        return {
            "ok": True,
            "appid": target_id,
            "message": f"{g_name} removed from MacLua"
        }

    elif path == "/queue":
        from core import queue
        return queue.DownloadQueue.shared().get_status()

    elif path == "/restart-steam":
        return restart_steam()

    return {"ok": False, "error": f"Unsupported endpoint: {path}"}


def get_managed_games(home=None):
    """Returns the list of games managed by stplug-in immediately without blocking I/O."""
    home = home or os.path.expanduser("~")
    from core import install, appinfo as ai, appcache
    stplug = paths.stplug_in(home)
    games = []
    if os.path.exists(stplug):
        for fn in sorted(os.listdir(stplug)):
            if fn.endswith(".lua"):
                try:
                    aid = int(fn[:-4])
                    p_id = ai.parent(aid)
                    if p_id is not None and p_id != aid:
                        continue
                    cfg = ai.config(aid)
                    name = cfg.get("name")
                    if not name:
                        cached = appcache.get_info(aid)
                        if cached and isinstance(cached, dict):
                            name = cached.get("name")
                    if not name:
                        name = f"Game {aid}"
                    installed = install.is_game_installed(aid, home)
                    games.append({
                        "appid": aid,
                        "name": name,
                        "installed": installed,
                        "cover": f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg"
                    })
                except Exception:
                    pass
    return games


def sync_library_in_steam(home=None):
    """Cleanly and safely synchronizes managed games in Steam's SharedJSContext.
    - First reconciles any appmanifests blocked by PICS updates (StateFlags 6 -> 4).
    - Sets visible_in_game_list = true and subscribed_to = true on appStore for all managed games.
    - For installed games, ensures ready state (installed: true, display_status: 11 'PLAY').
    - For uninstalled games, ensures clean state (installed: false, display_status: 9 'INSTALL').

    All modifications are made by assigning observable properties of appStore normally:
    MobX automatically notifies observers and reactions, so the UI updates itself.
    Never touch private internal MobX symbols (value_, dependenciesState_,
    onBecomeStale_) or the React fiber, as doing so corrupts the dependency graph and
    crashes Steam's library Error Boundary.
    """
    home = home or os.path.expanduser("~")
    try:
        from core import install
        install.reconcile_installed_appmanifests(paths.steamapps(home), home=home)
    except Exception:
        pass

    managed = get_managed_games(home)
    if not managed:
        return {"ok": True, "count": 0}

    installed_aids = [g["appid"] for g in managed if g.get("installed")]
    uninstalled_aids = [g["appid"] for g in managed if not g.get("installed")]
    all_managed_aids = [g["appid"] for g in managed]

    try:
        req = urllib.request.Request(CDP_URL, headers={"User-Agent": "MacLua"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            tabs = json.loads(resp.read().decode("utf-8"))

        shared_tab = next((t for t in tabs if t.get("title") == "SharedJSContext"), None)
        if not shared_tab or not shared_tab.get("webSocketDebuggerUrl"):
            return {"ok": False, "error": "SharedJSContext not available"}

        client = cdp.CDPClient(shared_tab["webSocketDebuggerUrl"], timeout=2)
        try:
            aids_json = json.dumps(all_managed_aids)
            installed_json = json.dumps(installed_aids)
            uninstalled_json = json.dumps(uninstalled_aids)

            script = f"""
            (() => {{
                const appStore = window.appStore;
                if (!appStore) return JSON.stringify({{ ok: false, error: "Stores not ready" }});
                // Cold start: do not touch anything until Steam has finished its
                // initialization, otherwise we risk poisoning MobX computeds.
                if (appStore.m_bIsInitialized !== true || !appStore.m_mapApps) {{
                    return JSON.stringify({{ ok: false, error: "appStore not yet initialized" }});
                }}
                const csRaw = window.collectionStore ? window.collectionStore.m_mapCollectionsFromStorage : null;
                const collectionsReady = !!(csRaw && typeof csRaw.values === 'function' && csRaw.size > 0);

                const allManaged = {aids_json};
                const installedSet = new Set({installed_json});
                const uninstalled = new Set({uninstalled_json});
                window.__macluaManagedSet = new Set(allManaged);

                // Protect visible_in_game_list and subscribed_to from async resets
                // caused by UpdateAppOverview -> AppOverview.prototype.InitFromProto
                try {{
                    const sampleApp = appStore.m_mapApps.values().next().value;
                    const appProto = sampleApp ? Object.getPrototypeOf(sampleApp) : null;
                    if (appProto && typeof appProto.InitFromProto === 'function' && !appProto.InitFromProto.__macluaWrapped) {{
                        const origInitFromProto = appProto.InitFromProto;
                        const wrappedInit = function(proto) {{
                            const res = origInitFromProto.apply(this, arguments);
                            try {{
                                if (window.__macluaManagedSet && window.__macluaManagedSet.has(this.appid)) {{
                                    this.visible_in_game_list = true;
                                    this.subscribed_to = true;
                                    this.is_subscribed = true;
                                }}
                            }} catch (e) {{}}
                            return res;
                        }};
                        wrappedInit.__macluaWrapped = true;
                        appProto.InitFromProto = wrappedInit;
                    }}
                }} catch (e) {{}}

                let modifiedCount = 0;
                for (const aid of allManaged) {{
                    const app = appStore.m_mapApps?.get(aid);
                    if (app) {{
                        if (!app.visible_in_game_list) {{
                            app.visible_in_game_list = true;
                            modifiedCount++;
                        }}
                        if (!app.subscribed_to) {{
                            app.subscribed_to = true;
                            modifiedCount++;
                        }}
                        if (app.is_subscribed !== true) {{
                            app.is_subscribed = true;
                        }}
                        if (installedSet.has(aid)) {{
                            try {{
                                if (window.SteamClient?.Downloads?.RemoveFromDownloadList) {{
                                    window.SteamClient.Downloads.RemoveFromDownloadList(aid);
                                }}
                            }} catch (e) {{}}
                            for (const pcd of [app.most_available_per_client_data, app.local_per_client_data, ...(app.per_client_data || [])]) {{
                                if (pcd) {{
                                    if (!pcd.installed) {{
                                        pcd.installed = true;
                                        modifiedCount++;
                                    }}
                                    const ds = pcd.display_status;
                                    if (ds === 34) {{
                                        try {{
                                            window.__macluaCloudDisabled = window.__macluaCloudDisabled || new Set();
                                            if (!window.__macluaCloudDisabled.has(aid) && window.SteamClient?.Apps?.ToggleAppSteamCloudEnabled) {{
                                                window.__macluaCloudDisabled.add(aid);
                                                window.SteamClient.Apps.ToggleAppSteamCloudEnabled(aid);
                                            }}
                                        }} catch (e) {{}}
                                    }}
                                    if (ds === 9 || ds === 20 || ds === 7 || ds === 6 || ds === 34) {{
                                        pcd.display_status = 11;
                                        modifiedCount++;
                                    }}
                                }}
                            }}
                        }} else if (uninstalled.has(aid)) {{
                            for (const pcd of [app.most_available_per_client_data, app.local_per_client_data, ...(app.per_client_data || [])]) {{
                                if (pcd) {{
                                    if (pcd.installed) {{
                                        pcd.installed = false;
                                        modifiedCount++;
                                    }}
                                    if (pcd.display_status !== 9) {{
                                        pcd.display_status = 9;
                                        modifiedCount++;
                                    }}
                                }}
                            }}
                        }}
                    }}
                }}

                // Sync ONLY "Lua" user collections using native public Steam methods
                // (ClearAppCounts + SetApps + Save), never touching private internal MobX symbols.
                //
                // IMPORTANT: NEVER read computed getters from collectionStore
                // (uncategorizedCollection, userCollections, collectionsFromStorage, ...).
                // They depend on the non-observable field m_mapCollectionsFromStorage, which Steam
                // sets only after initialization completes: if computed earlier (cold start),
                // MobX caches the "reading 'forEach'" exception in the computed and the library
                // stays broken ("Something went wrong while displaying this content") until Steam restarts.
                // We therefore read the raw map directly, and only when it exists.
                //
                // In addition to new additions (colChanged), if visible_in_game_list of uninstalled games
                // was just restored (modifiedCount > 0) or visibleApps / collection filtered counts
                // lagged behind allApps (because visible_in_game_list is not observable in MobX),
                // we recompute SetApps and ClearAppCounts so the sidebar displays all Lua games (both downloaded and not downloaded).
                let colChanged = false;
                try {{
                    const cs = window.collectionStore;
                    const rawMap = cs ? cs.m_mapCollectionsFromStorage : null;
                    if (collectionsReady && rawMap && typeof rawMap.values === 'function') {{
                        const luaCols = Array.from(rawMap.values()).filter(c =>
                            c && (c.displayName || '').trim().toLowerCase() === 'lua');
                        for (const col of luaCols) {{
                            if (!col || !col.m_setApps) continue;
                            const removed = col.m_setRemovedManually;
                            const manuallyAdded = col.m_setAddedManually;
                            for (const aid of allManaged) {{
                                if (removed && removed.has(aid)) continue;
                                if (!appStore.m_mapApps?.has(aid)) continue;
                                if (!col.m_setApps.has(aid)) {{
                                    col.m_setApps.add(aid);
                                    colChanged = true;
                                }}
                                if (manuallyAdded && !manuallyAdded.has(aid)) {{
                                    manuallyAdded.add(aid);
                                    colChanged = true;
                                }}
                            }}
                            const allLen = col.allApps ? col.allApps.length : 0;
                            const visLen = col.visibleApps ? col.visibleApps.length : 0;
                            const countsStale = Boolean(
                                col.m_mapFilterToAppCounts &&
                                col.m_mapFilterToAppCounts.size > 0 &&
                                Array.from(col.m_mapFilterToAppCounts.values()).some(v => v < allLen)
                            );
                            if (colChanged || modifiedCount > 0 || visLen < allLen || countsStale) {{
                                if (typeof col.ClearAppCounts === 'function') col.ClearAppCounts();
                                if (typeof col.SetApps === 'function') {{
                                    col.SetApps(Array.from(col.m_setApps));
                                }}
                                if (colChanged) {{
                                    try {{
                                        if (typeof col.Save === 'function') col.Save();
                                    }} catch (e) {{}}
                                }}
                            }}
                        }}
                    }}
                }} catch (e) {{}}

                return JSON.stringify({{
                    ok: true,
                    managedCount: allManaged.length,
                    modified: modifiedCount,
                    collectionChanged: colChanged
                }});
            }})()
            """
            res_str = client.evaluate(script)
            res = json.loads(res_str) if res_str else {"ok": False, "error": "No response"}
        finally:
            client.close()

        return res
    except Exception as e:
        return {"ok": False, "error": str(e)}


def remove_from_steam_library(appid, home=None):
    """Removes a game from Steam SharedJSContext when removed from MacLua."""
    home = home or os.path.expanduser("~")
    try:
        req = urllib.request.Request(CDP_URL, headers={"User-Agent": "MacLua"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            tabs = json.loads(resp.read().decode("utf-8"))

        shared_tab = next((t for t in tabs if t.get("title") == "SharedJSContext"), None)
        if not shared_tab or not shared_tab.get("webSocketDebuggerUrl"):
            return
        client = cdp.CDPClient(shared_tab["webSocketDebuggerUrl"], timeout=2)
        try:
            client.evaluate(f"""
            (() => {{
                const aid = {int(appid)};
                if (window.__macluaManagedSet) window.__macluaManagedSet.delete(aid);
                const app = window.appStore?.m_mapApps?.get(aid);
                if (app) app.visible_in_game_list = false;
                try {{
                    const cs = window.collectionStore;
                    const rawMap = cs ? cs.m_mapCollectionsFromStorage : null;
                    if (rawMap && typeof rawMap.values === 'function') {{
                        for (const col of Array.from(rawMap.values())) {{
                            if (!col || (col.displayName || '').trim().toLowerCase() !== 'lua') continue;
                            if (col.m_setAddedManually) col.m_setAddedManually.delete(aid);
                            if (col.m_setApps && col.m_setApps.has(aid)) {{
                                col.m_setApps.delete(aid);
                                if (typeof col.SetApps === 'function') col.SetApps(Array.from(col.m_setApps));
                                if (typeof col.ClearAppCounts === 'function') col.ClearAppCounts();
                                try {{
                                    if (typeof col.Save === 'function') col.Save();
                                }} catch (e) {{}}
                            }}
                        }}
                    }}
                }} catch (e) {{}}
            }})()
            """)
        finally:
            client.close()
    except Exception:
        pass


def broadcast_library_refresh(home=None):
    """Notifies that the managed library was updated and synchronizes SharedJSContext."""
    home = home or os.path.expanduser("~")
    games = get_managed_games(home)
    try:
        sync_library_in_steam(home)
    except Exception:
        pass
    return {"ok": True, "count": len(games)}


def drain_tab_rpc(client):
    """Checks and drains RPC requests created by the JS client in Steam."""
    try:
        has_pending = client.evaluate("String(typeof window !== 'undefined' && window.__MacLuaRPC && Object.keys(window.__MacLuaRPC.pending || {}).length > 0)")
        if has_pending != "true":
            return
        pending_raw = client.evaluate("JSON.stringify(window.__MacLuaRPC.pending)")
        if not pending_raw or pending_raw in ("{}", "null", "undefined"):
            return
        pending = json.loads(pending_raw)
        if not pending:
            return

        resps = {}
        for req_id, item in pending.items():
            p = item.get("path", "")
            m = item.get("method", "GET")
            d = item.get("data")
            resps[req_id] = handle_rpc_request(p, m, d)

        encoded = json.dumps(resps)
        client.evaluate(f"""
        (function() {{
            var r = {encoded};
            if (!window.__MacLuaRPC) return;
            window.__MacLuaRPC.responses = window.__MacLuaRPC.responses || {{}};
            for (var k in r) {{
                window.__MacLuaRPC.responses[k] = r[k];
                delete window.__MacLuaRPC.pending[k];
            }}
        }})();
        """)
    except Exception:
        pass


def drain_all_tabs_rpc():
    """Drains RPC requests from active Steam Store tabs."""
    try:
        req = urllib.request.Request(CDP_URL, headers={"User-Agent": "MacLua"})
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            tabs = json.loads(resp.read().decode("utf-8"))
        for t in tabs:
            url = t.get("url", "")
            ws = t.get("webSocketDebuggerUrl")
            if ws and "store.steampowered.com" in url:
                client = cdp.CDPClient(ws, timeout=1.5)
                try:
                    drain_tab_rpc(client)
                finally:
                    client.close()
    except Exception:
        pass


def inject_into_tabs(token=None, js_code=None, css_code=None, force=False):
    """Injects maclua.js and maclua.css into Steam Store tabs."""
    token = token or get_or_create_token()
    if js_code is None:
        js_path = os.path.join(os.path.dirname(__file__), "steamui", "maclua.js")
        if os.path.exists(js_path):
            with open(js_path, "r", encoding="utf-8") as f:
                js_code = f.read()
        else:
            js_code = "console.log('MacLua UI loaded');"

    if css_code is None:
        css_path = os.path.join(os.path.dirname(__file__), "steamui", "maclua.css")
        if os.path.exists(css_path):
            with open(css_path, "r", encoding="utf-8") as f:
                css_code = f.read()
        else:
            css_code = ""

    injected = []
    try:
        with urllib.request.urlopen(CDP_URL, timeout=1.0) as resp:
            tabs = json.loads(resp.read().decode("utf-8"))

        css_escaped = json.dumps(css_code)
        initial_games = get_managed_games()
        games_json = json.dumps(initial_games)

        bootstrap = f"""
        (function() {{
            window.__MACLUA = {{
                token: "{token}",
                base: "http://127.0.0.1:6767",
                initialGames: {games_json}
            }};
            if (!document.getElementById("maclua-injected-style")) {{
                var st = document.createElement("style");
                st.id = "maclua-injected-style";
                st.textContent = {css_escaped};
                (document.head || document.documentElement).appendChild(st);
            }}
        }})();
        """
        full_script = bootstrap + "\n" + js_code

        for t in tabs:
            url = t.get("url", "")
            ws = t.get("webSocketDebuggerUrl")
            # Inject exclusively into store tabs: never touch the library or internal interface
            if ws and "store.steampowered.com" in url:
                client = cdp.CDPClient(ws, timeout=2.0)
                try:
                    has_ver = client.evaluate("String(window.__MacLuaVersion)")
                    has_btn = client.evaluate("String(Boolean(document.getElementById('maclua-store-header-btn')))")
                    if force or has_ver != "10":
                        client.add_script_on_new_document(full_script)
                        client.evaluate(full_script)
                        injected.append({"id": t.get("id"), "url": url, "title": t.get("title")})
                    elif has_btn != "true":
                        client.evaluate("if (typeof window.ensureCartHeaderButton === 'function') window.ensureCartHeaderButton();")
                    drain_tab_rpc(client)
                finally:
                    client.close()
    except Exception as e:
        return {"ok": False, "error": str(e), "injected": injected}

    return {"ok": True, "injected_count": len(injected), "tabs": injected}


def bridge_agent_path(home=None):
    home = home or os.path.expanduser("~")
    return os.path.join(home, "Library/LaunchAgents/dev.maclua.bridge.plist")


def is_bridge_agent_installed(home=None):
    return os.path.exists(bridge_agent_path(home))


def install_bridge_agent(python_path=None, script_path=None, home=None):
    home = home or os.path.expanduser("~")
    plist_path = bridge_agent_path(home)
    os.makedirs(os.path.dirname(plist_path), exist_ok=True)
    py = python_path or sys.executable or "/usr/bin/python3"
    default_sc = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "maclua.py"))
    sc = script_path or default_sc

    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>dev.maclua.bridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>{py}</string>
        <string>{sc}</string>
        <string>bridge</string>
        <string>serve</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/maclua_bridge.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/maclua_bridge_err.log</string>
</dict>
</plist>
"""
    existing = None
    if os.path.exists(plist_path):
        try:
            with open(plist_path, "r", encoding="utf-8") as f:
                existing = f.read()
        except Exception:
            existing = None
    if existing != content:
        atomic_write(plist_path, content)
    import subprocess
    # IMPORTANT: NEVER call "launchctl unload" here!
    # When install_bridge_agent is invoked by enable_hook() / restart_steam()
    # inside the dev.maclua.bridge process itself, "launchctl unload" causes launchd
    # to immediately send SIGTERM to the bridge process, killing it before "launchctl load -w"
    # can run and leaving the service permanently unloaded.
    # "launchctl load -w" loads the agent if unloaded and is a safe no-op if already running.
    subprocess.run(["launchctl", "load", "-w", plist_path], capture_output=True)
    return {"ok": True, "path": plist_path}


def remove_bridge_agent(home=None):
    plist_path = bridge_agent_path(home)
    if os.path.exists(plist_path):
        import subprocess
        subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
        try:
            os.remove(plist_path)
        except OSError:
            pass
        return {"ok": True, "removed": True}
    return {"ok": True, "removed": False}

