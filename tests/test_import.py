"""Import lua (da file o da sorgente remota) nello stplug-in + store."""
import os

from core import install


def test_import_lua_writes_files(tmp_path):
    home = str(tmp_path)
    out = install.import_lua(1332010, "addappid(1332010)\n",
                             {"1332012_103.manifest": b"MAN"}, home)
    assert out["appid"] == 1332010
    lua = tmp_path / "Library/Application Support/Steam/config/stplug-in/1332010.lua"
    assert lua.read_text() == "addappid(1332010)\n"
    assert oct(os.stat(lua).st_mode & 0o777) == "0o600"
    man = tmp_path / "Library/Application Support/SLSsteam/manifests/1332012_103.manifest"
    assert man.read_bytes() == b"MAN"


def test_import_lua_rejects_foreign_app(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        install.import_lua(1332010, "addappid(555)\n", {}, str(tmp_path))
