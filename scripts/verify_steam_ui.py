#!/usr/bin/env python3
"""Script di verifica per l'integrazione in-client di Steam via CDP.
Verifica la disponibilità di Steam CEF e inietta maclua.js/maclua.css nei tab attivi.
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
    print("== Verifica In-Client Steam UI via CDP ==")
    status = steamhook.get_status()
    print("Marker presente:", status["marker_present"])
    print("CDP attivo (porta 8080):", status["cdp_available"])
    print("Tab trovati:", status["tabs_count"])

    if not status["cdp_available"]:
        print("AVVISO: Steam non ha la porta CDP 8080 aperta. Assicurati che Steam sia avviato con il marker.")
        return 1

    token = steamhook.get_or_create_token()
    print(f"Token bridge: {token[:8]}...")

    res = steamhook.inject_into_tabs(token=token)
    print("Risultato iniezione:", res)

    # Verifica diretta su ogni tab
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
        print("Errore verifica:", e)
        return 1

    print(f"Verifica completata: {verified} tab Steam hanno MacLua UI caricato con successo.")
    return 0 if verified > 0 else 1

if __name__ == "__main__":
    sys.exit(main())
