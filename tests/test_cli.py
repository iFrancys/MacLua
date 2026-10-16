import os
import subprocess
import sys

MACLUA = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "maclua.py"))


def _run(*args):
    return subprocess.run([sys.executable, MACLUA, *args], capture_output=True,
                          text=True, timeout=60)


def test_help_lists_commands():
    r = _run("--help")
    assert r.returncode == 0
    for cmd in ("search", "add", "update", "verify", "remove", "status",
                "doctor", "config", "agent", "install", "ensure"):
        assert cmd in r.stdout


def test_update_help():
    r = _run("update", "--help")
    assert r.returncode == 0 and "appid" in r.stdout.lower()


def test_doctor_runs():
    r = _run("doctor")
    assert r.returncode == 0
    assert "python" in r.stdout.lower()


def test_add_dlc_parent_inclusion():
    r = _run("--json", "add", "--appid", "1117850")
    assert r.returncode == 0
    import json
    data = json.loads(r.stdout)
    assert data["dlc"] is True
    assert data["parent_appid"] == 268910

