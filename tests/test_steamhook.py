import json
from unittest.mock import patch, MagicMock
from core import steamhook

def test_steamhook_broadcasts_library_update_on_add():
    assert hasattr(steamhook, "broadcast_library_refresh")

def test_broadcast_library_refresh_sends_to_steamloopback(tmp_path):
    mock_tabs = [
        {
            "id": "tab1",
            "title": "SharedJSContext",
            "url": "https://steamloopback.host/index.html",
            "webSocketDebuggerUrl": "ws://127.0.0.1:8080/page/1"
        },
        {
            "id": "tab2",
            "title": "Store",
            "url": "https://store.steampowered.com/",
            "webSocketDebuggerUrl": "ws://127.0.0.1:8080/page/2"
        }
    ]

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_tabs).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    mock_client = MagicMock()

    with patch("urllib.request.urlopen", return_value=mock_resp), \
         patch("core.cdp.CDPClient", return_value=mock_client):
        res = steamhook.broadcast_library_refresh(home=str(tmp_path))
        assert res["ok"] is True
        # CDPClient should have been opened for the steamloopback tab
        assert mock_client.evaluate.called
        eval_arg = mock_client.evaluate.call_args[0][0]
        assert "__MacLuaSyncLibrary" in eval_arg
