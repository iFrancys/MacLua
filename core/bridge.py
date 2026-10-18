"""Local HTTP bridge server on 127.0.0.1:6767 with token authentication.
Exposes REST APIs and SSE streams for the in-Steam interface (JS).
All endpoints strictly respect the rule: DLCs are ALWAYS integrated into base games and never shown separately.
"""
import os
import json
import time
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from core import steamhook, settings, catalog, paths, appinfo as ai, install, queue, collections as coll_mod, updates, fixes, vault, config, license, depotkeys

PORT = 6767
ALLOWED_ORIGINS = {
    "https://store.steampowered.com",
    "https://steamloopback.host",
    "http://127.0.0.1:6767",
    "http://localhost:6767"
}

# In-memory state of the "stale licenses" remediation: protects against Steam restart loops.
_STALE_RESTART_COOLDOWN = 600.0   # minimum seconds between two automatic restarts
_MAX_STALE_RESTARTS = 2           # consecutive automatic restarts before stopping
# Sentinels `None`: 0.0 is not a valid time (time.monotonic() at uptime start
# is close to zero, e.g. after a boot: cooldown would trigger without any restart).
_STALE_STATE = {"last_restart": None, "consecutive_restarts": 0, "last_notify": None}


class BridgeHandler(BaseHTTPRequestHandler):
    def _send_cors(self):
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", "https://store.steampowered.com")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-MacLua-Token, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def _verify_auth(self):
        # Health check is public
        if self.path.split("?")[0] in ("/health", "/icon"):
            return True
        expected = steamhook.get_or_create_token()
        token = self.headers.get("X-MacLua-Token")
        if not token:
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            token = params.get("token", [None])[0]
        return token == expected

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._verify_auth():
            return self._send_json(401, {"error": "Unauthorized: missing or invalid token"})

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/health":
            return self._send_json(200, {"ok": True, "version": "1.0.0"})

        elif path == "/icon":
            icon_p = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "maclua_icon.png")
            if os.path.exists(icon_p):
                with open(icon_p, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self._send_cors()
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(content)
                return
            return self._send_json(404, {"error": "Icon not found"})

        elif path == "/status":
            home = os.path.expanduser("~")
            import maclua
            roots = maclua._root_games(home)
            appids, depots = maclua._managed_sets(home)
            return self._send_json(200, {
                "ok": True,
                "apps": sorted(roots),
                "depots": len(depots),
            })

        elif path == "/settings":
            return self._send_json(200, settings.get_all())

        elif path == "/search":
            q = params.get("q", [""])[0].strip()
            if not q:
                return self._send_json(200, {"results": []})
            hits = catalog.search(q, limit=20)
            resolved = []
            seen = set()
            for h in hits:
                appid = h["appid"]
                # If it's a DLC, resolve to base game
                parent_id = ai.parent(appid)
                if parent_id is None:
                    parent_id, _ = catalog.parent_of(appid)
                target_id = parent_id if parent_id else appid
                if target_id not in seen:
                    seen.add(target_id)
                    resolved.append({
                        "appid": target_id,
                        "name": catalog.name_of(target_id) or h["name"],
                        "cover": f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{target_id}/header.jpg",
                        "is_dlc_resolved": bool(parent_id and parent_id != appid)
                    })
            return self._send_json(200, {"results": resolved})

        elif path == "/library":
            home = os.path.expanduser("~")
            stplug = paths.stplug_in(home)
            games = []
            if os.path.exists(stplug):
                for fn in sorted(os.listdir(stplug)):
                    if fn.endswith(".lua"):
                        try:
                            appid = int(fn[:-4])
                            # Exclude if not a base game
                            p_id = ai.parent(appid)
                            if p_id is not None and p_id != appid:
                                continue
                            name = catalog.name_of(appid) or f"Game {appid}"
                            installed = install.is_game_installed(appid, home)
                            up_status = updates.get_status(appid, home) if installed else None
                            if installed and not up_status:
                                try:
                                    chk = updates.check_updates(appid, home=home)
                                    if chk:
                                        up_status = updates.set_status(appid, {
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
                                "appid": appid,
                                "name": name,
                                "installed": installed,
                                "update": up_status,
                                "cover": f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
                            })
                        except Exception:
                            pass
            return self._send_json(200, {"games": games})

        elif path == "/update-status":
            home = os.path.expanduser("~")
            return self._send_json(200, {"ok": True,
                                         "status": updates.load_status(home)})

        elif path == "/api-list":
            return self._send_json(200, {
                "ok": True,
                "sources": [
                    {"id": "auto", "name": "Auto (Sushi -> Ryuu -> Hubcap)", "requires_key": False},
                    {"id": "sushi", "name": "Sushi (GitHub Raw - Free)", "requires_key": False},
                    {"id": "ryuu", "name": "Ryuu (Anonymous - Free)", "requires_key": False},
                    {"id": "hubcap", "name": "Hubcap / Morrenus (Requires API Key)", "requires_key": True}
                ]
            })

        elif path.startswith("/check-sources"):
            try:
                aid = int(path.split("/")[-1])
            except ValueError:
                return self._send_json(400, {"error": "Invalid AppID"})
            from core import source
            ryuu_avail = source.check_ryuu(aid)
            sushi_avail = False
            try:
                source.fetch_from_sushi(aid, timeout=5)
                sushi_avail = True
            except Exception:
                pass
            return self._send_json(200, {
                "ok": True,
                "appid": aid,
                "sources": {
                    "sushi": sushi_avail,
                    "ryuu": ryuu_avail,
                    "hubcap": True
                }
            })

        elif path.startswith("/game/"):
            try:
                appid = int(path.split("/")[-1])
            except ValueError:
                return self._send_json(400, {"error": "Invalid AppID"})
            name = catalog.name_of(appid) or f"Game {appid}"
            home = os.path.expanduser("~")
            installed = install.is_game_installed(appid, home)
            managed = os.path.exists(os.path.join(paths.stplug_in(home), f"{appid}.lua"))
            fix_list = fixes.get_fixes(appid)
            snapshots = vault.list_snapshots(appid)
            return self._send_json(200, {
                "appid": appid,
                "name": name,
                "installed": installed,
                "managed": managed,
                "fixes": fix_list,
                "vault_snapshots": len(snapshots),
                "cover": f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
            })

        elif path == "/queue":
            q_status = queue.DownloadQueue.shared().get_status()
            return self._send_json(200, q_status)

        elif path.startswith("/depots/"):
            try:
                aid = int(path.split("/")[-1])
            except ValueError:
                return self._send_json(400, {"error": "Invalid AppID"})
            return self._send_json(200, get_game_depots(aid))

        elif path == "/depots":
            home = os.path.expanduser("~")
            stplug = paths.stplug_in(home)
            res = []
            if os.path.exists(stplug):
                for fn in sorted(os.listdir(stplug)):
                    if fn.endswith(".lua"):
                        try:
                            aid = int(fn[:-4])
                            p_id = ai.parent(aid)
                            if p_id is not None and p_id != aid:
                                continue
                            res.append(get_game_depots(aid, home))
                        except Exception:
                            pass
            return self._send_json(200, {"games_depots": res})

        elif path == "/collections":
            sort = params.get("sort", ["popular"])[0]
            data = coll_mod.fetch_collections(sort=sort)
            return self._send_json(200, data)

        elif path.startswith("/collections/"):
            slug = path.split("/")[-1]
            details = coll_mod.fetch_collection_details(slug)
            return self._send_json(200, details)

        elif path == "/events":
            # Server-Sent Events for real-time updates
            self.send_response(200)
            self._send_cors()
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                for _ in range(15):
                    st = queue.DownloadQueue.shared().get_status()
                    msg = f"data: {json.dumps(st)}\n\n"
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(1.0)
            except Exception:
                pass
            return

        return self._send_json(404, {"error": "Endpoint not found"})

    def do_POST(self):
        if not self._verify_auth():
            return self._send_json(401, {"error": "Unauthorized"})

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        if path == "/settings":
            for k, v in data.items():
                settings.set_val(k, v)
            return self._send_json(200, {"ok": True, "settings": settings.get_all()})

        elif path == "/add":
            appid = data.get("appid")
            if not appid:
                return self._send_json(400, {"error": "Missing appid"})
            # Resolve if DLC
            p_id = ai.parent(appid)
            if p_id is None:
                p_id, _ = catalog.parent_of(appid)
            target_id = p_id if p_id else appid

            home = os.path.expanduser("~")
            key = config.get_key(home) or settings.get("hubcap_key", "")
            pref = settings.get("preferred_source", "auto")
            auto_up = settings.get("auto_update_apps", True)

            from core import source
            try:
                fetched = source.fetch_from_sources(target_id, key=key, preferred_source=pref, auto_update=auto_up)
                install.import_lua(target_id, fetched["lua"], fetched["manifests"], home)

                # Clean up potential stale ghost appmanifests (StateFlags 2 with size 0)
                steamapps_dir = paths.steamapps(home)
                install.cleanup_broken_appmanifests(steamapps_dir)

                # Synchronize licenses, keys, and manifests for Steam
                from maclua import _ensure
                _ensure(home)
                # Save snapshot in vault
                vault.snapshot(target_id, fetched["lua"], note="Automatic in-Steam import")

                try:
                    steamhook.broadcast_library_refresh(home)
                except Exception:
                    pass
            except Exception as e:
                return self._send_json(500, {"error": f"Error during addition: {str(e)}"})

            return self._send_json(200, {
                "ok": True,
                "appid": target_id,
                "source": fetched.get("source"),
                "dlc_resolved": bool(p_id and p_id != appid),
                "message": f"Added {target_id} ({fetched.get('source', 'Multi-Source')}) with all DLCs included."
            })

        elif path == "/cleanup-manifests":
            home = os.path.expanduser("~")
            steamapps_dir = paths.steamapps(home)
            cleaned = install.cleanup_broken_appmanifests(steamapps_dir)
            reconciled = install.reconcile_installed_appmanifests(steamapps_dir, home=home)
            try:
                steamhook.sync_library_in_steam(home)
            except Exception:
                pass
            return self._send_json(200, {"ok": True, "cleaned": cleaned, "reconciled": reconciled, "count": len(cleaned) + len(reconciled)})

        elif path == "/update":
            appid = data.get("appid")
            if not appid:
                return self._send_json(400, {"error": "Missing appid"})
            home = os.path.expanduser("~")
            # Tracked update: the real outcome is stored in updates.json
            # (visible via /update-status), avoiding silent failures.
            try:
                res = updates.request_update(appid, home=home)
            except Exception as e:
                return self._send_json(500, {"error": f"Update error: {e}"})
            return self._send_json(200, res)

        elif path == "/remove":
            appid = data.get("appid")
            if not appid:
                return self._send_json(400, {"error": "Missing appid"})
            p_id = ai.parent(appid)
            if p_id is None:
                p_id, _ = catalog.parent_of(appid)
            target_id = p_id if p_id else appid

            home = os.path.expanduser("~")
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
                steamhook.remove_from_steam_library(target_id, home)
                steamhook.broadcast_library_refresh(home)
            except Exception:
                pass

            g_name = catalog.name_of(target_id) or f"App {target_id}"
            return self._send_json(200, {"ok": True, "appid": target_id, "message": f"{g_name} removed from MacLua"})

        elif path == "/install":
            appid = data.get("appid")
            if not appid:
                return self._send_json(400, {"error": "Missing appid"})
            added = queue.DownloadQueue.shared().enqueue(appid, name=catalog.name_of(appid))
            return self._send_json(200, {"ok": added, "appid": appid})

        elif path == "/cancel":
            appid = data.get("appid")
            if not appid:
                return self._send_json(400, {"error": "Missing appid"})
            queue.DownloadQueue.shared().cancel(appid)
            return self._send_json(200, {"ok": True, "appid": appid})

        elif path == "/update-check":
            appid = data.get("appid")
            if not appid:
                return self._send_json(400, {"error": "Missing appid"})
            up_info = updates.check_updates(appid)
            return self._send_json(200, up_info)

        elif path == "/collections/add":
            slug = data.get("id")
            if not slug:
                return self._send_json(400, {"error": "Collection id required"})
            details = coll_mod.fetch_collection_details(slug)
            apps = details.get("apps", [])
            enqueued = []
            for a in apps:
                p_id = ai.parent(a)
                target_id = p_id if p_id else a
                queue.DownloadQueue.shared().enqueue(target_id, name=catalog.name_of(target_id))
                enqueued.append(target_id)
            return self._send_json(200, {"ok": True, "collection": slug, "enqueued": enqueued})

        elif path == "/restart-steam":
            res = steamhook.restart_steam()
            return self._send_json(200, res)

        return self._send_json(404, {"error": "Endpoint not found"})

    def log_message(self, format, *args):
        # Silence standard HTTP logs for clean output
        pass


def get_game_depots(appid, home=None):
    """Returns the complete list of depots for an app (inspired by LuaTools BuildsView).
    DLCs are strictly integrated: DLC depots belong to the base game.
    """
    home = home or os.path.expanduser("~")
    lua_path = os.path.join(paths.stplug_in(home), f"{appid}.lua")
    lua_data = {"keys": {}, "manifests": {}}
    if os.path.exists(lua_path):
        try:
            from core import lua
            with open(lua_path, "r", encoding="utf-8") as f:
                lua_data = lua.parse_lua(f.read())
        except Exception:
            pass

    app_depots = ai.depots(appid)
    by_id = {d["id"]: d for d in app_depots}

    all_depot_ids = set(lua_data["keys"].keys()) | set(lua_data["manifests"].keys()) | set(by_id.keys())
    all_depot_ids.discard(appid)

    all_keys = depotkeys.collect_keys(paths.stplug_in(home))
    keys_map = {dep: keyhex for dep, (_, keyhex) in all_keys.items()}

    store_dir = paths.sls_manifests(home)
    depotcache_dir = paths.depotcache(home)

    depot_list = []
    for did in sorted(all_depot_ids):
        info = by_id.get(did, {})
        os_target = info.get("oslist", "")
        gid = lua_data["manifests"].get(did) or info.get("gid")
        size = info.get("size")
        has_key = (did in lua_data["keys"]) or (did in keys_map)

        has_manifest = False
        if gid:
            for d in (store_dir, depotcache_dir):
                if os.path.exists(os.path.join(d, f"{did}_{gid}.manifest")):
                    has_manifest = True
                    break

        name = catalog.name_of(did) or f"Depot {did}"
        p_id, _ = catalog.parent_of(did)
        is_dlc = bool(p_id and p_id == appid)

        depot_list.append({
            "depot_id": did,
            "name": name,
            "os": os_target if os_target else ("all" if info.get("shared") else "content"),
            "gid": str(gid) if gid else "-",
            "size": size or 0,
            "size_str": f"{round(size / 1e6, 1)} MB" if size else "-",
            "has_key": has_key,
            "has_manifest": has_manifest,
            "is_dlc": is_dlc
        })

    return {
        "appid": appid,
        "name": catalog.name_of(appid) or f"Game {appid}",
        "depots_count": len(depot_list),
        "depots": depot_list
    }


def check_stale_client_licenses(home=None):
    """Detects "stale" licenses in the running Steam client and REMEDIES them automatically.

    The client only adopts packageinfo.vdf on startup: if the file on disk is
    valid but managed and installed games do not appear licensed in the running
    client (common after MacLua re-patches licenses while Steam is running),
    the only remedy is restarting Steam. Here:
    - ALL managed+installed games are checked (not just a single sample);
    - if needed, Steam is restarted automatically ONLY when safe
      (no game running) and if the auto_restart_steam setting is active;
    - with games running or after too many failed attempts: notify and stop
      (never a restart loop).

    Returns a dict with the outcome; False when there is nothing to do.
    """
    home = home or os.path.expanduser("~")
    if not steamhook.is_cdp_available(0.1):
        return False
    games = steamhook.get_managed_games(home)
    installed = [g for g in games if g.get("installed")]
    if not installed:
        return False

    stale = []
    for g in installed[:20]:
        if steamhook.client_app_licensed(g["appid"]) is False:
            stale.append(int(g["appid"]))
    if not stale:
        _STALE_STATE["consecutive_restarts"] = 0
        return False

    pkginfo = os.path.join(paths.appcache(home), "packageinfo.vdf")
    if not os.path.exists(pkginfo):
        return False

    import maclua
    appids, depots = maclua._managed_sets(home)
    m_app, m_dep = license.check(pkginfo, appids, depots)
    if m_app or m_dep:
        # The file itself is incomplete: handled by sentinel, not user.
        return False

    now = time.monotonic()

    def _notify_throttled(msg):
        if _STALE_STATE["last_notify"] is None or now - _STALE_STATE["last_notify"] >= 1800:
            steamhook.notify_macos("MacLua", msg)
            _STALE_STATE["last_notify"] = now

    if (_STALE_STATE["last_restart"] is not None
            and now - _STALE_STATE["last_restart"] < _STALE_RESTART_COOLDOWN):
        return {"stale": stale, "restarted": False, "reason": "cooldown"}

    if _STALE_STATE["consecutive_restarts"] >= _MAX_STALE_RESTARTS:
        _notify_throttled(
            "Steam is using outdated licenses: restart it manually "
            "(Restart Steam button in MacLua banner).")
        return {"stale": stale, "restarted": False, "reason": "limit"}

    running = steamhook.running_managed_appids(home)
    if running:
        _notify_throttled(
            "A game is running and Steam is using outdated licenses: "
            "restart Steam once finished playing.")
        return {"stale": stale, "restarted": False, "reason": "game_running"}

    if not settings.get("auto_restart_steam", True):
        _notify_throttled(
            "Steam is using outdated licenses: restart it to launch "
            "games (Restart Steam button in MacLua banner).")
        return {"stale": stale, "restarted": False, "reason": "setting_off"}

    steamhook.notify_macos(
        "MacLua",
        "Outdated Steam licenses: restarting Steam automatically to apply them.")
    steamhook.restart_steam()
    _STALE_STATE["last_restart"] = now
    _STALE_STATE["consecutive_restarts"] += 1
    return {"stale": stale, "restarted": True}


def start_continuous_injector_daemon():
    """Starts dedicated daemon threads:
    1. MacLuaTabRpcDaemon: ultra-fast loop (150ms) for Store tab RPC and injection.
    2. MacLuaSentinelDaemon: loop (500ms) for packageinfo.vdf sentinel and periodic library sync.
    """
    def _tab_rpc_loop():
        while True:
            try:
                if steamhook.is_cdp_available(0.1):
                    steamhook.drain_all_tabs_rpc()
                    steamhook.inject_into_tabs()
            except Exception:
                pass
            time.sleep(0.15)

    def _sentinel_loop():
        home = os.path.expanduser("~")
        try:
            import maclua
            maclua._ensure(home)
        except Exception:
            pass

        tick = 0
        last_pkginfo_mtime = 0.0
        last_library_sync = 0.0
        pkginfo = os.path.join(paths.appcache(home), "packageinfo.vdf")

        while True:
            try:
                now = time.monotonic()
                # 1. License sentinel: monitor packageinfo.vdf mtime
                if os.path.exists(pkginfo):
                    try:
                        cur_mtime = os.path.getmtime(pkginfo)
                        if cur_mtime != last_pkginfo_mtime or tick % 20 == 0:
                            last_pkginfo_mtime = cur_mtime
                            import maclua
                            from core import license
                            appids, depots = maclua._managed_sets(home)
                            m_app, m_dep = license.check(pkginfo, appids, depots)
                            has_forge = license.has_forged_package(pkginfo) if appids else True
                            if m_app or m_dep or not has_forge:
                                maclua._ensure(home)
                                last_pkginfo_mtime = os.path.getmtime(pkginfo)
                                if steamhook.is_cdp_available(0.1):
                                    steamhook.sync_library_in_steam(home)
                    except Exception:
                        pass

                # 2. Library synchronization in SharedJSContext (only if CDP is ready)
                if (tick < 10 or (now - last_library_sync) >= 10.0) and steamhook.is_cdp_available(0.1):
                    res = steamhook.sync_library_in_steam(home)
                    if res and res.get("ok"):
                        last_library_sync = now

                # 3. Client stale license check every 5 minutes: if file on disk
                #    is valid but client does not see licenses, restart Steam
                #    automatically (with anti-loop guards and running games check).
                if tick > 0 and tick % 600 == 0:
                    try:
                        check_stale_client_licenses(home)
                    except Exception:
                        pass

                # 4. Update watcher every 10 minutes: applies updates automatically
                #    when manifests are available, with retries and status in updates.json.
                if tick % 1200 == 0:
                    try:
                        updates.background_tick(home)
                    except Exception:
                        pass
            except Exception:
                pass
            tick += 1
            time.sleep(0.5)

    t1 = threading.Thread(target=_tab_rpc_loop, daemon=True, name="MacLuaTabRpcDaemon")
    t1.start()
    t2 = threading.Thread(target=_sentinel_loop, daemon=True, name="MacLuaSentinelDaemon")
    t2.start()


def run_bridge_server(port=PORT):
    start_continuous_injector_daemon()
    server = HTTPServer(("127.0.0.1", port), BridgeHandler)
    server.serve_forever()

