"""Installazione: selezione depot macOS, fetch, adopt in Steam, verify."""
import io
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from core import install
from core.manifest import adler0


class _H(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):
        body, code = _H.routes.get(self.path, (b"missing", 404))
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture()
def server():
    _H.routes = {}
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _appinfo_depots():
    return [
        {"id": 11, "oslist": "macos", "gid": "9001", "size": "10",
         "shared": False},
        {"id": 12, "oslist": "windows", "gid": "9002", "size": "10",
         "shared": False},
        {"id": 13, "oslist": "windows", "gid": None, "size": None,
         "shared": True},
        {"id": 10, "oslist": "", "gid": None, "size": None, "shared": False},
    ]


def test_select_depots_keeps_macos_only():
    wanted, skipped = install.select_depots(
        10, {11, 12, 13, 10, 99}, _appinfo_depots())
    assert wanted == [11]
    assert "windows" in skipped[12]
    assert "shared" in skipped[13]
    assert "ticket" in skipped[10] or "appid" in skipped[10]
    assert "appinfo" in skipped[99]


ACF = ('"AppState"\n{\n\t"appid"\t\t"10"\n\t"StateFlags"\t\t"2"\n'
       '\t"installdir"\t\t"Demo"\n\t"LastUpdated"\t\t"0"\n'
       '\t"SizeOnDisk"\t\t"0"\n\t"UpdateResult"\t\t"8"\n'
       '\t"BytesToDownload"\t\t"5"\n\t"BytesDownloaded"\t\t"5"\n'
       '\t"InstalledDepots"\n\t{\n\t}\n\t"UserConfig"\n\t{\n\t}\n}\n')


def test_patch_appmanifest(tmp_path):
    acf = tmp_path / "appmanifest_10.acf"
    acf.write_text(ACF)
    install.patch_appmanifest(str(acf), {11: ("9001", 1234)}, 1234)
    txt = acf.read_text()
    assert '"StateFlags"\t\t"4"' in txt
    assert '"SizeOnDisk"\t\t"1234"' in txt
    assert '"11"' in txt and '"9001"' in txt
    assert '"BytesToDownload"\t\t"0"' in txt


def _cipher(plain, key):
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


def _setup_app(tmp_path, server):
    from Crypto.Random import get_random_bytes
    import base64
    key = get_random_bytes(32)
    plain = b"demo data " * 100
    cipher = _cipher(plain, key)
    import hashlib
    sha = hashlib.sha1(cipher).digest()
    _H.routes[f"/depot/11/chunk/{sha.hex()}"] = (cipher, 200)
    entry = {"name": "Demo.app\\Contents\\game.bin", "size": len(plain),
             "flags": 0, "sha_content": hashlib.sha1(plain).digest(),
             "chunks": [{"sha": sha, "crc": adler0(plain), "offset": 0,
                         "cb_original": len(plain),
                         "cb_compressed": len(cipher)}],
             "linktarget": None}
    return key, plain, entry


def test_fetch_app_end_to_end(server, tmp_path, monkeypatch):
    import core.install as I
    from Crypto.Random import get_random_bytes
    import base64
    import hashlib
    key = get_random_bytes(32)
    plain = b"demo data " * 100
    cipher = _cipher(plain, key)
    sha = hashlib.sha1(cipher).digest()
    _H.routes[f"/depot/11/chunk/{sha.hex()}"] = (cipher, 200)

    stplug = tmp_path / "stplug-in"
    stplug.mkdir()
    (stplug / "10.lua").write_text(
        "addappid(10)\naddappid(11, 1, \"%s\")\n" % key.hex())
    cache = tmp_path / "cache"
    store = tmp_path / "manifests"
    store.mkdir()
    # manifest minimo: lo costruiamo via core.manifest? serve protobuf:
    # riusiamo il builder dei test copiando la logica essenziale qui.
    import struct

    def varint(n):
        out = b""
        while True:
            b = n & 0x7F
            n >>= 7
            if n:
                out += bytes([b | 0x80])
            else:
                return out + bytes([b])

    def tag(f, w):
        return varint((f << 3) | w)

    def bs(f, b):
        return tag(f, 2) + varint(len(b)) + b

    def uv(f, n):
        return tag(f, 0) + varint(n)

    def fx(f, n):
        return tag(f, 5) + struct.pack("<I", n)

    chunk = (bs(1, sha) + fx(2, adler0(plain)) + uv(3, 0)
             + uv(4, len(plain)) + uv(5, len(cipher)))
    fmap = (bs(1, b"Demo.app\\Contents\\game.bin") + uv(2, len(plain))
            + uv(3, 0) + bs(4, b"\x00" * 20) + bs(5, hashlib.sha1(plain).digest())
            + bs(6, chunk))
    payload = bs(1, fmap)
    meta = uv(1, 11) + uv(2, 9001) + uv(3, 1700000000) + uv(4, 0)
    man = (struct.pack("<II", 0x71F617D0, len(payload)) + payload
           + struct.pack("<II", 0x1F4812BE, len(meta)) + meta
           + struct.pack("<I", 0x32C415AB))
    (store / "11_9001.manifest").write_bytes(man)
    (store / ".preferred_11").write_text("9001\n")

    steamapps = tmp_path / "steamapps"
    (steamapps / "common").mkdir(parents=True)
    (steamapps / "appmanifest_10.acf").write_text(ACF)

    monkeypatch.setattr(I, "DEFAULT_BASES", [server])
    rep = I.fetch_app(10, stplug_dir=str(stplug), cache_dir=str(cache),
                      store_dir=str(store), steamapps_dir=str(steamapps),
                      workers=2, appinfo_depots=[
                          {"id": 11, "oslist": "macos", "gid": "9001",
                           "size": "1100", "shared": False}])
    assert rep["depots"] == [11]
    got = (steamapps / "common" / "Demo" / "Demo.app" / "Contents"
           / "game.bin").read_bytes()
    assert got == plain
    acf = (steamapps / "appmanifest_10.acf").read_text()
    assert '"StateFlags"\t\t"4"' in acf and '"9001"' in acf
    bad = I.verify_app(10, steamapps_dir=str(steamapps),
                       store_dir=str(store))
    assert bad == []


def test_verify_detects_corruption(tmp_path):
    import core.install as I
    store = tmp_path / "manifests"
    store.mkdir()
    steamapps = tmp_path / "steamapps"
    target = steamapps / "common" / "Demo" / "Demo.app" / "Contents"
    target.mkdir(parents=True)
    (target / "game.bin").write_bytes(b"corrotto")
    # manifest con lo stesso file ma contenuto diverso atteso
    import struct
    import hashlib

    def varint(n):
        out = b""
        while True:
            b = n & 0x7F
            n >>= 7
            if n:
                out += bytes([b | 0x80])
            else:
                return out + bytes([b])

    def tag(f, w):
        return varint((f << 3) | w)

    def bs(f, b):
        return tag(f, 2) + varint(len(b)) + b

    def uv(f, n):
        return tag(f, 0) + varint(n)

    def fx(f, n):
        return tag(f, 5) + struct.pack("<I", n)

    good = b"originale"
    chunk = (bs(1, b"\x99" * 20) + fx(2, adler0(good)) + uv(3, 0)
             + uv(4, len(good)) + uv(5, 10))
    fmap = (bs(1, "Demo.app\\Contents\\game.bin".encode()) + uv(2, len(good))
            + uv(3, 0) + bs(4, b"\x00" * 20)
            + bs(5, hashlib.sha1(good).digest()) + bs(6, chunk))
    man = (struct.pack("<II", 0x71F617D0, len(bs(1, fmap))) + bs(1, fmap)
           + struct.pack("<II", 0x1F4812BE,
                         len(uv(1, 11) + uv(2, 9001))) + uv(1, 11) + uv(2, 9001)
           + struct.pack("<I", 0x32C415AB))
    (store / "11_9001.manifest").write_bytes(man)
    acf = ACF.replace('"InstalledDepots"\n\t{\n\t}',
                      '"InstalledDepots"\n\t{\n\t\t"11"\n\t\t{\n'
                      '\t\t\t"manifest"\t\t"9001"\n\t\t\t"size"\t\t"9"\n\t\t}')
    (steamapps / "appmanifest_10.acf").write_text(acf)
    bad = I.verify_app(10, steamapps_dir=str(steamapps),
                       store_dir=str(store))
    assert bad == ["Demo.app/Contents/game.bin"]
