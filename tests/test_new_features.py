"""Test per le nuove funzionalità ispirate a LuaTools:
Settings, NetResilience (DoH), AppCache, Vault, Fixes, Updates, Collections, Queue, Bridge HTTP e SteamHook.
"""
import os
import json
import subprocess
import time
import pytest
from core import settings, netresil, appcache, vault, fixes, updates, collections as coll_mod, queue, steamhook, bridge


def test_install_bridge_agent_writes_plist(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.append(args))
    res = steamhook.install_bridge_agent(python_path="/usr/bin/python3", script_path="/x/maclua.py", home=str(tmp_path))
    plist = steamhook.bridge_agent_path(str(tmp_path))
    assert res["ok"] is True
    assert os.path.exists(plist)
    with open(plist) as f:
        content = f.read()
    assert "dev.maclua.bridge" in content
    assert "<string>serve</string>" in content
    assert any(c[:3] == ["launchctl", "load", "-w"] for c in calls)
    # Regressione: mai chiamare "launchctl unload" dentro install_bridge_agent,
    # altrimenti il demone bridge uccide se stesso con SIGTERM durante restart_steam().
    assert not any(c[:2] == ["launchctl", "unload"] for c in calls)


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
    monkeypatch.setattr(steamhook, "_candidate_markers", lambda home=None: [os.path.join(steam_root, ".cef-enable-remote-debugging")])
    monkeypatch.setattr(steamhook, "bridge_agent_path", lambda home=None: str(tmp_path / "dev.maclua.bridge.plist"))
    monkeypatch.setattr(steamhook, "HOOK_DIR", str(tmp_path / "MacLua"))
    monkeypatch.setattr(steamhook, "MANIFEST_FILE", str(tmp_path / "MacLua" / "hook_manifest.json"))
    monkeypatch.setattr(steamhook, "TOKEN_FILE", str(tmp_path / "MacLua" / "bridge_token"))
    # Mai parlare con launchd nei test: il label del plist è reale, un unload per path
    # scaricherebbe il servizio vero dell'utente.
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)

    token = steamhook.get_or_create_token()
    assert len(token) >= 32

    en = steamhook.enable_hook()
    assert os.path.exists(os.path.join(steam_root, ".cef-enable-remote-debugging"))

    dis = steamhook.disable_hook()
    assert not os.path.exists(os.path.join(steam_root, ".cef-enable-remote-debugging"))


def test_multidatabase_settings_and_rpc(tmp_path, monkeypatch):
    s_file = str(tmp_path / "settings.json")
    monkeypatch.setattr(settings, "SETTINGS_FILE", s_file)
    monkeypatch.setattr(settings, "SETTINGS_DIR", str(tmp_path))
    from core import config
    monkeypatch.setattr(config, "config_dir", lambda home=None: str(tmp_path))
    monkeypatch.setattr(config, "key_file", lambda home=None: str(tmp_path / "config.json"))

    settings.set_val("preferred_source", "sushi")
    settings.set_val("hubcap_key", "smm_test123")
    settings.set_val("donate_keys", True)

    assert settings.get("preferred_source") == "sushi"
    assert settings.get("hubcap_key") == "smm_test123"
    assert settings.get("donate_keys") is True


def test_steamhook_rpc_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(steamhook.paths, "steamapps", lambda home=None: str(tmp_path))
    monkeypatch.setattr(steamhook.paths, "stplug_in", lambda home=None: str(tmp_path / "stplug-in"))

    # Test /api-list
    res = steamhook.handle_rpc_request("/api-list")
    assert res["ok"] is True
    assert any(s["id"] == "sushi" for s in res["sources"])
    assert any(s["id"] == "ryuu" for s in res["sources"])
    assert any(s["id"] == "hubcap" for s in res["sources"])

    # Test /cleanup-manifests
    res_clean = steamhook.handle_rpc_request("/cleanup-manifests", method="POST")
    assert res_clean["ok"] is True
    assert "cleaned" in res_clean
