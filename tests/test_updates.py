"""Aggiornamenti: stato persistente onesto + watcher di background con retry."""
import time
from unittest.mock import patch

from core import updates


def test_status_roundtrip(tmp_path):
    updates.set_status(322170, {"status": "pending", "next_try_at": 9999999999},
                       home=str(tmp_path))
    st = updates.load_status(home=str(tmp_path))
    assert st["322170"]["status"] == "pending"
    assert updates.get_status(322170, home=str(tmp_path))["status"] == "pending"
    assert updates.get_status(999, home=str(tmp_path)) is None


def test_load_status_tolerates_missing_or_corrupt(tmp_path):
    assert updates.load_status(home=str(tmp_path)) == {}
    p = tmp_path / "updates.json"
    p.write_text("{rotto")
    assert updates.load_status(home=str(tmp_path)) == {}


def test_background_tick_pending_sets_backoff(tmp_path):
    games = [{"appid": 322170, "installed": True}]
    info = {"has_update": True, "manifest_ready": False,
            "current_buildid": 1, "latest_buildid": 2}
    with patch("core.steamhook.get_managed_games", return_value=games), \
         patch("core.updates.check_updates", return_value=info), \
         patch("core.settings.get", return_value=True):
        res = updates.background_tick(home=str(tmp_path))
    assert res["pending"] == [322170]
    st = updates.get_status(322170, home=str(tmp_path))
    assert st["status"] == "pending"
    assert st["next_try_at"] > int(time.time())
    assert st["attempts"] == 1


def test_background_tick_skips_until_next_try(tmp_path):
    updates.set_status(322170, {"status": "pending",
                                "next_try_at": int(time.time()) + 3600},
                       home=str(tmp_path))
    games = [{"appid": 322170, "installed": True}]
    with patch("core.steamhook.get_managed_games", return_value=games), \
         patch("core.updates.check_updates") as cu, \
         patch("core.settings.get", return_value=True):
        res = updates.background_tick(home=str(tmp_path))
    assert res["checked"] == 0
    cu.assert_not_called()


def test_background_tick_marks_ok_when_up_to_date(tmp_path):
    games = [{"appid": 322170, "installed": True}]
    info = {"has_update": False, "manifest_ready": True,
            "current_buildid": 10, "latest_buildid": 10}
    with patch("core.steamhook.get_managed_games", return_value=games), \
         patch("core.updates.check_updates", return_value=info), \
         patch("core.settings.get", return_value=True):
        res = updates.background_tick(home=str(tmp_path))
    assert res["checked"] == 1
    assert res["applied"] == [] and res["pending"] == []
    assert updates.get_status(322170, home=str(tmp_path))["status"] == "ok"


def test_background_tick_applies_when_manifest_ready(tmp_path):
    games = [{"appid": 322170, "installed": True}]
    info = {"has_update": True, "manifest_ready": True,
            "current_buildid": 1, "latest_buildid": 2}
    with patch("core.steamhook.get_managed_games", return_value=games), \
         patch("core.updates.check_updates", return_value=info), \
         patch("core.updates._running_managed", return_value=set()), \
         patch("core.updates._apply_locked",
               return_value={"ok": True}) as apply, \
         patch("core.settings.get", return_value=True):
        res = updates.background_tick(home=str(tmp_path))
    assert res["applied"] == [322170]
    apply.assert_called_once()


def test_background_tick_defers_when_game_running(tmp_path):
    games = [{"appid": 322170, "installed": True}]
    info = {"has_update": True, "manifest_ready": True,
            "current_buildid": 1, "latest_buildid": 2}
    with patch("core.steamhook.get_managed_games", return_value=games), \
         patch("core.updates.check_updates", return_value=info), \
         patch("core.updates._running_managed", return_value={322170}), \
         patch("core.updates._apply_locked") as apply, \
         patch("core.settings.get", return_value=True):
        res = updates.background_tick(home=str(tmp_path))
    assert res["pending"] == [322170]
    apply.assert_not_called()
    assert updates.get_status(322170, home=str(tmp_path))["status"] == "pending"


def test_background_tick_disabled_by_setting(tmp_path):
    with patch("core.settings.get", return_value=False), \
         patch("core.steamhook.get_managed_games") as gm:
        res = updates.background_tick(home=str(tmp_path))
    assert res == {"checked": 0, "applied": [], "pending": []}
    gm.assert_not_called()


def test_apply_locked_records_pending_on_manifest_missing(tmp_path):
    missing = {"ok": False, "manifest_missing": True,
               "current_buildid": 1, "target_buildid": 2,
               "error": "in attesa"}
    with patch("core.updates.apply_update", return_value=missing):
        out = updates._apply_locked(322170, str(tmp_path), prev={})
    assert out["ok"] is False
    assert out["status"] == "pending"
    st = updates.get_status(322170, home=str(tmp_path))
    assert st["status"] == "pending"
    assert st["message"] == "in attesa"
    assert st["next_try_at"] > int(time.time())


def test_apply_locked_records_error(tmp_path):
    err = {"ok": False, "error": "boom"}
    with patch("core.updates.apply_update", return_value=err), \
         patch("core.updates.set_status") as ss:
        out = updates._apply_locked(322170, str(tmp_path), prev={})
    assert out["ok"] is False
    assert out["status"] == "error"
    assert ss.call_args[0][1]["status"] == "error"


def test_apply_locked_records_success(tmp_path):
    ok = {"app": 322170, "files": 5}
    with patch("core.updates.apply_update", return_value=ok), \
         patch("core.updates.ai.public_buildid", return_value=42), \
         patch("core.steamhook.is_cdp_available", return_value=False):
        out = updates._apply_locked(322170, str(tmp_path), prev={})
    assert out["ok"] is True
    st = updates.get_status(322170, home=str(tmp_path))
    assert st["status"] == "ok"
    assert st["updated_at"] > 0


def test_request_update_returns_immediately(tmp_path):
    with patch("core.updates._apply_locked", return_value={"ok": True}) as apply:
        res = updates.request_update(322170, home=str(tmp_path))
    assert res == {"ok": True, "appid": 322170, "updating": True}


def test_check_updates_fetches_missing_manifests_from_sources(tmp_path):
    """Se PICS indica un aggiornamento ma il manifest target non è ancora su disco,
    check_updates deve interrogare le sorgenti remote e importare il manifest."""
    home = str(tmp_path)
    from core import paths
    import os
    steamapps = paths.steamapps(home)
    store_dir = paths.sls_manifests(home)
    os.makedirs(steamapps, exist_ok=True)
    os.makedirs(store_dir, exist_ok=True)
    with open(os.path.join(steamapps, "appmanifest_322170.acf"), "w") as f:
        f.write('"AppState"\n{\n\t"appid"\t\t"322170"\n\t"buildid"\t\t"100"\n\t"InstalledDepots"\n\t{\n\t\t"322172"\n\t\t{\n\t\t\t"manifest"\t\t"111"\n\t\t}\n\t}\n}\n')

    def _fake_import(appid, lua_text, manifests, h=None):
        for fn, data in manifests.items():
            with open(os.path.join(store_dir, fn), "wb") as mf:
                mf.write(data)

    with patch("core.updates.ai.public_buildid", return_value=200), \
         patch("core.updates.ai.depots", return_value=[{"id": 322172, "gid": "222", "oslist": "macos"}]), \
         patch("core.updates.ai.listofdlc", return_value=[]), \
         patch("core.source.fetch_from_sources", return_value={
             "lua": "addappid(322170)\n",
             "manifests": {"322172_222.manifest": b"FAKE"},
         }) as fetch_mock, \
         patch("core.updates.install.import_lua", side_effect=_fake_import):
        info = updates.check_updates(322170, home=home)

    fetch_mock.assert_called_once()
    assert info["has_update"] is True
    assert info["manifest_ready"] is True

