#!/usr/bin/env python3
"""MacLua: Steam game manager for macOS without client hooks.

Commands: search/add/update/verify/remove/status/doctor.
Only touches Steam data files (packageinfo, depotcache, stplug-in,
appmanifest) + public HTTPS. Never processes, never binaries, never CEF.
"""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import paths  # noqa: E402


def emit(args, obj):
    """If --json, prints the object and returns True (caller skips human output)."""
    if getattr(args, "json", False):
        print(json.dumps(obj, ensure_ascii=False))
        return True
    return False


def _root_games(home):
    """Set of AppIDs for managed base games only (from stplug-in/<appid>.lua). Strictly excludes DLCs."""
    sp = paths.stplug_in(home)
    root = set()
    try:
        names = os.listdir(sp)
    except OSError:
        return root
    import re
    from core import appinfo as ai, catalog
    for fn in names:
        m = re.match(r"(\d+)\.lua$", fn)
        if m:
            aid = int(m.group(1))
            p = ai.parent(aid)
            if p is None:
                p, _ = catalog.parent_of(aid)
            if p is None or p == aid:
                root.add(aid)
    return root


def _managed_sets(home):
    """(appids, depots) from the entire stplug-in + actual appinfo."""
    from core import appinfo as ai
    from core.lua import parse_lua
    sp = paths.stplug_in(home)
    appids, depots = set(), set()
    try:
        names = os.listdir(sp)
    except OSError:
        return appids, depots
    import re
    for fn in names:
        m = re.match(r"(\d+)\.lua$", fn)
        if not m:
            continue
        appid = int(m.group(1))
        appids.add(appid)
        try:
            with open(os.path.join(sp, fn), encoding="utf-8",
                      errors="replace") as f:
                parsed = parse_lua(f.read())
        except OSError:
            continue
        for bare in parsed.get("bare", []):
            appids.add(bare)
        for dep in parsed["keys"]:
            if dep != appid:
                depots.add(dep)
        try:
            for d in ai.depot_ids(appid):
                depots.add(d)
        except (OSError, ValueError):
            pass
        try:
            for dlc_id in ai.listofdlc(appid):
                appids.add(dlc_id)
                for d in ai.depot_ids(dlc_id):
                    depots.add(d)
        except (OSError, ValueError):
            pass
    return appids, depots


def _ensure(home):
    """Licenses + manifests + keys for all stplug-in entries, in SINGLE-FLIGHT.

    `ensure` is called concurrently from multiple entry points (LaunchAgent at login,
    bridge watchdog, client RPC, CLI). Without serialization, two concurrent
    executions will collide on the same files (packageinfo.vdf, key cache, appmanifest):
    this is the known cause of 'No licenses' when restarting Steam.
    The inter-process lock guarantees that only one ensure touches the files at a time;
    others wait and reuse the already applied state.
    """
    from core.atomic import FileLock
    lock = FileLock(os.path.join(paths.maclua_dir(home), "ensure.lock"))
    if not lock.acquire(timeout=20.0):
        return {"apps": [], "licensed_apps": [], "added": (set(), set()),
                "removed": (set(), set()), "staged": [], "keys": 0,
                "concurrent": True}
    try:
        return _ensure_locked(home)
    finally:
        lock.release()


def _ensure_locked(home):
    """Body of `_ensure`, executed under exclusive lock."""
    from core import appinfo as ai
    from core import depotkeys, license, manifests
    from core.lua import parse_lua
    sp = paths.stplug_in(home)
    roots = _root_games(home)
    appids, depots = _managed_sets(home)
    state = os.path.join(paths.sls_dir(home), ".managed.json")
    pkginfo = os.path.join(paths.appcache(home), "packageinfo.vdf")
    added, removed = license.sync(pkginfo, appids, depots, state)
    license.forge(pkginfo, sorted(appids), sorted(depots))
    staged, _ = manifests.stage_all(paths.sls_manifests(home),
                                    paths.depotcache(home))
    nkeys = 0
    try:
        names = os.listdir(sp)
    except OSError:
        names = []
    import re
    for fn in names:
        m = re.match(r"(\d+)\.lua$", fn)
        if not m:
            continue
        try:
            with open(os.path.join(sp, fn), encoding="utf-8",
                      errors="replace") as f:
                parsed = parse_lua(f.read())
        except OSError:
            continue
        for dep, keyhex in parsed["keys"].items():
            depotkeys.write_cache(paths.sls_cache(home), int(m.group(1)),
                                  dep, keyhex)
            nkeys += 1
    all_keys = depotkeys.collect_keys(sp)
    depotkeys.sync_config_vdf(os.path.join(paths.steam_config(home), "config.vdf"), all_keys)

    # Clean up any phantom appmanifests (StateFlags 2/18 with size 0) and reconcile installed games
    from core import install
    steamapps_dir = paths.steamapps(home)
    install.cleanup_broken_appmanifests(steamapps_dir)
    install.reconcile_installed_appmanifests(steamapps_dir, home=home)

    # Auto-restore bridge daemon if hook is enabled on real user home
    try:
        real_user_home = os.path.realpath(os.path.expanduser("~"))
        if os.path.realpath(home) == real_user_home:
            from core import steamhook
            mf_path = os.path.join(paths.maclua_dir(home), "hook_manifest.json")
            hook_enabled = os.path.exists(steamhook.bridge_agent_path(home))
            if os.path.exists(mf_path):
                with open(mf_path, "r", encoding="utf-8") as mf_f:
                    mf_data = json.load(mf_f)
                    hook_enabled = bool(mf_data.get("enabled", True))
            if hook_enabled:
                steamhook.install_bridge_agent(home=home)
    except Exception:
        pass

    return {"apps": sorted(roots), "licensed_apps": sorted(appids), "added": added, "removed": removed,
            "staged": staged, "keys": nkeys}


def cmd_search(args):
    from core import catalog, appinfo as ai
    results = catalog.search(args.name)
    resolved = []
    seen = set()
    for r in results:
        appid = r["appid"]
        parent_id = ai.parent(appid)
        if parent_id is None:
            parent_id, _ = catalog.parent_of(appid)
        target_id = parent_id if parent_id else appid
        if target_id not in seen:
            seen.add(target_id)
            name = (catalog.name_of(target_id) if target_id != appid else r["name"]) or r["name"]
            resolved.append({"appid": target_id, "name": name})
    if emit(args, resolved):
        return 0
    for r in resolved:
        print("%d\t%s" % (r["appid"], r["name"]))
    return 0


def cmd_add(args):
    import time
    from core import config, install, source, appinfo as ai, catalog
    home = os.path.expanduser("~")
    target_appid = args.appid
    is_dlc = False
    parent_id = None

    if args.lua:
        with open(args.lua, encoding="utf-8", errors="replace") as f:
            lua_text = f.read()
        manifests = {}
        if args.manifest_dir:
            for fn in sorted(os.listdir(args.manifest_dir)):
                if fn.endswith(".manifest") or fn.startswith(".preferred_"):
                    with open(os.path.join(args.manifest_dir, fn), "rb") as f:
                        manifests[fn] = f.read()
    else:
        from core import settings
        key = config.get_key(home) or settings.get("hubcap_key", "")
        pref = settings.get("preferred_source", "auto")
        auto_up = settings.get("auto_update_apps", True)

        # Check if requested AppID is a DLC for a base game
        try:
            parent_id = ai.parent(args.appid)
            if parent_id is None:
                parent_id, _ = catalog.parent_of(args.appid)
        except Exception:
            parent_id = None

        if parent_id is not None and parent_id != args.appid:
            is_dlc = True
            parent_lua = os.path.join(paths.stplug_in(home), "%d.lua" % parent_id)
            if os.path.exists(parent_lua):
                # Base game is already managed: update lua from remote to fetch DLC manifests/keys
                try:
                    f_parent = source.fetch_from_sources(parent_id, key=key, preferred_source=pref, auto_update=auto_up)
                    install.import_lua(parent_id, f_parent["lua"], f_parent["manifests"], home)
                except Exception:
                    pass
                ens = _ensure(home)
                msg = "Base game %d synced with all included DLCs." % parent_id
                if emit(args, {"appid": args.appid, "parent_appid": parent_id, "dlc": True,
                               "already_managed": True, "apps": ens["apps"],
                               "staged": ens["staged"], "keys": ens["keys"], "message": msg}):
                    return 0
                print(msg)
                return 0
            else:
                # Base game is not present: add base game which automatically includes DLC
                target_appid = parent_id

        quiet = getattr(args, "json", False)
        if not quiet:
            if is_dlc:
                print("AppID %d is a DLC of %d: downloading base game and associated DLCs..." % (args.appid, target_appid))
            else:
                print("downloading lua for %d from source..." % target_appid)
        try:
            fetched = source.fetch_from_sources(target_appid, key=key, preferred_source=pref, auto_update=auto_up)
            lua_text, manifests = fetched["lua"], fetched["manifests"]
        except Exception as e:
            if not key:
                emit(args, {"error": "API key required (Settings)"})
                print("API key required: maclua config set-key", file=sys.stderr)
                return 2
            raise
        if not quiet:
            print("lua ok + %d manifests (%s)" % (len(manifests), fetched.get("source", "Multi-Source")))

    rep = install.import_lua(target_appid, lua_text, manifests, home)
    ens = _ensure(home)
    msg = ("Added base game %d with all included DLCs." % target_appid) if is_dlc else ("Imported %d." % target_appid)
    if emit(args, {"appid": args.appid, "target_appid": target_appid,
                   "parent_appid": parent_id if is_dlc else None,
                   "dlc": is_dlc, "lua": rep["lua"],
                   "manifests": rep["manifests"], "apps": ens["apps"],
                   "staged": ens["staged"], "keys": ens["keys"], "message": msg}):
        return 0
    print("imported %s + %d manifests" % (rep["lua"], len(rep["manifests"])))
    print("add %d: licenses ok, %d manifests staged, %d keys"
          % (target_appid, len(ens["staged"]), ens["keys"]))
    print("Now click Install in Steam (creates appmanifest), then run:")
    print("  maclua update %d" % target_appid)
    return 0


def cmd_update(args):
    import time
    from core import appinfo as ai, config, install, settings, source
    home = os.path.expanduser("~")

    # Always fetch any new manifests/lua from sources (including free: Sushi, Ryuu, GitHub mirror)
    key = config.get_key(home) or settings.get("hubcap_key", "")
    pref = settings.get("preferred_source", "auto")
    try:
        target_gids = {int(d["id"]): str(d["gid"]) for d in (ai.depots(args.appid) or []) if d.get("gid")}
    except Exception:
        target_gids = {}
    try:
        fetched = source.fetch_from_sources(
            args.appid,
            key=key,
            preferred_source=pref,
            auto_update=True,
            target_gids=target_gids,
        )
        install.import_lua(args.appid, fetched["lua"], fetched["manifests"], home)
    except Exception:
        pass

    rep = _ensure(home)
    prog = {"bytes": 0, "total_bytes": 0, "total_mb": 0.0}
    last_print = [0.0, 0]

    def progress(n):
        prog["bytes"] += n
        now = time.time()
        # Throttling if not completed: emit at most every 0.1s or every 512KB
        if (now - last_print[0] < 0.1) and (prog["bytes"] - last_print[1] < 512 * 1024):
            return
        last_print[0] = now
        last_print[1] = prog["bytes"]

        tot = prog.get("total_bytes") or int(prog.get("total_mb", 0) * 1e6)
        cur_mb = round(prog["bytes"] / 1e6, 1)
        tot_mb = round(tot / 1e6, 1) if tot > 0 else 0.0
        pct = min(100, max(0, round(100.0 * prog["bytes"] / tot))) if tot > 0 else None

        if getattr(args, "json", False):
            print(json.dumps({"mb": cur_mb, "total": tot_mb, "pct": pct}))
        else:
            print("\r  %.1f MB" % cur_mb, end="", flush=True)

    out = install.fetch_app(
        args.appid, stplug_dir=paths.stplug_in(home),
        cache_dir=paths.sls_cache(home), store_dir=paths.sls_manifests(home),
        steamapps_dir=paths.steamapps(home),
        depotcache_dir=paths.depotcache(home), workers=args.jobs,
        dry_run=args.dry_run, progress=None if args.dry_run else progress,
        totals=prog)
    if not args.dry_run:
        install.reconcile_installed_appmanifests(paths.steamapps(home), home=home)
        try:
            from core import steamhook
            if steamhook.is_cdp_available(0.1):
                steamhook.sync_library_in_steam(home)
        except Exception:
            pass
    if getattr(args, "json", False):
        if not args.dry_run:
            tot = prog.get("total_bytes") or int(prog.get("total_mb", 0) * 1e6)
            tot_mb = round(tot / 1e6, 1) if tot > 0 else round(prog["bytes"] / 1e6, 1)
            print(json.dumps({"mb": tot_mb, "total": tot_mb, "pct": 100}))
            print()
        print(json.dumps({"appid": args.appid, "depots": out["depots"],
                          "files": out["files"], "bytes": out["bytes"],
                          "out": out["out"]}, ensure_ascii=False))
        return 0
    print("\nupdate %d: %d depots, %d files, %.1f MB -> %s"
          % (args.appid, len(out["depots"]), out["files"],
             out["bytes"] / 1e6, out["out"]))
    if not args.dry_run:
        print("Restart Steam (or verify file integrity) and click Play.")
    return 0


def cmd_verify(args):
    from core import install
    home = os.path.expanduser("~")
    bad = install.verify_app(args.appid,
                             steamapps_dir=paths.steamapps(home),
                             store_dir=paths.sls_manifests(home),
                             depotcache_dir=paths.depotcache(home))
    if emit(args, {"appid": args.appid, "bad": bad}):
        # JSON: mismatched files are data, not a command failure.
        return 0
    if bad:
        print("%d mismatched files:" % len(bad))
        for rel in bad[:20]:
            print("  " + rel)
        return 1
    print("verify %d: all files verified" % args.appid)
    return 0


def cmd_remove(args):
    import re
    from core.lua import parse_lua
    home = os.path.expanduser("~")
    lua = os.path.join(paths.stplug_in(home), "%d.lua" % args.appid)
    try:
        with open(lua, encoding="utf-8", errors="replace") as f:
            depots_of_app = set(parse_lua(f.read())["keys"])
    except OSError:
        depots_of_app = set()
        print("no lua found for %d" % args.appid)
    try:
        os.remove(lua)
        print("removed %s" % lua)
    except OSError:
        pass
    for fn in os.listdir(paths.sls_cache(home)) if os.path.isdir(
            paths.sls_cache(home)) else []:
        m = re.match(r"depotkey_(\d+)\.yaml$", fn)
        if m and int(m.group(1)) in depots_of_app:
            os.remove(os.path.join(paths.sls_cache(home), fn))
    for d in (paths.sls_manifests(home), paths.depotcache(home)):
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            m = re.match(r"(\d+)_\d+\.manifest$", fn)
            if m and int(m.group(1)) in depots_of_app:
                os.remove(os.path.join(d, fn))
    rep = _ensure(home)
    if emit(args, {"appid": args.appid, "removed": True}):
        return 0
    print("remove %d: licenses rebuilt without app" % args.appid)
    print("(package0 preserves historical entries: harmless, unlisted)")
    return 0


def cmd_status(args):
    from core import license
    home = os.path.expanduser("~")
    if args.appid:
        appids, depots = _managed_sets(home)
        if args.appid not in appids:
            if emit(args, {"appid": args.appid, "managed": False}):
                return 0
            print("%d: not managed (missing %d.lua)" % (args.appid, args.appid))
            return 1
        from core import appinfo as ai
        try:
            ds = ai.depots(args.appid)
        except (OSError, ValueError):
            ds = []
        acf = paths.appmanifest(home, args.appid)
        info = {"appid": args.appid, "managed": True,
                "appinfo_depots": len(ds),
                "has_appmanifest": os.path.exists(acf)}
        if info["has_appmanifest"]:
            from core import install as _ins
            with open(acf, encoding="utf-8", errors="replace") as f:
                info["versions"] = _ins.update_check(f.read(), ds)
        if emit(args, info):
            return 0
        print("%d: managed, %d depots in appinfo, appmanifest: %s"
              % (args.appid, len(ds),
                 "present" if info["has_appmanifest"] else "missing (click Install)"))
        return 0
    roots = _root_games(home)
    appids, depots = _managed_sets(home)
    pkginfo = os.path.join(paths.appcache(home), "packageinfo.vdf")
    try:
        m_app, m_dep = license.check(pkginfo, appids, depots)
    except (OSError, ValueError) as e:
        # Full schema here too: GUI always parses the same format.
        if emit(args, {"apps": sorted(roots), "depots": len(depots),
                       "ok": False, "error": str(e),
                       "missing": {"appids": [], "depots": []}}):
            return 0
        print("unreadable packageinfo: %s" % e)
        return 1
    if emit(args, {"apps": sorted(roots),
                   "depots": len(depots),
                   "ok": not (m_app or m_dep),
                   "missing": {"appids": sorted(m_app),
                               "depots": sorted(m_dep)}}):
        # JSON: missing licenses = status (ok=false), not command error.
        return 0
    print("%d managed apps, %d depots" % (len(roots), len(depots)))
    if m_app or m_dep:
        print("missing in package0: app=%s depot=%s"
              % (sorted(m_app), sorted(m_dep)))
        return 1
    print("licenses ok")
    return 0


def cmd_config(args):
    from core import config
    home = os.path.expanduser("~")
    if args.action == "set-key":
        key = args.value
        if key == "-":
            # From stdin: GUI does not expose it in argv (visible via `ps`).
            key = sys.stdin.readline()
        elif not key:
            import getpass
            key = getpass.getpass("hubcap API key: ")
        config.set_key(home, key)
        if emit(args, {"has_key": True}):
            return 0
        print("key saved (0600 permissions, never logged)")
        return 0
    if args.action == "clear-key":
        removed = config.clear_key(home)
        if emit(args, {"has_key": False, "removed": removed}):
            return 0
        print("key removed" if removed else "no key saved")
        return 0
    cur = config.get_key(home)
    if emit(args, {"has_key": bool(cur),
                   "source": ("env" if os.getenv("MACLUA_HUBCAP_KEY")
                              else "file") if cur else None}):
        return 0
    if cur:
        print("key: %s...%s (from %s)" % (
            cur[:3], cur[-2:],
            "env MACLUA_HUBCAP_KEY" if os.getenv("MACLUA_HUBCAP_KEY") else "file"))
    else:
        print("no key configured (maclua config set-key)")
        return 1
    return 0


def steam_url(appid):
    return "steam://install/%d" % int(appid)


def cmd_install(args):
    import subprocess
    url = steam_url(args.appid)
    if emit(args, {"appid": args.appid, "url": url}):
        return 0
    print("opening %s (Steam Install dialog)" % url)
    subprocess.run(["open", url], check=False)
    return 0


def cmd_ensure(args, home=None):
    home = home or os.path.expanduser("~")
    rep = _ensure(home)
    if rep.get("concurrent"):
        if emit(args, {"apps": [], "staged": [], "keys": 0,
                       "added": {"appids": [], "depots": []},
                       "removed": {"appids": [], "depots": []},
                       "concurrent": True}):
            return 0
        print("ensure already in progress in another MacLua process: nothing to do.")
        return 0
    (added_app, added_dep), (removed_app, removed_dep) = (
        rep["added"], rep["removed"])
    if emit(args, {"apps": rep["apps"], "staged": rep["staged"],
                   "keys": rep["keys"],
                   "added": {"appids": sorted(added_app),
                             "depots": sorted(added_dep)},
                   "removed": {"appids": sorted(removed_app),
                               "depots": sorted(removed_dep)}}):
        return 0
    print("ensure: %d apps, %d manifests staged, %d keys; added=%s removed=%s"
          % (len(rep["apps"]), len(rep["staged"]), rep["keys"],
             rep["added"], rep["removed"]))
    print("Restart Steam to reload licenses.")
    return 0


def cmd_agent(args):
    from core import agent
    home = os.path.expanduser("~")
    lad = os.path.join(home, "Library/LaunchAgents")
    if args.action == "install":
        path = agent.install(sys.executable, os.path.abspath(__file__), lad)
        if emit(args, {"installed": True, "path": path}):
            return 0
        print("agent installed: %s" % path)
        print("Will be loaded on next login.")
        print("To load immediately: launchctl bootstrap gui/$(id -u) %s" % path)
        print("NOTE: disable 'Steam -> Open at Login' to prevent race conditions.")
        return 0
    if args.action == "remove":
        removed = agent.remove(lad)
        if emit(args, {"installed": False, "removed": removed}):
            return 0
        print("agent removed" if removed else "agent not present")
        return 0
    on = agent.installed(lad)
    if emit(args, {"installed": on}):
        return 0
    print("agent: %s" % ("active" if on else "not installed"))
    return 0


def cmd_doctor(args):
    home = os.path.expanduser("~")
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        return ok

    check("python", True, sys.version.split()[0])
    for label, p in (("steam", paths.steam_root(home)),
                     ("steamapps", paths.steamapps(home)),
                     ("appcache", paths.appcache(home)),
                     ("stplug-in", paths.stplug_in(home)),
                     ("sls", paths.sls_dir(home))):
        exists = os.path.isdir(p)
        check(label, exists, p if exists else "missing: " + p)
    for mod in ("Crypto.Cipher", "zstandard"):
        try:
            __import__(mod)
            check("lib " + mod, True)
        except ImportError:
            pkg = "zstandard" if mod == "zstandard" else "pycryptodome"
            check("lib " + mod, False, "pip install " + pkg)
    pkginfo = os.path.join(paths.appcache(home), "packageinfo.vdf")
    try:
        from core import license
        license.load_groups(pkginfo)
        check("packageinfo", True, "readable")
    except (OSError, ValueError) as e:
        check("packageinfo", False, str(e))
    ok = all(c["ok"] for c in checks)
    if emit(args, {"ok": ok, "checks": checks}):
        return 0
    for c in checks:
        print("%s: %s %s" % (c["name"], "ok" if c["ok"] else "MISSING",
                             c["detail"]))
    return 0 if ok else 1


def cmd_bridge(args):
    from core import bridge, steamhook
    if args.action == "token":
        t = steamhook.get_or_create_token()
        if emit(args, {"token": t}):
            return 0
        print(t)
        return 0
    elif args.action == "serve":
        port = getattr(args, "port", 6767) or 6767
        if not getattr(args, "json", False):
            print(f"Starting MacLua bridge on http://127.0.0.1:{port}/...")
        bridge.run_bridge_server(port=port)
        return 0
    return 1


def cmd_steam_hook(args):
    from core import steamhook
    home = os.path.expanduser("~")
    if args.action == "enable":
        rep = steamhook.enable_hook(home)
        if emit(args, rep):
            return 0
        print("Steam hook enabled (.cef-enable-remote-debugging created).")
        return 0
    elif args.action == "disable":
        rep = steamhook.disable_hook(home)
        if emit(args, rep):
            return 0
        print("Steam hook disabled and cleaned up.")
        return 0
    elif args.action == "status":
        rep = steamhook.get_status(home)
        if emit(args, rep):
            return 0
        print("Marker present:", rep["marker_present"])
        print("CDP active:", rep["cdp_available"])
        print("Tabs found:", rep["tabs_count"])
        return 0
    elif args.action == "inject":
        rep = steamhook.inject_into_tabs()
        if emit(args, rep):
            return 0
        print("Injection completed. Tabs updated:", rep.get("injected_count", 0))
        return 0
    elif args.action == "restart":
        rep = steamhook.restart_steam()
        if emit(args, rep):
            return 0
        print("Steam restarted with CEF debug port enabled.")
        return 0
    return 1


def cmd_collections(args):
    from core import collections as coll_mod
    if args.action == "list":
        sort = getattr(args, "sort", "popular") or "popular"
        rep = coll_mod.fetch_collections(sort=sort)
        if emit(args, rep):
            return 0
        for c in rep.get("collections", []):
            print(f"[{c['id']}] {c['title']} ({c['appCount']} games) - {c['author']}")
        return 0
    elif args.action in ("show", "details"):
        slug = args.slug
        rep = coll_mod.fetch_collection_details(slug)
        if emit(args, rep):
            return 0
        print(f"Collection: {rep.get('title')} ({len(rep.get('apps', []))} games)")
        for a in rep.get("apps", []):
            print(" -", a)
        return 0
    elif args.action == "add":
        slug = args.slug
        rep = coll_mod.fetch_collection_details(slug)
        apps = rep.get("apps", [])
        from core import queue, catalog, appinfo as ai
        enqueued = []
        for a in apps:
            p_id = ai.parent(a)
            target_id = p_id if p_id else a
            queue.DownloadQueue.shared().enqueue(target_id, name=catalog.name_of(target_id))
            enqueued.append(target_id)
        if emit(args, {"ok": True, "collection": slug, "enqueued": enqueued}):
            return 0
        print(f"Enqueued {len(enqueued)} games from collection {slug}")
        return 0
    return 1


def cmd_vault(args):
    from core import vault
    if args.action == "list":
        appid = getattr(args, "appid", None)
        rep = vault.list_snapshots(appid)
        if emit(args, {"snapshots": rep}):
            return 0
        for s in rep:
            print(f"AppID {s['appid']} - {s['timestamp']} - {s['hash']} ({s['bytes']} bytes) - {s.get('note')}")
        return 0
    elif args.action == "restore":
        home = os.path.expanduser("~")
        stplug = paths.stplug_in(home)
        vault.restore(args.appid, args.timestamp, stplug)
        if emit(args, {"ok": True, "appid": args.appid, "restored": args.timestamp}):
            return 0
        print(f"Restored snapshot {args.timestamp} for {args.appid}")
        return 0
    return 1


def cmd_fixes(args):
    from core import fixes
    appid = getattr(args, "appid", None)
    rep = fixes.get_fixes(appid)
    if emit(args, {"fixes": rep}):
        return 0
    print(json.dumps(rep, indent=2))
    return 0


def cmd_depots(args):
    from core import bridge
    rep = bridge.get_game_depots(args.appid)
    if emit(args, rep):
        return 0
    print(json.dumps(rep, indent=2))
    return 0


def cmd_queue(args):
    from core import queue
    q = queue.DownloadQueue.shared()
    if args.action == "status":
        st = q.get_status()
        if emit(args, st):
            return 0
        print(json.dumps(st, indent=2))
        return 0
    elif args.action == "cancel":
        q.cancel(args.appid)
        if emit(args, {"ok": True, "cancelled": args.appid}):
            return 0
        print("Cancelled download of", args.appid)
        return 0
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="maclua",
                                 description="Steam game manager for macOS without client hooks.")
    ap.add_argument("--json", action="store_true",
                    help="machine-readable JSON output for GUI")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("search", help="search appid by name")
    p.add_argument("name")
    p.set_defaults(fn=cmd_search)
    p = sub.add_parser("add", help="import a .lua (file or remote source)")
    p.add_argument("--appid", type=int, required=True)
    p.add_argument("--lua", default=None,
                   help="local .lua file (default: download from source)")
    p.add_argument("--manifest-dir", default=None)
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("update", help="download or update files without reinstalling")
    p.add_argument("appid", type=int)
    p.add_argument("-j", "--jobs", type=int, default=8)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_update)
    p = sub.add_parser("verify", help="verify installed files")
    p.add_argument("appid", type=int)
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("remove", help="remove a managed game")
    p.add_argument("appid", type=int)
    p.set_defaults(fn=cmd_remove)
    p = sub.add_parser("status", help="status of licenses and managed games")
    p.add_argument("appid", type=int, nargs="?")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("install", help="open Steam install dialog")
    p.add_argument("appid", type=int)
    p.set_defaults(fn=cmd_install)
    p = sub.add_parser("ensure", help="reapply licenses, manifests, and keys")
    p.set_defaults(fn=cmd_ensure)
    p = sub.add_parser("doctor", help="environment diagnostics")
    p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("config", help="source API key configuration")
    p.add_argument("action", choices=["set-key", "clear-key", "show"])
    p.add_argument("value", nargs="?")
    p.set_defaults(fn=cmd_config)
    p = sub.add_parser("agent", help="automatic ensure on user login")
    p.add_argument("action", choices=["install", "remove", "status"])
    p.set_defaults(fn=cmd_agent)

    # Bridge and steam-hook commands
    p = sub.add_parser("bridge", help="local bridge HTTP server for Steam UI and GUI")
    p.add_argument("action", choices=["serve", "token"])
    p.add_argument("--port", type=int, default=6767)
    p.set_defaults(fn=cmd_bridge)

    p = sub.add_parser("steam-hook", help="native Steam client CEF integration")
    p.add_argument("action", choices=["enable", "disable", "status", "inject", "restart"])
    p.set_defaults(fn=cmd_steam_hook)

    p = sub.add_parser("collections", help="community game collections")
    p.add_argument("action", choices=["list", "show", "add"])
    p.add_argument("slug", nargs="?")
    p.add_argument("--sort", default="popular")
    p.set_defaults(fn=cmd_collections)

    p = sub.add_parser("vault", help="backup and versioning for lua files")
    p.add_argument("action", choices=["list", "restore"])
    p.add_argument("appid", type=int, nargs="?")
    p.add_argument("timestamp", type=int, nargs="?")
    p.set_defaults(fn=cmd_vault)

    p = sub.add_parser("fixes", help="applied fixes registry")
    p.add_argument("action", choices=["list"])
    p.add_argument("appid", type=int, nargs="?")
    p.set_defaults(fn=cmd_fixes)

    p = sub.add_parser("depots", help="depot and build inspector (LuaTools style)")
    p.add_argument("appid", type=int)
    p.set_defaults(fn=cmd_depots)

    p = sub.add_parser("queue", help="download queue")
    p.add_argument("action", choices=["status", "cancel"])
    p.add_argument("appid", type=int, nargs="?")
    p.set_defaults(fn=cmd_queue)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        print("error: %s" % e, file=sys.stderr)
        return 1
    except OSError as e:
        if getattr(args, "json", False):
            print(json.dumps({"error": "I/O: %s" % e}, ensure_ascii=False))
        print("I/O error: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
