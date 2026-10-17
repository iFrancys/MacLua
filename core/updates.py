"""Controllo e applicazione aggiornamenti in-place per giochi base e nuovi DLC.
Confronta la build/manifest realmente installati su disco con quelli pubblici PICS
e applica aggiornamenti delta in-place senza disinstallare né perdere dati.
"""
import os
import re
from core import paths, appinfo as ai, install


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

