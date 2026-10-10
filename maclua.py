#!/usr/bin/env python3
"""MacLua: gestione giochi Steam su macOS senza hook nel client.

Comandi: search/add/update/verify/remove/status/doctor.
Tocca solo file dati di Steam (packageinfo, depotcache, stplug-in,
appmanifest) + HTTPS pubbliche. Mai processi, mai binari, mai CEF.
"""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import paths  # noqa: E402


def emit(args, obj):
    """Se --json, stampa l'oggetto e ritorna True (il chiamante salta l'umano)."""
    if getattr(args, "json", False):
        print(json.dumps(obj, ensure_ascii=False))
        return True
    return False


def _root_games(home):
    """Set di AppID dei soli giochi base gestiti (da stplug-in/<appid>.lua). Esclude rigorosamente i DLC."""
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
    """(appids, depotids) dall'intero stplug-in + appinfo reale."""
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
    """Licenze+manifest+chiavi per tutto lo stplug-in. Ritorna report."""
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

    # Pulisce eventuali appmanifest fantasma (StateFlags 2/18 con size 0) che causano "DOWNLOAD RICHIESTO"
    from core import install
    steamapps_dir = paths.steamapps(home)
    install.cleanup_broken_appmanifests(steamapps_dir)

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

        # Verifica se l'AppID richiesto è un DLC di un gioco base
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
                # Il gioco base è già gestito: aggiorna il lua dal remote per recuperare manifest/chiavi del DLC
                try:
                    f_parent = source.fetch_from_sources(parent_id, key=key, preferred_source=pref, auto_update=auto_up)
                    install.import_lua(parent_id, f_parent["lua"], f_parent["manifests"], home)
                except Exception:
                    pass
                ens = _ensure(home)
                msg = "Gioco base %d sincronizzato con tutti i DLC inclusi." % parent_id
                if emit(args, {"appid": args.appid, "parent_appid": parent_id, "dlc": True,
                               "already_managed": True, "apps": ens["apps"],
                               "staged": ens["staged"], "keys": ens["keys"], "message": msg}):
                    return 0
                print(msg)
                return 0
            else:
                # Il gioco base non è presente: aggiunge il gioco base che include automaticamente il DLC
                target_appid = parent_id

        quiet = getattr(args, "json", False)
        if not quiet:
            if is_dlc:
                print("AppID %d è un DLC di %d: scarico gioco base e relativi DLC..." % (args.appid, target_appid))
            else:
                print("scarico lua per %d dalla sorgente..." % target_appid)
        try:
            fetched = source.fetch_from_sources(target_appid, key=key, preferred_source=pref, auto_update=auto_up)
            lua_text, manifests = fetched["lua"], fetched["manifests"]
        except Exception as e:
            if not key:
                emit(args, {"error": "serve una chiave API (Impostazioni)"})
                print("serve una chiave API: maclua config set-key", file=sys.stderr)
                return 2
            raise
        if not quiet:
            print("lua ok + %d manifest (%s)" % (len(manifests), fetched.get("source", "Multi-Source")))

    rep = install.import_lua(target_appid, lua_text, manifests, home)
    ens = _ensure(home)
    msg = ("Aggiunto gioco base %d con tutti i DLC inclusi." % target_appid) if is_dlc else ("Importato %d." % target_appid)
    if emit(args, {"appid": args.appid, "target_appid": target_appid,
                   "parent_appid": parent_id if is_dlc else None,
                   "dlc": is_dlc, "lua": rep["lua"],
                   "manifests": rep["manifests"], "apps": ens["apps"],
                   "staged": ens["staged"], "keys": ens["keys"], "message": msg}):
        return 0
    print("importato %s + %d manifest" % (rep["lua"], len(rep["manifests"])))
    print("add %d: licenze ok, %d manifest staged, %d chiavi"
          % (target_appid, len(ens["staged"]), ens["keys"]))
    print("Ora premi Installa in Steam (crea l'appmanifest), poi:")
    print("  maclua update %d" % target_appid)
    return 0


def cmd_update(args):
    import time
    from core import config, install, source
    home = os.path.expanduser("~")

    # Controlla se la sorgente ha un aggiornamento del lua (o nuovi DLC/depot)
    key = config.get_key(home)
    if key:
        try:
            fetched = source.fetch_lua(args.appid, key)
            install.import_lua(args.appid, fetched["lua"], fetched["manifests"], home)
        except Exception:
            pass

    rep = _ensure(home)
    prog = {"bytes": 0, "total_bytes": 0, "total_mb": 0.0}
    last_print = [0.0, 0]

    def progress(n):
        prog["bytes"] += n
        now = time.time()
        # Throttling se non completato: emetti al massimo ogni 0.1s o ogni 512KB
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
    print("\nupdate %d: %d depot, %d file, %.1f MB -> %s"
          % (args.appid, len(out["depots"]), out["files"],
             out["bytes"] / 1e6, out["out"]))
    if not args.dry_run:
        print("Riavvia Steam (o verifica integrità) e premi Gioca.")
    return 0


def cmd_verify(args):
    from core import install
    home = os.path.expanduser("~")
    bad = install.verify_app(args.appid,
                             steamapps_dir=paths.steamapps(home),
                             store_dir=paths.sls_manifests(home),
                             depotcache_dir=paths.depotcache(home))
    if emit(args, {"appid": args.appid, "bad": bad}):
        # JSON: i file anomali sono un dato, non un fallimento del comando.
        return 0
    if bad:
        print("%d file anomali:" % len(bad))
        for rel in bad[:20]:
            print("  " + rel)
        return 1
    print("verify %d: tutto integro" % args.appid)
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
        print("nessun lua per %d" % args.appid)
    try:
        os.remove(lua)
        print("rimosso %s" % lua)
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
    print("remove %d: licenze ricostruite senza l'app" % args.appid)
    print("(package0 conserva eventuali voci storiche: innocue, non listate)")
    return 0


def cmd_status(args):
    from core import license
    home = os.path.expanduser("~")
    if args.appid:
        appids, depots = _managed_sets(home)
        if args.appid not in appids:
            if emit(args, {"appid": args.appid, "managed": False}):
                return 0
            print("%d: non gestito (manca %d.lua)" % (args.appid, args.appid))
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
        print("%d: gestito, %d depot in appinfo, appmanifest: %s"
              % (args.appid, len(ds),
                 "presente" if info["has_appmanifest"] else "assente (premi Installa)"))
        return 0
    roots = _root_games(home)
    appids, depots = _managed_sets(home)
    pkginfo = os.path.join(paths.appcache(home), "packageinfo.vdf")
    try:
        m_app, m_dep = license.check(pkginfo, appids, depots)
    except (OSError, ValueError) as e:
        # Schema completo anche qui: la GUI decodifica sempre la stessa forma.
        if emit(args, {"apps": sorted(roots), "depots": len(depots),
                       "ok": False, "error": str(e),
                       "missing": {"appids": [], "depots": []}}):
            return 0
        print("packageinfo illeggibile: %s" % e)
        return 1
    if emit(args, {"apps": sorted(roots),
                   "depots": len(depots),
                   "ok": not (m_app or m_dep),
                   "missing": {"appids": sorted(m_app),
                               "depots": sorted(m_dep)}}):
        # JSON: licenze mancanti = stato (ok=false), non errore del comando.
        return 0
    print("%d app gestite, %d depot" % (len(roots), len(depots)))
    if m_app or m_dep:
        print("mancanti in package0: app=%s depot=%s"
              % (sorted(m_app), sorted(m_dep)))
        return 1
    print("licenze ok")
    return 0


def cmd_config(args):
    from core import config
    home = os.path.expanduser("~")
    if args.action == "set-key":
        key = args.value
        if key == "-":
            # Da stdin: la GUI non la espone in argv (visibile con `ps`).
            key = sys.stdin.readline()
        elif not key:
            import getpass
            key = getpass.getpass("hubcap API key: ")
        config.set_key(home, key)
        if emit(args, {"has_key": True}):
            return 0
        print("chiave salvata (0600, mai nei log)")
        return 0
    if args.action == "clear-key":
        removed = config.clear_key(home)
        if emit(args, {"has_key": False, "removed": removed}):
            return 0
        print("chiave rimossa" if removed else "nessuna chiave salvata")
        return 0
    cur = config.get_key(home)
    if emit(args, {"has_key": bool(cur),
                   "source": ("env" if os.getenv("MACLUA_HUBCAP_KEY")
                              else "file") if cur else None}):
        return 0
    if cur:
        print("chiave: %s...%s (da %s)" % (
            cur[:3], cur[-2:],
            "env MACLUA_HUBCAP_KEY" if os.getenv("MACLUA_HUBCAP_KEY") else "file"))
    else:
        print("nessuna chiave (maclua config set-key)")
        return 1
    return 0


def steam_url(appid):
    return "steam://install/%d" % int(appid)


def cmd_install(args):
    import subprocess
    url = steam_url(args.appid)
    if emit(args, {"appid": args.appid, "url": url}):
        return 0
    print("apro %s (dialogo Installa di Steam)" % url)
    subprocess.run(["open", url], check=False)
    return 0


def cmd_ensure(args, home=None):
    home = home or os.path.expanduser("~")
    rep = _ensure(home)
    (added_app, added_dep), (removed_app, removed_dep) = (
        rep["added"], rep["removed"])
    if emit(args, {"apps": rep["apps"], "staged": rep["staged"],
                   "keys": rep["keys"],
                   "added": {"appids": sorted(added_app),
                             "depots": sorted(added_dep)},
                   "removed": {"appids": sorted(removed_app),
                               "depots": sorted(removed_dep)}}):
        return 0
    print("ensure: %d app, %d manifest staged, %d chiavi; aggiunti=%s rimossi=%s"
          % (len(rep["apps"]), len(rep["staged"]), rep["keys"],
             rep["added"], rep["removed"]))
    print("Riavvia Steam per caricare le licenze.")
    return 0


def cmd_agent(args):
    from core import agent
    home = os.path.expanduser("~")
    lad = os.path.join(home, "Library/LaunchAgents")
    if args.action == "install":
        path = agent.install(sys.executable, os.path.abspath(__file__), lad)
        if emit(args, {"installed": True, "path": path}):
            return 0
        print("agent installato: %s" % path)
        print("Eseguilo ora? verrà caricato al prossimo login.")
        print("Per caricarlo subito: launchctl bootstrap gui/$(id -u) %s" % path)
        print("NOTA: disattiva 'Steam -> apri al login' per evitare la race.")
        return 0
    if args.action == "remove":
        removed = agent.remove(lad)
        if emit(args, {"installed": False, "removed": removed}):
            return 0
        print("agent rimosso" if removed else "agent non presente")
        return 0
    on = agent.installed(lad)
    if emit(args, {"installed": on}):
        return 0
    print("agent: %s" % ("attivo" if on else "non installato"))
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
        check(label, exists, p if exists else "manca: " + p)
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
        check("packageinfo", True, "leggibile")
    except (OSError, ValueError) as e:
        check("packageinfo", False, str(e))
    ok = all(c["ok"] for c in checks)
    if emit(args, {"ok": ok, "checks": checks}):
        return 0
    for c in checks:
        print("%s: %s %s" % (c["name"], "ok" if c["ok"] else "MANCA",
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
            print(f"Avvio bridge MacLua su http://127.0.0.1:{port}/...")
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
        print("Hook Steam abilitato (.cef-enable-remote-debugging creato).")
        return 0
    elif args.action == "disable":
        rep = steamhook.disable_hook(home)
        if emit(args, rep):
            return 0
        print("Hook Steam disabilitato e file puliti.")
        return 0
    elif args.action == "status":
        rep = steamhook.get_status(home)
        if emit(args, rep):
            return 0
        print("Marker presente:", rep["marker_present"])
        print("CDP attivo:", rep["cdp_available"])
        print("Tab trovati:", rep["tabs_count"])
        return 0
    elif args.action == "inject":
        rep = steamhook.inject_into_tabs()
        if emit(args, rep):
            return 0
        print("Iniezione completata. Tab aggiornati:", rep.get("injected_count", 0))
        return 0
    elif args.action == "restart":
        rep = steamhook.restart_steam()
        if emit(args, rep):
            return 0
        print("Steam riavviato con porta di debug CEF attiva.")
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
            print(f"[{c['id']}] {c['title']} ({c['appCount']} giochi) - {c['author']}")
        return 0
    elif args.action in ("show", "details"):
        slug = args.slug
        rep = coll_mod.fetch_collection_details(slug)
        if emit(args, rep):
            return 0
        print(f"Collezione: {rep.get('title')} ({len(rep.get('apps', []))} giochi)")
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
        print(f"Accodati {len(enqueued)} giochi dalla collezione {slug}")
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
        print(f"Ripristinato snapshot {args.timestamp} per {args.appid}")
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
        print("Annullato download di", args.appid)
        return 0
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="maclua",
                                 description="Giochi Steam su macOS, senza hook.")
    ap.add_argument("--json", action="store_true",
                    help="output macchina-leggibile per la GUI")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("search", help="cerca appid per nome")
    p.add_argument("name")
    p.set_defaults(fn=cmd_search)
    p = sub.add_parser("add", help="importa un .lua (file o sorgente)")
    p.add_argument("--appid", type=int, required=True)
    p.add_argument("--lua", default=None,
                   help="file .lua locale (senza: scarica dalla sorgente)")
    p.add_argument("--manifest-dir", default=None)
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("update", help="scarica/aggiorna senza reinstallare")
    p.add_argument("appid", type=int)
    p.add_argument("-j", "--jobs", type=int, default=8)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_update)
    p = sub.add_parser("verify", help="verifica file installati")
    p.add_argument("appid", type=int)
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("remove", help="rimuove un gioco gestito")
    p.add_argument("appid", type=int)
    p.set_defaults(fn=cmd_remove)
    p = sub.add_parser("status", help="stato licenze/gestiti")
    p.add_argument("appid", type=int, nargs="?")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("install", help="apre il dialogo Installa di Steam")
    p.add_argument("appid", type=int)
    p.set_defaults(fn=cmd_install)
    p = sub.add_parser("ensure", help="riapplica licenze+manifest+chiavi")
    p.set_defaults(fn=cmd_ensure)
    p = sub.add_parser("doctor", help="controlli ambiente")
    p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("config", help="chiave API sorgente")
    p.add_argument("action", choices=["set-key", "clear-key", "show"])
    p.add_argument("value", nargs="?")
    p.set_defaults(fn=cmd_config)
    p = sub.add_parser("agent", help="ensure automatico a ogni login")
    p.add_argument("action", choices=["install", "remove", "status"])
    p.set_defaults(fn=cmd_agent)

    # Nuovi comandi bridge e steam-hook
    p = sub.add_parser("bridge", help="server bridge locale per Steam UI e GUI")
    p.add_argument("action", choices=["serve", "token"])
    p.add_argument("--port", type=int, default=6767)
    p.set_defaults(fn=cmd_bridge)

    p = sub.add_parser("steam-hook", help="integrazione nativa Steam client CEF")
    p.add_argument("action", choices=["enable", "disable", "status", "inject", "restart"])
    p.set_defaults(fn=cmd_steam_hook)

    p = sub.add_parser("collections", help="collezioni comunitarie di giochi")
    p.add_argument("action", choices=["list", "show", "add"])
    p.add_argument("slug", nargs="?")
    p.add_argument("--sort", default="popular")
    p.set_defaults(fn=cmd_collections)

    p = sub.add_parser("vault", help="backup e versioni dei file lua")
    p.add_argument("action", choices=["list", "restore"])
    p.add_argument("appid", type=int, nargs="?")
    p.add_argument("timestamp", type=int, nargs="?")
    p.set_defaults(fn=cmd_vault)

    p = sub.add_parser("fixes", help="registro fix applicati")
    p.add_argument("action", choices=["list"])
    p.add_argument("appid", type=int, nargs="?")
    p.set_defaults(fn=cmd_fixes)

    p = sub.add_parser("depots", help="ispettore depot e build (stile LuaTools)")
    p.add_argument("appid", type=int)
    p.set_defaults(fn=cmd_depots)

    p = sub.add_parser("queue", help="coda di download")
    p.add_argument("action", choices=["status", "cancel"])
    p.add_argument("appid", type=int, nargs="?")
    p.set_defaults(fn=cmd_queue)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        print("errore: %s" % e, file=sys.stderr)
        return 1
    except OSError as e:
        if getattr(args, "json", False):
            print(json.dumps({"error": "I/O: %s" % e}, ensure_ascii=False))
        print("errore I/O: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
