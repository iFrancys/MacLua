"""Ensure licenses + Steam install helper URL."""
import subprocess

import maclua


def test_steam_url_format():
    assert maclua.steam_url(1671210) == "steam://install/1671210"


def test_install_opens_url(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: seen.append(a))
    ns = type("ns", (), {"appid": 1671210})()
    assert maclua.cmd_install(ns) == 0
    assert seen[0][0] == ["open", "steam://install/1671210"]


def test_ensure_on_empty_tree(tmp_path, monkeypatch):
    import os, sys
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    from test_license import _pkg0, _file
    home = tmp_path / "home"
    appcache = home / "Library/Application Support/Steam/appcache"
    appcache.mkdir(parents=True)
    data, _ = _file([_pkg0([100], [200])])
    (appcache / "packageinfo.vdf").write_bytes(data)
    ns = type("ns", (), {})()
    assert maclua.cmd_ensure(ns, home=str(home)) == 0
    from core import license as L
    assert L.check(str(appcache / "packageinfo.vdf"), set(), set()) == (
        set(), set())
