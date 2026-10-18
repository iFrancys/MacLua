"""Applied Fixes Registry (Fix Index).
Tracks compatibility tweaks, Mach-O wrappers, and patches applied to games.
"""
import os
import json
import time

from core.atomic import atomic_write

FIXES_DIR = os.path.expanduser("~/Library/Application Support/MacLua")
FIXES_FILE = os.path.join(FIXES_DIR, "fixes.json")


def _ensure():
    os.makedirs(FIXES_DIR, exist_ok=True)
    if not os.path.exists(FIXES_FILE):
        with open(FIXES_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)


def _load():
    _ensure()
    try:
        with open(FIXES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data):
    _ensure()
    atomic_write(FIXES_FILE, json.dumps(data, indent=2, ensure_ascii=False))


def record_fix(appid, fix_type, details=None):
    """Records a compatibility fix applied to a game."""
    data = _load()
    key = str(appid)
    if key not in data:
        data[key] = []

    fix_entry = {
        "type": fix_type,
        "details": details or {},
        "timestamp": int(time.time())
    }
    # Avoid duplicate entries of the same type
    data[key] = [f for f in data[key] if f.get("type") != fix_type]
    data[key].append(fix_entry)
    _save(data)
    return fix_entry


def get_fixes(appid=None):
    """Returns recorded fixes for a specific appid or all games."""
    data = _load()
    if appid is not None:
        return data.get(str(appid), [])
    return data

