"""Catalogo Steam via API pubbliche (nessuna chiave richiesta).

- search: /api/storesearch/?term=... -> [{appid, name}]
- platforms: /api/appdetails?appids=... -> {windows,mac,linux} disponibili
"""
import json
import urllib.error
import urllib.parse
import urllib.request

STORE = "https://store.steampowered.com"


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "MacLua/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise ValueError("HTTP %s da %s" % (resp.status, url))
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            OSError, json.JSONDecodeError) as e:
        raise ValueError("catalogo non raggiungibile: %s" % e)


def search(query, base=STORE):
    """[(appid, name)] per nome gioco, ordinati per rilevanza dello store."""
    url = "%s/api/storesearch/?term=%s&l=english&cc=US" % (
        base.rstrip("/"), urllib.parse.quote(query))
    data = _get_json(url)
    out = []
    for item in data.get("items", []):
        try:
            out.append({"appid": int(item["id"]), "name": str(item["name"])})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def platforms(appid, base=STORE):
    """Sottoinsieme di {'windows','mac','linux'} disponibile."""
    url = "%s/api/appdetails?appids=%d&filters=platforms" % (
        base.rstrip("/"), int(appid))
    data = _get_json(url)
    entry = data.get(str(int(appid)), {})
    plats = ((entry.get("data") or {}).get("platforms") or {})
    return {k for k in ("windows", "mac", "linux") if plats.get(k) is True}


def app_details(appid, base=STORE):
    """Informazioni base dell'app dallo store: type, parent_appid, dlc, name."""
    url = "%s/api/appdetails?appids=%d&filters=basic" % (
        base.rstrip("/"), int(appid))
    try:
        data = _get_json(url)
    except Exception:
        return {}
    entry = (data.get(str(int(appid))) or {}).get("data") or {}
    t = entry.get("type") or "game"
    fg = entry.get("fullgame") or {}
    parent_id = None
    if fg.get("appid") and str(fg["appid"]).isdigit():
        parent_id = int(fg["appid"])
    dlcs = [int(x) for x in entry.get("dlc") or [] if str(x).isdigit()]
    return {
        "appid": int(appid),
        "name": entry.get("name") or "",
        "type": t,
        "is_dlc": (t == "dlc") or (parent_id is not None),
        "parent_appid": parent_id,
        "parent_name": fg.get("name"),
        "dlc": dlcs
    }


def parent_of(appid, base=STORE):
    """(parent_appid, parent_name) se appid è un DLC, altrimenti (None, None)."""
    info = app_details(appid, base=base)
    return info.get("parent_appid"), info.get("parent_name")


def dlc_ids(appid, base=STORE):
    """[dlc_appid, ...] per un gioco base dallo store."""
    info = app_details(appid, base=base)
    return info.get("dlc") or []


def name_of(appid, base=STORE):
    """Nome dell'app dallo store o None."""
    info = app_details(appid, base=base)
    return info.get("name") or None

