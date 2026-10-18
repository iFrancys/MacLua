"""Sync with prune: adds managed, removes unmanaged entries."""
import json

from core.license import sync, check, FORGE_ID
from tests.test_license import _pkg0, _write


def test_sync_adds_and_records_state(tmp_path):
    p = _write(tmp_path, [_pkg0([100], [200])])
    state = str(tmp_path / "managed.json")
    added, removed = sync(p, {1332010}, {1332012}, state)
    assert added == ({1332010}, {1332012}) and removed == (set(), set())
    assert check(p, {1332010}, {1332012}) == (set(), set())
    saved = json.loads(open(state).read())
    assert saved == {"appids": [1332010], "depotids": [1332012]}
    # Native preserved
    assert check(p, {100}, {200}) == (set(), set())


def test_sync_prunes_stale_managed(tmp_path):
    p = _write(tmp_path, [_pkg0([100], [200])])
    state = str(tmp_path / "managed.json")
    sync(p, {1332010, 322170}, {1332012, 322172}, state)
    added, removed = sync(p, {1332010}, {1332012}, state)
    assert added == (set(), set())
    assert removed == ({322170}, {322172})
    assert check(p, {1332010}, {1332012}) == (set(), set())
    assert check(p, {100}, {200}) == (set(), set())


def test_sync_idempotent(tmp_path):
    p = _write(tmp_path, [_pkg0([100], [200])])
    state = str(tmp_path / "managed.json")
    sync(p, {1332010}, {1332012}, state)
    before = open(p, "rb").read()
    assert sync(p, {1332010}, {1332012}, state) == (
        (set(), set()), (set(), set()))
    assert open(p, "rb").read() == before


def test_sync_without_state_starts_tracking(tmp_path):
    p = _write(tmp_path, [_pkg0([100], [200])])
    state = str(tmp_path / "managed.json")
    sync(p, {1332010}, {1332012}, state)
    assert json.loads(open(state).read())["appids"] == [1332010]
