"""Parse Steam .lua files: addappid, depot keys, manifest refs.

Only line-initial statements (after stripping comments) are counted:
-- comments and --[[ ]] long blocks never produce declarations.
"""
import re

_ADD_BARE = re.compile(r"^addappid\s*\(\s*(\d+)\s*\)\s*;?\s*$", re.I)
_ADD_KEY = re.compile(
    r"^addappid\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*['\"]([0-9A-Fa-f]{64})['\"]"
    r"\s*\)\s*;?\s*$", re.I)
_SET_MAN = re.compile(
    r"^setManifestid\s*\(\s*(\d+)\s*,\s*['\"](\d+)['\"]", re.I)


def _strip_line(line, in_block):
    """Remove comments; in_block tracks long blocks across lines."""
    if in_block:
        end = line.find(in_block)
        if end < 0:
            return "", in_block
        line, in_block = line[end + len(in_block):], None
    while True:
        i = line.find("--")
        if i < 0:
            break
        m = re.match(r"--\[(=*)\[", line[i:])
        if not m:
            line = line[:i]
            break
        in_block = "]" + m.group(1) + "]"
        line = line[:i]
        end = line.find(in_block)  # block continues below
        break
    # Neutralize long [[ ]] strings outside of comments
    line = re.sub(r"\[(=*)\[.*?\]\1\]", " ", line)
    return line, in_block


def _positive(n):
    n = int(n)
    return n if n > 0 else None


def parse_lua(text):
    """{'bare': {appid}, 'keys': {depot: hex64lower}, 'manifests': {depot: gid}}."""
    bare, keys, manifests = {}, {}, {}
    in_block = None
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line, in_block = _strip_line(raw, in_block)
        line = line.strip()
        if not line:
            continue
        m = _ADD_BARE.match(line)
        if m:
            bare[_positive(m.group(1))] = True
            continue
        m = _ADD_KEY.match(line)
        if m:
            keys[_positive(m.group(1))] = m.group(3).lower()
            continue
        m = _SET_MAN.match(line)
        if m:
            manifests[_positive(m.group(1))] = m.group(2).lstrip("0") or "0"
    bare = {k for k in bare if k}
    keys = {k: v for k, v in keys.items() if k}
    manifests = {k: v for k, v in manifests.items() if k}
    return {"bare": bare, "keys": keys, "manifests": manifests}


def merge_lua(primary_text, secondary_text):
    """Merge two .lua files, preserving all depot keys and bare addappids
    present in secondary_text but missing in primary_text (e.g. Sushi + Hubcap merge)."""
    if not secondary_text:
        return primary_text
    if not primary_text:
        return secondary_text
    p1 = parse_lua(primary_text)
    p2 = parse_lua(secondary_text)
    extra_lines = []
    for dep in sorted(p2["keys"]):
        if dep not in p1["keys"]:
            extra_lines.append('addappid(%d, 1, "%s")' % (dep, p2["keys"][dep]))
    covered = set(p1["bare"]) | set(p1["keys"]) | set(p2["keys"])
    for aid in sorted(p2["bare"]):
        if aid not in covered:
            extra_lines.append("addappid(%d)" % aid)
    if not extra_lines:
        return primary_text
    sep = "" if primary_text.endswith("\n") else "\n"
    trail = "\n" if primary_text.endswith("\n") else ""
    return primary_text + sep + "\n".join(extra_lines) + trail

