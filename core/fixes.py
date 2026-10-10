"""Registro delle correzioni applicate (Fix Index).
Tiene traccia di modifiche di compatibilità, wrapper Mach-O e patch applicate ai giochi.
"""
import os
import json
import time

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
    tmp = FIXES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, FIXES_FILE)


def record_fix(appid, fix_type, details=None):
    """Registra una correzione applicata a un gioco."""
    data = _load()
    key = str(appid)
    if key not in data:
        data[key] = []

    fix_entry = {
        "type": fix_type,
        "details": details or {},
        "timestamp": int(time.time())
    }
    # Evita duplicati identici
    data[key] = [f for f in data[key] if f.get("type") != fix_type]
    data[key].append(fix_entry)
    _save(data)
    return fix_entry


def get_fixes(appid=None):
    """Restituisce le correzioni registrate per un gioco o per tutti."""
    data = _load()
    if appid is not None:
        return data.get(str(appid), [])
    return data
