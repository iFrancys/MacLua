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
    # Synchronize "Lua" collection on native sets: additions go into both
    # live set (m_setApps) and m_setAddedManually, and membership is
    # persisted using native Save() method - never with custom flags or direct writes.
    assert "m_setAddedManually" in script
    assert "m_setRemovedManually" in script
    assert "col.Save" in script
    assert "__macluaLuaColRefreshed" not in script


def test_sync_library_script_never_reads_collectionstore_computeds(tmp_path):
    """Regression (crash "reading 'forEach'" / "removeEventListener" in library):
    on cold start reading collectionStore.uncategorizedCollection/userCollections before
    Steam sets m_mapCollectionsFromStorage permanently poisons the MobX computed.
    The script must await appStore.m_bIsInitialized and use only the raw map."""
    tabs = [{"title": "SharedJSContext", "webSocketDebuggerUrl": "ws://127.0.0.1:8080/devtools/page/1"}]
    captured = {}
    fake_client = MagicMock()

    def _evaluate(script, *args, **kwargs):
        captured["script"] = script
        return json.dumps({"ok": True})

    fake_client.evaluate.side_effect = _evaluate
    with patch("core.steamhook.get_managed_games", return_value=[{"appid": 123, "installed": False}]), \
         patch("core.steamhook.urllib.request.urlopen", return_value=_fake_urlopen(tabs)), \
         patch("core.steamhook.cdp.CDPClient", return_value=fake_client):
        steamhook.sync_library_in_steam(home=str(tmp_path))

    script = captured["script"]
    for computed in (".uncategorizedCollection", ".userCollections", ".collectionsFromStorage",
                     ".allAppsCollection", ".myGamesCollection", ".GetCollection("):
        assert computed not in script, computed
    assert "m_bIsInitialized" in script
    assert "m_mapCollectionsFromStorage" in script


def test_refresh_steam_ui_tabs_removed():
    """ReactVirtualized fiber manipulation was removed because it corrupted MobX."""
    assert not hasattr(steamhook, "refresh_steam_ui_tabs")


def test_remove_from_steam_library_also_cleans_lua_collection(tmp_path):
    """Removing a game from MacLua must also remove it from the "Lua" collection
    (m_setAddedManually + m_setApps + Save), without ever adding it to m_setRemovedManually."""
    tabs = [{"title": "SharedJSContext", "webSocketDebuggerUrl": "ws://127.0.0.1:8080/devtools/page/1"}]
    captured = {}
    fake_client = MagicMock()

    def _evaluate(script, *args, **kwargs):
        captured["script"] = script
        return "{}"

    fake_client.evaluate.side_effect = _evaluate
    with patch("core.steamhook.urllib.request.urlopen", return_value=_fake_urlopen(tabs)), \
         patch("core.steamhook.cdp.CDPClient", return_value=fake_client):
        steamhook.remove_from_steam_library(322170, home=str(tmp_path))

    script = captured["script"]
    assert "visible_in_game_list = false" in script
    assert "m_setAddedManually.delete" in script
    assert "m_setApps.delete" in script
    assert "col.Save" in script
    # Never mark as "removed manually": the app is simply outside MacLua, not manually removed by the user.
    assert "m_setRemovedManually.add" not in script


def test_running_managed_appids_matches_installdir(tmp_path):
    steamapps = tmp_path / "Library/Application Support/Steam/steamapps"
    stplug = tmp_path / "Library/Application Support/Steam/config/stplug-in"
    steamapps.mkdir(parents=True)
    stplug.mkdir(parents=True)
    (stplug / "322170.lua").write_text("addappid(322170)")
    (steamapps / "appmanifest_322170.acf").write_text(
        '"AppState"\n{\n\t"installdir"\t\t"Geometry Dash"\n}\n')
    seen = []

    def _run(cmd, **kwargs):
        seen.append(cmd)
        r = MagicMock()
        r.returncode = 0
        return r

    with patch("subprocess.run", side_effect=_run):
        assert steamhook.running_managed_appids(home=str(tmp_path)) == [322170]
    assert seen == [["/usr/bin/pgrep", "-f", "steamapps/common/Geometry Dash"]]


def test_running_managed_appids_ignores_games_not_running(tmp_path):
    steamapps = tmp_path / "Library/Application Support/Steam/steamapps"
    stplug = tmp_path / "Library/Application Support/Steam/config/stplug-in"
    steamapps.mkdir(parents=True)
    stplug.mkdir(parents=True)
    (stplug / "322170.lua").write_text("addappid(322170)")
    (steamapps / "appmanifest_322170.acf").write_text(
        '"AppState"\n{\n\t"installdir"\t\t"Geometry Dash"\n}\n')
    r = MagicMock()
    r.returncode = 1
    with patch("subprocess.run", return_value=r):
        assert steamhook.running_managed_appids(home=str(tmp_path)) == []


def test_running_managed_appids_only_managed(tmp_path):
    """Appmanifests without a MacLua-managed .lua file are ignored."""
    steamapps = tmp_path / "Library/Application Support/Steam/steamapps"
    stplug = tmp_path / "Library/Application Support/Steam/config/stplug-in"
    steamapps.mkdir(parents=True)
    stplug.mkdir(parents=True)
    (steamapps / "appmanifest_999.acf").write_text(
        '"AppState"\n{\n\t"installdir"\t\t"Altro"\n}\n')
    with patch("subprocess.run") as run:
        assert steamhook.running_managed_appids(home=str(tmp_path)) == []
        run.assert_not_called()


def test_running_managed_appids_conservative_on_pgrep_error(tmp_path):
    """Non-interpretable pgrep pattern (returncode >= 2): be conservative, consider game active."""
    steamapps = tmp_path / "Library/Application Support/Steam/steamapps"
    stplug = tmp_path / "Library/Application Support/Steam/config/stplug-in"
    steamapps.mkdir(parents=True)
    stplug.mkdir(parents=True)
    (stplug / "322170.lua").write_text("addappid(322170)")
    (steamapps / "appmanifest_322170.acf").write_text(
        '"AppState"\n{\n\t"installdir"\t\t"Geometry Dash"\n}\n')
    r = MagicMock()
    r.returncode = 2
    with patch("subprocess.run", return_value=r):
        assert steamhook.running_managed_appids(home=str(tmp_path)) == [322170]


def test_sync_library_refreshes_lua_collection_when_visibility_stale(tmp_path):
    """Regression (LUA shows 3 instead of 11/12):
    when games are already saved in col.m_setApps and col.m_setAddedManually
    (colChanged === false), but visible_in_game_list of uninstalled games
    has just been restored (modifiedCount > 0) or col.visibleApps.length < col.allApps.length,
    sync_library_in_steam must still invoke ClearAppCounts() and SetApps() and
    protect InitFromProto against future resets of visible_in_game_list."""
    tabs = [{"title": "SharedJSContext", "webSocketDebuggerUrl": "ws://127.0.0.1:8080/devtools/page/1"}]
    captured = {}
    fake_client = MagicMock()

    def _evaluate(script, *args, **kwargs):
        captured["script"] = script
        return json.dumps({"ok": True})

    fake_client.evaluate.side_effect = _evaluate
    with patch("core.steamhook.get_managed_games", return_value=[
        {"appid": 322170, "installed": True},
        {"appid": 504230, "installed": False},
    ]), \
         patch("core.steamhook.urllib.request.urlopen", return_value=_fake_urlopen(tabs)), \
         patch("core.steamhook.cdp.CDPClient", return_value=fake_client):
        steamhook.sync_library_in_steam(home=str(tmp_path))

    script = captured["script"]
    assert "colChanged || modifiedCount > 0 || visLen < allLen || countsStale" in script
    assert "InitFromProto" in script
    assert "ToggleAppSteamCloudEnabled" in script


def test_client_app_licensed_waits_for_appstore_init():
    """On cold Steam startup, if appStore.m_bIsInitialized is not yet true,
    client_app_licensed must not report false positives of missing licenses."""
    tabs = [{"title": "SharedJSContext", "webSocketDebuggerUrl": "ws://127.0.0.1:8080/devtools/page/1"}]
    captured = {}
    fake_client = MagicMock()

    def _evaluate(script, *args, **kwargs):
        captured["script"] = script
        return "null"

    fake_client.evaluate.side_effect = _evaluate
    with patch("core.steamhook.urllib.request.urlopen", return_value=_fake_urlopen(tabs)), \
         patch("core.steamhook.cdp.CDPClient", return_value=fake_client):
        assert steamhook.client_app_licensed(322170) is None
    assert "m_bIsInitialized !== true" in captured["script"]


