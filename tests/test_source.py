"""Sorgente lua remota (hubcapmanifest): fetch + validazione zip."""
import io
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from core import source

K = "a" * 64
LUA = f'addappid(1332010)\naddappid(1332012, 1, "{K}")\n'.encode()
MAN = b"\xd0\x17\xf6\x71" + b"\x00" * 100


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            zf.writestr(name, data)
    return buf.getvalue()


class _H(BaseHTTPRequestHandler):
    body = (b"{}", 401)

    def do_GET(self):
        body, code = _H.body
        if self.path.startswith("/api/v1/manifest/"):
            body, code = _H.body
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture()
def server():
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_fetch_ok(server):
    _H.body = (_zip([("1332010.lua", LUA),
                     ("1332012_103.manifest", MAN)]), 200)
    out = source.fetch_lua(1332010, "KEY", base=server)
    assert out["lua"] == LUA.decode()
    assert out["manifests"] == {"1332012_103.manifest": MAN}


def test_fetch_unauthorized(server):
    _H.body = (b'{"detail":"key"}', 401)
    with pytest.raises(ValueError):
        source.fetch_lua(1332010, "BAD", base=server)


def test_fetch_not_found(server):
    _H.body = (b'{"detail":"nope"}', 404)
    with pytest.raises(ValueError):
        source.fetch_lua(999, "KEY", base=server)


def test_fetch_rejects_non_zip(server):
    _H.body = (b'{"detail":"key required"}', 200)
    with pytest.raises(ValueError):
        source.fetch_lua(1332010, "KEY", base=server)


def test_fetch_rejects_zip_without_lua(server):
    _H.body = (_zip([("other.txt", b"hi")]), 200)
    with pytest.raises(ValueError):
        source.fetch_lua(1332010, "KEY", base=server)


def test_fetch_rejects_traversal(server):
    _H.body = (_zip([("1332010.lua", LUA), ("../evil.sh", b"x")]), 200)
    with pytest.raises(ValueError):
        source.fetch_lua(1332010, "KEY", base=server)


def test_symlink_blocked():
    import stat
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("1332010.lua", LUA.decode())
        zi = zipfile.ZipInfo("link")
        zi.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(zi, "target")
    with pytest.raises(ValueError):
        source._safe_extract(buf.getvalue(), 1332010)


def test_fetch_wrong_app_lua(server):
    _H.body = (_zip([("555.lua", b"addappid(555)\n")]), 200)
    with pytest.raises(ValueError):
        source.fetch_lua(1332010, "KEY", base=server)
