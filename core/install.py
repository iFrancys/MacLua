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


def resolve_manifest(store_dir, depotcache_dir, depot):
    """Manifest staged da usare: pin .preferred_<depot>, senò il più nuovo."""
    pref = os.path.join(store_dir, ".preferred_%d" % depot)
    try:
        with open(pref, encoding="utf-8", errors="replace") as f:
            gid = f.read().strip()
        if gid.isdigit():
            for d in (store_dir, depotcache_dir):
                cand = os.path.join(d, "%d_%s.manifest" % (depot, gid))
                if os.path.exists(cand):
                    return cand
    except OSError:
        pass
    best, best_mtime = None, -1.0
    for d in (store_dir, depotcache_dir):
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
            if mt > best_mtime:
                best, best_mtime = p, mt
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


def update_check(acf_text, appinfo_depots):
    """Confronta manifest installati (acf) con gid pubblici (appinfo).

    Ritorna {'installed': {depot: gid}, 'live': {depot: gid},
    'available': bool}. 'available' solo se un depot installato ha un gid
    pubblico diverso e noto.
    """
    installed = installed_gids(acf_text)
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
    """Verifica se il gioco è effettivamente installato (scaricato con file su disco)."""
    from core import paths
    home = home or os.path.expanduser("~")
    acf = os.path.join(paths.steamapps(home), f"appmanifest_{int(appid)}.acf")
    if not os.path.exists(acf):
        return False
    try:
        with open(acf, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        m_flags = re.search(r'"StateFlags"\s+"(\d+)"', content)
        if m_flags and int(m_flags.group(1)) == 4:
            m_dir = re.search(r'"installdir"\s+"([^"]+)"', content)
            if m_dir:
                g_dir = os.path.join(paths.steamapps(home), "common", m_dir.group(1))
                return os.path.isdir(g_dir) and len(os.listdir(g_dir)) > 0
            return True
        return False
    except Exception:
        return False


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


def _create_macho_launcher(dest_path, target_real_name):
    """Crea un launcher Mach-O nativo universale (arm64 + x86_64) per i bundle macOS.
    Questo permette a Steam di tracciare il processo nativamente senza fallire
    la gestione del processo POSIX e senza che l'overlay chiuda l'applicazione."""
    import subprocess
    import tempfile

    src = (
        '#include <unistd.h>\n'
        '#include <libgen.h>\n'
        '#include <mach-o/dyld.h>\n'
        '#include <stdio.h>\n'
        'int main(int argc, char *argv[]) {\n'
        '    char path[1024]; uint32_t size = sizeof(path);\n'
        '    if (_NSGetExecutablePath(path, &size) != 0) return 1;\n'
        '    char *dir = dirname(path);\n'
        '    chdir(dir);\n'
        '    chdir("../Resources");\n'
        '    char real_path[1024];\n'
        '    snprintf(real_path, sizeof(real_path), "%s/' + target_real_name + '", dir);\n'
        '    execv(real_path, argv);\n'
        '    return 1;\n'
        '}\n'
    )
    with tempfile.NamedTemporaryFile(suffix=".c", mode="w", delete=False) as tf:
        tf.write(src)
        c_path = tf.name
    try:
        cmd = ["clang", "-O2", "-arch", "arm64", "-arch", "x86_64", c_path, "-o", dest_path]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode == 0:
            subprocess.run(["codesign", "--force", "--sign", "-", dest_path], capture_output=True)
            os.chmod(dest_path, 0o755)
            return True
    except Exception:
        pass
    finally:
        try:
            os.unlink(c_path)
        except OSError:
            pass

    # Fallback sicuro nel caso in cui clang non sia disponibile
    wrapper = (
        '#!/bin/bash\n'
        'DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        'cd "$DIR/../Resources"\n'
        'exec "$DIR/%s" "$@"\n' % target_real_name
    )
    with open(dest_path, "w", encoding="utf-8") as wf:
        wf.write(wrapper)
    os.chmod(dest_path, 0o755)
    return False


def fix_executables(root):
    """+x su Mach-O e script (il manifest non porta il bit exec)."""
    fixed = 0
    for dirpath, _, filenames in os.walk(root):
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

    # Per bundle macOS (.app) che contengono Resources/:
    # crea launcher Mach-O che garantisce la corretta working directory all'avvio
    # e permette il tracciamento diretto da parte del client Steam.
    for dirpath, dirs, _ in os.walk(root):
        if dirpath.endswith(".app/Contents/MacOS"):
            res_dir = os.path.normpath(os.path.join(dirpath, "../Resources"))
            if os.path.isdir(res_dir):
                for fn in os.listdir(dirpath):
                    if fn.endswith(".real"):
                        continue
                    p = os.path.join(dirpath, fn)
                    real_p = p + ".real"
                    if os.path.isfile(p):
                        try:
                            with open(p, "rb") as f:
                                head = f.read(4)
                            if head in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
                                        b"\xca\xfe\xba\xbe", b"\xce\xfa\xed\xfe",
                                        b"\xcf\xfa\xed\xfe"):
                                if not os.path.exists(real_p):
                                    os.rename(p, real_p)
                                    _create_macho_launcher(p, fn + ".real")
                                    os.chmod(real_p, 0o755)
                                    fixed += 1
                            elif head.startswith(b"#!") and os.path.exists(real_p):
                                _create_macho_launcher(p, fn + ".real")
                                os.chmod(real_p, 0o755)
                                fixed += 1
                        except OSError:
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

    depot_info, grand, nfiles = {}, 0, 0
    parsed = []
    for depot in wanted:
        man_path = resolve_manifest(store_dir, depotcache_dir, depot)
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
    patch_appmanifest(acf_path, depot_info, grand, buildid=b_id)
    return {"app": appid, "depots": wanted, "out": out, "bytes": grand,
            "files": nfiles, "exec_fixed": nfix,
            "manifest": os.path.join(steamapps_dir,
                                     "appmanifest_%d.acf" % appid)}


def verify_app(appid, steamapps_dir, store_dir, depotcache_dir=None):
    """File su disco vs manifest dell'acf. Ritorna [relpath anomali]."""
    _, acf_text = _read_acf(steamapps_dir, appid)
    out = os.path.join(steamapps_dir, "common", _installdir_of(acf_text))
    depotcache_dir = depotcache_dir or os.path.join(
        os.path.dirname(os.path.abspath(steamapps_dir)), "depotcache")
    bad = []
    for depot, gid in sorted(installed_gids(acf_text).items()):
        cand = os.path.join(store_dir, "%d_%s.manifest" % (depot, gid))
        if not os.path.exists(cand):
            cand = os.path.join(depotcache_dir, "%d_%s.manifest" % (depot, gid))
        info = manifest.parse_manifest(cand)
        for entry in info["files"]:
            rel = entry["name"].replace("\\", "/")
            if entry.get("flags", 0) & fetch.FLAG_DIRECTORY:
                continue
            p = os.path.join(out, *rel.split("/"))
            try:
                with open(p, "rb") as f:
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
