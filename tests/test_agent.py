"""Agent di login: plist valido, install/remove round-trip."""
import plistlib

from core import agent


def test_plist_is_valid_and_runs_ensure(tmp_path):
    raw = agent.plist_bytes("/usr/bin/python3", "/x/maclua.py")
    info = plistlib.loads(raw)
    assert info["Label"] == "com.maclua.ensure"
    assert info["ProgramArguments"][-1] == "ensure"
    assert info["ProgramArguments"][-2].endswith("maclua.py")
    assert info["RunAtLoad"] is True


def test_install_remove_round_trip(tmp_path):
    d = str(tmp_path)
    assert agent.installed(d) is False
    path = agent.install("/usr/bin/python3", "/x/maclua.py", d)
    assert agent.installed(d) is True
    assert plistlib.load(open(path, "rb"))["Label"] == "com.maclua.ensure"
    assert agent.remove(d) is True
    assert agent.installed(d) is False
    assert agent.remove(d) is False
