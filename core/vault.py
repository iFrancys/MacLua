"""Lua Vault: Sistema di backup, versioning e ripristino per i file lua.
Permette di conservare storici delle configurazioni e ripristinare versioni precedenti.
"""
import os
import time
import hashlib
import json

VAULT_DIR = os.path.expanduser("~/Library/Application Support/MacLua/vault")


def _ensure(appid=None):
    os.makedirs(VAULT_DIR, exist_ok=True)
    if appid is not None:
        p = os.path.join(VAULT_DIR, str(appid))
        os.makedirs(p, exist_ok=True)
        return p
    return VAULT_DIR


def snapshot(appid, lua_content, note="Auto snapshot"):
    """Crea un salvataggio versionato del file lua per un dato appid."""
    app_dir = _ensure(appid)
    if isinstance(lua_content, str):
        data = lua_content.encode("utf-8")
    else:
        data = lua_content

    h = hashlib.sha256(data).hexdigest()[:12]
    ts = int(time.time() * 1000)
    fn = f"{ts}_{h}.lua"
    p = os.path.join(app_dir, fn)
    with open(p, "wb") as f:
        f.write(data)

    # Scrivi metadati
    meta_fn = f"{ts}_{h}.json"
    with open(os.path.join(app_dir, meta_fn), "w", encoding="utf-8") as f:
        json.dump({
            "appid": appid,
            "timestamp": ts,
            "hash": h,
            "bytes": len(data),
            "note": note
        }, f, indent=2)

    return {"appid": appid, "timestamp": ts, "hash": h, "filename": fn}


def list_snapshots(appid=None):
    """Restituisce la cronologia dei backup per un appid (o per tutti)."""
    _ensure()
    results = []
    if appid is not None:
        app_dirs = [os.path.join(VAULT_DIR, str(appid))]
    else:
        app_dirs = [os.path.join(VAULT_DIR, d) for d in os.listdir(VAULT_DIR) if os.path.isdir(os.path.join(VAULT_DIR, d))]

    for ad in app_dirs:
        if not os.path.isdir(ad):
            continue
        cur_appid = int(os.path.basename(ad)) if os.path.basename(ad).isdigit() else 0
        for f in sorted(os.listdir(ad), reverse=True):
            if f.endswith(".json"):
                try:
                    with open(os.path.join(ad, f), "r", encoding="utf-8") as mf:
                        results.append(json.load(mf))
                except Exception:
                    pass
    return sorted(results, key=lambda x: x.get("timestamp", 0), reverse=True)


def restore(appid, timestamp, target_dir):
    """Ripristina una versione salvata nel percorso stplug-in."""
    app_dir = _ensure(appid)
    target_lua = os.path.join(target_dir, f"{appid}.lua")

    found_lua = None
    for f in os.listdir(app_dir):
        if f.startswith(f"{timestamp}_") and f.endswith(".lua"):
            found_lua = os.path.join(app_dir, f)
            break

    if not found_lua or not os.path.exists(found_lua):
        raise FileNotFoundError(f"Nessun backup trovato per appid {appid} al timestamp {timestamp}")

    with open(found_lua, "rb") as sf, open(target_lua, "wb") as df:
        df.write(sf.read())

    return True
