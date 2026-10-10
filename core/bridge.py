"""Server bridge HTTP locale su 127.0.0.1:6767 con autenticazione via token.
Espone le API REST e stream SSE per l'interfaccia in-Steam (JS) e l'app nativa MacLua (Swift).
Tutti gli endpoint rispettano rigorosamente la regola: i DLC sono SEMPRE integrati nei giochi base e mai mostrati separatamente.
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
        # Health check è pubblico
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

    def do_GET(self):
        if not self._verify_auth():
            return self._send_json(401, {"error": "Non autorizzato: token mancante o errato"})

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
                # Se è un DLC, risolvi al gioco base
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
                            # Escludi se non è gioco base
                            p_id = ai.parent(appid)
                            if p_id is not None and p_id != appid:
                                continue
                            name = catalog.name_of(appid) or f"Gioco {appid}"
                            installed = install.is_game_installed(appid, home)
                            games.append({
                                "appid": appid,
                                "name": name,
                                "installed": installed,
                                "cover": f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
                            })
                        except Exception:
                            pass
            return self._send_json(200, {"games": games})

        elif path == "/api-list":
            return self._send_json(200, {
                "ok": True,
                "sources": [
                    {"id": "auto", "name": "Auto (Sushi -> Ryuu -> Hubcap)", "requires_key": False},
                    {"id": "sushi", "name": "Sushi (GitHub Raw - Gratuito)", "requires_key": False},
                    {"id": "ryuu", "name": "Ryuu (Anonimo - Gratuito)", "requires_key": False},
                    {"id": "hubcap", "name": "Hubcap / Morrenus (Richiede API Key)", "requires_key": True}
                ]
            })

        elif path.startswith("/check-sources"):
            try:
                aid = int(path.split("/")[-1])
            except ValueError:
                return self._send_json(400, {"error": "AppID non valido"})
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
                return self._send_json(400, {"error": "AppID non valido"})
            name = catalog.name_of(appid) or f"Gioco {appid}"
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
                return self._send_json(400, {"error": "AppID non valido"})
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
            # Server-Sent Events per aggiornamenti in tempo reale
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

        return self._send_json(404, {"error": "Endpoint non trovato"})

    def do_POST(self):
        if not self._verify_auth():
            return self._send_json(401, {"error": "Non autorizzato"})

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
                return self._send_json(400, {"error": "Serve appid"})
            # Risolvi se è DLC
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

                # Pulisce eventuali vecchi appmanifest fantasma (StateFlags 2 con size 0)
                steamapps_dir = paths.steamapps(home)
                install.cleanup_broken_appmanifests(steamapps_dir)

                # Sincronizza licenze, chiavi e manifest per Steam
                from maclua import _ensure
                _ensure(home)
                # Salva snapshot nel vault
                vault.snapshot(target_id, fetched["lua"], note="Importazione automatica in-Steam")

                from core import steamhook
                try:
                    steamhook.broadcast_library_refresh(home)
                except Exception:
                    pass
            except Exception as e:
                return self._send_json(500, {"error": f"Errore durante l'aggiunta: {str(e)}"})

            return self._send_json(200, {
                "ok": True,
                "appid": target_id,
                "source": fetched.get("source"),
                "dlc_resolved": bool(p_id and p_id != appid),
                "message": f"Aggiunto {target_id} ({fetched.get('source', 'Multi-Source')}) con tutti i DLC inclusi."
            })

        elif path == "/cleanup-manifests":
            home = os.path.expanduser("~")
            cleaned = install.cleanup_broken_appmanifests(paths.steamapps(home))
            return self._send_json(200, {"ok": True, "cleaned": cleaned, "count": len(cleaned)})

        elif path == "/remove":
            appid = data.get("appid")
            if not appid:
                return self._send_json(400, {"error": "Serve appid"})
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

            from core import steamhook
            try:
                steamhook.broadcast_library_refresh(home)
            except Exception:
                pass

            g_name = catalog.name_of(target_id) or f"App {target_id}"
            return self._send_json(200, {"ok": True, "appid": target_id, "message": f"{g_name} rimosso da MacLua"})

        elif path == "/install":
            appid = data.get("appid")
            if not appid:
                return self._send_json(400, {"error": "Serve appid"})
            added = queue.DownloadQueue.shared().enqueue(appid, name=catalog.name_of(appid))
            return self._send_json(200, {"ok": added, "appid": appid})

        elif path == "/cancel":
            appid = data.get("appid")
            if not appid:
                return self._send_json(400, {"error": "Serve appid"})
            queue.DownloadQueue.shared().cancel(appid)
            return self._send_json(200, {"ok": True, "appid": appid})

        elif path == "/update-check":
            appid = data.get("appid")
            if not appid:
                return self._send_json(400, {"error": "Serve appid"})
            up_info = updates.check_updates(appid)
            return self._send_json(200, up_info)

        elif path == "/collections/add":
            slug = data.get("id")
            if not slug:
                return self._send_json(400, {"error": "Serve id della collezione"})
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

        return self._send_json(404, {"error": "Endpoint non trovato"})

    def log_message(self, format, *args):
        # Silenzia i log HTTP standard per pulizia output
        pass


def get_game_depots(appid, home=None):
    """Ritorna l'elenco completo dei depot per un'app (ispirato a BuildsView di LuaTools).
    I DLC sono rigorosamente integrati: i depot dei DLC appartengono al gioco base.
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
        "name": catalog.name_of(appid) or f"Gioco {appid}",
        "depots_count": len(depot_list),
        "depots": depot_list
    }


def start_continuous_injector_daemon():
    """Avvia il thread demone per monitorare e gestire Steam continuamente (RPC rapido a 200ms e iniezione a 1s)."""
    def _loop():
        home = os.path.expanduser("~")
        try:
            import maclua
            maclua._ensure(home)
        except Exception:
            pass

        tick = 0
        while True:
            try:
                steamhook.drain_all_tabs_rpc()
                if tick % 5 == 0:
                    steamhook.inject_into_tabs()
                # Verifica salute packageinfo.vdf ogni ~10s (50 tick)
                if tick % 50 == 0:
                    try:
                        import maclua
                        from core import license
                        pkginfo = os.path.join(paths.appcache(home), "packageinfo.vdf")
                        if os.path.exists(pkginfo):
                            appids, depots = maclua._managed_sets(home)
                            m_app, m_dep = license.check(pkginfo, appids, depots)
                            if m_app or m_dep:
                                maclua._ensure(home)
                    except Exception:
                        pass
            except Exception:
                pass
            tick += 1
            time.sleep(0.2)

    t = threading.Thread(target=_loop, daemon=True, name="MacLuaInjectorDaemon")
    t.start()


def run_bridge_server(port=PORT):
    start_continuous_injector_daemon()
    server = HTTPServer(("127.0.0.1", port), BridgeHandler)
    server.serve_forever()

