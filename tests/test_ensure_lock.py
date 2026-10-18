"""Single-flight di `ensure`.

`ensure` è invocato in parallelo da più punti (LaunchAgent al login, sentinella
del bridge, RPC del client): prima del lock, due esecuzioni concorrenti
scrivevano gli stessi file con lo stesso temporaneo a nome fisso e una
rinominava un packageinfo.vdf scritto a metà — la causa nota di "Nessuna
licenza" nel client dopo il riavvio.
"""
import threading
import time
from unittest.mock import patch

import maclua


def _ok_result(home):
    return {"apps": [], "licensed_apps": [], "added": (set(), set()),
            "removed": (set(), set()), "staged": [], "keys": 0}


def test_ensure_runs_body_under_lock(tmp_path):
    calls = []

    def fake_locked(home):
        calls.append(home)
        return _ok_result(home)

    with patch("maclua._ensure_locked", side_effect=fake_locked):
        res = maclua._ensure(str(tmp_path))
    assert calls == [str(tmp_path)]
    assert res["keys"] == 0


def test_ensure_serializes_concurrent_threads(tmp_path):
    """Tre `ensure` concorrenti: il corpo non deve mai girare in parallelo."""
    active, peaks, results = [], [], []

    def fake_locked(home):
        active.append(1)
        peaks.append(len(active))
        time.sleep(0.2)
        active.pop()
        return _ok_result(home)

    with patch("maclua._ensure_locked", side_effect=fake_locked):
        threads = [threading.Thread(target=lambda: results.append(
            maclua._ensure(str(tmp_path)))) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert len(results) == 3
    assert max(peaks) == 1, "ensure eseguito in parallelo: il lock non serializza"
    assert all(r.get("concurrent") is not True for r in results)


def test_ensure_degrades_cleanly_when_lock_busy(tmp_path):
    """Lock occupato oltre il timeout: nessun crash, risultato `concurrent`
    compatibile con cmd_ensure (stesse chiavi del risultato normale)."""
    with patch("maclua._ensure_locked") as body, \
         patch("core.atomic.FileLock.acquire", return_value=False):
        res = maclua._ensure(str(tmp_path))
    body.assert_not_called()
    assert res["concurrent"] is True
    for key in ("apps", "licensed_apps", "added", "removed", "staged", "keys"):
        assert key in res
