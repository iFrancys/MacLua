"""Licenze offline: poison package0 + forged package, con SHA1 valido."""
import hashlib
import struct

from core.license import (
    load_groups, poison, check, forge, HEADER, FORGE_ID,
)
from core.bkv import ser_node

OPAQUE12 = bytes.fromhex("1fef5a01a951256fea34b56f")


def _pkg0(appids=(), depotids=()):
    return ("sec", "0", [
        ("sec", "appids", [("i32", str(i), a) for i, a in enumerate(appids)]),
        ("sec", "depotids", [("i32", str(i), d) for i, d in enumerate(depotids)]),
    ])


def _file(pkgs, changenumber=1234):
    body = bytearray()
    for n in pkgs:
        ser_node(n, body)
    body1 = bytes(body) + b"\x08"
    header = bytearray(HEADER)
    struct.pack_into("<I", header, 0x20, changenumber)
    new = bytes(header) + body1 + b"REST\xff\xff\xff\xff"
    hend = HEADER + len(body1)
    h = hashlib.sha1(new[HEADER:hend]).digest()
    return new[:0x0C] + h + new[0x20:], hend


def _write(tmp_path, pkgs):
    data, _ = _file(pkgs)
    p = tmp_path / "packageinfo.vdf"
    p.write_bytes(data)
    return str(p)


def test_check_reports_missing(tmp_path):
    p = _write(tmp_path, [_pkg0([100], [200])])
    missing_app, missing_dep = check(p, {100, 1332010}, {200, 1332012})
    assert missing_app == {1332010}
    assert missing_dep == {1332012}


def test_poison_injects_and_rehashes(tmp_path):
    p = _write(tmp_path, [_pkg0([100], [200])])
    poison(p, {1332010}, {1332012})
    missing_app, missing_dep = check(p, {1332010}, {1332012})
    assert missing_app == set() and missing_dep == set()
    data = open(p, "rb").read()
    header, pkgs, rest = load_groups(p)
    hend = HEADER + len(_body1(pkgs))
    assert data[0x0C:0x20] == hashlib.sha1(data[HEADER:hend]).digest()


def _body1(pkgs):
    from io import BytesIO  # noqa
    body = bytearray()
    for n in pkgs:
        ser_node(n, body)
    return bytes(body) + b"\x08"


def test_poison_is_idempotent(tmp_path):
    p = _write(tmp_path, [_pkg0([100], [200])])
    poison(p, {1332010}, {1332012})
    before = open(p, "rb").read()
    poison(p, {1332010}, {1332012})
    assert open(p, "rb").read() == before


def test_forge_adds_package_with_valid_entry_hash(tmp_path):
    from core.bkv import Reader, parse_node
    p = _write(tmp_path, [_pkg0([100], [200])])
    forge(p, [1332010], [1332012])
    data = open(p, "rb").read()
    at = data.find(struct.pack("<I", FORGE_ID))
    assert at > 0
    h = data[at + 4:at + 24]
    kv_start = at + 36
    tag = b"\x00" + str(FORGE_ID).encode() + b"\x00"
    assert data[kv_start:kv_start + len(tag)] == tag
    r = Reader(data[kv_start:])
    node = parse_node(r)
    assert node[0] == "sec" and node[1] == str(FORGE_ID)
    term = parse_node(r)
    assert term == ("end",)
    kv = data[kv_start:kv_start + r.o]
    assert hashlib.sha1(kv).digest() == h
    appids = {v for _, _, v in next(
        c[2] for c in node[2] if c[0] == "sec" and c[1] == "appids")}
    depots = {v for _, _, v in next(
        c[2] for c in node[2] if c[0] == "sec" and c[1] == "depotids")}
    assert appids == {1332010} and depots == {1332012}
    forge(p, [1332010], [1332012])
    assert open(p, "rb").read() == data


def test_forge_empty_appids_removes_entry(tmp_path):
    p = _write(tmp_path, [_pkg0([100], [200])])
    forge(p, [1332010], [1332012])
    assert struct.pack("<I", FORGE_ID) in open(p, "rb").read()
    forge(p, [], [])
    assert struct.pack("<I", FORGE_ID) not in open(p, "rb").read()


def test_poison_preserves_changenumber(tmp_path):
    p = _write(tmp_path, [_pkg0([100], [200])], )
    before = struct.unpack("<I", open(p, "rb").read()[0x20:0x24])[0]
    poison(p, {1332010}, {1332012})
    after = struct.unpack("<I", open(p, "rb").read()[0x20:0x24])[0]
    assert before == after == 1234
