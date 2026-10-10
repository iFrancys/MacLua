"""Test per le nuove funzionalità ispirate a LuaTools:
Settings, NetResilience (DoH), AppCache, Vault, Fixes, Updates, Collections, Queue, Bridge HTTP e SteamHook.
"""
import os
import json
import time
import pytest
from core import settings, netresil, appcache, vault, fixes, updates, collections as coll_mod, queue, steamhook, bridge


def test_settings_get_set(tmp_path, monkeypatch):
    s_file = str(tmp_path / "settings.json")
    monkeypatch.setattr(settings, "SETTINGS_FILE", s_file)
    monkeypatch.setattr(settings, "SETTINGS_DIR", str(tmp_path))

    assert settings.get("dns_mode") == "auto"
    settings.set_val("dns_mode", "always")
    assert settings.get("dns_mode") == "always"

    all_s = settings.get_all()
    assert all_s["dns_mode"] == "always"
    assert "theme" in all_s


def test_netresil_modes(monkeypatch):
    monkeypatch.setattr(settings, "get", lambda k, d=None: "never" if k == "dns_mode" else d)
    # in never mode, should use socket.gethostbyname
    monkeypatch.setattr(netresil.socket, "gethostbyname", lambda h: "1.2.3.4")
    assert netresil.resolve("example.com") == "1.2.3.4"

    # in always mode, should try DoH
    monkeypatch.setattr(settings, "get", lambda k, d=None: "always" if k == "dns_mode" else "cloudflare")
    monkeypatch.setattr(netresil, "resolve_doh", lambda h, provider="cloudflare": "5.6.7.8")
    assert netresil.resolve("example.com") == "5.6.7.8"


def test_appcache(tmp_path, monkeypatch):
    c_file = str(tmp_path / "appcache.json")
    monkeypatch.setattr(appcache, "CACHE_FILE", c_file)
    monkeypatch.setattr(appcache, "CACHE_DIR", str(tmp_path))

    assert appcache.get_info(12345) is None
    appcache.set_info(12345, {"name": "Test Game", "rating": 95}, ttl=60)
    cached = appcache.get_info(12345)
    assert cached["name"] == "Test Game"

    # expired ttl
    appcache.set_info(12345, {"name": "Expired"}, ttl=-1)
    assert appcache.get_info(12345) is None


def test_vault_snapshots_and_restore(tmp_path, monkeypatch):
    v_dir = str(tmp_path / "vault")
    target_dir = str(tmp_path / "stplug-in")
    os.makedirs(target_dir, exist_ok=True)
    monkeypatch.setattr(vault, "VAULT_DIR", v_dir)

    rep1 = vault.snapshot(322170, "addappid(322170)\n", note="v1")
    time.sleep(0.01)
    rep2 = vault.snapshot(322170, "addappid(322170)\naddappid(322171)\n", note="v2")

    snaps = vault.list_snapshots(322170)
    assert len(snaps) == 2
    assert snaps[0]["note"] == "v2"

    # Test restore
    vault.restore(322170, rep1["timestamp"], target_dir)
    restored_lua = os.path.join(target_dir, "322170.lua")
    with open(restored_lua, "r") as f:
        content = f.read()
    assert content == "addappid(322170)\n"


def test_fixes_tracking(tmp_path, monkeypatch):
    f_file = str(tmp_path / "fixes.json")
    monkeypatch.setattr(fixes, "FIXES_FILE", f_file)
    monkeypatch.setattr(fixes, "FIXES_DIR", str(tmp_path))

    fixes.record_fix(322170, "macho_launcher", {"file": "Geometry Dash"})
    fx = fixes.get_fixes(322170)
    assert len(fx) == 1
    assert fx[0]["type"] == "macho_launcher"


def test_collections_parsing_and_fallback(tmp_path, monkeypatch):
    c_file = str(tmp_path / "collections_cache.json")
    monkeypatch.setattr(coll_mod, "CACHE_FILE", c_file)
    monkeypatch.setattr(coll_mod, "CACHE_DIR", str(tmp_path))

    # Offline fallback should return default curated pack without error
    import urllib.request
    def mock_fail(*args, **kwargs):
        raise OSError("Network unreachable")
    monkeypatch.setattr(urllib.request, "urlopen", mock_fail)

    res = coll_mod.fetch_collections()
    assert len(res["collections"]) >= 1
    assert res["cached"] is True

    # Test details lookup
    details = coll_mod.fetch_collection_details("e4f40c3c-friendslop")
    assert "apps" in details
    assert len(details["apps"]) >= 1


def test_queue_enqueue_and_cancel():
    q = queue.DownloadQueue(auto_start=False)
    q.enqueue(99999, "Gioco Fake")
    st = q.get_status()
    assert any(item["appid"] == 99999 for item in st["queued"])

    q.cancel(99999)
    st = q.get_status()
    assert not any(item["appid"] == 99999 for item in st["queued"])


def test_steamhook_enable_disable(tmp_path, monkeypatch):
    steam_root = str(tmp_path / "Steam")
    os.makedirs(steam_root, exist_ok=True)
    monkeypatch.setattr(steamhook.paths, "steam_root", lambda home=None: steam_root)
    monkeypatch.setattr(steamhook, "HOOK_DIR", str(tmp_path / "MacLua"))
    monkeypatch.setattr(steamhook, "MANIFEST_FILE", str(tmp_path / "MacLua" / "hook_manifest.json"))
    monkeypatch.setattr(steamhook, "TOKEN_FILE", str(tmp_path / "MacLua" / "bridge_token"))

    token = steamhook.get_or_create_token()
    assert len(token) >= 32

    en = steamhook.enable_hook()
    assert os.path.exists(os.path.join(steam_root, ".cef-enable-remote-debugging"))

    dis = steamhook.disable_hook()
    assert not os.path.exists(os.path.join(steam_root, ".cef-enable-remote-debugging"))
