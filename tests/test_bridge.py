from unittest.mock import patch
from core import bridge


def test_stale_noop_without_installed_games():
    games = [{"appid": 322170, "installed": False}]
    with patch("core.bridge.steamhook.get_managed_games", return_value=games):
        assert bridge.check_stale_client_licenses(home="/tmp/maclua-test") is False


def test_stale_noop_when_client_licensed():
    games = [{"appid": 322170, "installed": True}]
    with patch("core.bridge.steamhook.get_managed_games", return_value=games), \
         patch("core.bridge.steamhook.client_app_licensed", return_value=True) as lic:
        assert bridge.check_stale_client_licenses(home="/tmp/maclua-test") is False
        lic.assert_called_once_with(322170)


def test_stale_noop_when_client_unreachable():
    games = [{"appid": 322170, "installed": True}]
    with patch("core.bridge.steamhook.get_managed_games", return_value=games), \
         patch("core.bridge.steamhook.client_app_licensed", return_value=None), \
         patch("core.bridge.steamhook.notify_macos") as notify:
        assert bridge.check_stale_client_licenses(home="/tmp/maclua-test") is False
        notify.assert_not_called()


def test_stale_notifies_when_file_ok_but_client_stale(tmp_path):
    (tmp_path / "packageinfo.vdf").write_bytes(b"x")
    games = [{"appid": 322170, "installed": True}]
    with patch("core.bridge.steamhook.get_managed_games", return_value=games), \
         patch("core.bridge.steamhook.client_app_licensed", return_value=False), \
         patch("core.bridge.paths.appcache", return_value=str(tmp_path)), \
         patch("maclua._managed_sets", return_value=({322170}, {322171})), \
         patch("core.bridge.license.check", return_value=(set(), set())), \
         patch("core.bridge.steamhook.notify_macos") as notify:
        assert bridge.check_stale_client_licenses(home=str(tmp_path)) is True
        notify.assert_called_once()


def test_stale_noop_when_file_incomplete(tmp_path):
    (tmp_path / "packageinfo.vdf").write_bytes(b"x")
    games = [{"appid": 322170, "installed": True}]
    with patch("core.bridge.steamhook.get_managed_games", return_value=games), \
         patch("core.bridge.steamhook.client_app_licensed", return_value=False), \
         patch("core.bridge.paths.appcache", return_value=str(tmp_path)), \
         patch("maclua._managed_sets", return_value=({322170}, set())), \
         patch("core.bridge.license.check", return_value=({322170}, set())), \
         patch("core.bridge.steamhook.notify_macos") as notify:
        assert bridge.check_stale_client_licenses(home=str(tmp_path)) is False
        notify.assert_not_called()
