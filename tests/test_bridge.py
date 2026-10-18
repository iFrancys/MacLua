import time
from unittest.mock import patch

import pytest

from core import bridge


@pytest.fixture(autouse=True)
def _reset_stale_state():
    def _reset():
        bridge._STALE_STATE.update({"last_restart": None,
                                    "consecutive_restarts": 0,
                                    "last_notify": None})
    _reset()
    yield
    _reset()


def test_stale_noop_without_installed_games():
    games = [{"appid": 322170, "installed": False}]
    with patch("core.bridge.steamhook.is_cdp_available", return_value=True), \
         patch("core.bridge.steamhook.get_managed_games", return_value=games):
        assert bridge.check_stale_client_licenses(home="/tmp/maclua-test") is False


def test_stale_noop_without_cdp():
    games = [{"appid": 322170, "installed": True}]
    with patch("core.bridge.steamhook.is_cdp_available", return_value=False), \
         patch("core.bridge.steamhook.get_managed_games", return_value=games), \
         patch("core.bridge.steamhook.client_app_licensed") as lic:
        assert bridge.check_stale_client_licenses(home="/tmp/maclua-test") is False
        lic.assert_not_called()


def test_stale_noop_when_client_licensed():
    games = [{"appid": 322170, "installed": True}]
    with patch("core.bridge.steamhook.is_cdp_available", return_value=True), \
         patch("core.bridge.steamhook.get_managed_games", return_value=games), \
         patch("core.bridge.steamhook.client_app_licensed", return_value=True) as lic:
        assert bridge.check_stale_client_licenses(home="/tmp/maclua-test") is False
        lic.assert_called_once_with(322170)


def test_stale_checks_every_installed_game():
    games = [{"appid": 322170, "installed": True},
             {"appid": 413150, "installed": True},
             {"appid": 730, "installed": False}]
    with patch("core.bridge.steamhook.is_cdp_available", return_value=True), \
         patch("core.bridge.steamhook.get_managed_games", return_value=games), \
         patch("core.bridge.steamhook.client_app_licensed", return_value=True) as lic:
        assert bridge.check_stale_client_licenses(home="/tmp/maclua-test") is False
        assert lic.call_count == 2


def test_stale_noop_when_client_unreachable():
    games = [{"appid": 322170, "installed": True}]
    with patch("core.bridge.steamhook.is_cdp_available", return_value=True), \
         patch("core.bridge.steamhook.get_managed_games", return_value=games), \
         patch("core.bridge.steamhook.client_app_licensed", return_value=None), \
         patch("core.bridge.steamhook.notify_macos") as notify:
        assert bridge.check_stale_client_licenses(home="/tmp/maclua-test") is False
        notify.assert_not_called()


def _stale_env(tmp_path, running=(), setting_on=True):
    (tmp_path / "packageinfo.vdf").write_bytes(b"x")
    return [
        patch("core.bridge.steamhook.is_cdp_available", return_value=True),
        patch("core.bridge.steamhook.get_managed_games",
              return_value=[{"appid": 322170, "installed": True}]),
        patch("core.bridge.steamhook.client_app_licensed", return_value=False),
        patch("core.bridge.paths.appcache", return_value=str(tmp_path)),
        patch("maclua._managed_sets", return_value=({322170}, {322171})),
        patch("core.bridge.license.check", return_value=(set(), set())),
        patch("core.bridge.steamhook.running_managed_appids",
              return_value=list(running)),
        patch("core.bridge.settings.get", return_value=setting_on),
    ]


def test_stale_restarts_steam_when_safe(tmp_path):
    patches = _stale_env(tmp_path)
    for p in patches:
        p.start()
    try:
        with patch("core.bridge.steamhook.restart_steam") as restart, \
             patch("core.bridge.steamhook.notify_macos") as notify:
            res = bridge.check_stale_client_licenses(home=str(tmp_path))
    finally:
        for p in patches:
            p.stop()
    assert res["restarted"] is True
    assert res["stale"] == [322170]
    restart.assert_called_once()
    notify.assert_called_once()


def test_stale_defers_while_game_running(tmp_path):
    patches = _stale_env(tmp_path, running=[322170])
    for p in patches:
        p.start()
    try:
        with patch("core.bridge.steamhook.restart_steam") as restart, \
             patch("core.bridge.steamhook.notify_macos") as notify:
            res = bridge.check_stale_client_licenses(home=str(tmp_path))
    finally:
        for p in patches:
            p.stop()
    assert res["restarted"] is False
    assert res["reason"] == "game_running"
    restart.assert_not_called()
    notify.assert_called_once()


def test_stale_never_restarts_when_setting_off(tmp_path):
    patches = _stale_env(tmp_path, setting_on=False)
    for p in patches:
        p.start()
    try:
        with patch("core.bridge.steamhook.restart_steam") as restart, \
             patch("core.bridge.steamhook.notify_macos"):
            res = bridge.check_stale_client_licenses(home=str(tmp_path))
    finally:
        for p in patches:
            p.stop()
    assert res["restarted"] is False
    assert res["reason"] == "setting_off"
    restart.assert_not_called()


def test_stale_anti_loop_after_max_restarts(tmp_path):
    bridge._STALE_STATE["consecutive_restarts"] = bridge._MAX_STALE_RESTARTS
    patches = _stale_env(tmp_path)
    for p in patches:
        p.start()
    try:
        with patch("core.bridge.steamhook.restart_steam") as restart, \
             patch("core.bridge.steamhook.notify_macos") as notify:
            res = bridge.check_stale_client_licenses(home=str(tmp_path))
    finally:
        for p in patches:
            p.stop()
    assert res["restarted"] is False
    assert res["reason"] == "limit"
    restart.assert_not_called()
    notify.assert_called_once()


def test_stale_cooldown_after_recent_restart(tmp_path):
    bridge._STALE_STATE["last_restart"] = time.monotonic()
    patches = _stale_env(tmp_path)
    for p in patches:
        p.start()
    try:
        with patch("core.bridge.steamhook.restart_steam") as restart:
            res = bridge.check_stale_client_licenses(home=str(tmp_path))
    finally:
        for p in patches:
            p.stop()
    assert res["restarted"] is False
    assert res["reason"] == "cooldown"
    restart.assert_not_called()


def test_stale_resets_restart_counter_when_healthy(tmp_path):
    bridge._STALE_STATE["consecutive_restarts"] = 2
    games = [{"appid": 322170, "installed": True}]
    with patch("core.bridge.steamhook.is_cdp_available", return_value=True), \
         patch("core.bridge.steamhook.get_managed_games", return_value=games), \
         patch("core.bridge.steamhook.client_app_licensed", return_value=True):
        assert bridge.check_stale_client_licenses(home="/tmp/maclua-test") is False
    assert bridge._STALE_STATE["consecutive_restarts"] == 0


def test_stale_noop_when_file_incomplete(tmp_path):
    (tmp_path / "packageinfo.vdf").write_bytes(b"x")
    games = [{"appid": 322170, "installed": True}]
    with patch("core.bridge.steamhook.is_cdp_available", return_value=True), \
         patch("core.bridge.steamhook.get_managed_games", return_value=games), \
         patch("core.bridge.steamhook.client_app_licensed", return_value=False), \
         patch("core.bridge.paths.appcache", return_value=str(tmp_path)), \
         patch("maclua._managed_sets", return_value=({322170}, set())), \
         patch("core.bridge.license.check", return_value=({322170}, set())), \
         patch("core.bridge.steamhook.restart_steam") as restart, \
         patch("core.bridge.steamhook.notify_macos") as notify:
        assert bridge.check_stale_client_licenses(home=str(tmp_path)) is False
        restart.assert_not_called()
        notify.assert_not_called()


def test_bridge_post_restart_steam_and_cleanup_manifests_no_unbound_local(tmp_path):
    """Regressione: do_POST non deve mai ridefinire localmente `steamhook`,
    altrimenti /restart-steam e /cleanup-manifests falliscono con UnboundLocalError."""
    import io
    sent = []

    class DummyHandler(bridge.BridgeHandler):
        def __init__(self, path):
            self.path = path
            self.headers = {"Content-Length": "2"}
            self.rfile = io.BytesIO(b"{}")

        def _verify_auth(self):
            return True

        def _send_json(self, status, payload):
            sent.append((status, payload))

    with patch("core.bridge.steamhook.restart_steam", return_value={"ok": True, "restarted": True}):
        DummyHandler("/restart-steam").do_POST()
    assert sent[-1] == (200, {"ok": True, "restarted": True})

    with patch("core.bridge.paths.steamapps", return_value=str(tmp_path)), \
         patch("core.bridge.install.cleanup_broken_appmanifests", return_value=[]), \
         patch("core.bridge.install.reconcile_installed_appmanifests", return_value=[]), \
         patch("core.bridge.steamhook.sync_library_in_steam", return_value={"ok": True}):
        DummyHandler("/cleanup-manifests").do_POST()
    assert sent[-1][0] == 200
    assert sent[-1][1]["ok"] is True

