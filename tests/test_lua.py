"""Parse dei file .lua: addappid nudi, chiavi depot, manifest ref.
I commenti -- non devono mai produrre dichiarazioni."""
from core.lua import parse_lua

K1 = "a" * 64
K2 = "b" * 64


def test_bare_and_keyed():
    p = parse_lua(f'addappid(1332010)\naddappid(1332011, 1, "{K1}")\n')
    assert p["bare"] == {1332010}
    assert p["keys"] == {1332011: K1}
    assert p["manifests"] == {}


def test_comments_are_ignored():
    p = parse_lua(f"-- addappid(99)\n--addappid(1332011,1,\"{K2}\")\n"
                  f"addappid(1332010) -- trailing\n")
    assert 99 not in p["bare"]
    assert 1332011 not in p["keys"]
    assert p["bare"] == {1332010}


def test_manifest_refs():
    p = parse_lua('addappid(1332010)\nsetManifestid(1332012, "103")\n')
    assert p["manifests"] == {1332012: "103"}


def test_long_comments_and_strings_ignored():
    p = parse_lua('--[[\naddappid(20)\n]]\naddappid(21)\n'
                  '[=[addappid(22)]=]\n')
    assert p["bare"] == {21}


def test_case_insensitive_key():
    p = parse_lua(f'ADDAPPID(5, 1, "{K1.upper()}")\n')
    assert p["keys"] == {5: K1}


def test_empty_and_garbage():
    assert parse_lua("") == {"bare": set(), "keys": {}, "manifests": {}}
    assert parse_lua('print("hi")\n')["bare"] == set()
