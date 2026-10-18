"""Network resilience: DNS-over-HTTPS (DoH) resolution and proxy support.
Inspired by LuaTools DohResolver but implemented with Python 3 stdlib.
Allows bypassing ISP DNS blocks for Valve CDN and manifest sources.
"""
import json
import socket
import urllib.request
import urllib.parse
from core import settings

CLOUDFLARE_DOH = "https://cloudflare-dns.com/dns-query"
GOOGLE_DOH = "https://dns.google/resolve"

_CACHE = {}


def resolve_doh(hostname, provider="cloudflare", timeout=5):
    """Resolves a hostname via DNS-over-HTTPS."""
    if hostname in _CACHE:
        return _CACHE[hostname]

    base = CLOUDFLARE_DOH if provider == "cloudflare" else GOOGLE_DOH
    params = urllib.parse.urlencode({"name": hostname, "type": "A"})
    url = f"{base}?{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/dns-json", "User-Agent": "MacLua/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        answers = data.get("Answer", [])
        for a in answers:
            if a.get("type") == 1: # A record (IPv4)
                ip = a.get("data")
                if ip:
                    _CACHE[hostname] = ip
                    return ip
    except Exception:
        pass
    return None


def resolve(hostname):
    """Resolves hostname taking configured mode into account (auto, always, never)."""
    mode = settings.get("dns_mode", "auto")
    provider = settings.get("doh_provider", "cloudflare")

    if mode == "never":
        try:
            return socket.gethostbyname(hostname)
        except Exception:
            return None

    if mode == "always":
        ip = resolve_doh(hostname, provider=provider)
        if ip:
            return ip
        # Fallback to system DNS if DoH fails
        try:
            return socket.gethostbyname(hostname)
        except Exception:
            return None

    # mode == "auto": try system DNS first; if it fails try DoH
    try:
        return socket.gethostbyname(hostname)
    except Exception:
        return resolve_doh(hostname, provider=provider)
