"""Modulo Collezioni: integrazione e recupero elenchi curati dalla community (lua.tools/collections).
Supporta parsing HTML live di Next.js e fallback offline robusto.
"""
import os
import re
import json
import urllib.request

CACHE_DIR = os.path.expanduser("~/Library/Application Support/MacLua")
CACHE_FILE = os.path.join(CACHE_DIR, "collections_cache.json")

# Collezione di fallback locale curata
DEFAULT_FALLBACK = [
    {
        "id": "e4f40c3c-friendslop",
        "title": "Friendslop Co-op Pack",
        "cover": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1966720/header.jpg",
        "appCount": 20,
        "author": "Community",
        "apps": [1966720, 2881650, 3643170, 2567870, 3722330, 1686940, 673750, 3059070, 2644470, 945360]
    },
    {
        "id": "81f2d24a-euro-truck-simulator-complete-edition",
        "title": "Euro Truck Simulator Complete Edition",
        "cover": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/227300/header.jpg",
        "appCount": 12,
        "author": "TruckSimFan",
        "apps": [227300]
    },
    {
        "id": "05a702f5-sonic-games",
        "title": "Sonic Collection Pack",
        "cover": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1848380/header.jpg",
        "appCount": 8,
        "author": "Speedster",
        "apps": [1848380, 2324650]
    }
]


def _ensure():
    os.makedirs(CACHE_DIR, exist_ok=True)
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_FALLBACK, f, indent=2)


def _load_cache():
    _ensure()
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_FALLBACK


def _save_cache(data):
    _ensure()
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CACHE_FILE)


def fetch_collections(sort="popular", timeout=8):
    """Scarica l'elenco delle collezioni live da lua.tools/collections."""
    url = f"https://lua.tools/collections?sort={sort}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MacLua/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8")

        collections = []
        # Estrai slug /c/<slug> e dati del blocco
        pattern = re.compile(
            r'href="/c/([a-zA-Z0-9_-]+)"[^>]*>.*?'
            r'<img[^>]+src="([^"]+)"[^>]*>.*?'
            r'lucide-layers[^>]*>.*?</svg>(\d+)</span>.*?'
            r'<span[^>]*style="[^"]*font-weight:600[^"]*"[^>]*>([^<]+)</span>',
            re.DOTALL
        )

        matches = pattern.findall(html)
        for slug, cover, count, title in matches:
            collections.append({
                "id": slug,
                "title": title.strip(),
                "cover": cover.strip(),
                "appCount": int(count) if count.isdigit() else 0,
                "author": "Community",
                "apps": []
            })

        if collections:
            _save_cache(collections)
            return {"collections": collections, "cached": False, "stale": False}
    except Exception as e:
        pass

    # Fallback offline
    cached = _load_cache()
    return {"collections": cached, "cached": True, "stale": True}


def fetch_collection_details(slug, timeout=8):
    """Scarica i dettagli e la lista degli AppID per una specifica collezione."""
    # Prima cerca nella cache se ha già apps
    cached = _load_cache()
    for c in cached:
        if c.get("id") == slug and c.get("apps"):
            return c

    url = f"https://lua.tools/c/{slug}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MacLua/1.0"})
    apps = []
    title = slug

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8")

        raw_appids = re.findall(r"/apps/(\d+)/", html)
        seen = set()
        for a in raw_appids:
            ia = int(a)
            if ia not in seen:
                seen.add(ia)
                apps.append(ia)

        # Cerca titolo
        t_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        if t_match:
            title = t_match.group(1).strip()
    except Exception:
        pass

    # Aggiorna la cache
    for c in cached:
        if c.get("id") == slug:
            if apps:
                c["apps"] = apps
            return c

    item = {
        "id": slug,
        "title": title,
        "cover": "",
        "appCount": len(apps),
        "author": "Community",
        "apps": apps
    }
    cached.append(item)
    _save_cache(cached)
    return item
