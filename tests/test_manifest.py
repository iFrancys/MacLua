"""Parse manifest binari Steam su fixture sintetiche + vettori noti."""
import struct

from core.manifest import (
    parse_manifest,
    adler0,
    decrypt_chunk,
    decompress_chunk,
)

PAYLOAD_MAGIC = 0x71F617D0
METADATA_MAGIC = 0x1F4812BE
TERMINAL_MAGIC = 0x32C415AB


def _varint(n):
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out += bytes([b | 0x80])
        else:
            return out + bytes([b])


def _tag(f, w):
    return _varint((f << 3) | w)


def _bytes(f, b):
    return _tag(f, 2) + _varint(len(b)) + b


def _uvar(f, n):
    return _tag(f, 0) + _varint(n)


def _fixed32(f, n):
    return _tag(f, 5) + struct.pack("<I", n)


def _section(magic, body):
    return struct.pack("<II", magic, len(body)) + body


def _chunk(sha=b"\x11" * 20, crc=0xAABBCCDD, off=0, orig=100, comp=90):
    return (_bytes(1, sha) + _fixed32(2, crc) + _uvar(3, off)
            + _uvar(4, orig) + _uvar(5, comp))


def _file(name=b"a/b.txt", size=100, flags=0, chunks=()):
    return (_bytes(1, name) + _uvar(2, size) + _uvar(3, flags)
            + _bytes(4, b"\x22" * 20) + _bytes(5, b"\x33" * 20)
            + b"".join(_bytes(6, c) for c in chunks))


def _manifest_bytes(encrypted=False, files=None):
    if files is None:
        files = [_file(chunks=[_chunk()])]
    payload = b"".join(_bytes(1, f) for f in files)
    meta = _uvar(1, 1332012) + _uvar(2, 103) + _uvar(3, 1700000000)
    meta += _uvar(4, 1 if encrypted else 0)
    return (_section(PAYLOAD_MAGIC, payload) + _section(METADATA_MAGIC, meta)
            + struct.pack("<I", TERMINAL_MAGIC))


def test_parse_synthetic(tmp_path):
    p = tmp_path / "m.manifest"
    p.write_bytes(_manifest_bytes())
    info = parse_manifest(str(p))
    assert info["depot"] == 1332012
    assert info["gid"] == 103
    assert info["filenames_encrypted"] is False
    assert len(info["files"]) == 1
    f = info["files"][0]
    assert f["name"] == "a/b.txt"
    assert f["size"] == 100
    assert len(f["chunks"]) == 1
    c = f["chunks"][0]
    assert c["sha"] == b"\x11" * 20
    assert c["crc"] == 0xAABBCCDD
    assert (c["offset"], c["cb_original"], c["cb_compressed"]) == (0, 100, 90)


def test_encrypted_filenames_rejected(tmp_path):
    p = tmp_path / "m.manifest"
    p.write_bytes(_manifest_bytes(encrypted=True))
    import pytest
    with pytest.raises(ValueError):
        parse_manifest(str(p))


def test_missing_payload_rejected(tmp_path):
    p = tmp_path / "m.manifest"
    meta = _uvar(1, 1) + _uvar(2, 2)
    p.write_bytes(_section(METADATA_MAGIC, meta) + struct.pack("<I", TERMINAL_MAGIC))
    import pytest
    with pytest.raises(ValueError):
        parse_manifest(str(p))


def test_adler0_known_vectors():
    # zlib.adler32(b"")=1 -> s1=0,s2=0 ; zlib(b"a")=0x00620062 -> 97,97
    assert adler0(b"") == 0
    assert adler0(b"a") == 0x00610061


def test_decrypt_round_trip():
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes
    key = get_random_bytes(32)
    iv = get_random_bytes(16)
    data = b"hello steam chunks!" * 100
    pad = 16 - len(data) % 16
    cbc = AES.new(key, AES.MODE_CBC, iv).encrypt(data + bytes([pad]) * pad)
    cipher = AES.new(key, AES.MODE_ECB).encrypt(iv) + cbc
    assert decrypt_chunk(cipher, key) == data


def test_decompress_zip():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("x", b"zip payload " * 50)
    assert decompress_chunk(buf.getvalue()) == b"zip payload " * 50


def test_decompress_unknown_magic():
    import pytest
    with pytest.raises(ValueError):
        decompress_chunk(b"XXXX" + b"\x00" * 32)


def test_decompress_vsza_zero_size_footer():
    import struct
    import zstandard
    from core.manifest import decompress_chunk
    raw = b"deltarune data " * 100
    frame = zstandard.ZstdCompressor().compress(raw)
    blob = (b"VSZa" + struct.pack("<i", 0) + frame
            + struct.pack("<Ii", 0, 0) + b"zsv")
    assert decompress_chunk(blob) == raw


def test_decompress_vsza_bad_size_still_rejected():
    import struct
    import zstandard
    from core.manifest import decompress_chunk
    import pytest
    frame = zstandard.ZstdCompressor().compress(b"abc" * 10)
    blob = (b"VSZa" + struct.pack("<i", 0) + frame
            + struct.pack("<Ii", 0, 9999) + b"zsv")
    with pytest.raises(ValueError):
        decompress_chunk(blob)
