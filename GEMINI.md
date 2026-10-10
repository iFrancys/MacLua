# MacLua — local project rules

This file is **self-sufficient** for working in `~/Desktop/MacLua`: identity,
architecture, invariants, and which skills to use. The global catalog is not
needed.

## 1. Identity

MacLua manages Steam games on macOS: it imports `.lua` files into `stplug-in`,
applies offline licenses (`packageinfo.vdf`), generates manifests, downloads
content from the Steam CDNs anonymously, and adopts it into the installation.
Primary path = standalone Python CLI; native SwiftUI GUI; optional local bridge
that talks to the Steam client. Logic reference: LuaTools v1.3.2 — **reference
only, never copy-paste**, credit in `CREDITS.md`.

## 2. Current architecture (contract: `docs/INTEGRATION_SPEC.md`)

```
Steam (CEF, remote debugging on port 8080)  ◄── CDP Runtime.evaluate
        ▲  injected JS/CSS: core/steamui/maclua.{js,css}
MacLua bridge (Python, 127.0.0.1:6767, token)  ◄──►  MacLua.app (Swift, same CLI/bridge)
        │
core/ (maclua.py CLI: license, manifests, fetch, install, queue, vault…)  →  steamapps + stplug-in + depotcache
```

- The CLI is the single source of truth; the GUI goes through `--json` and the
  bridge, never duplicating logic.
- The bridge runs as a LaunchAgent (`dev.maclua.bridge`); a 32-byte hex token
  lives in `~/Library/Application Support/MacLua/bridge_token` (0600), sent via
  the `X-MacLua-Token` header; CORS allows only `store.steampowered.com` and
  `steamloopback.host`. The token is never hardcoded and never exposed on
  open endpoints.
- The bridge/CDP integration is **optional and reversible**: `steam-hook disable`
  removes the marker, the LaunchAgent, and the injected assets, and records a
  manifest at `~/Library/Application Support/MacLua/hook_manifest.json`.
- Application state lives in `~/Library/Application Support/MacLua/`
  (`settings.json`, `bridge_token`, `hook_manifest.json`, `Backgrounds/`).
  Steam data files touched: `stplug-in/`, `depotcache/`, `packageinfo.vdf`,
  `appmanifest`, `appcache`.
- ⚠️ Known discrepancy: the README claims "no resident process / no CEF
  injection", but the code implements the bridge + CDP hook
  (`maclua.py bridge|steam-hook`, `core/{bridge,cdp,steamhook}.py`).
  `docs/INTEGRATION_SPEC.md` is authoritative; fixing the README is a separate
  task.

## 3. Stack and constraints

- Python 3.9+: **stdlib only** + `pycryptodome`, `zstandard`
  (`requirements.txt`). Do not add Python dependencies without a real reason.
- Swift/SwiftUI: `native/Sources/MacApp` (macOS 14+, swift-tools 6.4, a single
  executable target; checks run inside the same module with `MACLUA_CHECK=1`).
- Electron/React web GUI: mentioned by the README but **absent** (`app/` does
  not exist).
- Product rule: **DLCs are never listed on their own** — always resolved to the
  parent game. Anything that enumerates appids must honor this.

## 4. Commands and verification

```bash
python3 maclua.py <search|add|update|verify|remove|status|ensure|doctor|
                   config|agent|collections|queue|vault|fixes|depots|
                   bridge|steam-hook>   # --json = machine output for the GUI
python3 -m pytest tests/                # 124 hermetic tests (local HTTP mocks, synthetic fixtures)
cd native && ./package.sh               # checks + universal release build (arm64+x86_64) + signing
MACLUA_CHECK=1 swift run -c release MacApp   # integrated check harness (32 checks)
```

Quality bar before calling anything done: `pytest tests/` green,
`MACLUA_CHECK=1` green (32/32), `package.sh` complete if packaging is touched.
No secrets, no personal absolute paths, and no writes outside the paths listed
above without explicit confirmation.

## 5. Non-negotiable invariants

1. **Idempotency + atomic writes** with an implicit backup on every Steam file.
2. **Reversibility**: every hook/LaunchAgent installation must have a clean,
   verified uninstall path.
3. **No runtime process/binary/compilation** in the CLI path (no `clang`/
   `codesign` generated on the fly: the roadmap pre-compiles them at packaging
   time).
4. Security: no secrets in the repo, sensitive files 0600, defensive binary
   parsing (bound checks, never `eval` on remote content).
5. Hermetic tests: no real network in tests, except `catalog` (already live).

## 6. Active roadmap — 100% Rust backend migration

Architectural verdict documented in `~/Desktop/indicazioni MacLua.md` (the
roadmap source): Rust backend + Swift/SwiftUI frontend, single universal
`universal2-apple-darwin` binary. Planned crates: `clap` (CLI), `axum`+`tokio`
(bridge REST/SSE), `tokio-tungstenite` (persistent CDP with `Runtime.addBinding`
replacing polling), `reqwest` (concurrent downloads), `aes`+`cbc`,
`zstd`/`lzma-rs`/`zip` (VZa/VSZa), `nom`/`byteorder` (VDF/protobuf), `rusqlite`
WAL (unified state).

Phases: **1** binary engine + crypto (bkv, manifest, chunks, Steam-style
Adler-32 with s1=0/s2=0 seeds, AES-256 ECB/CBC) → **2** clap CLI + axum bridge
+ license/config.vdf (AST KeyValues1 parser, offset-driven `appinfo.vdf` reader,
`packageinfo.vdf` poisoning with SHA-1 recalculation) → **3** event-driven CDP
→ **4** Swift talking to the daemon over `URLSession`, universal packaging,
removal of the Python `core/`, `requirements.txt`, and duplicated artifacts
(the backend is currently duplicated inside
`MacLua.app/Contents/Resources/backend/`).

## 7. Skills to load (trigger → skill)

| Situation | Skill |
|---|---|
| Rust code, crates, unsafe, migration | `rust-skills` |
| Swift/SwiftUI code in `native/Sources/MacApp` | `swiftui-pro` |
| Existing Python backend in `maclua.py` or `core/` | `python-pro` |
| Pytest fixtures, mocks, or tests in `tests/` | `python-testing-patterns` |
| Python download/chunk bottleneck before the Rust migration | `python-performance-optimization`, then `performance-profiler` |
| Changes to `native/package.sh` or other shell tooling | `bash-defensive-patterns`, `shellcheck-configuration` |
| macOS app design/UX | `apple-hig-expert` |
| New feature or refactor | `ponytail` (smallest thing that works, stdlib before dependencies) |
| HTTP bridge, API, daemon, phases 1-2 | `senior-backend` |
| Migration architecture decisions | `senior-architect`, `writing-plans` |
| Any bug or failing test | `systematic-debugging` (never guess-fix) |
| Making an area work end-to-end | `focused-fix` |
| New module or fix | `test-driven-development`, then `senior-qa` |
| Token/CORS/0600 files/binary parsing/signing | `security-and-hardening` |
| py/npm/crate dependencies | `dependency-auditor` |
| Download/chunk performance | `performance-profiler` |
| Binary/format analysis needs artifact evidence (VDF, Mach-O, chunks) | `rea` MCP + skill `reverse-engineer-anything` |
| Orienting in a 10k+ line codebase | `understand` |
| Before saying "done" | `verification-before-completion` |
| Reviewing changes | `open-code-review-delegate` |

## 8. Harness notes (Antigravity)

- Slash commands do not exist here: `/tc`, `/a11y-audit`, `/ocr-review` are
  natural-language requests.
- Skills are loaded by reading `~/.gemini/config/skills/<id>/SKILL.md`
  (progressive disclosure: 1-3 skills per step).
- MCP tools are called by server name (`rea`, `jev`, `originkit`, …).
- Rules budget: 24 KB max per file, 20,000 tokens aggregate — this file is
  deliberately compact.
