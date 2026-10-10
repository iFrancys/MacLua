"""Config locale MacLua: SOLO la chiave API hubcap, file 0600.

Precedenza: env MACLUA_HUBCAP_KEY > file. La chiave non passa mai per i log.
"""
import json
import os


def config_dir(home=None):
    h = home if home else os.path.expanduser("~")
    return os.path.join(h, "Library/Application Support/MacLua")


def key_file(home=None):
    return os.path.join(config_dir(home), "config.json")


def set_key(home, key):
    key = (key or "").strip()
    if not key:
        raise ValueError("chiave vuota")
    d = config_dir(home)
    os.makedirs(d, exist_ok=True)
    os.chmod(d, 0o700)
    path = key_file(home)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps({"hubcap_key": key}))
    os.rename(tmp, path)
    os.chmod(path, 0o600)
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
    """Rimuove la chiave salvata su file. True se esisteva."""
    try:
        os.remove(key_file(home))
        return True
    except OSError:
        return False
