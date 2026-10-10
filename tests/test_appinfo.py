"""Lettura depots da appinfo.vdf su fixture sintetica (niente Steam reale)."""
import struct

from core.appinfo import depots, depot_ids

NAMES = ["appinfo", "appid", "depots", "1332012", "1332011", "config",
         "oslist", "manifests", "public", "gid", "size", "depotfromapp",
         "sharedinstall", "common", "name", "installdir", "branches",
         "buildid"]


def _cstr(s):
    return s.encode() + b"\x00"


def _i32(idx, v):
    return b"\x02" + struct.pack("<I", idx) + struct.pack("<i", v)


def _str(idx, v):
    return b"\x01" + struct.pack("<I", idx) + _cstr(v)


def _sec(idx, body):
    return b"\x00" + struct.pack("<I", idx) + body + b"\x08"


def _fixture(path):
    i = {n: k for k, n in enumerate(NAMES)}
    assert i["appid"] == 1, "l'anchor cerca indice 1 == 'appid'"
    pub = _sec(i["public"], _str(i["gid"], "103") + _str(i["size"], "8367"))
    dep_mac = _sec(i["1332012"], _sec(i["config"], _str(i["oslist"], "macos")) + _sec(i["manifests"], pub))
    dep_win = _sec(i["1332011"], _sec(i["config"], _str(i["oslist"], "windows")) + _sec(i["manifests"], pub)
                   + _i32(i["depotfromapp"], 228980) + _i32(i["sharedinstall"], 1))
    head = b"\x00" + struct.pack("<I", i["appinfo"])
    anchor = b"\x02\x01\x00\x00\x00" + struct.pack("<I", 1332010)
    common = _sec(i["common"], _str(i["name"], "Stray"))
    config = _sec(i["config"], _str(i["installdir"], "Stray"))
    branches = _sec(i["branches"], _sec(i["public"], _i32(i["buildid"], 128)))
    depots_sec = _sec(i["depots"], dep_mac + dep_win + branches)
    tail = depots_sec + common + config
    tail += b"\x08"
    data = head + anchor + tail + b"\x08"  # terminatore dopo l'ultima entry
    # Header reale: 0x2C byte, offset tabella stringhe a +8 (come appinfo.vdf).
    table = struct.pack("<I", len(NAMES)) + b"".join(_cstr(n) for n in NAMES)
    table_off = 0x2C + len(data)
    header = b"\x00" * 8 + struct.pack("<I", table_off) + b"\x00" * (0x2C - 12)
    blob = header + data + table
    with open(path, "wb") as f:
        f.write(blob)


def test_depots_parse(tmp_path):
    p = str(tmp_path / "appinfo.vdf")
    _fixture(p)
    ds = {d["id"]: d for d in depots(1332010, p)}
    assert set(ds) == {1332012, 1332011}
    assert ds[1332012]["oslist"] == "macos"
    assert ds[1332012]["gid"] == "103"
    assert ds[1332012]["shared"] is False
    assert ds[1332011]["oslist"] == "windows"
    assert ds[1332011]["shared"] is True


def test_depot_ids(tmp_path):
    p = str(tmp_path / "appinfo.vdf")
    _fixture(p)
    assert sorted(depot_ids(1332010, p)) == [1332011, 1332012]


def test_config_name_installdir(tmp_path):
    from core.appinfo import config
    p = str(tmp_path / "appinfo.vdf")
    _fixture(p)
    assert config(1332010, p) == {"name": "Stray", "installdir": "Stray"}


def test_public_buildid(tmp_path):
    from core.appinfo import public_buildid
    p = str(tmp_path / "appinfo.vdf")
    _fixture(p)
    assert public_buildid(1332010, p) == 128


def test_config_missing_returns_empty(tmp_path):
    from core.appinfo import config, public_buildid
    p = str(tmp_path / "appinfo.vdf")
    _fixture(p)
    assert config(999, p) == {}
    assert public_buildid(999, p) is None


def test_missing_app_returns_empty(tmp_path):
    p = str(tmp_path / "appinfo.vdf")
    _fixture(p)
    assert depots(999, p) == []


def test_listofdlc_and_parent(tmp_path):
    from core.appinfo import listofdlc, parent
    p = str(tmp_path / "appinfo.vdf")
    _fixture(p)
    assert listofdlc(1332010, p) == []
    assert parent(1332010, p) is None
    assert listofdlc(999, p) == []
    assert parent(999, p) is None

