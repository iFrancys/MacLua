"""Config locale MacLua (solo la chiave API, 0600)."""
import os

from core import config


def test_set_get_round_trip(tmp_path):
    home = str(tmp_path)
    config.set_key(home, "SECRET123")
    assert config.get_key(home) == "SECRET123"
    st = os.stat(config.key_file(home))
    assert st.st_mode & 0o777 == 0o600


def test_get_missing_returns_none(tmp_path):
    assert config.get_key(str(tmp_path)) is None


def test_env_overrides_file(tmp_path, monkeypatch):
    home = str(tmp_path)
    config.set_key(home, "FILEKEY")
    monkeypatch.setenv("MACLUA_HUBCAP_KEY", "ENVKEY")
    assert config.get_key(home) == "ENVKEY"


def test_empty_key_rejected(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        config.set_key(str(tmp_path), "  ")
