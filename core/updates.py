"""Controllo e applicazione aggiornamenti in-place per giochi base e nuovi DLC.
Confronta la build/manifest realmente installati su disco con quelli pubblici PICS
e applica aggiornamenti delta in-place senza disinstallare né perdere dati.

Include lo stato persistente degli aggiornamenti (`updates.json`) e il watcher
di background: finché una sorgente non pubblica i manifest della nuova build,
MacLua ritenta da sola con backoff e lo dice chiaramente nella UI — mai
fallimenti silenziosi.
"""
import os
import re
import time

from core import paths, appinfo as ai, install
from core.atomic import atomic_write, FileLock

RETRY_INTERVAL = 1800  # 30 minuti di backoff quando i manifest non sono ancora disponibili


def _status_path(home):
    return os.path.join(paths.maclua_dir(home), "updates.json")


def _update_lock_path(home, appid):
    return os.path.join(paths.maclua_dir(home), "update_%d.lock" % int(appid))


def load_status(home=None):
    """{appid: entry} con lo stato reale di ogni aggiornamento gestito."""
    import json
    home = home or os.path.expanduser("~")
    try:
        with open(_status_path(home), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get_status(appid, home=None):
    return load_status(home).get(str(int(appid)))


def set_status(appid, entry, home=None):
    import json
    home = home or os.path.expanduser("~")
    status = load_status(home)
    status[str(int(appid))] = entry
    try:
        atomic_write(_status_path(home), json.dumps(status, indent=2,
                                                    ensure_ascii=False))
    except OSError:
        pass
    return entry


def get_installed_buildid(steamapps_dir, appid, store_dir=None):
    """Legge il buildid reale registrato in .installed_<appid>.json o nell'appmanifest."""
    if store_dir:
        st = install.read_installed_state(store_dir, appid)
        if st and st.get("buildid"):
            return int(st["buildid"])
    acf_path = os.path.join(steamapps_dir, f"appmanifest_{appid}.acf")
    if not os.path.exists(acf_path):
        return None
    try:
        with open(acf_path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
        m = re.search(r'"buildid"\s+"(\d+)"', txt)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def check_updates(appid, home=None):
    """Verifica se per un appid è disponibile un aggiornamento di gioco o nuovi DLC."""
    home = home or os.path.expanduser("~")
    appid = int(appid)
    steamapps = paths.steamapps(home)
    store_dir = paths.sls_manifests(home)
    depotcache_dir = paths.depotcache(home)

    current_b = get_installed_buildid(steamapps, appid, store_dir=store_dir)
    public_b = ai.public_buildid(appid)

    has_game_update = False
    if current_b is not None and public_b is not None and public_b > current_b:
        has_game_update = True

    acf_path = os.path.join(steamapps, f"appmanifest_{appid}.acf")
    depot_status = {"installed": {}, "live": {}, "available": False}
    manifest_ready = True
    if os.path.exists(acf_path):
        try:
            with open(acf_path, "r", encoding="utf-8", errors="replace") as f:
                acf_txt = f.read()
            app_depots = ai.depots(appid)
            depot_status = install.update_check(acf_txt, app_depots, store_dir=store_dir, appid=appid)
            if depot_status.get("available"):
                has_game_update = True
            for dep, live_gid in (depot_status.get("live") or {}).items():
                if dep in (depot_status.get("installed") or {}):
                    if not (
                        os.path.exists(os.path.join(store_dir, f"{dep}_{live_gid}.manifest"))
                        or os.path.exists(os.path.join(depotcache_dir, f"{dep}_{live_gid}.manifest"))
                    ):
                        manifest_ready = False
        except Exception:
            pass

    # Verifica nuovi DLC analizzando il lua installato vs appinfo
    lua_path = os.path.join(paths.stplug_in(home), f"{appid}.lua")
    new_dlcs = []
    if os.path.exists(lua_path):
        try:
            with open(lua_path, "r", encoding="utf-8", errors="replace") as f:
                lua_txt = f.read()
            dlcs = ai.listofdlc(appid)
            for d_id in dlcs:
                if f"addappid({d_id}" not in lua_txt:
                    new_dlcs.append(d_id)
        except Exception:
            pass

    return {
        "appid": appid,
        "current_buildid": current_b,
        "latest_buildid": public_b,
        "has_update": has_game_update or bool(new_dlcs),
        "game_update": has_game_update,
        "manifest_ready": manifest_ready,
        "depots": depot_status,
        "new_dlcs": new_dlcs,
    }


def apply_update(appid, home=None, workers=8, progress=None):
    """Scarica gli ultimi manifest disponibili dalle sorgenti e applica l'aggiornamento delta
    in-place ai file del gioco senza disinstallare né perdere alcun salvataggio."""
    from core import config, settings, source
    import maclua

    home = home or os.path.expanduser("~")
    appid = int(appid)
    key = config.get_key(home) or settings.get("hubcap_key", "")
    pref = settings.get("preferred_source", "auto")

    try:
        app_depots = list(ai.depots(appid))
    except Exception:
        app_depots = []

    lua_path = os.path.join(paths.stplug_in(home), f"{appid}.lua")
    keyed_depots = None
    if os.path.exists(lua_path):
        try:
            from core.lua import parse_lua
            with open(lua_path, "r", encoding="utf-8", errors="replace") as f:
                keyed_depots = set(parse_lua(f.read()).get("keys", {}).keys())
        except Exception:
            keyed_depots = None

    if keyed_depots and app_depots:
        wanted_deps, _ = install.select_depots(appid, keyed_depots, app_depots)
        wanted_set = set(wanted_deps)
        target_gids = {
            int(d["id"]): str(d["gid"])
            for d in app_depots
            if d.get("gid") and int(d["id"]) in wanted_set
        }
    else:
        target_gids = {
            int(d["id"]): str(d["gid"])
            for d in (app_depots or [])
            if d.get("gid")
            and not d.get("shared")
            and str(d.get("oslist") or "").lower() in ("macos", "osx", "mac", "macosx", "")
        }

    fetched = None
    try:
        fetched = source.fetch_from_sources(
            appid,
            key=key,
            preferred_source=pref,
            auto_update=True,
            target_gids=target_gids,
        )
        if fetched and fetched.get("manifests"):
            install.import_lua(appid, fetched["lua"], fetched["manifests"], home)
    except Exception:
        pass

    # Verifica se i manifest necessari per la versione target sono effettivamente presenti
    store_dir = paths.sls_manifests(home)
    depotcache_dir = paths.depotcache(home)
    missing_targets = []
    for dep, gid in target_gids.items():
        fname = f"{dep}_{gid}.manifest"
        if not (
            os.path.exists(os.path.join(store_dir, fname))
            or os.path.exists(os.path.join(depotcache_dir, fname))
            or (fetched and fname in fetched.get("manifests", {}))
        ):
            missing_targets.append(dep)

    # Se mancano i manifest della nuova versione pubblica e non sono stati scaricati
    if missing_targets:
        pub_b = ai.public_buildid(appid)
        cur_b = get_installed_buildid(paths.steamapps(home), appid, store_dir=store_dir)
        return {
            "ok": False,
            "error": f"L'aggiornamento alla build {pub_b} non è ancora disponibile nelle sorgenti pubbliche (in attesa di pubblicazione su Sushi/Hubcap). I file di gioco correnti (build {cur_b}) sono intatti e pienamente funzionanti.",
            "current_buildid": cur_b,
            "target_buildid": pub_b,
            "manifest_missing": True,
        }

    maclua._ensure(home)
    out = install.fetch_app(
        appid,
        stplug_dir=paths.stplug_in(home),
        cache_dir=paths.sls_cache(home),
        store_dir=paths.sls_manifests(home),
        steamapps_dir=paths.steamapps(home),
        depotcache_dir=paths.depotcache(home),
        workers=workers,
        progress=progress,
    )
    install.reconcile_installed_appmanifests(paths.steamapps(home), home=home)
    return out


def _running_managed(home):
    from core import steamhook
    try:
        return set(steamhook.running_managed_appids(home))
    except Exception:
        return set()


def _apply_locked(appid, home, prev=None):
    """Applica un aggiornamento sotto lock per-app e registra SEMPRE l'esito reale
    in updates.json (ok / errore / in attesa dei manifest con backoff)."""
    appid = int(appid)
    prev = prev or {}
    lock = FileLock(_update_lock_path(home, appid))
    if not lock.acquire(timeout=0.5):
        return {"ok": False, "busy": True, "error": "Aggiornamento già in corso"}
    try:
        now = int(time.time())
        set_status(appid, {
            "status": "updating",
            "checked_at": now,
            "current_buildid": prev.get("current_buildid"),
            "latest_buildid": prev.get("latest_buildid"),
            "message": "Aggiornamento in corso...",
        }, home)
        try:
            res = apply_update(appid, home=home)
        except Exception as e:
            res = {"ok": False, "error": str(e)}

        if isinstance(res, dict) and res.get("ok") is False:
            attempts = int(prev.get("attempts") or 0) + 1
            entry = {
                "status": "pending" if res.get("manifest_missing") else "error",
                "checked_at": now,
                "current_buildid": res.get("current_buildid"),
                "latest_buildid": res.get("target_buildid"),
                "attempts": attempts,
                "next_try_at": now + RETRY_INTERVAL,
                "message": res.get("error") or "Aggiornamento non riuscito",
            }
            set_status(appid, entry, home)
            return {"ok": False, **entry}

        set_status(appid, {
            "status": "ok",
            "checked_at": now,
            "updated_at": now,
            "current_buildid": ai.public_buildid(appid),
            "latest_buildid": ai.public_buildid(appid),
            "message": "Aggiornato all'ultima versione disponibile.",
        }, home)
        try:
            from core import steamhook as _sh
            if _sh.is_cdp_available(0.1):
                _sh.sync_library_in_steam(home)
        except Exception:
            pass
        return {"ok": True, "status": "ok", "result": res}
    finally:
        lock.release()


def request_update(appid, home=None, background=True):
    """Aggiornamento richiesto dall'utente (pulsante Aggiorna): avvia in
    background sotto lock e traccia l'esito reale in updates.json."""
    home = home or os.path.expanduser("~")
    appid = int(appid)
    if background:
        import threading
        t = threading.Thread(target=_apply_locked, args=(appid, home),
                             kwargs={"prev": get_status(appid, home) or {}},
                             daemon=True, name="MacLuaUpdate%d" % appid)
        t.start()
        return {"ok": True, "appid": appid, "updating": True}
    return _apply_locked(appid, home)


def background_tick(home=None):
    """Watcher aggiornamenti: per ogni gioco gestito e installato controlla la
    build pubblica PICS; se c'è un aggiornamento e i manifest sono disponibili
    lo applica da solo, altrimenti ritenta con backoff (mai mentre il gioco è
    in esecuzione). Ogni esito è registrato in updates.json."""
    from core import settings
    home = home or os.path.expanduser("~")
    if not settings.get("auto_update_apps", True):
        return {"checked": 0, "applied": [], "pending": []}
    now = int(time.time())
    applied, pending, errori, checked = [], [], [], 0
    from core import steamhook
    try:
        games = steamhook.get_managed_games(home)
    except Exception:
        games = []
    for g in games:
        if not g.get("installed"):
            continue
        aid = int(g["appid"])
        st = get_status(aid, home) or {}
        try:
            if st.get("next_try_at") and int(st["next_try_at"]) > now:
                continue
        except (TypeError, ValueError):
            pass
        checked += 1
        try:
            info = check_updates(aid, home=home)
        except Exception:
            continue
        if not info.get("has_update"):
            set_status(aid, {
                "status": "ok",
                "checked_at": now,
                "current_buildid": info.get("current_buildid"),
                "latest_buildid": info.get("latest_buildid"),
                "message": "Aggiornato all'ultima versione disponibile.",
            }, home)
            continue
        if not info.get("manifest_ready"):
            attempts = int(st.get("attempts") or 0) + 1
            set_status(aid, {
                "status": "pending",
                "checked_at": now,
                "current_buildid": info.get("current_buildid"),
                "latest_buildid": info.get("latest_buildid"),
                "attempts": attempts,
                "next_try_at": now + RETRY_INTERVAL,
                "message": ("Aggiornamento alla build %s non ancora disponibile "
                            "nelle sorgenti: MacLua ritenta da sola."
                            % info.get("latest_buildid")),
            }, home)
            pending.append(aid)
            continue
        if aid in _running_managed(home):
            set_status(aid, {
                "status": "pending",
                "checked_at": now,
                "current_buildid": info.get("current_buildid"),
                "latest_buildid": info.get("latest_buildid"),
                "next_try_at": now + RETRY_INTERVAL,
                "message": "Gioco in esecuzione: aggiornamento rimandato.",
            }, home)
            pending.append(aid)
            continue
        res = _apply_locked(aid, home, prev=st)
        if res.get("ok"):
            applied.append(aid)
        elif res.get("status") == "error":
            errori.append(aid)
        else:
            pending.append(aid)
    return {"checked": checked, "applied": applied,
            "pending": pending, "errored": errori}

