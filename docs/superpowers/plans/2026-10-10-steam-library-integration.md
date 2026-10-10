# Steam In-Client Library Discovery & Native UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make games added via MacLua in Steam (via `.lua` in `stplug-in/` and offline licenses in `packageinfo.vdf`) appear cleanly in the Steam Library sidebar under "SENZA CATEGORIA" with the native "INSTALLA" button and download size, eliminating both missing library entries and the erroneous "DOWNLOAD RICHIESTO" banner.

**Architecture:** 
Extend the in-Steam client hook (`core/steamui/maclua.js` and `core/steamhook.py`) to run in `steamloopback.host` (`SharedJSContext` and Library tabs) as well as `store.steampowered.com`. In `SharedJSContext`, the script dynamically syncs managed games into Steam's MobX `appStore.m_mapApps` (`visible_in_game_list: true`) and `collectionStore.uncategorizedCollection` (`m_rgApps`). In the backend (`core/install.py` and `maclua.py`), remove the generation of fake `StateFlags 2` appmanifest stubs (which previously caused the "DOWNLOAD RICHIESTO" 0-byte error), leaving appmanifest creation strictly to real game adoption (`StateFlags 4`) or Steam's native installer wizard.

**Tech Stack:** JavaScript (Steam CEF / React / MobX client hooks), Python 3.9+ (CDP WebSocket client, local HTTP bridge), Rust (backend migration parity), pytest, cargo.

**Spec:** `docs/INTEGRATION_SPEC.md`

## Global Constraints

- Standalone Python stdlib + pycryptodome + zstandard; no extra Python dependencies.
- Swift/SwiftUI in `native/Sources/MacApp` with zero regressions (`MACLUA_CHECK=1` must remain 100% green).
- Reversibility: no permanent corruption of Steam data files; all files touched have backups or clean uninstall paths.
- Product rule: DLCs are never listed as standalone games in the library sidebar—always resolved to the parent base game.
- No secrets or personal absolute paths in repository files.

## Review Focus

1. **Host isolation:** `maclua.js` must differentiate between `store.steampowered.com` (Store header button, game page Add/Play buttons) and `steamloopback.host` (SharedJSContext and Library sidebar synchronization) without collisions or uncaught exceptions.
2. **MobX reactivity:** Changes to `uncategorizedCollection` and `appStore.m_mapApps` must trigger React re-renders in Steam's library sidebar without crashing Steam or freezing CEF.
3. **No fake appmanifest stubs:** `maclua add` and the in-Steam "Aggiungi con MacLua" button must never create incomplete `StateFlags 2` / 0-byte appmanifests on disk that cause Steam's "DOWNLOAD RICHIESTO" state.
4. **DLC handling:** Adding or syncing a DLC must resolve to its parent game and never insert standalone DLC appids into `collectionStore`.
5. **Real-time updates:** Clicking "Aggiungi con MacLua" or "Rimuovi da MacLua" must immediately reflect in the Steam Library sidebar across active tabs without requiring a client restart.

---

### Task 1: In-Steam Library Synchronization in `core/steamui/maclua.js`

**Files:**
- Modify: `core/steamui/maclua.js`
- Test: `tests/test_steamui_library.py`

**Interfaces:**
- Consumes: `GET /library` and `window.__MacLuaRPC` from local bridge / CDP.
- Produces: `initLibrarySync()`, updating `appStore.m_mapApps` and `collectionStore.uncategorizedCollection` on `steamloopback.host`.

- [ ] **Step 1: Write failing test in `tests/test_steamui_library.py`**

```python
import os
import re

def test_maclua_js_supports_steamloopback_and_library_sync():
    js_path = os.path.join(os.path.dirname(__file__), "..", "core", "steamui", "maclua.js")
    with open(js_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Must NOT early-return if on steamloopback.host
    assert 'location.hostname !== "store.steampowered.com"' not in content or 'steamloopback.host' in content
    # Must contain library synchronization logic for uncategorized collection and appStore
    assert "uncategorizedCollection" in content
    assert "syncManagedLibrary" in content or "initLibrarySync" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_steamui_library.py -v`
Expected: FAIL (assertion fails because `maclua.js` currently exits if hostname is not `store.steampowered.com`).

- [ ] **Step 3: Implement library synchronization in `core/steamui/maclua.js`**

1. Update hostname guard at top of `core/steamui/maclua.js` to allow both `store.steampowered.com` and `steamloopback.host`.
2. Add `initLibrarySync()` that runs when `location.hostname === "steamloopback.host"`:
   - Polls or listens for managed game list from `api("/library")`.
   - Iterates through managed games: for each `appid`, if `appStore && appStore.m_mapApps.has(appid)`, sets `a.visible_in_game_list = true`.
   - Retrieves `collectionStore.uncategorizedCollection`, adds missing managed `appids` to `m_rgApps` and `m_setApps`, and invokes `SetApps()` to trigger React/MobX re-render.
   - Provides `window.__MacLuaSyncLibrary(games)` hook callable via CDP on `/add` or `/remove`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_steamui_library.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/steamui/maclua.js tests/test_steamui_library.py
git commit -m "feat(steamui): add Steam library synchronization for steamloopback.host"
```

---

### Task 2: Multi-Tab Injection and Real-Time Library Broadcast in `core/steamhook.py`

**Files:**
- Modify: `core/steamhook.py`
- Test: `tests/test_steamhook.py`

**Interfaces:**
- Consumes: `inject_into_tabs()`, `handle_rpc_request()`, `CDPClient`.
- Produces: Automatic injection into both Store and `SharedJSContext` tabs; real-time broadcast of `/add` and `/remove` events to `SharedJSContext`.

- [ ] **Step 1: Write failing test in `tests/test_steamhook.py`**

```python
from core import steamhook

def test_steamhook_broadcasts_library_update_on_add():
    # Verify that steamhook exposes a broadcast function for library changes
    assert hasattr(steamhook, "broadcast_library_refresh")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_steamhook.py -k test_steamhook_broadcasts_library_update_on_add -v`
Expected: FAIL with `AttributeError: module 'core.steamhook' has no attribute 'broadcast_library_refresh'`.

- [ ] **Step 3: Implement `broadcast_library_refresh()` and hook into `handle_rpc_request` in `core/steamhook.py`**

1. Implement `broadcast_library_refresh(home=None)` in `core/steamhook.py`:
   - Queries `CDP_URL` (`http://127.0.0.1:8080/json`).
   - Finds all tabs with `steamloopback.host` (especially `SharedJSContext`).
   - Retrieves managed games from `stplug-in/`.
   - Sends CDP `Runtime.evaluate` calling `window.__MacLuaSyncLibrary && window.__MacLuaSyncLibrary(<games_json>)`.
2. In `handle_rpc_request` for `/add` and `/remove`:
   - Call `broadcast_library_refresh(home)` immediately after importing or removing `.lua` and updating licenses.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_steamhook.py -k test_steamhook_broadcasts_library_update_on_add -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/steamhook.py tests/test_steamhook.py
git commit -m "feat(steamhook): add real-time library refresh broadcast over CDP"
```

---

### Task 3: Appmanifest Generation Cleanup in `core/install.py` and `maclua.py`

**Files:**
- Modify: `core/install.py`, `maclua.py`
- Test: `tests/test_install.py`, `tests/test_acf.py`

**Interfaces:**
- Consumes: `paths.steamapps()`, `paths.stplug_in()`.
- Produces: Clean manifest lifecycle where uninstalled games rely on native Steam state flags, and fully installed games have valid `StateFlags 4`.

- [ ] **Step 1: Write failing test in `tests/test_acf.py`**

```python
import os
from core import install

def test_install_does_not_create_broken_state_flags_2_stub(tmp_path):
    steamapps = tmp_path / "steamapps"
    steamapps.mkdir()
    # Ensure create_appmanifest is only used when buildid and depots are known,
    # and cleanup_broken_appmanifests removes legacy broken stubs without touching valid files.
    cleaned = install.cleanup_broken_appmanifests(str(steamapps))
    assert isinstance(cleaned, list)
```

- [ ] **Step 2: Run test to verify it runs and check current behavior**

Run: `python3 -m pytest tests/test_acf.py -v`
Expected: Verify existing tests pass and baseline is established.

- [ ] **Step 3: Refactor appmanifest creation in `core/install.py` and remove broken stub generation**

1. Ensure `import_lua()` and `maclua add` do NOT create empty dummy `.acf` files with `StateFlags "2"` and `SizeOnDisk "0"`. Steam native installer creates the `.acf` cleanly when the user clicks "Installa".
2. Keep `cleanup_broken_appmanifests()` to purge any legacy 0-byte `StateFlags 2` files created by older versions.
3. In `maclua.py _ensure()`, retain license forging in `packageinfo.vdf` and key synchronization in `config.vdf`.
4. Update `core/install.py` so `create_appmanifest` is only called during physical game adoption with actual depot sizes and build IDs.

- [ ] **Step 4: Run test suite to verify all manifest tests pass**

Run: `python3 -m pytest tests/test_acf.py tests/test_install.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/install.py maclua.py tests/test_acf.py
git commit -m "refactor(install): prevent creation of broken StateFlags 2 appmanifest stubs"
```

---

### Task 4: Mirroring Bridge Endpoints and Manifest Logic in Rust Backend

**Files:**
- Modify: `rust/src/engine/install.rs`, `rust/src/server/routes.rs`
- Test: `rust/tests/`

**Interfaces:**
- Consumes: Rust `axum` routes `/library`, `/add`, `/remove`.
- Produces: Parity between Python and Rust implementations for in-Steam bridge.

- [ ] **Step 1: Inspect Rust test suite and existing route coverage**

Run: `cargo test` in `rust/`
Expected: PASS (14 tests passing).

- [ ] **Step 2: Verify Rust `/library` and manifest handling match refactored Python behavior**

1. Verify `cleanup_broken_appmanifests` in `rust/src/engine/install.rs`.
2. Ensure `/library` in `rust/src/server/routes.rs` returns all uninstalled and installed games from `stplug-in/`.

- [ ] **Step 3: Run Rust test suite to verify everything compiles and passes**

Run: `cargo test` in `rust/`
Expected: PASS with 0 errors.

- [ ] **Step 4: Commit**

```bash
git add rust/
git commit -m "feat(rust): align library discovery and manifest handling with Python backend"
```

---

### Task 5: Live Verification & Full Regression Harness

**Files:**
- Test: `tests/`, `rust/`, `native/`

- [ ] **Step 1: Run full Python pytest test suite**

Run: `python3 -m pytest tests/`
Expected: 127+ tests passing (100% green).

- [ ] **Step 2: Run full Rust test suite**

Run: `cargo test` in `rust/`
Expected: All tests passing.

- [ ] **Step 3: Run native Swift verification check harness**

Run: `MACLUA_CHECK=1 swift run -c release MacApp` in `native/`
Expected: 49/49 checks passing.

- [ ] **Step 4: Live Steam verification**

Run CDP query against Steam's `SharedJSContext` and Library tabs:
- Verify Stardew Valley (`413150`), Isaac (`250900`), and other managed games appear in the Library sidebar under "SENZA CATEGORIA".
- Verify clicking on an uninstalled game displays the native "Installa" button with real download size, without any "DOWNLOAD RICHIESTO" error.
- Verify clicking on an already installed game (e.g. Cuphead `268910`) displays the native green "Gioca" button.
