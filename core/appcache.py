"""Cache persistente per metadati Steam, copertine e nomi giochi.
Riduce il carico sulle API Valve e garantisce disponibilità offline.
"""
import os
import json
import time

CACHE_DIR = os.path.expanduser("~/Library/Application Support/MacLua/cache")
CACHE_FILE = os.path.join(CACHE_DIR, "appcache.json")
DEFAULT_TTL = 7 * 86400  # 7 giorni di validità


def _ensure():
    os.makedirs(CACHE_DIR, exist_ok=True)
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)


def _load():
    _ensure()
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data):
    _ensure()
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CACHE_FILE)


def get_info(appid):
    """Restituisce le info cached se presenti e non scadute."""
    data = _load()
    key = str(appid)
    if key in data:
        item = data[key]
        if time.time() - item.get("cached_at", 0) < item.get("ttl", DEFAULT_TTL):
            return item.get("payload")
    return None


def set_info(appid, payload, ttl=DEFAULT_TTL):
    """Memorizza le info nella cache."""
    data = _load()
    data[str(appid)] = {
        "cached_at": time.time(),
        "ttl": ttl,
        "payload": payload
    }
    _save(data)


def clear():
    """Svuota la cache."""
    _save({})
