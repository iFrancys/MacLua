"""Sorgente lua remota: download zip da hubcapmanifest + validazione.

Endpoint (sondato live): GET {base}/api/v1/manifest/<appid>?api_key=<key>
con <key> via query (l'API accetta anche Bearer/X-API-Key). Risponde 200
con uno zip contenente esattamente un <appid>.lua (+ eventuali manifest).
Validazione stretta prima di usare un byte: niente path assoluti, niente
"..", niente symlink, niente entry speciali, cap su numero/size.
"""
import io
import os
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from core.lua import parse_lua

HUBCAP = "https://hubcapmanifest.com"
_MAX_ZIP_BYTES = 256 * 1024 * 1024
_MAX_ENTRIES = 10000
_MAX_EXPANDED = 1024 * 1024 * 1024
_MAX_LUA = 16 * 1024 * 1024
_MAX_MANIFEST = 64 * 1024 * 1024


def _download(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "MacLua/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise ValueError("HTTP %s" % resp.status)
            size = resp.headers.get("Content-Length")
            if size is not None and int(size) > _MAX_ZIP_BYTES:
                raise ValueError("zip oltre 256MB")
            data = resp.read(_MAX_ZIP_BYTES + 1)
            if len(data) > _MAX_ZIP_BYTES:
                raise ValueError("zip oltre 256MB")
            return data
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ValueError("chiave API rifiutata (401/403)")
        if e.code == 404:
            raise ValueError("nessun lua per questa app sulla sorgente")
        if e.code == 429:
            raise ValueError("troppe richieste, riprova più tardi")
        raise ValueError("HTTP %s" % e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError("sorgente non raggiungibile: %s" % e)


def _safe_extract(data, appid):
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("la sorgente non ha risposto uno zip valido")
    names = zf.namelist()
    if len(names) > _MAX_ENTRIES:
        raise ValueError("troppe entry nello zip")
    total = 0
    for info in zf.infolist():
        total += info.file_size
        if total > _MAX_EXPANDED:
            raise ValueError("zip espanso oltre 1GB")
        name = info.filename
        if (name.startswith("/") or ".." in name.split("/")
                or info.is_dir()
                or (info.external_attr >> 16) & 0o170000 in (0o120000,)):
            raise ValueError("entry non sicura nello zip: %r" % name)
    want = "%d.lua" % appid
    if sum(1 for n in names if n.rsplit("/", 1)[-1] == want) != 1:
        raise ValueError("nello zip manca %s (o duplicato)" % want)
    lua_raw = zf.read(next(n for n in names if n.rsplit("/", 1)[-1] == want))
    if len(lua_raw) > _MAX_LUA or not lua_raw:
        raise ValueError("%s illeggibile" % want)
    try:
        lua_text = lua_raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("%s non UTF-8" % want)
    parsed = parse_lua(lua_text)
    if appid not in parsed["bare"] and appid not in parsed["keys"]:
        raise ValueError("il lua scaricato è per un'altra app")
    manifests = {}
    for n in names:
        base = n.rsplit("/", 1)[-1]
        if base.endswith(".manifest"):
            with zf.open(n) as f:
                blob = f.read(_MAX_MANIFEST + 1)
            if len(blob) > _MAX_MANIFEST:
                raise ValueError("manifest oltre 64MB: %s" % base)
            manifests[base] = blob
    return lua_text, manifests


def fetch_lua(appid, key, base=HUBCAP, timeout=60):
    """{'lua': str, 'manifests': {nome: bytes}}. Solleva ValueError."""
    appid = int(appid)
    if not key:
        raise ValueError("serve una chiave API (maclua config set-key)")
    url = "%s/api/v1/manifest/%d?%s" % (
        base.rstrip("/"), appid, urllib.parse.urlencode({"api_key": key}))
    lua_text, manifests = _safe_extract(_download(url, timeout), appid)
    return {"lua": lua_text, "manifests": manifests}
