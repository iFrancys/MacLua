"""Depot key cache: stplug-in/*.lua -> cache/depotkey_<d>.yaml (0600).

Format identical to slsteam-moon (appId/depotId/key base64/managed) so
any key delivery mechanism can read from here.
"""
import base64
import os
import re

from core.atomic import atomic_write
from core.lua import parse_lua

_KEY_FILE = re.compile(r"^depotkey_(\d+)\.yaml$")
_APP = re.compile(r"^appId:\s*(\d+)", re.M)
_DEP = re.compile(r"^depotId:\s*(\d+)", re.M)
_KEY = re.compile(r"^key:\s*(\S+)", re.M)


def key_path(cache_dir, depot):
    return os.path.join(cache_dir, f"depotkey_{depot}.yaml")


def collect_keys(stplug_dir):
    """{depot: (appid, keyhex)} from all <appid>.lua (excluding comments)."""
    found = {}
    try:
        names = sorted(os.listdir(stplug_dir))
    except OSError:
        return found
    for fn in names:
        m = re.match(r"(\d+)\.lua$", fn)
        if not m:
            continue
        appid = int(m.group(1))
        try:
            with open(os.path.join(stplug_dir, fn), encoding="utf-8",
                      errors="replace") as f:
                parsed = parse_lua(f.read())
        except OSError:
            continue
        for depot, keyhex in parsed["keys"].items():
            found[depot] = (appid, keyhex)
    return found


def write_cache(cache_dir, appid, depot, keyhex):
    """Writes (atomic) key; idempotent when content is identical."""
    try:
        raw = bytes.fromhex(keyhex)
    except ValueError:
        raise ValueError(f"non-hex key for depot {depot}")
    if len(raw) != 32:
        raise ValueError(f"depot key {depot}: {len(raw)}B, expected 32")
    os.makedirs(cache_dir, exist_ok=True)
    body = ("appId: %d\ndepotId: %d\nkey: %s\nmanaged: true\n"
            % (appid, depot, base64.b64encode(raw).decode()))
    path = key_path(cache_dir, depot)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == body:
                return path
    except OSError:
        pass
    atomic_write(path, body, mode=0o600)
    return path


def load_key(cache_dir, depot):
    """32 raw bytes or ValueError."""
    try:
        with open(key_path(cache_dir, depot), encoding="utf-8") as f:
            txt = f.read()
    except OSError:
        raise ValueError(f"no key in cache for depot {depot}")
    m = _KEY.search(txt)
    a = _APP.search(txt)
    d = _DEP.search(txt)
    if not (m and a and d) or int(d.group(1)) != depot:
        raise ValueError(f"unreadable key cache for depot {depot}")
    try:
        raw = base64.b64decode(m.group(1))
    except Exception:
        raise ValueError(f"corrupt key cache for depot {depot}")
    if len(raw) != 32:
        raise ValueError(f"corrupt key cache for depot {depot}")
    return raw


def sync_config_vdf(config_vdf_path, keys_map):
    """Injects depot decryption keys into Steam/config/config.vdf ('depots' section).

    Reads all existing keys (depot, DecryptionKey) in config.vdf,
    merges them with keys provided in keys_map, and rewrites the 'depots' section
    cleanly and balanced at the first level, avoiding unintended nesting.
    """
    if not os.path.isfile(config_vdf_path):
        return 0
    try:
        with open(config_vdf_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return 0

    depots_pos = text.find('"depots"')
    if depots_pos == -1:
        steam_match = re.search(r'(\t*"Steam"\s*\{)', text)
        if not steam_match:
            return 0
        indent = "\t\t\t\t"
        block = f'\n{indent}"depots"\n{indent}{{\n{indent}}}'
        text = text[:steam_match.end()] + block + text[steam_match.end():]
        depots_pos = text.find('"depots"')
        if depots_pos == -1:
            return 0

    brace_pos = text.find('{', depots_pos)
    if brace_pos == -1:
        return 0

    depth = 0
    in_str = False
    escape = False
    closing_pos = -1

    for i in range(brace_pos, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if not in_str:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    closing_pos = i
                    break

    if closing_pos == -1:
        return 0

    inner_text = text[brace_pos + 1 : closing_pos]
    pairs = re.findall(r'"(\d+)"\s*\{\s*"DecryptionKey"\s*"([0-9a-fA-F]{64})"', inner_text)
    existing_keys = {int(d): k.lower() for d, k in pairs}

    injected = 0
    for depot, item in keys_map.items():
        keyhex = item[1] if isinstance(item, tuple) else item
        if not keyhex or len(keyhex) != 64:
            continue
        depot_id = int(depot)
        key_lower = keyhex.lower()
        if existing_keys.get(depot_id) != key_lower:
            existing_keys[depot_id] = key_lower
            injected += 1

    # No new or modified keys: avoid rewriting config.vdf (prevents
    # unnecessary race conditions with Steam rewriting it on shutdown).
    if injected == 0:
        return 0

    lines = ['\t\t\t\t"depots"', '\t\t\t\t{']
    for dep_id in sorted(existing_keys.keys()):
        key = existing_keys[dep_id]
        lines.append(f'\t\t\t\t\t"{dep_id}"')
        lines.append('\t\t\t\t\t{')
        lines.append(f'\t\t\t\t\t\t"DecryptionKey"\t\t"{key}"')
        lines.append('\t\t\t\t\t}')
    lines.append('\t\t\t\t}')
    new_depots_block = '\n'.join(lines)

    depots_start = text.rfind('\n', 0, depots_pos) + 1
    new_text = text[:depots_start] + new_depots_block + text[closing_pos + 1:]

    try:
        atomic_write(config_vdf_path, new_text)
    except OSError:
        return 0
    return injected


