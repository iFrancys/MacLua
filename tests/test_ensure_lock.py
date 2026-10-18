"""Single-flight execution of `ensure`.

`ensure` is invoked concurrently from multiple points (LaunchAgent at login,
bridge sentinel, client RPC): prior to locking, two concurrent executions
wrote the same files with the same fixed temp name and one renamed a half-written
packageinfo.vdf — the root cause of "No license" in the client after restart.
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
    """Three concurrent `ensure` calls: body must never run in parallel."""
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
    assert max(peaks) == 1, "ensure ran in parallel: lock failed to serialize"
    assert all(r.get("concurrent") is not True for r in results)


def test_ensure_degrades_cleanly_when_lock_busy(tmp_path):
    """Lock held beyond timeout: no crash, `concurrent` result compatible
    with cmd_ensure (same keys as normal result)."""
    with patch("maclua._ensure_locked") as body, \
         patch("core.atomic.FileLock.acquire", return_value=False):
        res = maclua._ensure(str(tmp_path))
    body.assert_not_called()
    assert res["concurrent"] is True
    for key in ("apps", "licensed_apps", "added", "removed", "staged", "keys"):
        assert key in res
