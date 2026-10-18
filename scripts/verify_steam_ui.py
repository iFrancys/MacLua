#!/usr/bin/env python3
"""Verification script for Steam in-client integration via CDP.
Checks Steam CEF availability and injects maclua.js/maclua.css into active tabs.
"""
import sys
import os
import json
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import steamhook, cdp

def main():
    print("== In-Client Steam UI Verification via CDP ==")
    status = steamhook.get_status()
    print("Marker present:", status["marker_present"])
    print("CDP active (port 8080):", status["cdp_available"])
    print("Tabs found:", status["tabs_count"])

    if not status["cdp_available"]:
        print("WARNING: Steam does not have CDP port 8080 open. Ensure Steam is launched with the marker.")
        return 1

    token = steamhook.get_or_create_token()
    print(f"Bridge token: {token[:8]}...")

    res = steamhook.inject_into_tabs(token=token)
    print("Injection result:", res)

    # Direct verification on each tab
    verified = 0
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/json", timeout=2) as resp:
            tabs = json.loads(resp.read().decode("utf-8"))
        for t in tabs:
            url = t.get("url", "")
            ws = t.get("webSocketDebuggerUrl")
            if ws and ("store.steampowered.com" in url or "steamloopback.host" in url):
                client = cdp.CDPClient(ws)
                ready = client.evaluate("String(window.__MacLuaReady === true)")
                title = client.evaluate("document.title")
                client.close()
                print(f"Tab [{title}] ({url[:45]}...): window.__MacLuaReady = {ready}")
                if ready == "true":
                    verified += 1
    except Exception as e:
        print("Verification error:", e)
        return 1

    print(f"Verification completed: {verified} Steam tab(s) have MacLua UI successfully loaded.")
    return 0 if verified > 0 else 1

if __name__ == "__main__":
    sys.exit(main())
