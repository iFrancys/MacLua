"""Catalogo: ricerca appid via Store API, piattaforme via appdetails."""
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from core import catalog


class _H(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):
        body, code = _H.routes.get(self.path.split("?")[0], (b"{}", 404))
        raw = self.path
        key = self.path.split("?")[0]
        if key == "/api/storesearch/":
            import urllib.parse
            q = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
            body, code = _H.routes.get(("search", q.get("term", [""])[0]),
                                       (b'{"total":0,"items":[]}', 200))
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else body.encode())

    def log_message(self, *a):
        pass


@pytest.fixture()
def server():
    _H.routes = {}
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_search_returns_id_and_name(server):
    _H.routes[("search", "stray")] = (
        '{"total":1,"items":[{"id":1332010,"name":"Stray"}]}', 200)
    assert catalog.search("stray", base=server) == [
        {"appid": 1332010, "name": "Stray"}]


def test_search_empty(server):
    assert catalog.search("xyz-no-game", base=server) == []


def test_search_http_error(server):
    _H.routes[("search", "boom")] = (b"err", 500)
    with pytest.raises(ValueError):
        catalog.search("boom", base=server)


def test_platforms(server):
    _H.routes["/api/appdetails"] = (
        '{"1332010":{"success":true,"data":{"platforms":'
        '{"windows":true,"mac":true,"linux":false}}}}', 200)
    assert catalog.platforms(1332010, base=server) == {"windows", "mac"}
