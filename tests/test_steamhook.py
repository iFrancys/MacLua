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


def test_sync_library_script_never_touches_mobx_internals(tmp_path):
    """Regressione: la sincronizzazione deve assegnare solo proprietà osservabili pubbliche di appStore
    e invocare i metodi pubblici delle collezioni (ClearAppCounts, SetApps),
    senza mai toccare i simboli privati interni di MobX (getOwnPropertySymbols, value_,
    dependenciesState_, onBecomeStale_, derivation) né il fiber React."""
    tabs = [{"title": "SharedJSContext", "webSocketDebuggerUrl": "ws://127.0.0.1:8080/devtools/page/1"}]
    captured = {}

    fake_client = MagicMock()

    def _evaluate(script, *args, **kwargs):
        captured["script"] = script
        return json.dumps({"ok": True})

    fake_client.evaluate.side_effect = _evaluate

    with patch("core.steamhook.get_managed_games", return_value=[{"appid": 123, "installed": True}]), \
         patch("core.steamhook.urllib.request.urlopen", return_value=_fake_urlopen(tabs)), \
         patch("core.steamhook.cdp.CDPClient", return_value=fake_client):
        res = steamhook.sync_library_in_steam(home=str(tmp_path))

    assert res["ok"] is True
    script = captured["script"]
    # Nessuna manipolazione unsafe dei simboli privati di MobX o del fiber di React
    assert "getOwnPropertySymbols" not in script
    assert "dependenciesState_" not in script
    assert "onBecomeStale_" not in script
    assert "derivation" not in script
    assert "__reactFiber" not in script
    assert "ReactVirtualized" not in script
    # Uso esclusivo dei metodi pubblici ufficiali per le collezioni e proprietà di appStore
    assert "ClearAppCounts" in script
    assert "SetApps" in script
    assert "visible_in_game_list" in script
    assert "appStore.m_mapApps" in script


def test_refresh_steam_ui_tabs_removed():
    """La manipolazione del fiber ReactVirtualized è stata rimossa perché corrompeva MobX."""
    assert not hasattr(steamhook, "refresh_steam_ui_tabs")


