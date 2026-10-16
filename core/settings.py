"""Gestione impostazioni centralizzate di MacLua.
Condivise tra il backend Python, il bridge HTTP e l'interfaccia in-Steam.
File memorizzato in ~/Library/Application Support/MacLua/settings.json.
"""
import os
import json

SETTINGS_DIR = os.path.expanduser("~/Library/Application Support/MacLua")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "dns_mode": "auto",           # "auto", "always", "never"
    "doh_provider": "cloudflare",  # "cloudflare", "google"
    "max_parallel_downloads": 4,
    "auto_update_apps": True,
    "steam_hook_enabled": False,
    "fast_fetch": True,
    "theme": "dark",              # "dark", "light", "steam", "cyberpunk"
    "accent_color": "#38bdf8",    # sky blue default
    "card_opacity": 0.85,
    "background_mode": "default", # "default", "color", "image", "gif"
    "background_path": "",
    "background_blur": 15.0,
    "background_dim": 0.35,
    "low_power_pause_gif": True,
    "preferred_source": "auto",   # "auto", "sushi", "ryuu", "hubcap"
    "hubcap_key": "",
    "donate_keys": False,
}


def _ensure_dir():
    os.makedirs(SETTINGS_DIR, exist_ok=True)


def get_all():
    _ensure_dir()
    if not os.path.exists(SETTINGS_FILE):
        save_all(DEFAULT_SETTINGS)
        data = dict(DEFAULT_SETTINGS)
    else:
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    merged = dict(DEFAULT_SETTINGS)
    merged.update(data)
    # Sincronizza hubcap_key con config.py se vuoto
    if not merged.get("hubcap_key"):
        from core import config
        k = config.get_key()
        if k:
            merged["hubcap_key"] = k
    return merged


def get(key, default=None):
    settings = get_all()
    return settings.get(key, default if default is not None else DEFAULT_SETTINGS.get(key))


def set_val(key, value):
    settings = get_all()
    settings[key] = value
    if key == "hubcap_key" and value:
        try:
            from core import config
            config.set_key(None, value)
        except Exception:
            pass
    save_all(settings)
    return settings


def save_all(settings):
    _ensure_dir()
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    os.replace(tmp, SETTINGS_FILE)
