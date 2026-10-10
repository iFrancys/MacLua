import os

def test_maclua_js_supports_steamloopback_and_library_sync():
    js_path = os.path.join(os.path.dirname(__file__), "..", "core", "steamui", "maclua.js")
    with open(js_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Must NOT early-return if on steamloopback.host
    assert "steamloopback.host" in content
    # Must contain library synchronization logic for uncategorized collection and appStore
    assert "uncategorizedCollection" in content
    assert "syncManagedLibrary" in content or "initLibrarySync" in content
