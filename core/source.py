"""Remote Lua source: multi-database support (Sushi, Ryuu, Hubcap).
Enables anonymous and free downloads of manifests and Lua files without
requiring an API key, replicating LuaTools functionality.
"""
import io
import json
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from core.lua import parse_lua

HUBCAP = "https://hubcapmanifest.com"
SUSHI_PRIMARY = "https://raw.githubusercontent.com/sushi-dev55/sushitools-games-repo/main"
SUSHI_ALT = "https://raw.githubusercontent.com/sushi-dev55-alt/sushitools-games-repo-alt/refs/heads/main"
GITHUB_MANIFEST_MIRROR = "https://raw.githubusercontent.com/qwe213312/k25FCdfEOoEJ42S6/main"
RYUU_BASE = "http://167.235.229.108"

_MAX_ZIP_BYTES = 256 * 1024 * 1024
_MAX_ENTRIES = 10000
_MAX_EXPANDED = 1024 * 1024 * 1024
_MAX_LUA = 16 * 1024 * 1024
_MAX_MANIFEST = 64 * 1024 * 1024


def comment_out_manifest_pins(lua_text: str) -> str:
    """Comment out setManifestid/setManifestId statements in Lua files.
    Allows Steam to automatically download and track the latest available build."""
    lines = []
    for line in lua_text.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("setManifestid(") or trimmed.startswith("setManifestId("):
            lines.append(f"-- {line} -- commented out by MacLua auto_update")
        else:
            lines.append(line)
    return "\n".join(lines) + ("\n" if lua_text.endswith("\n") else "")


def _download(url, timeout=60, headers=None):
    hdrs = {"User-Agent": "MacLua/1.0"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise ValueError("HTTP %s" % resp.status)
            size = resp.headers.get("Content-Length")
            if size is not None and int(size) > _MAX_ZIP_BYTES:
                raise ValueError("zip exceeds 256MB")
            data = resp.read(_MAX_ZIP_BYTES + 1)
            if len(data) > _MAX_ZIP_BYTES:
                raise ValueError("zip exceeds 256MB")
            return data
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ValueError("API key rejected (401/403)")
        if e.code == 404:
            raise ValueError("no lua for this app on source")
        if e.code == 429:
            raise ValueError("too many requests, please retry later")
        raise ValueError("HTTP %s" % e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError("source unreachable: %s" % e)


def _safe_extract(data, appid):
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("source did not return a valid zip")
    names = zf.namelist()
    if len(names) > _MAX_ENTRIES:
        raise ValueError("too many entries in zip")
    total = 0
    for info in zf.infolist():
        total += info.file_size
        if total > _MAX_EXPANDED:
            raise ValueError("expanded zip exceeds 1GB")
        # Normalize Windows path separators '\' for archives created on Windows (Sushi/Ryuu)
        name = info.filename.replace("\\", "/")
        if (name.startswith("/") or ".." in name.split("/")
                or info.is_dir()
                or (info.external_attr >> 16) & 0o170000 in (0o120000,)):
            raise ValueError("insecure entry in zip: %r" % name)
    want = "%d.lua" % appid
    matching_lua = [n for n in names if n.replace("\\", "/").rsplit("/", 1)[-1] == want]
    if len(matching_lua) != 1:
        raise ValueError("zip is missing %s (or duplicate)" % want)
    lua_raw = zf.read(matching_lua[0])
    if len(lua_raw) > _MAX_LUA or not lua_raw:
        raise ValueError("%s unreadable" % want)
    try:
        lua_text = lua_raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("%s not UTF-8" % want)
    parsed = parse_lua(lua_text)
    if appid not in parsed["bare"] and appid not in parsed["keys"]:
        raise ValueError("downloaded lua is for another app")
    manifests = {}
    for n in names:
        base = n.replace("\\", "/").rsplit("/", 1)[-1]
        if base.endswith(".manifest"):
            with zf.open(n) as f:
                blob = f.read(_MAX_MANIFEST + 1)
            if len(blob) > _MAX_MANIFEST:
                raise ValueError("manifest exceeds 64MB: %s" % base)
            manifests[base] = blob
    return lua_text, manifests


def fetch_from_sushi(appid: int, timeout=20):
    """Download from Sushi (GitHub Raw) without requiring an API key."""
    for base in (SUSHI_PRIMARY, SUSHI_ALT):
        url = f"{base}/{appid}.zip"
        try:
            data = _download(url, timeout=timeout)
            return _safe_extract(data, appid)
        except Exception:
            continue
    raise ValueError(f"App {appid} not found on Sushi")


def check_ryuu(appid: int, timeout=10) -> bool:
    """Check availability on Ryuu."""
    url = f"{RYUU_BASE}/check_apis?appid={appid}"
    try:
        data = _download(url, timeout=timeout, headers={"User-Agent": "secretgoonpoon"})
        js = json.loads(data.decode("utf-8", errors="replace"))
        return js.get("Luie") == "available" or js.get("Ryuu") == "available"
    except Exception:
        return False


def fetch_from_ryuu(appid: int, timeout=30):
    """Download from Ryuu (free anonymous API, User-Agent secretgoonpoon)."""
    url = f"{RYUU_BASE}/{appid}"
    try:
        data = _download(url, timeout=timeout, headers={"User-Agent": "secretgoonpoon"})
        return _safe_extract(data, appid)
    except Exception as e:
        raise ValueError(f"Ryuu download failed for {appid}: {e}")


def fetch_depot_manifest(depot_id: int, manifest_id: str, key=None, timeout=15):
    """Download a single .manifest file for (depot_id, manifest_id) from free mirrors or Hubcap."""
    from core.manifest import parse_manifest_bytes
    depot_id = int(depot_id)
    manifest_id = str(manifest_id).strip()
    if not manifest_id.isdigit():
        return None

    urls = [f"{GITHUB_MANIFEST_MIRROR}/{depot_id}_{manifest_id}.manifest"]
    if key:
        q = urllib.parse.urlencode({"depot_id": depot_id, "manifest_id": manifest_id, "api_key": key})
        urls.append(f"{HUBCAP}/api/v1/generate/manifest?{q}")

    for url in urls:
        try:
            blob = _download(url, timeout=timeout)
            if blob and len(blob) <= _MAX_MANIFEST:
                info = parse_manifest_bytes(blob)
                if str(info.get("gid")) == manifest_id:
                    return blob
        except Exception:
            continue
    return None


def _missing_target_gids(manifests: dict, target_gids: dict) -> dict:
    if not target_gids:
        return {}
    missing = {}
    for dep, gid in target_gids.items():
        if gid and f"{int(dep)}_{gid}.manifest" not in manifests:
            missing[int(dep)] = str(gid)
    return missing


def fetch_from_sources(appid: int, key=None, preferred_source="auto", auto_update=True, timeout=30, target_gids=None):
    """Search and download from Sushi, Ryuu, or Hubcap based on configuration.
    When looking for updates (target_gids specified), if the preferred source does not
    yet have the new manifest, automatically queries other available sources and merges
    both manifests and depot keys."""
    from core.lua import merge_lua
    appid = int(appid)
    source_used = None
    res = None

    def _combine(cur, nxt, nxt_name):
        nonlocal source_used
        if cur is None:
            source_used = nxt_name
            return nxt
        merged_mfs = dict(cur[1])
        merged_mfs.update(nxt[1])
        merged_lua = merge_lua(nxt[0], cur[0])
        source_used = f"{source_used}+{nxt_name}" if source_used else nxt_name
        return (merged_lua, merged_mfs)

    if preferred_source == "sushi":
        try:
            res = fetch_from_sushi(appid, timeout=timeout)
            source_used = "Sushi"
        except Exception as e:
            if not target_gids:
                raise ValueError(f"Sorgente Sushi: {e}")

    elif preferred_source == "ryuu":
        try:
            res = fetch_from_ryuu(appid, timeout=timeout)
            source_used = "Ryuu"
        except Exception as e:
            if not target_gids:
                raise ValueError(f"Ryuu source: {e}")

    elif preferred_source == "hubcap":
        if not key and not target_gids:
            raise ValueError("An API key is required for Hubcap source")
        if key:
            try:
                url = f"{HUBCAP}/api/v1/manifest/{appid}?{urllib.parse.urlencode({'api_key': key})}"
                res = _safe_extract(_download(url, timeout=timeout), appid)
                source_used = "Hubcap"
            except Exception:
                if not target_gids:
                    raise

    if preferred_source == "auto" or target_gids:
        # 1. Try Sushi (fast, GitHub CDN, free) if not already queried
        if preferred_source != "sushi":
            need_more = (res is None) or bool(_missing_target_gids(res[1], target_gids))
            if need_more:
                try:
                    s_res = fetch_from_sushi(appid, timeout=15)
                    res = _combine(res, s_res, "Sushi")
                except Exception:
                    pass

        # 2. If not on Sushi (or if target_gids manifests are missing), try Ryuu
        if preferred_source != "ryuu":
            need_more = (res is None) or bool(_missing_target_gids(res[1], target_gids))
            if need_more:
                try:
                    if check_ryuu(appid, timeout=8):
                        ryuu_res = fetch_from_ryuu(appid, timeout=timeout)
                        res = _combine(res, ryuu_res, "Ryuu")
                except Exception:
                    pass

        # 3. If still absent (or missing target_gids) and user configured a Hubcap key, try Hubcap
        if preferred_source != "hubcap":
            need_more = (res is None) or bool(_missing_target_gids(res[1], target_gids))
            if need_more and key:
                try:
                    url = f"{HUBCAP}/api/v1/manifest/{appid}?{urllib.parse.urlencode({'api_key': key})}"
                    hc_res = _safe_extract(_download(url, timeout=timeout), appid)
                    res = _combine(res, hc_res, "Hubcap")
                except Exception:
                    pass

    if res is None:
        raise ValueError(f"No manifest/lua found for appid {appid} on available sources (Sushi, Ryuu, Hubcap)")

    lua_text, manifests = res
    manifests = dict(manifests)

    # If specific target_gids were requested and not yet present in archive, try per-depot download
    for dep, gid in _missing_target_gids(manifests, target_gids).items():
        blob = fetch_depot_manifest(dep, gid, key=key, timeout=10)
        if blob:
            manifests[f"{dep}_{gid}.manifest"] = blob

    if auto_update:
        lua_text = comment_out_manifest_pins(lua_text)

    return {"lua": lua_text, "manifests": manifests, "source": source_used}



def fetch_lua(appid, key=None, base=HUBCAP, timeout=60, auto_update=True):
    """Maintains backward compatibility for CLI and unit tests."""
    appid = int(appid)
    if base != HUBCAP:
        # Custom server (e.g. mock in unit tests)
        if not key:
            raise ValueError("API key required (maclua config set-key)")
        url = "%s/api/v1/manifest/%d?%s" % (
            base.rstrip("/"), appid, urllib.parse.urlencode({"api_key": key}))
        lua_text, manifests = _safe_extract(_download(url, timeout), appid)
        if auto_update:
            lua_text = comment_out_manifest_pins(lua_text)
        return {"lua": lua_text, "manifests": manifests}

    # Default base: uses fetch_from_sources
    from core import settings
    pref = settings.get("preferred_source", "auto")
    eff_key = key or settings.get("hubcap_key", None)
    return fetch_from_sources(appid, key=eff_key, preferred_source=pref, auto_update=auto_update, timeout=timeout)
