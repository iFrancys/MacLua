import json
import os
import subprocess
import sys

MACLUA = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "maclua.py"))


def _run(*args):
    return subprocess.run([sys.executable, MACLUA, *args], capture_output=True,
                          text=True, timeout=60)


def test_json_search_shape():
    r = _run("--json", "search", "stray")
    assert r.returncode == 0, r.stderr[:300]
    data = json.loads(r.stdout)
    assert isinstance(data, list) and data
    assert {"appid", "name"} <= set(data[0])
    assert data[0]["appid"] == 1332010


def test_json_status_shape():
    r = _run("--json", "status")
    assert r.returncode == 0, r.stderr[:300]
    data = json.loads(r.stdout)
    assert {"apps", "ok", "missing"} <= set(data)
    assert isinstance(data["apps"], list)


def test_json_doctor_shape():
    r = _run("--json", "doctor")
    assert r.returncode == 0, r.stderr[:300]
    data = json.loads(r.stdout)
    assert {"ok", "checks"} <= set(data)
    assert isinstance(data["checks"], list)


def test_human_output_unchanged_by_default():
    r = _run("search", "stray")
    assert r.returncode == 0
    assert r.stdout.splitlines()[0].startswith("1332010\t")


def test_json_error_envelope():
    r = _run("--json", "verify", "999999999")
    assert r.returncode == 1
    data = json.loads(r.stdout)
    assert "error" in data


def test_json_config_show_no_secret():
    r = _run("--json", "config", "show")
    assert r.returncode in (0, 1)
    data = json.loads(r.stdout)
    assert "has_key" in data
    longest = max((len(w) for w in r.stdout.split()), default=0)
    assert longest < 20, "possibile secret in output!"


def test_json_agent_status():
    r = _run("--json", "agent", "status")
    assert r.returncode == 0
    assert json.loads(r.stdout)["installed"] is True


def test_json_ensure_shape():
    r = _run("--json", "ensure")
    assert r.returncode == 0, r.stderr[:300] + r.stdout[:300]
    data = json.loads(r.stdout)
    assert {"apps", "staged", "keys", "added", "removed"} <= set(data)


def _run_home(home, *args, stdin=None):
    import os
    env = dict(os.environ, HOME=str(home))
    env.pop("MACLUA_HUBCAP_KEY", None)
    return subprocess.run([sys.executable, MACLUA, *args], capture_output=True,
                          text=True, timeout=60, env=env, input=stdin)


def test_json_status_unreadable_packageinfo_keeps_schema(tmp_path):
    # Steam assente: stato degradato ma comando riuscito, schema completo.
    r = _run_home(tmp_path, "--json", "status")
    assert r.returncode == 0, r.stderr[:300]
    data = json.loads(r.stdout)
    assert {"apps", "depots", "ok", "missing", "error"} <= set(data)
    assert data["ok"] is False


def test_json_status_unmanaged_app_is_data(tmp_path):
    r = _run_home(tmp_path, "--json", "status", "123")
    assert r.returncode == 0
    assert json.loads(r.stdout) == {"appid": 123, "managed": False}


def test_json_errors_also_on_stderr(tmp_path):
    r = _run_home(tmp_path, "--json", "verify", "999999999")
    assert r.returncode == 1
    assert "error" in json.loads(r.stdout)
    assert r.stderr.strip()


def test_json_add_without_key_reports_error(tmp_path):
    r = _run_home(tmp_path, "--json", "add", "--appid", "1")
    assert r.returncode == 2
    err = json.loads(r.stdout)["error"].lower()
    assert "key" in err or "chiave" in err


def test_set_key_from_stdin_and_clear(tmp_path):
    r = _run_home(tmp_path, "--json", "config", "set-key", "-",
                  stdin="segreto-molto-lungo-123\n")
    assert r.returncode == 0, r.stderr
    assert "segreto" not in r.stdout
    show = json.loads(_run_home(tmp_path, "--json", "config", "show").stdout)
    assert show["has_key"] is True
    r = _run_home(tmp_path, "--json", "config", "clear-key")
    assert json.loads(r.stdout) == {"has_key": False, "removed": True}
    show = json.loads(_run_home(tmp_path, "--json", "config", "show").stdout)
    assert show["has_key"] is False
