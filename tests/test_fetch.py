"""Chunk fetch and file assembly against local HTTP test servers."""
import io
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from core.fetch import fetch_chunk, download_file, DEFAULT_CDN_BASES
from core.manifest import adler0


class _Handler(BaseHTTPRequestHandler):
    routes = {}
    hits = []

    def do_GET(self):
        _Handler.hits.append(self.path)
        body, code = _Handler.routes.get(self.path, (b"missing", 404))
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture()
def server():
    _Handler.routes = {}
    _Handler.hits = []
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_bases_have_https_default():
    assert DEFAULT_CDN_BASES and all(
        b.startswith("https://") for b in DEFAULT_CDN_BASES)


def test_fetch_chunk_ok(server):
    _Handler.routes["/depot/7/chunk/" + "ab" * 20] = (b"x" * 100, 200)
    out = fetch_chunk(7, bytes.fromhex("ab" * 20), 100, [server])
    assert out == b"x" * 100


def test_fetch_chunk_size_mismatch(server):
    _Handler.routes["/depot/7/chunk/" + "cd" * 20] = (b"short", 200)
    with pytest.raises(ValueError):
        fetch_chunk(7, bytes.fromhex("cd" * 20), 100, [server])


def test_fetch_chunk_rotates_hosts(server):
    _Handler.routes["/depot/7/chunk/" + "ef" * 20] = (b"no", 500)
    with pytest.raises(ValueError):
        fetch_chunk(7, bytes.fromhex("ef" * 20), 2,
                    ["http://127.0.0.1:1", server])


def _zip_cipher(plain, key):
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("x", plain)
    zipped = buf.getvalue()
    iv = get_random_bytes(16)
    pad = 16 - len(zipped) % 16
    return (AES.new(key, AES.MODE_ECB).encrypt(iv)
            + AES.new(key, AES.MODE_CBC, iv).encrypt(
                zipped + bytes([pad]) * pad))


def _entry(plain, key):
    import hashlib as _h
    cipher = _zip_cipher(plain, key)
    return {
        "name": "dir\\game.bin",
        "size": len(plain),
        "flags": 32,
        "sha_content": _h.sha1(plain).digest(),
        "chunks": [{
            "sha": _h.sha1(cipher).digest(),
            "crc": adler0(plain),
            "offset": 0,
            "cb_original": len(plain),
            "cb_compressed": len(cipher),
        }],
        "linktarget": None,
    }, cipher


def test_download_file_roundtrip(server, tmp_path):
    from Crypto.Random import get_random_bytes
    key = get_random_bytes(32)
    plain = b"hello maclua " * 200
    entry, cipher = _entry(plain, key)
    sha = entry["chunks"][0]["sha"].hex()
    _Handler.routes[f"/depot/9/chunk/{sha}"] = (cipher, 200)
    kind, rel = download_file(9, entry, key, [server],
                              str(tmp_path))
    assert kind == "file"
    data = (tmp_path / "dir" / "game.bin").read_bytes()
    assert data == plain
    import os
    assert os.stat(tmp_path / "dir" / "game.bin").st_mode & 0o111


def test_resume_skips_valid(server, tmp_path):
    from Crypto.Random import get_random_bytes
    key = get_random_bytes(32)
    plain = b"stable " * 100
    entry, cipher = _entry(plain, key)
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "game.bin").write_bytes(plain)
    _Handler.hits = []
    download_file(9, entry, key, [server], str(tmp_path))
    assert _Handler.hits == []


def test_resume_repairs_corrupt(server, tmp_path):
    from Crypto.Random import get_random_bytes
    key = get_random_bytes(32)
    plain = b"repair me " * 100
    entry, cipher = _entry(plain, key)
    sha = entry["chunks"][0]["sha"].hex()
    _Handler.routes[f"/depot/9/chunk/{sha}"] = (cipher, 200)
    (tmp_path / "dir").mkdir()
    bad = bytearray(plain)
    bad[10] ^= 0xFF
    (tmp_path / "dir" / "game.bin").write_bytes(bytes(bad))
    download_file(9, entry, key, [server], str(tmp_path))
    assert (tmp_path / "dir" / "game.bin").read_bytes() == plain
    assert _Handler.hits != []
