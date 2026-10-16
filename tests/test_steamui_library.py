import os

def test_maclua_js_is_isolated_to_store_and_never_touches_library_internals():
    js_path = os.path.join(os.path.dirname(__file__), "..", "core", "steamui", "maclua.js")
    with open(js_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Must strictly restrict to store.steampowered.com
    assert 'location.hostname !== "store.steampowered.com"' in content
    # Must NOT touch or monkey-patch private Steam Library internals
    assert "uncategorizedCollection" not in content
    assert "syncManagedLibrary" not in content


def test_maclua_js_settings_modal_requirements():
    js_path = os.path.join(os.path.dirname(__file__), "..", "core", "steamui", "maclua.js")
    with open(js_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Multi-language dictionary contains en, it, de, es, fr
    assert "const I18N =" in content
    for lang in ["en:", "it:", "de:", "es:", "fr:"]:
        assert lang in content

    # 2. English is default
    assert 'localStorage.getItem("maclua_lang") || "en"' in content

    # 3. No double dash or em-dash in MacLua Settings
    assert 'title: "MacLua Settings"' in content
    assert "MacLua — Impostazioni" not in content
    assert "MacLua -- Impostazioni" not in content

    # 4. Auto-update and donate checkboxes removed from modal
    assert "maclua-cfg-autoupdate" not in content
    assert "maclua-cfg-donate" not in content
    assert "auto_update_apps: true" in content

    # 5. Redundant helper descriptions removed
    assert "Seleziona la sorgente" not in content
    assert "Rimuove gli appmanifest fantasma" not in content
    assert "Necessaria solo se usi Hubcap" not in content
    assert "(stile LuaTools)" not in content

    # 6. Clean non-snake_case sources
    assert "Auto (Sushi, Ryuu, Hubcap)" in content
    assert "Sushi (GitHub Raw - Free)" in content
    assert "Ryuu (Anonymous - Free)" in content
    assert "Hubcap / Morrenus (Requires Key)" in content

    # 7. Initial games synchronous rendering
    assert "initialGames" in content
    assert "window.__MACLUA.initialGames" in content

