"""Gestione dell'integrazione nativa in-client di Steam.
Attiva il debugging CEF (porta 8080) e inietta l'interfaccia MacLua (JS/CSS) nei tab dello Store e della Libreria.
Garantisce la reversibilità totale (disinstallazione pulita con prima/dopo manifest).
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
    """Verifica velocemente via socket TCP se la porta CDP 8080 è aperta (latenza <1ms)."""
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
    """Abilita l'integrazione Steam creando il marker CEF in tutte le posizioni note, installando il LaunchAgent e registrando il manifest."""
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

    # Assicura che il daemon del bridge sia sempre attivo e registrato come LaunchAgent
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
    """Rimuove l'integrazione Steam, disinstalla il LaunchAgent e ripristina lo stato precedente."""
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

    # Rimuovi e scarica il LaunchAgent del bridge
    agent_removed = remove_bridge_agent(home=home)

    manifest["enabled"] = False
    manifest["bridge_agent"] = None
    atomic_write(MANIFEST_FILE, json.dumps(manifest, indent=2))

    return {"ok": True, "removed": removed, "agent_removed": agent_removed}


def restart_steam():
    """Riavvia Steam assicurando l'apertura con il flag di debug CEF (-cef-enable-debugging)."""
    import subprocess
    import time

    # Assicura che i marker di debug siano presenti su disco
    enable_hook()

    # Chiedi a Steam di chiudersi per salvare i dati
    subprocess.run(["/usr/bin/osascript", "-e", 'tell application "Steam" to quit'], capture_output=True)

    # Attendi che il processo termini effettivamente
    for _ in range(35):
        p1 = subprocess.run(["/usr/bin/pgrep", "-f", "Steam.AppBundle"], capture_output=True)
        p2 = subprocess.run(["/usr/bin/pgrep", "-x", "Steam"], capture_output=True)
        p3 = subprocess.run(["/usr/bin/pgrep", "steam_osx"], capture_output=True)
        if p1.returncode != 0 and p2.returncode != 0 and p3.returncode != 0:
            break
        time.sleep(0.2)
    else:
        # Se non si chiude entro 7s, forza la terminazione
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

    # Prima di riaprire Steam (mentre è completamente chiuso e non può più
    # sovrascrivere packageinfo.vdf in chiusura), riallinea licenze e chiavi.
    try:
        import maclua
        maclua._ensure(os.path.expanduser("~"))
    except Exception:
        pass

    time.sleep(0.5)
    subprocess.Popen(["/usr/bin/open", "-a", "Steam", "--args", "-cef-enable-debugging"])
    return {"ok": True, "restarted": True}


def notify_macos(title, message):
    """Mostra una notifica nativa macOS (usata per avvisare che Steam va riavviato per le licenze)."""
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
    """Interroga il client Steam in esecuzione (SharedJSContext) sul possesso di un'app.
    Ritorna True/False, oppure None se il client non è raggiungibile (CDP assente o Steam chiuso)."""
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
    """AppID dei giochi gestiti con un processo in esecuzione (per non riavviare
    Steam mentre si gioca).

    Euristica robusta su macOS: il processo del gioco contiene nel proprio
    command line il path `steamapps/common/<installdir>`. In caso di dubbio
    (pattern pgrep non valido) si è conservativi e si considera il gioco attivo.
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
            # Pattern non interpretabile: prudenza, trattalo come attivo.
            running.append(appid)
    return running


def get_status(home=None):
    """Controlla lo stato di attivazione, la presenza di Steam e la disponibilità della porta CDP."""
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
            return {"ok": False, "error": "AppID mancante"}
        try:
            aid = int(aid)
        except ValueError:
            return {"ok": False, "error": "AppID non valido"}
        from core import updates
        # Aggiornamento tracciato: l'esito reale finisce in updates.json
        # (visibile via /update-status), mai più fallimenti silenziosi.
        try:
            return updates.request_update(aid, home=home)
        except Exception as e:
            return {"ok": False, "error": f"Errore aggiornamento: {e}"}

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
                        name = catalog.name_of(aid) or f"Gioco {aid}"
                        installed = install.is_game_installed(aid, home)
                        games.append({
                            "appid": aid,
                            "name": name,
                            "installed": installed,
                            "update": updates.get_status(aid, home) if installed else None,
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
            remove_from_steam_library(target_id, home)
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


def get_managed_games(home=None):
    """Ritorna la lista dei giochi gestiti da stplug-in in modo immediato senza I/O bloccante."""
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
                        name = f"Gioco {aid}"
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
    """Sincronizza in modo pulito e sicuro i giochi gestiti in SharedJSContext di Steam.
    - Riconcilia prima eventuali appmanifest bloccati da aggiornamenti PICS (StateFlags 6 -> 4).
    - Imposta visible_in_game_list = true e subscribed_to = true su appStore per tutti i giochi gestiti.
    - Per i giochi installati, assicura stato pronto (installed: true, display_status: 11 'GIOCA').
    - Per i giochi non installati, assicura stato pulito (installed: false, display_status: 9 'INSTALLA').

    Tutte le modifiche avvengono assegnando normalmente le proprietà osservabili di appStore:
    MobX notifica automaticamente observer e reazioni, quindi la UI si aggiorna da sola.
    Non vengono mai toccati i simboli/simboli privati interni di MobX (value_, dependenciesState_,
    onBecomeStale_) né il fiber di React, perché ciò corrompe il grafo delle dipendenze e fa crashare
    l'Error Boundary della libreria di Steam.
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
            return {"ok": False, "error": "SharedJSContext non disponibile"}

        client = cdp.CDPClient(shared_tab["webSocketDebuggerUrl"], timeout=2)
        try:
            aids_json = json.dumps(all_managed_aids)
            installed_json = json.dumps(installed_aids)
            uninstalled_json = json.dumps(uninstalled_aids)

            script = f"""
            (() => {{
                const appStore = window.appStore;
                if (!appStore) return JSON.stringify({{ ok: false, error: "Stores non pronti" }});
                // Avvio a freddo: non toccare nulla finché Steam non ha completato la propria
                // inizializzazione, altrimenti si rischia di avvelenare i computed MobX.
                if (appStore.m_bIsInitialized !== true || !appStore.m_mapApps) {{
                    return JSON.stringify({{ ok: false, error: "appStore non ancora inizializzato" }});
                }}
                const csRaw = window.collectionStore ? window.collectionStore.m_mapCollectionsFromStorage : null;
                const collectionsReady = !!(csRaw && typeof csRaw.values === 'function' && csRaw.size > 0);

                const allManaged = {aids_json};
                const installedSet = new Set({installed_json});
                const uninstalled = new Set({uninstalled_json});
                window.__macluaManagedSet = new Set(allManaged);

                // Protegge visible_in_game_list e subscribed_to da reset asincroni
                // causati da UpdateAppOverview -> AppOverview.prototype.InitFromProto
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

                // Sincronizza SOLO le collezioni utente "Lua" usando i metodi pubblici nativi di Steam
                // (ClearAppCounts + SetApps + Save), senza mai toccare i simboli privati interni di MobX.
                //
                // IMPORTANTE: non leggere MAI i getter computed di collectionStore
                // (uncategorizedCollection, userCollections, collectionsFromStorage, ...).
                // Dipendono dal campo NON osservabile m_mapCollectionsFromStorage, che Steam imposta
                // solo a inizializzazione completata: se vengono calcolati prima (avvio a freddo),
                // MobX memorizza l'eccezione "reading 'forEach'" nel computed e la libreria resta
                // rotta ("Something went wrong while displaying this content") fino al riavvio di Steam.
                // Si legge quindi direttamente la mappa grezza, e solo quando esiste.
                //
                // Oltre al caso di nuove aggiunte (colChanged), se visible_in_game_list dei giochi
                // non installati è appena stato ripristinato (modifiedCount > 0) o visibleApps / i
                // conteggi filtrati della collezione sono rimasti indietro rispetto ad allApps
                // (perché visible_in_game_list non è osservabile in MobX), si ricalcolano SetApps e
                // ClearAppCounts così la sidebar mostra tutti i giochi Lua (scaricati e non scaricati).
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
            res = json.loads(res_str) if res_str else {"ok": False, "error": "Nessuna risposta"}
        finally:
            client.close()

        return res
    except Exception as e:
        return {"ok": False, "error": str(e)}


def remove_from_steam_library(appid, home=None):
    """Rimuove un gioco da SharedJSContext di Steam quando rimosso da MacLua."""
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
    """Notifica che la libreria gestita è stata aggiornata e sincronizza SharedJSContext."""
    home = home or os.path.expanduser("~")
    games = get_managed_games(home)
    try:
        sync_library_in_steam(home)
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
    """Drena le richieste RPC dal tab attivo dello Store di Steam."""
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
    """Inietta maclua.js e maclua.css nei tab dello Store di Steam."""
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
            # Inietta solo ed esclusivamente nei tab dello store: non toccare mai la libreria o l'interfaccia interna
            if ws and "store.steampowered.com" in url:
                client = cdp.CDPClient(ws, timeout=2.0)
                try:
                    has_ver = client.evaluate("String(window.__MacLuaVersion)")
                    has_btn = client.evaluate("String(Boolean(document.getElementById('maclua-store-header-btn')))")
                    if force or has_ver != "9":
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
    # IMPORTANTE: NON chiamare mai "launchctl unload" qui!
    # Quando install_bridge_agent viene invocato da enable_hook() / restart_steam()
    # dentro il processo dev.maclua.bridge stesso, "launchctl unload" fa sì che launchd
    # invii immediatamente SIGTERM al processo bridge, uccidendolo prima che "launchctl load -w"
    # possa essere eseguito e lasciando il servizio scaricato permanentemente.
    # "launchctl load -w" carica l'agente se è scaricato ed è un no-op sicuro se è già attivo.
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

