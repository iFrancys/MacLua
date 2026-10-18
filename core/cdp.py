"""Client minimale WebSocket (RFC 6455) puro Python stdlib per Chrome DevTools Protocol (CDP).
Nessuna dipendenza esterna (niente websocket-client / aiohttp). Funziona con Python 3.9 standard di macOS.
"""
import socket
import base64
import os
import struct
import json
import urllib.parse


class CDPClient:
    def __init__(self, ws_url, timeout=5):
        self.ws_url = ws_url
        self.timeout = timeout
        self.sock = None
        self._msg_id = 1
        self._connect()

    def _connect(self):
        u = urllib.parse.urlparse(self.ws_url)
        host = u.hostname or "127.0.0.1"
        port = u.port or 8080
        path = u.path or "/"

        self.sock = socket.create_connection((host, port), timeout=self.timeout)

        # Handshake HTTP per WebSocket
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        headers = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}:{port}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
            "\r\n"
        ]
        self.sock.sendall("\r\n".join(headers).encode("ascii"))

        # Leggi risposta handshake
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("Connessione chiusa durante handshake")
            resp += chunk

        if b" 101 " not in resp and b"101" not in resp[:20]:
            raise ConnectionError(f"Handshake WebSocket fallito: {resp[:200]}")

    def send_frame(self, data):
        """Invia frame di testo mascherato (RFC 6455 client-to-server)."""
        payload = data.encode("utf-8") if isinstance(data, str) else data
        length = len(payload)
        mask = os.urandom(4)

        header = bytearray([0x81])  # FIN + Text Frame
        if length <= 125:
            header.append(0x80 | length)
        elif length <= 65535:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))

        masked_payload = bytearray(length)
        for i in range(length):
            masked_payload[i] = payload[i] ^ mask[i % 4]

        self.sock.sendall(header + mask + masked_payload)

    def read_frame(self):
        """Legge un frame in risposta dal server."""
        head = self._recv_exact(2)
        b1, b2 = head[0], head[1]
        opcode = b1 & 0x0F
        is_masked = bool(b2 & 0x80)
        length = b2 & 0x7F

        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]

        mask = self._recv_exact(4) if is_masked else None
        data = self._recv_exact(length)

        if is_masked and mask:
            unmasked = bytearray(length)
            for i in range(length):
                unmasked[i] = data[i] ^ mask[i % 4]
            data = bytes(unmasked)

        # Ping handling (RFC 6455 opcode 0x09) -> send Pong (0x0A)
        if opcode == 0x09:
            pong_head = bytearray([0x8A, 0x80 | (len(data) & 0x7F)])
            pm = os.urandom(4)
            p_payload = bytearray(len(data))
            for i in range(len(data)):
                p_payload[i] = data[i] ^ pm[i % 4]
            self.sock.sendall(pong_head + pm + p_payload)
            return self.read_frame()

        if opcode == 0x08:
            raise ConnectionError("WebSocket closed by server")

        return data.decode("utf-8", errors="replace")

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection closed prematurely")
            buf += chunk
        return buf

    def evaluate(self, script, return_by_value=True):
        """Executes JavaScript in the context of the page via Runtime.evaluate."""
        call_id = self._msg_id
        self._msg_id += 1
        req = {
            "id": call_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": script,
                "returnByValue": return_by_value,
                "awaitPromise": True
            }
        }
        self.send_frame(json.dumps(req))

        # Read until matching id response or error arrives
        for _ in range(50):
            raw = self.read_frame()
            try:
                res = json.loads(raw)
                if res.get("id") == call_id:
                    if "error" in res:
                        return None
                    result = res.get("result", {}).get("result", {})
                    return result.get("value")
            except Exception:
                pass
        return None

    def add_script_on_new_document(self, script):
        """Registers the script in CEF via Page.addScriptToEvaluateOnNewDocument.
        Executes instantly and automatically before any other script on every navigation,
        page switch, or tab load.
        """
        try:
            call_id = self._msg_id
            self._msg_id += 1
            self.send_frame(json.dumps({"id": call_id, "method": "Page.enable", "params": {}}))
            for _ in range(10):
                raw = self.read_frame()
                if json.loads(raw).get("id") == call_id:
                    break

            call_id = self._msg_id
            self._msg_id += 1
            self.send_frame(json.dumps({
                "id": call_id,
                "method": "Page.addScriptToEvaluateOnNewDocument",
                "params": {"source": script}
            }))
            for _ in range(10):
                raw = self.read_frame()
                if json.loads(raw).get("id") == call_id:
                    break
            return True
        except Exception:
            return False

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
