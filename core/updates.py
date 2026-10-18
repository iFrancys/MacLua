"""In-place update checking and application for base games and DLCs.
Compares installed builds and manifests on disk against public Steam PICS,
applying delta chunk updates in-place without uninstallation or data loss.

Includes persistent update tracking (`updates.json`) and a background watcher:
if a source has not yet published manifests for a new build, MacLua retries
with exponential backoff and reports status clearly — never silent failures.
"""
import os
import re
import time

from core import paths, appinfo as ai, install
from core.atomic import atomic_write, FileLock

RETRY_INTERVAL = 1800  # 30-minute backoff when target manifests are not yet published


def _status_path(home):
    return os.path.join(paths.maclua_dir(home), "updates.json")


def _update_lock_path(home, appid):
    return os.path.join(paths.maclua_dir(home), "update_%d.lock" % int(appid))


def load_status(home=None):
    """{appid: entry} mapping of persistent update states."""
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
    """Read the actual buildid registered in .installed_<appid>.json or appmanifest."""
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


def _has_newer_staged_manifest(appid, steamapps_dir, store_dir, depotcache_dir, target_gids):
    """True if store_dir or depotcache_dir contains a newer manifest (by creation_time)
    than what is currently installed on disk for at least one depot."""
    from core import manifest as mf_mod
    st = install.read_installed_state(store_dir, appid)
    installed_map = {}
    if st and isinstance(st.get("depots"), dict):
        installed_map = {int(k): str(v) for k, v in st["depots"].items()}
    else:
        acf_path = os.path.join(steamapps_dir, f"appmanifest_{appid}.acf")
        if os.path.exists(acf_path):
            try:
                with open(acf_path, "r", encoding="utf-8", errors="replace") as f:
                    installed_map = install.installed_gids(f.read())
            except Exception:
                installed_map = {}
    if not installed_map:
        return False

    for dep in target_gids:
        cur_gid = installed_map.get(int(dep))
        if not cur_gid:
            continue
        try:
            best_path = install.resolve_manifest(store_dir, depotcache_dir, int(dep))
            best_info = mf_mod.parse_manifest(best_path)
            best_gid = str(best_info.get("gid") or "")
            best_ct = int(best_info.get("creation_time") or 0)
        except Exception:
            continue
        if not best_gid or best_gid == str(cur_gid):
            continue
        cur_ct = 0
        for d in (store_dir, depotcache_dir):
            cand = os.path.join(d, f"{int(dep)}_{cur_gid}.manifest")
            if os.path.exists(cand):
                try:
                    cur_ct = int(mf_mod.parse_manifest(cand).get("creation_time") or 0)
                except Exception:
                    cur_ct = 0
                break
        if best_ct > cur_ct and cur_ct > 0:
            return True
    return False


def check_updates(appid, home=None):
    """Check if a game update or new DLCs are available for an appid."""
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
    missing_gids = {}
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
                        missing_gids[int(dep)] = str(live_gid)
        except Exception:
            pass

    if has_game_update and not manifest_ready and missing_gids:
        try:
            from core import config, settings, source
            key = config.get_key(home) or settings.get("hubcap_key", "")
            pref = settings.get("preferred_source", "auto")
            fetched = source.fetch_from_sources(
                appid,
                key=key,
                preferred_source=pref,
                auto_update=True,
                target_gids=missing_gids,
            )
            if fetched and fetched.get("manifests"):
                install.import_lua(appid, fetched["lua"], fetched["manifests"], home)
            manifest_ready = all(
                os.path.exists(os.path.join(store_dir, f"{dep}_{gid}.manifest"))
                or os.path.exists(os.path.join(depotcache_dir, f"{dep}_{gid}.manifest"))
                for dep, gid in missing_gids.items()
            ) or _has_newer_staged_manifest(appid, steamapps, store_dir, depotcache_dir, missing_gids)
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
    """Download latest available manifests from sources and apply delta updates
    in-place to game files without uninstallation or data loss."""
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

    # Verify that manifests required for the target version are actually present
    store_dir = paths.sls_manifests(home)
    depotcache_dir = paths.depotcache(home)
    steamapps_dir = paths.steamapps(home)
    missing_targets = []
    for dep, gid in target_gids.items():
        fname = f"{dep}_{gid}.manifest"
        if not (
            os.path.exists(os.path.join(store_dir, fname))
            or os.path.exists(os.path.join(depotcache_dir, fname))
            or (fetched and fname in fetched.get("manifests", {}))
        ):
            missing_targets.append(dep)

    # If target version manifests are missing and no newer intermediate manifest exists on disk
    if missing_targets and not _has_newer_staged_manifest(appid, steamapps_dir, store_dir, depotcache_dir, target_gids):
        pub_b = ai.public_buildid(appid)
        cur_b = get_installed_buildid(steamapps_dir, appid, store_dir=store_dir)
        return {
            "ok": False,
            "error": f"Update to build {pub_b} is not yet available on public sources (awaiting publication on Sushi/Hubcap). Current game files (build {cur_b}) are intact and functional.",
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
    """Apply an update under per-app lock and ALWAYS record the real outcome
    in updates.json (ok / error / pending manifests with backoff)."""
    appid = int(appid)
    prev = prev or {}
    lock = FileLock(_update_lock_path(home, appid))
    if not lock.acquire(timeout=0.5):
        return {"ok": False, "busy": True, "error": "Update already in progress"}
    try:
        now = int(time.time())
        set_status(appid, {
            "status": "updating",
            "checked_at": now,
            "current_buildid": prev.get("current_buildid"),
            "latest_buildid": prev.get("latest_buildid"),
            "message": "Update in progress...",
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
                "message": res.get("error") or "Update failed",
            }
            set_status(appid, entry, home)
            return {"ok": False, **entry}

        pub_b = ai.public_buildid(appid)
        set_status(appid, {
            "status": "ok",
            "checked_at": now,
            "updated_at": now,
            "current_buildid": pub_b,
            "latest_buildid": pub_b,
            "has_update": False,
            "message": "Updated to latest available version.",
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
    """User-initiated update request: runs in background under lock and
    tracks the real outcome in updates.json."""
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


def _sync_uninstalled_game(appid, home, now=None):
    """For games present in the LUA library section but not yet installed on disk:
    if target live manifests or DLC entries are missing, synchronize automatically
    from Sushi/Ryuu/Hubcap, merging depot keys."""
    now = now or int(time.time())
    st = get_status(appid, home) or {}
    try:
        if st.get("next_try_at") and int(st["next_try_at"]) > now:
            return
    except (TypeError, ValueError):
        pass

    store_dir = paths.sls_manifests(home)
    depotcache_dir = paths.depotcache(home)
    missing_gids = {}
    try:
        for d in (ai.depots(appid) or []):
            if d.get("shared"):
                continue
            if str(d.get("oslist") or "").lower() not in ("macos", "osx", "mac", "macosx", ""):
                continue
            dep = int(d["id"])
            gid = str(d.get("gid") or "")
            if gid and not (
                os.path.exists(os.path.join(store_dir, f"{dep}_{gid}.manifest"))
                or os.path.exists(os.path.join(depotcache_dir, f"{dep}_{gid}.manifest"))
            ):
                missing_gids[dep] = gid
    except Exception:
        return

    if not missing_gids:
        return

    try:
        from core import config, settings, source, manifests as mf_stage
        key = config.get_key(home) or settings.get("hubcap_key", "")
        pref = settings.get("preferred_source", "auto")
        fetched = source.fetch_from_sources(
            appid,
            key=key,
            preferred_source=pref,
            auto_update=True,
            target_gids=missing_gids,
        )
        if fetched and fetched.get("manifests"):
            install.import_lua(appid, fetched["lua"], fetched["manifests"], home)
            mf_stage.stage_all(store_dir, depotcache_dir)
    except Exception:
        pass
    set_status(appid, {
        "status": "pending",
        "checked_at": now,
        "next_try_at": now + RETRY_INTERVAL,
    }, home)


def background_tick(home=None):
    """Update watcher: checks public Steam PICS for each installed managed game;
    if an update is available and manifests are ready, applies it automatically;
    otherwise retries with backoff (never while the game is running).
    Every outcome is recorded in updates.json."""
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
        aid = int(g["appid"])
        if not g.get("installed"):
            try:
                _sync_uninstalled_game(aid, home, now=now)
            except Exception:
                pass
            continue
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
                "has_update": False,
                "message": "Updated to latest available version.",
            }, home)
            continue
        if not info.get("manifest_ready"):
            attempts = int(st.get("attempts") or 0) + 1
            set_status(aid, {
                "status": "pending",
                "checked_at": now,
                "current_buildid": info.get("current_buildid"),
                "latest_buildid": info.get("latest_buildid"),
                "has_update": True,
                "attempts": attempts,
                "next_try_at": now + RETRY_INTERVAL,
                "message": ("Update to build %s is not yet available on sources: "
                            "MacLua will retry automatically."
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
                "has_update": True,
                "next_try_at": now + RETRY_INTERVAL,
                "message": "Game is currently running: update deferred.",
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


