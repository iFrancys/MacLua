"""Gestione dell'integrazione nativa in-client di Steam.
Attiva il debugging CEF (porta 8080) e inietta l'interfaccia MacLua (JS/CSS) nei tab dello Store e della Libreria.
Garantisce la reversibilità totale (disinstallazione pulita con prima/dopo manifest).
"""
import os
import json
import secrets
import urllib.request
from core import paths, cdp

HOOK_DIR = os.path.expanduser("~/Library/Application Support/MacLua")
TOKEN_FILE = os.path.join(HOOK_DIR, "bridge_token")
MANIFEST_FILE = os.path.join(HOOK_DIR, "hook_manifest.json")
CDP_URL = "http://127.0.0.1:8080/json"


def get_or_create_token():
    """Genera o recupera il token crittografico univoco per il bridge locale."""
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
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(token)
    os.chmod(TOKEN_FILE, 0o600)
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
    """Abilita l'integrazione Steam creando il marker CEF in tutte le posizioni note e registrando il manifest."""
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

    manifest = {
        "enabled": True,
        "created_markers": created_markers,
        "existed_markers": existed_markers,
    }
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return {"ok": True, "created": created_markers, "existed": existed_markers}


def disable_hook(home=None):
    """Rimuove l'integrazione Steam e ripristina lo stato precedente."""
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
        # Fallback se vecchio manifest
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

    manifest["enabled"] = False
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return {"ok": True, "removed": removed}


def restart_steam():
    """Riavvia Steam assicurando l'apertura con il flag di debug CEF (-cef-enable-debugging)."""
    import subprocess
    import time

    # Chiedi a Steam di chiudersi per salvare i dati
    subprocess.run(["/usr/bin/osascript", "-e", 'tell application "Steam" to quit'], capture_output=True)

    # Attendi che il processo termini effettivamente
    for _ in range(35):
        p = subprocess.run(["/usr/bin/pgrep", "steam_osx"], capture_output=True)
        if p.returncode != 0:
            break
        time.sleep(0.2)
    else:
        # Se non si chiude entro 7s, forza la terminazione
        subprocess.run(["/usr/bin/killall", "steam_osx"], capture_output=True)
        for _ in range(15):
            p = subprocess.run(["/usr/bin/pgrep", "steam_osx"], capture_output=True)
            if p.returncode != 0:
                break
            time.sleep(0.2)
        else:
            subprocess.run(["/usr/bin/killall", "-9", "steam_osx"], capture_output=True)
            time.sleep(0.5)

    time.sleep(0.5)
    subprocess.Popen(["/usr/bin/open", "-a", "Steam", "--args", "-cef-enable-debugging"])
    return {"ok": True, "restarted": True}


def get_status(home=None):
    """Controlla lo stato di attivazione, la presenza di Steam e la disponibilità della porta CDP."""
    home = home or os.path.expanduser("~")
    steam_dir = paths.steam_root(home)
    marker = os.path.join(steam_dir, ".cef-enable-remote-debugging")

    marker_present = os.path.exists(marker)
    cdp_available = False
    tabs = []

    try:
        req = urllib.request.Request(CDP_URL, headers={"User-Agent": "MacLua"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
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
        "tabs": tabs
    }


def handle_rpc_request(path, method="GET", data=None):
    """Gestisce localmente le chiamate RPC originate dallo script in-Steam via CDP."""
    home = os.path.expanduser("~")
    data = data or {}
    path = (path or "").rstrip("/")

    if path.startswith("/game/"):
        try:
            aid = int(path.split("/")[-1])
        except ValueError:
            return {"error": "AppID non valido"}
        from core import catalog, install
        name = catalog.name_of(aid) or f"Gioco {aid}"
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
            return {"ok": False, "error": "AppID mancante"}
        try:
            aid = int(aid)
        except ValueError:
            return {"ok": False, "error": "AppID non valido"}

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

            # Pulisce eventuali vecchi appmanifest fantasma (StateFlags 2 con size 0)
            steamapps_dir = paths.steamapps(home)
            install.cleanup_broken_appmanifests(steamapps_dir)

            from maclua import _ensure
            _ensure(home)

            vault.snapshot(target_id, fetched["lua"], note="Aggiunto da Steam")
            game_name = catalog.name_of(target_id) or f"Gioco {target_id}"

            try:
                broadcast_library_refresh(home)
            except Exception:
                pass

            return {
                "ok": True,
                "appid": target_id,
                "name": game_name,
                "source": fetched.get("source"),
                "message": f"Aggiunto {game_name}!"
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
                {"id": "sushi", "name": "Sushi (GitHub Raw - Gratuito)", "requires_key": False},
                {"id": "ryuu", "name": "Ryuu (Anonimo - Gratuito)", "requires_key": False},
                {"id": "hubcap", "name": "Hubcap / Morrenus (Richiede API Key)", "requires_key": True}
            ]
        }

    elif path.startswith("/check-sources"):
        try:
            aid = int(path.split("/")[-1]) if "/" in path[1:] else int(data.get("appid", 0))
        except ValueError:
            return {"ok": False, "error": "AppID non valido"}
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
        cleaned = install.cleanup_broken_appmanifests(paths.steamapps(home))
        return {"ok": True, "cleaned": cleaned, "count": len(cleaned)}

    elif path == "/library":
        from core import catalog, install, appinfo as ai
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
                        name = catalog.name_of(aid) or f"Gioco {aid}"
                        installed = install.is_game_installed(aid, home)
                        games.append({
                            "appid": aid,
                            "name": name,
                            "installed": installed,
                            "cover": f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg"
                        })
                    except Exception:
                        pass
        return {"ok": True, "games": games}

    elif path == "/remove":
        aid = data.get("appid")
        if not aid:
            return {"ok": False, "error": "AppID mancante"}
        try:
            aid = int(aid)
        except ValueError:
            return {"ok": False, "error": "AppID non valido"}

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
            broadcast_library_refresh(home)
        except Exception:
            pass

        g_name = catalog.name_of(target_id) or f"App {target_id}"
        return {
            "ok": True,
            "appid": target_id,
            "message": f"{g_name} rimosso da MacLua"
        }

    elif path == "/queue":
        from core import queue
        return queue.DownloadQueue.shared().get_status()

    elif path == "/restart-steam":
        return restart_steam()

    return {"ok": False, "error": f"Endpoint non supportato: {path}"}


def broadcast_library_refresh(home=None):
    """Notifica in tempo reale a SharedJSContext e ai tab della Libreria l'elenco aggiornato dei giochi gestiti."""
    home = home or os.path.expanduser("~")
    from core import catalog, install, appinfo as ai
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
                    name = catalog.name_of(aid) or f"Gioco {aid}"
                    installed = install.is_game_installed(aid, home)
                    games.append({
                        "appid": aid,
                        "name": name,
                        "installed": installed,
                    })
                except Exception:
                    pass

    try:
        req = urllib.request.Request(CDP_URL, headers={"User-Agent": "MacLua"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            tabs = json.loads(resp.read().decode("utf-8"))

        games_json = json.dumps(games)
        eval_script = f"if (typeof window.__MacLuaSyncLibrary === 'function') {{ window.__MacLuaSyncLibrary({games_json}); }}"

        for t in tabs:
            url = t.get("url", "")
            ws = t.get("webSocketDebuggerUrl")
            if ws and ("steamloopback.host" in url or "SharedJSContext" in t.get("title", "")):
                client = cdp.CDPClient(ws, timeout=2)
                try:
                    client.evaluate(eval_script)
                finally:
                    client.close()
    except Exception:
        pass
    return {"ok": True, "count": len(games)}


def drain_tab_rpc(client):
    """Verifica e drena le richieste RPC create dal client JS in Steam."""
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
    """Drena le richieste RPC da tutti i tab attivi di Steam."""
    try:
        req = urllib.request.Request(CDP_URL, headers={"User-Agent": "MacLua"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            tabs = json.loads(resp.read().decode("utf-8"))
        for t in tabs:
            url = t.get("url", "")
            ws = t.get("webSocketDebuggerUrl")
            if ws and ("store.steampowered.com" in url or "steamloopback.host" in url):
                client = cdp.CDPClient(ws, timeout=2)
                try:
                    drain_tab_rpc(client)
                finally:
                    client.close()
    except Exception:
        pass


def inject_into_tabs(token=None, js_code=None, css_code=None, force=False):
    """Inietta maclua.js e maclua.css in tutti i tab idonei di Steam (Store e Library)."""
    token = token or get_or_create_token()
    if js_code is None:
        js_path = os.path.join(os.path.dirname(__file__), "steamui", "maclua.js")
        if os.path.exists(js_path):
            with open(js_path, "r", encoding="utf-8") as f:
                js_code = f.read()
        else:
            js_code = "console.log('MacLua UI caricato');"

    if css_code is None:
        css_path = os.path.join(os.path.dirname(__file__), "steamui", "maclua.css")
        if os.path.exists(css_path):
            with open(css_path, "r", encoding="utf-8") as f:
                css_code = f.read()
        else:
            css_code = ""

    injected = []
    try:
        with urllib.request.urlopen(CDP_URL, timeout=2) as resp:
            tabs = json.loads(resp.read().decode("utf-8"))

        css_escaped = json.dumps(css_code)
        bootstrap = f"""
        (function() {{
            window.__MACLUA = {{
                token: "{token}",
                base: "http://127.0.0.1:6767"
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
            if ws and ("store.steampowered.com" in url or "steamloopback.host" in url):
                client = cdp.CDPClient(ws, timeout=3)
                try:
                    has_ver = client.evaluate("String(window.__MacLuaVersion)")
                    if force or has_ver != "4":
                        client.evaluate(full_script)
                        injected.append({"id": t.get("id"), "url": url, "title": t.get("title")})
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
    py = python_path or "/usr/bin/python3"
    sc = script_path or os.path.expanduser("~/Desktop/MacLua/maclua.py")

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
    with open(plist_path, "w", encoding="utf-8") as f:
        f.write(content)
    import subprocess
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

