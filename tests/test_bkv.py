"""VDF binario di Steam (packageinfo.vdf): deve fare round-trip byte-identico."""
import struct

from core.bkv import Reader, parse_node, ser_node


def _enc(nodes):
    buf = bytearray()
    for n in nodes:
        ser_node(n, buf)
    buf.append(0x08)
    return bytes(buf)


def test_section_round_trip():
    nodes = [
        ("sec", "0", [
            ("sec", "appids", [("i32", "0", 1332010), ("i32", "1", 322170)]),
            ("sec", "depotids", [("i32", "0", 1332012)]),
        ]),
    ]
    data = _enc(nodes)
    r = Reader(data)
    out = []
    while True:
        n = parse_node(r)
        if n[0] == "end":
            break
        out.append(n)
    assert out == nodes


def test_string_and_i64():
    nodes = [("sec", "x", [("str", "name", "Stray"), ("i64", "big", 2 ** 40)])]
    data = _enc(nodes)
    r = Reader(data)
    assert parse_node(r) == nodes[0]
    assert parse_node(r)[0] == "end"


def test_unknown_type_fails_loudly():
    import pytest
    r = Reader(b"\x09name\x00")
    with pytest.raises(ValueError):
        parse_node(r)


def test_truncated_fails_loudly():
    import pytest
    r = Reader(b"\x02ab")
    with pytest.raises(EOFError):
        parse_node(r)


def test_i32_encoding_is_little_endian():
    buf = bytearray()
    ser_node(("i32", "k", 0x01020304), buf)
    assert struct.pack("<i", 0x01020304) in bytes(buf)
