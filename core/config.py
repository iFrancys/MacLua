"""Local MacLua config: ONLY the hubcap API key, 0600 file.

Precedence: env MACLUA_HUBCAP_KEY > file. The key is never logged.
"""
import json
import os

from core.atomic import atomic_write


def config_dir(home=None):
    h = home if home else os.path.expanduser("~")
    return os.path.join(h, "Library/Application Support/MacLua")


def key_file(home=None):
    return os.path.join(config_dir(home), "config.json")


def set_key(home, key):
    key = (key or "").strip()
    if not key:
        raise ValueError("empty key")
    d = config_dir(home)
    os.makedirs(d, exist_ok=True)
    os.chmod(d, 0o700)
    path = key_file(home)
    atomic_write(path, json.dumps({"hubcap_key": key}), mode=0o600)
    return path


def get_key(home=None):
    env = os.getenv("MACLUA_HUBCAP_KEY", "").strip()
    if env:
        return env
    try:
        with open(key_file(home), encoding="utf-8") as f:
            return json.loads(f.read()).get("hubcap_key") or None
    except (OSError, ValueError):
        return None


def clear_key(home=None):
    """Removes key saved to file. Returns True if it existed."""
    try:
        os.remove(key_file(home))
        return True
    except OSError:
        return False

