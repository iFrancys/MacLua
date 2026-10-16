import json
from unittest.mock import patch, MagicMock
from core import steamhook

def test_steamhook_broadcasts_library_update_on_add():
    assert hasattr(steamhook, "broadcast_library_refresh")

def test_broadcast_library_refresh_safe_count(tmp_path):
    res = steamhook.broadcast_library_refresh(home=str(tmp_path))
    assert res["ok"] is True
    assert "count" in res


def _fake_urlopen(tabs):
    resp = MagicMock()
    resp.read.return_value = json.dumps(tabs).encode("utf-8")
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm

def test_client_app_licensed_none_when_cdp_unreachable():
    with patch("core.steamhook.urllib.request.urlopen", side_effect=OSError):
        assert steamhook.client_app_licensed(322170) is None

def test_client_app_licensed_none_without_shared_context():
    tabs = [{"title": "Store", "webSocketDebuggerUrl": "ws://x"}]
    with patch("core.steamhook.urllib.request.urlopen", return_value=_fake_urlopen(tabs)):
        assert steamhook.client_app_licensed(322170) is None

def test_client_app_licensed_maps_client_answer():
    tabs = [{"title": "SharedJSContext", "webSocketDebuggerUrl": "ws://127.0.0.1:8080/devtools/page/1"}]
    fake_client = MagicMock()
    with patch("core.steamhook.urllib.request.urlopen", return_value=_fake_urlopen(tabs)), \
         patch("core.steamhook.cdp.CDPClient", return_value=fake_client):
        fake_client.evaluate.return_value = "true"
        assert steamhook.client_app_licensed(322170) is True
        fake_client.evaluate.return_value = "false"
        assert steamhook.client_app_licensed(322170) is False
        fake_client.evaluate.return_value = None
        assert steamhook.client_app_licensed(322170) is None

def test_notify_macos_builds_clean_osascript_command():
    with patch("subprocess.run") as run:
        assert steamhook.notify_macos("MacLua", 'Riavvia "Steam"') is True
        run.assert_called_once()
        args = run.call_args[0][0]
        assert args[0] == "/usr/bin/osascript"
        assert args[2] == 'display notification "Riavvia \'Steam\'" with title "MacLua"'

def test_notify_macos_failure_is_silent():
    with patch("subprocess.run", side_effect=OSError):
        assert steamhook.notify_macos("MacLua", "test") is False

