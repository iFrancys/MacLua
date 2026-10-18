"""Persistent cache for Steam metadata, covers, and game names.
Reduces load on Valve APIs and ensures offline availability.
"""
import os
import json
import time

from core.atomic import atomic_write

CACHE_DIR = os.path.expanduser("~/Library/Application Support/MacLua/cache")
CACHE_FILE = os.path.join(CACHE_DIR, "appcache.json")
DEFAULT_TTL = 7 * 86400  # 7 days validity


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
    atomic_write(CACHE_FILE, json.dumps(data, indent=2, ensure_ascii=False))


def get_info(appid):
    """Returns cached info if present and not expired."""
    data = _load()
    key = str(appid)
    if key in data:
        item = data[key]
        if time.time() - item.get("cached_at", 0) < item.get("ttl", DEFAULT_TTL):
            return item.get("payload")
    return None


def set_info(appid, payload, ttl=DEFAULT_TTL):
    """Stores info in cache."""
    data = _load()
    data[str(appid)] = {
        "cached_at": time.time(),
        "ttl": ttl,
        "payload": payload
    }
    _save(data)


def clear():
    """Clears the cache."""
    _save({})
