"""Installazione: selezione depot, fetch, adopt in Steam, verify, fixup exec."""
import os
import re
import time

from core import depotkeys, fetch, manifest
from core.fetch import DEFAULT_CDN_BASES
from core.lua import parse_lua as _parse_lua
from core.manifests import valid_name as _valid_manifest_name
from core import paths as _paths


def import_lua(appid, lua_text, manifests, home):
    """Valida e scrive lua + manifest nello stplug-in/store. Ritorna report."""
    parsed = _parse_lua(lua_text)
    if appid not in parsed["bare"] and appid not in parsed["keys"]:
        raise ValueError("il lua è per un'altra app, non %d" % appid)
    sp = _paths.stplug_in(home)
    os.makedirs(sp, exist_ok=True)
    dst = os.path.join(sp, "%d.lua" % appid)
    tmp = dst + ".tmp.maclua"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(lua_text)
    os.rename(tmp, dst)
    os.chmod(dst, 0o600)
    store = _paths.sls_manifests(home)
    os.makedirs(store, exist_ok=True)
    staged = []
    for name, blob in (manifests or {}).items():
        base = name.rsplit("/", 1)[-1]
        if not _valid_manifest_name(base):
            continue
        with open(os.path.join(store, base), "wb") as f:
            f.write(blob)
        staged.append(base)
    return {"appid": appid, "lua": dst, "manifests": sorted(staged)}

DEFAULT_BASES = list(DEFAULT_CDN_BASES)

_MAC_OSLISTS = {"macos", "osx", "mac", "macosx", ""}


def select_depots(appid, keyed, appinfo_depots):
    """(wanted, skipped): solo depot contenuto macOS con chiave.

    Salta: ticket dell'app, voci senza appinfo, shared redist, non-macOS.
    """
    by_id = {d["id"]: d for d in appinfo_depots}
    wanted, skipped = [], {}
    for dep in sorted(keyed):
        if dep == appid:
            skipped[dep] = "chiave ticket dell'app, non depot contenuto"
            continue
        meta = by_id.get(dep)
        if meta is None:
            skipped[dep] = "fuori da appinfo"
            continue
        if meta.get("shared"):
            skipped[dep] = "shared redist (Steam lo gestisce)"
            continue
        if str(meta.get("oslist") or "").lower() not in _MAC_OSLISTS:
            skipped[dep] = "oslist=%s, non macOS" % meta.get("oslist")
            continue
        wanted.append(dep)
    return wanted, skipped


def resolve_manifest(store_dir, depotcache_dir, depot, preferred_gid=None):
    """Manifest staged da usare: preferred_gid, pin .preferred_<depot>, senò il più nuovo (per creation_time/mtime)."""
    if preferred_gid is not None and str(preferred_gid).strip().isdigit():
        gid = str(preferred_gid).strip()
        for d in (store_dir, depotcache_dir):
            if not d:
                continue
            cand = os.path.join(d, "%d_%s.manifest" % (depot, gid))
            if os.path.exists(cand):
                return cand

    pref = os.path.join(store_dir, ".preferred_%d" % depot)
    try:
        with open(pref, encoding="utf-8", errors="replace") as f:
            gid = f.read().strip()
        if gid.isdigit():
            for d in (store_dir, depotcache_dir):
                if not d:
                    continue
                cand = os.path.join(d, "%d_%s.manifest" % (depot, gid))
                if os.path.exists(cand):
                    return cand
    except OSError:
        pass
    best, best_rank = None, (-1, -1.0)
    for d in (store_dir, depotcache_dir):
        if not d:
            continue
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for fn in names:
            if not fn.startswith("%d_" % depot) or not fn.endswith(".manifest"):
                continue
            if not fn[len(str(depot)) + 1:-9].isdigit():
                continue
            p = os.path.join(d, fn)
            try:
                mt = os.path.getmtime(p)
            except OSError:
                continue
            ct = 0
            try:
                ct = int(manifest.parse_manifest(p).get("creation_time") or 0)
            except Exception:
                ct = 0
            rank = (ct, mt)
            if rank > best_rank:
                best, best_rank = p, rank
    if best is None:
        raise ValueError("nessun manifest staged per depot %d" % depot)
    return best


def _read_acf(steamapps_dir, appid):
    path = os.path.join(steamapps_dir, "appmanifest_%d.acf" % appid)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return path, f.read()
    except OSError:
        raise ValueError("appmanifest_%d.acf assente: premi Installa in Steam"
                         % appid)


def _installdir_of(acf_text):
    m = re.search(r'"installdir"\s+"([^"]+)"', acf_text)
    if not m:
        raise ValueError("appmanifest senza installdir")
    return m.group(1)


def installed_gids(acf_text):
    pairs = re.findall(r'"(\d+)"\s*\{\s*"manifest"\s+"(\d+)"', acf_text)
    return {int(d): g for d, g in pairs}


def _installed_state_path(store_dir, appid):
    return os.path.join(store_dir, f".installed_{int(appid)}.json")


def read_installed_state(store_dir, appid):
    """Legge lo stato reale installato su disco (.installed_<appid>.json) se presente."""
    import json
    p = _installed_state_path(store_dir, appid)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_installed_state(store_dir, appid, buildid, depot_gids):
    """Salva lo stato reale dei file installati su disco (.installed_<appid>.json)."""
    import json
    os.makedirs(store_dir, exist_ok=True)
    p = _installed_state_path(store_dir, appid)
    payload = {
        "appid": int(appid),
        "buildid": int(buildid) if buildid else 0,
        "depots": {str(k): str(v) for k, v in (depot_gids or {}).items()},
        "updated_at": int(time.time()),
    }
    tmp = p + ".tmp.maclua"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.rename(tmp, p)
    return p


def update_check(acf_text, appinfo_depots, store_dir=None, appid=None):
    """Confronta manifest installati (stato reale o acf) con gid pubblici (appinfo).

    Ritorna {'installed': {depot: gid}, 'live': {depot: gid},
    'available': bool}. 'available' solo se un depot installato ha un gid
    pubblico diverso e noto.
    """
    installed = installed_gids(acf_text)
    if store_dir and appid:
        st = read_installed_state(store_dir, appid)
        if st and isinstance(st.get("depots"), dict):
            for k, v in st["depots"].items():
                if str(k).isdigit():
                    installed[int(k)] = str(v)
    live = {d["id"]: d["gid"] for d in (appinfo_depots or [])
            if d.get("gid")}
    available = any(gid != live.get(depot)
                    for depot, gid in installed.items()
                    if depot in live)
    return {"installed": installed, "live": live, "available": available}


def last_owner(loginusers_path):
    """SteamID64 con Timestamp più recente, o '0'."""
    try:
        with open(loginusers_path, encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except OSError:
        return "0"
    best, best_ts = "0", -1
    for m in re.finditer(r'"(\d{17})"\s*\{\s*"[Tt]imestamp"\s+"(\d+)"', txt):
        if int(m.group(2)) > best_ts:
            best, best_ts = m.group(1), int(m.group(2))
    return best


def is_game_installed(appid, home=None):
    """Verifica se il gioco è effettivamente installato (scaricato con file su disco).
    Considera installati anche i giochi con StateFlags 6 (Update Required | Fully Installed)
    o SizeOnDisk > 0 purché la cartella in common/ esista e non sia vuota.
    """
    from core import paths
    home = home or os.path.expanduser("~")
    acf = os.path.join(paths.steamapps(home), f"appmanifest_{int(appid)}.acf")
    if not os.path.exists(acf):
        return False
    try:
        with open(acf, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        m_flags = re.search(r'"StateFlags"\s+"(\d+)"', content)
        m_size = re.search(r'"SizeOnDisk"\s+"(\d+)"', content)
        flags = int(m_flags.group(1)) if m_flags else 0
        size = int(m_size.group(1)) if m_size else 0
        if (flags & 4) != 0 or size > 0:
            m_dir = re.search(r'"installdir"\s+"([^"]+)"', content)
            if m_dir:
                g_dir = os.path.join(paths.steamapps(home), "common", m_dir.group(1))
                return os.path.isdir(g_dir) and len(os.listdir(g_dir)) > 0
            return (flags & 4) != 0
        return False
    except Exception:
        return False


def reconcile_installed_appmanifests(steamapps_dir, home=None):
    """Riconcilia gli appmanifest dei giochi gestiti già installati su disco:
    1. Rimuove pin obsoleti (.preferred_<depot> e setManifestid nei .lua) se auto_update_apps è attivo.
    2. Se Steam ha marcato un gioco installato con StateFlags != 4 (es. StateFlags 6 'Update Required',
       UpdateResult 6 'Access Denied') perché è uscito un aggiornamento su PICS di cui Steam non può
       scaricare il manifest senza token, salva la versione reale in .installed_<appid>.json e allinea
       appmanifest_<appid>.acf a StateFlags 4 + public_buildid + live GID, così il gioco resta sempre
       avviabile e aggiornabile in-place tramite MacLua senza mai perdere i dati o bloccarsi.
    """
    from core import appinfo as _ai, paths as _paths, settings as _settings, source as _source
    home = home or os.path.expanduser("~")
    if not os.path.isdir(steamapps_dir):
        return []

    stplug_dir = _paths.stplug_in(home)
    store_dir = _paths.sls_manifests(home)
    depotcache_dir = _paths.depotcache(home)

    # 1. Se auto_update è attivo, rimuovi i vecchi file .preferred_* e commenta setManifestid nei .lua
    if _settings.get("auto_update_apps", True):
        if os.path.isdir(store_dir):
            for fn in os.listdir(store_dir):
                if fn.startswith(".preferred_"):
                    try:
                        os.remove(os.path.join(store_dir, fn))
                    except OSError:
                        pass
        if os.path.isdir(stplug_dir):
            for fn in os.listdir(stplug_dir):
                if fn.endswith(".lua"):
                    lp = os.path.join(stplug_dir, fn)
                    try:
                        with open(lp, "r", encoding="utf-8", errors="replace") as f:
                            orig = f.read()
                        cleaned_lua = _source.comment_out_manifest_pins(orig)
                        if cleaned_lua != orig:
                            with open(lp, "w", encoding="utf-8") as f:
                                f.write(cleaned_lua)
                    except OSError:
                        pass

    reconciled = []
    for fn in sorted(os.listdir(steamapps_dir)):
        if not (fn.startswith("appmanifest_") and fn.endswith(".acf")):
            continue
        m_id = re.match(r"appmanifest_(\d+)\.acf$", fn)
        if not m_id:
            continue
        appid = int(m_id.group(1))
        lua_path = os.path.join(stplug_dir, f"{appid}.lua")
        if not os.path.exists(lua_path):
            continue
        if not is_game_installed(appid, home):
            continue

        acf_path = os.path.join(steamapps_dir, fn)
        try:
            with open(acf_path, "r", encoding="utf-8", errors="replace") as f:
                txt = f.read()
        except OSError:
            continue

        try:
            g_dir = os.path.join(steamapps_dir, "common", _installdir_of(txt))
            if os.path.isdir(g_dir):
                unwrap_executables(g_dir)
        except Exception:
            pass

        m_flags = re.search(r'"StateFlags"\s+"(\d+)"', txt)
        m_build = re.search(r'"buildid"\s+"(\d+)"', txt)
        m_size = re.search(r'"SizeOnDisk"\s+"(\d+)"', txt)
        flags = int(m_flags.group(1)) if m_flags else 0
        cur_build = int(m_build.group(1)) if m_build else 0
        size_on_disk = int(m_size.group(1)) if m_size else 0

        cur_gids = installed_gids(txt)
        try:
            pub_build = _ai.public_buildid(appid)
            app_depots = _ai.depots(appid)
        except Exception:
            pub_build = None
            app_depots = []

        live_gids = {int(d["id"]): str(d["gid"]) for d in (app_depots or []) if d.get("gid")}
        needs_patch = (flags != 4)
        if pub_build and cur_build and pub_build != cur_build:
            needs_patch = True
        for dep, gid in cur_gids.items():
            if dep in live_gids and live_gids[dep] != str(gid):
                needs_patch = True

        if not needs_patch:
            continue

        # Salva la versione effettivamente presente su disco in .installed_<appid>.json
        # se i manifest correnti dell'acf esistono localmente (cioè non erano già stati riconciliati).
        existing_state = read_installed_state(store_dir, appid)
        acf_manifests_local = all(
            os.path.exists(os.path.join(store_dir, f"{dep}_{gid}.manifest"))
            or os.path.exists(os.path.join(depotcache_dir, f"{dep}_{gid}.manifest"))
            for dep, gid in cur_gids.items()
        ) if cur_gids else False

        if acf_manifests_local or existing_state is None:
            write_installed_state(store_dir, appid, cur_build, cur_gids)

        # Costruisci depot_info aggiornato preservando le size dei singoli depot
        depot_sizes = {}
        for m_dep in re.finditer(
            r'"(\d+)"\s*\{\s*"manifest"\s+"(\d+)"(?:\s*"size"\s+"(\d+)")?', txt
        ):
            depot_sizes[int(m_dep.group(1))] = int(m_dep.group(3) or 0)

        new_depot_info = {}
        for dep, old_gid in cur_gids.items():
            target_gid = live_gids.get(dep, old_gid)
            new_depot_info[dep] = (target_gid, depot_sizes.get(dep, size_on_disk))

        patch_appmanifest(
            acf_path,
            new_depot_info,
            size_on_disk,
            buildid=pub_build or cur_build,
        )
        reconciled.append(appid)

    return reconciled


def cleanup_broken_appmanifests(steamapps_dir):
    """Rimuove gli appmanifest corrotti o finti (StateFlags 2/18 con SizeOnDisk 0 e common vuoto).
    Questi manifest fittizi fanno comparire 'DOWNLOAD RICHIESTO' invece del pulsante nativo 'INSTALLA'.
    Ritorna la lista di appid puliti.
    """
    cleaned = []
    if not os.path.isdir(steamapps_dir):
        return cleaned
    for fn in os.listdir(steamapps_dir):
        if not (fn.startswith("appmanifest_") and fn.endswith(".acf")):
            continue
        p = os.path.join(steamapps_dir, fn)
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            m_flags = re.search(r'"StateFlags"\s+"(\d+)"', content)
            m_size = re.search(r'"SizeOnDisk"\s+"(\d+)"', content)
            flags = int(m_flags.group(1)) if m_flags else 0
            size = int(m_size.group(1)) if m_size else 0
            if flags in (2, 18) and size == 0:
                m_dir = re.search(r'"installdir"\s+"([^"]+)"', content)
                has_files = False
                if m_dir:
                    common_dir = os.path.join(steamapps_dir, "common", m_dir.group(1))
                    if os.path.isdir(common_dir) and len(os.listdir(common_dir)) > 0:
                        has_files = True
                if not has_files:
                    m_aid = re.search(r'"appid"\s+"(\d+)"', content)
                    aid = int(m_aid.group(1)) if m_aid else 0
                    os.remove(p)
                    cleaned.append(aid)
        except Exception:
            pass
    return cleaned


def create_appmanifest(steamapps_dir, appid, name, installdir, buildid, owner):
    """Crea appmanifest minimo (Update Required) se assente. Idempotente:
    se esiste già, lo lascia intatto e ritorna il path."""
    path = os.path.join(steamapps_dir, "appmanifest_%d.acf" % appid)
    if os.path.exists(path):
        return path
    body = ('"AppState"\n{\n\t"appid"\t\t"%d"\n\t"Universe"\t\t"1"\n'
            '\t"name"\t\t"%s"\n\t"StateFlags"\t\t"2"\n'
            '\t"installdir"\t\t"%s"\n\t"LastUpdated"\t\t"0"\n'
            '\t"LastPlayed"\t\t"0"\n\t"SizeOnDisk"\t\t"0"\n'
            '\t"StagingSize"\t\t"0"\n\t"buildid"\t\t"%s"\n'
            '\t"LastOwner"\t\t"%s"\n\t"DownloadType"\t\t"1"\n'
            '\t"UpdateResult"\t\t"0"\n\t"BytesToDownload"\t\t"0"\n'
            '\t"BytesDownloaded"\t\t"0"\n\t"BytesToStage"\t\t"0"\n'
            '\t"BytesStaged"\t\t"0"\n\t"TargetBuildID"\t\t"%s"\n'
            '\t"AutoUpdateBehavior"\t\t"1"\n'
            '\t"AllowOtherDownloadsWhileRunning"\t\t"0"\n'
            '\t"ScheduledAutoUpdate"\t\t"0"\n\t"InstalledDepots"\n\t{\n\t}\n'
            '\t"UserConfig"\n\t{\n\t\t"language"\t\t"english"\n\t}\n'
            '\t"MountedConfig"\n\t{\n\t}\n}\n'
            % (appid, name, installdir, buildid, owner, buildid))
    tmp = path + ".tmp.maclua"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(body)
    os.rename(tmp, path)
    return path


def patch_appmanifest(acf_path, depot_info, size_on_disk, buildid=None):
    """depots {depot: (gid, size)} + Fully Installed. Scrittura atomica."""
    with open(acf_path, encoding="utf-8", errors="replace") as f:
        txt = f.read()

    def set_kv(text, key, value):
        pat = re.compile(r'^(\s*"' + re.escape(key) + r'"\s+)"[^"]*"', re.M)
        new, n = pat.subn(r'\g<1>"%s"' % value, text, count=1)
        if n == 0:
            pos = text.find('"InstalledDepots"')
            if pos != -1:
                return text[:pos] + ('\t"%s"\t\t"%s"\n' % (key, value)) + text[pos:], True
            return text, False
        return new, True

    txt, ok = set_kv(txt, "StateFlags", "4")
    if not ok:
        raise ValueError("appmanifest senza StateFlags")
    for key, value in (("SizeOnDisk", str(size_on_disk)),
                       ("UpdateResult", "0"),
                       ("LastUpdated", str(int(time.time()))),
                       ("BytesToDownload", "0"),
                       ("BytesDownloaded", "0"),
                       ("BytesToStage", "0"),
                       ("BytesStaged", "0"),
                       ("AutoUpdateBehavior", "1"),
                       ("ScheduledAutoUpdate", "0")):
        txt, _ = set_kv(txt, key, value)
    if buildid:
        txt, _ = set_kv(txt, "buildid", str(buildid))
        txt, _ = set_kv(txt, "TargetBuildID", str(buildid))
    lines = txt.split("\n")
    start = end = None
    for i, line in enumerate(lines):
        if re.match(r'^\s*"InstalledDepots"\s*$', line):
            start = i
        elif start is not None and re.match(r'^\s*"UserConfig"\s*$', line):
            end = i
            break
    if start is None or end is None:
        raise ValueError("layout appmanifest non riconosciuto")
    block = ['\t"InstalledDepots"', '\t{']
    for dep, (gid, dep_size) in sorted(depot_info.items()):
        block += ['\t\t"%d"' % dep, '\t\t{',
                  '\t\t\t"manifest"\t\t"%s"' % gid,
                  '\t\t\t"size"\t\t"%s"' % dep_size, '\t\t}']
    block.append('\t}')
    lines[start:end] = block
    tmp = acf_path + ".tmp.maclua"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.rename(tmp, acf_path)
    return acf_path


def unwrap_executables(root):
    """Ripristina eventuali file <bin>.real -> <bin> nei bundle .app,
    garantendo che gli eseguibili e le librerie (.dylib) rimangano integri e nativi."""
    unwrapped = 0
    if not os.path.isdir(root):
        return unwrapped
    for dirpath, _, filenames in os.walk(root):
        if dirpath.endswith(".app/Contents/MacOS"):
            for fn in filenames:
                if fn.endswith(".real"):
                    real_p = os.path.join(dirpath, fn)
                    orig_p = os.path.join(dirpath, fn[:-5])
                    if os.path.isfile(real_p):
                        try:
                            os.replace(real_p, orig_p)
                            unwrapped += 1
                        except OSError:
                            pass
    return unwrapped


def fix_executables(root):
    """Imposta i permessi di esecuzione (+x) su binari Mach-O e script,
    ripristina eventuali .real residui senza mai alterare i binari o le dylib del bundle,
    e verifica/ripara la firma digitale dei bundle .app se necessario."""
    import subprocess
    unwrap_executables(root)
    fixed = 0
    app_bundles = []
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            if d.endswith(".app"):
                app_bundles.append(os.path.join(dirpath, d))
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            try:
                with open(p, "rb") as f:
                    head = f.read(4)
            except OSError:
                continue
            if head in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
                        b"\xca\xfe\xba\xbe", b"\xce\xfa\xed\xfe",
                        b"\xcf\xfa\xed\xfe") or head.startswith(b"#!"):
                os.chmod(p, 0o755)
                fixed += 1

    # Verifica che ogni bundle .app abbia una firma valida su disco (necessaria per taskgated su Apple Silicon).
    # Se la firma originale dello sviluppatore è valida, non viene toccata; se è assente o corrotta,
    # applica una firma ad-hoc completa (--force --deep --sign -) sull'intero bundle.
    for bundle in app_bundles:
        try:
            chk = subprocess.run(
                ["codesign", "-vvv", "--deep", "--strict", bundle],
                capture_output=True,
                timeout=30,
            )
            if chk.returncode != 0:
                subprocess.run(
                    ["codesign", "--force", "--deep", "--sign", "-", bundle],
                    capture_output=True,
                    timeout=60,
                )
        except Exception:
            pass
    return fixed


def fetch_app(appid, stplug_dir, cache_dir, store_dir, steamapps_dir,
              depotcache_dir=None, bases=None, workers=8, dry_run=False,
              progress=None, appinfo_depots=None, totals=None):
    """Pipeline completa per un'app: chiavi -> depot -> manifest -> fetch ->
    adopt. Ritorna report {'app','depots','out','bytes','files'}."""
    from core import appinfo as _ai
    from core.lua import parse_lua
    bases = list(bases) if bases else list(DEFAULT_BASES)
    depotcache_dir = depotcache_dir or os.path.join(
        os.path.dirname(os.path.abspath(steamapps_dir)), "depotcache")

    lua_path = os.path.join(stplug_dir, "%d.lua" % appid)
    try:
        with open(lua_path, encoding="utf-8", errors="replace") as f:
            parsed = parse_lua(f.read())
    except OSError:
        raise ValueError("manca %d.lua in stplug-in: importa prima il lua"
                         % appid)
    for depot, keyhex in parsed["keys"].items():
        depotkeys.write_cache(cache_dir, appid, depot, keyhex)
    keyed = set(parsed["keys"])
    if appinfo_depots is None:
        appinfo_depots = list(_ai.depots(appid))
        for dlc_id in _ai.listofdlc(appid):
            for d in _ai.depots(dlc_id):
                if d["id"] not in {x["id"] for x in appinfo_depots}:
                    appinfo_depots.append(d)
    wanted, skipped = select_depots(appid, keyed, appinfo_depots)
    for dep, why in sorted(skipped.items()):
        print("  depot %d: salto (%s)" % (dep, why))
    if not wanted:
        raise ValueError("nessun depot macOS con chiave per %d" % appid)

    try:
        _, acf_text = _read_acf(steamapps_dir, appid)
    except ValueError:
        cfg = _ai.config(appid)
        if not cfg.get("name") or not cfg.get("installdir"):
            raise ValueError("app %d senza appmanifest e senza appinfo: "
                             "premi Installa in Steam" % appid)
        from core import paths as _paths
        owner = last_owner(os.path.join(_paths.steam_config(), "loginusers.vdf"))
        create_appmanifest(steamapps_dir, appid, cfg["name"],
                           cfg["installdir"],
                           _ai.public_buildid(appid) or 0, owner)
        print("appmanifest creato da appinfo (build %s)"
              % (_ai.public_buildid(appid) or 0))
        _, acf_text = _read_acf(steamapps_dir, appid)
    out = os.path.join(steamapps_dir, "common", _installdir_of(acf_text))
    os.makedirs(out, exist_ok=True)

    live_by_depot = {int(d["id"]): str(d["gid"]) for d in (appinfo_depots or []) if d.get("gid")}
    depot_info, grand, nfiles = {}, 0, 0
    parsed = []
    for depot in wanted:
        man_path = resolve_manifest(store_dir, depotcache_dir, depot,
                                    preferred_gid=live_by_depot.get(depot))
        info = manifest.parse_manifest(man_path)
        key = depotkeys.load_key(cache_dir, depot)
        total = sum(f["size"] for f in info["files"])
        depot_info[depot] = (info["gid"], total)
        parsed.append((depot, info, key))
        grand += total
        nchunks = sum(len(f["chunks"]) for f in info["files"])
        print("depot %d gid %s: %d file, %d chunk, %.1f MB"
              % (depot, info["gid"], len(info["files"]), nchunks, total / 1e6))
    if totals is not None:
        totals["total_bytes"] = grand
        totals["total_mb"] = grand / 1e6
    if dry_run:
        return {"app": appid, "depots": wanted, "out": out, "bytes": grand,
                "files": sum(len(i["files"]) for _, i, _ in parsed)}

    # Ripristina eventuali .real -> eseguibile prima del download delta in-place
    unwrap_executables(out)

    # Rimuovi file obsoleti appartenenti a versioni precedenti del manifest dello stesso depot
    old_gids = dict(installed_gids(acf_text))
    prev_state = read_installed_state(store_dir, appid)
    if prev_state and isinstance(prev_state.get("depots"), dict):
        for k_dep, v_gid in prev_state["depots"].items():
            if str(k_dep).isdigit():
                old_gids[int(k_dep)] = str(v_gid)
    for depot, new_info, _ in parsed:
        old_gid = old_gids.get(depot)
        if old_gid and str(old_gid) != str(new_info.get("gid")):
            for d_cand in (store_dir, depotcache_dir):
                if not d_cand:
                    continue
                old_man_p = os.path.join(d_cand, "%d_%s.manifest" % (depot, old_gid))
                if os.path.exists(old_man_p):
                    try:
                        old_info = manifest.parse_manifest(old_man_p)
                        new_rels = {
                            fetch._norm_path(e["name"])
                            for e in new_info["files"]
                            if not (e.get("flags", 0) & fetch.FLAG_DIRECTORY)
                        }
                        for old_e in old_info["files"]:
                            if old_e.get("flags", 0) & fetch.FLAG_DIRECTORY:
                                continue
                            old_rel = fetch._norm_path(old_e["name"])
                            if old_rel not in new_rels:
                                obsolete_p = os.path.join(out, old_rel)
                                if os.path.isfile(obsolete_p) or os.path.islink(obsolete_p):
                                    try:
                                        os.remove(obsolete_p)
                                    except OSError:
                                        pass
                    except Exception:
                        pass
                    break

    import concurrent.futures
    for depot, info, key in parsed:
        entries = info["files"]
        if len(entries) > 10:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(4, workers * 2)) as ex:
                futs = [ex.submit(fetch.download_file, depot, entry, key, bases, out,
                                  workers=1, progress=progress)
                        for entry in entries]
                for fut in concurrent.futures.as_completed(futs):
                    fut.result()
                    nfiles += 1
        else:
            for entry in entries:
                fetch.download_file(depot, entry, key, bases, out,
                                    workers=workers, progress=progress)
                nfiles += 1
    nfix = fix_executables(out)
    acf_path, _ = _read_acf(steamapps_dir, appid)
    b_id = _ai.public_buildid(appid)

    # Salva i GID effettivamente scaricati su disco in .installed_<appid>.json
    installed_depot_gids = {dep: gid for dep, (gid, _) in depot_info.items()}
    all_live = all(
        live_by_depot.get(dep) == str(gid)
        for dep, gid in installed_depot_gids.items()
        if dep in live_by_depot
    )
    real_build = b_id if all_live else 0
    try:
        write_installed_state(store_dir, appid, real_build, installed_depot_gids)
    except OSError:
        pass

    # Nell'appmanifest per Steam, usa sempre i live GID se disponibili così Steam non blocca il gioco con StateFlags 6
    acf_depot_info = {}
    for dep, (gid, dep_size) in depot_info.items():
        acf_depot_info[dep] = (live_by_depot.get(dep, gid), dep_size)
    patch_appmanifest(acf_path, acf_depot_info, grand, buildid=b_id)
    return {"app": appid, "depots": wanted, "out": out, "bytes": grand,
            "files": nfiles, "exec_fixed": nfix,
            "manifest": os.path.join(steamapps_dir,
                                     "appmanifest_%d.acf" % appid)}


def verify_app(appid, steamapps_dir, store_dir, depotcache_dir=None):
    """File su disco vs manifest dell'acf (o .installed_<appid>.json). Ritorna [relpath anomali]."""
    _, acf_text = _read_acf(steamapps_dir, appid)
    out = os.path.join(steamapps_dir, "common", _installdir_of(acf_text))
    depotcache_dir = depotcache_dir or os.path.join(
        os.path.dirname(os.path.abspath(steamapps_dir)), "depotcache")
    bad = []
    state = read_installed_state(store_dir, appid)
    state_depots = (state.get("depots") or {}) if isinstance(state, dict) else {}
    for depot, gid in sorted(installed_gids(acf_text).items()):
        cand = os.path.join(store_dir, "%d_%s.manifest" % (depot, gid))
        if not os.path.exists(cand):
            cand = os.path.join(depotcache_dir, "%d_%s.manifest" % (depot, gid))
        if not os.path.exists(cand) and str(depot) in state_depots:
            real_gid = state_depots[str(depot)]
            cand = os.path.join(store_dir, "%d_%s.manifest" % (depot, real_gid))
            if not os.path.exists(cand):
                cand = os.path.join(depotcache_dir, "%d_%s.manifest" % (depot, real_gid))
        info = manifest.parse_manifest(cand)
        for entry in info["files"]:
            rel = entry["name"].replace("\\", "/")
            if entry.get("flags", 0) & fetch.FLAG_DIRECTORY:
                continue
            p = os.path.join(out, *rel.split("/"))
            check_p = (p + ".real") if os.path.exists(p + ".real") else p
            try:
                with open(check_p, "rb") as f:
                    data = f.read()
            except OSError:
                bad.append(rel)
                continue
            if len(data) != entry["size"]:
                bad.append(rel)
                continue
            ok = True
            for c in entry["chunks"]:
                seg = data[c["offset"]:c["offset"] + c["cb_original"]]
                if (len(seg) != c["cb_original"]
                        or manifest.adler0(seg) != c["crc"]):
                    ok = False
                    break
            if not ok:
                bad.append(rel)
    return bad
