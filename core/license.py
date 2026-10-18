"""Offline licenses in packageinfo.vdf: poison package0 + forged package.

- package0 (group 1, always owned): injects managed appids + depotids.
- forged FORGE_ID (group 2): Steam sidebar lists non-zero packages.
- SHA1(file[0x2C:group2_start]) recalculated on each write; changenumber
  untouched so PICS doesn't see updates. Fully idempotent.
"""
import hashlib
import struct

from core.bkv import Reader, parse_node, ser_node
from core.atomic import atomic_write

HEADER = 0x2C
FORGE_ID = 4000001
_OPAQUE12 = bytes.fromhex("1fef5a01a951256fea34b56f")


def load_groups(path):
    with open(path, "rb") as f:
        data = f.read()
    r = Reader(data[HEADER:])
    pkgs = []
    while True:
        n = parse_node(r)
        if n[0] == "end":
            break
        pkgs.append(n)
    return data[:HEADER], pkgs, data[HEADER + r.o:]


def _vecs(pkg0):
    appids, depotids = set(), set()
    for c in pkg0[2]:
        if c[0] == "sec" and c[1] == "appids":
            appids = {v for _, _, v in c[2]}
        elif c[0] == "sec" and c[1] == "depotids":
            depotids = {v for _, _, v in c[2]}
    return appids, depotids


def _package0(pkgs):
    for p in pkgs:
        if p[0] == "sec" and p[1] == "0":
            return p
    return None


def check(path, appids, depotids):
    _, pkgs, _ = load_groups(path)
    p0 = _package0(pkgs)
    have_app, have_dep = _vecs(p0) if p0 is not None else (set(), set())
    return set(appids) - have_app, set(depotids) - have_dep


def _write_back(path, header, pkgs, rest):
    body = bytearray()
    for n in pkgs:
        ser_node(n, body)
    body1 = bytes(body) + b"\x08"
    new = header + body1 + rest
    hend = HEADER + len(body1)
    h = hashlib.sha1(new[HEADER:hend]).digest()
    new = new[:0x0C] + h + new[0x20:]
    atomic_write(path, new, mode=0o755)
    return new


def poison(path, appids, depotids):
    """Injects missing IDs into package0; returns (added_app, added_dep)."""
    header, pkgs, rest = load_groups(path)
    p0 = _package0(pkgs)
    if p0 is None:
        raise ValueError("package 0 missing")
    added_app = added_dep = 0
    for c in p0[2]:
        if c[0] == "sec" and c[1] == "appids":
            have = {v for _, _, v in c[2]}
            for a in sorted(set(appids) - have):
                c[2].append(("i32", str(len(c[2])), a))
                added_app += 1
        elif c[0] == "sec" and c[1] == "depotids":
            have = {v for _, _, v in c[2]}
            for d in sorted(set(depotids) - have):
                c[2].append(("i32", str(len(c[2])), d))
                added_dep += 1
    _write_back(path, header, pkgs, rest)
    return added_app, added_dep


def _load_state(state_path):
    try:
        with open(state_path, encoding="utf-8") as f:
            data = f.read()
        import json as _json
        obj = _json.loads(data)
        return set(obj.get("appids", [])), set(obj.get("depotids", []))
    except (OSError, ValueError):
        return set(), set()


def _save_state(state_path, appids, depotids):
    import json as _json
    atomic_write(state_path,
                 _json.dumps({"appids": sorted(appids),
                              "depotids": sorted(depotids)}))


def sync(path, want_app, want_dep, state_path):
    """Reconciles package0 with the managed set: adds missing entries, prunes
    only previously managed IDs that are now absent (native IDs are always kept).

    Returns ((added_app, added_dep), (removed_app, removed_dep))."""
    want_app, want_dep = set(want_app), set(want_dep)
    prev_app, prev_dep = _load_state(state_path)
    header, pkgs, rest = load_groups(path)
    p0 = _package0(pkgs)
    if p0 is None:
        raise ValueError("package 0 missing")
    added_app, added_dep = set(), set()
    removed_app, removed_dep = set(), set()
    for c in p0[2]:
        if c[0] != "sec" or c[1] not in ("appids", "depotids"):
            continue
        is_app = c[1] == "appids"
        want = want_app if is_app else want_dep
        prev = prev_app if is_app else prev_dep
        have = {v for _, _, v in c[2]}
        for v in sorted(want - have):
            c[2].append(("i32", str(len(c[2])), v))
            (added_app if is_app else added_dep).add(v)
        stale = (prev - want) & have
        if stale:
            c[2][:] = [n for n in c[2] if n[2] not in stale]
            for i, n in enumerate(c[2]):
                c[2][i] = (n[0], str(i), n[2])
            (removed_app if is_app else removed_dep).update(stale)
    if added_app or added_dep or removed_app or removed_dep:
        _write_back(path, header, pkgs, rest)
    _save_state(state_path, want_app, want_dep)
    return (added_app, added_dep), (removed_app, removed_dep)


def _build_kv(pkgid, appids, depots):
    kids = [
        ("i32", "packageid", pkgid),
        ("i32", "billingtype", 12),
        ("i32", "licensetype", 1),
        ("i32", "status", 0),
        ("sec", "extended", [
            ("i32", "allowpurchasefromrestrictedcountries", 0),
            ("str", "purchaserestrictedcountries", "CN"),
        ]),
        ("sec", "appids", [("i32", str(i), a) for i, a in enumerate(appids)]),
        ("sec", "depotids", [("i32", str(i), d) for i, d in enumerate(depots)]),
        ("sec", "appitems", []),
    ]
    w = bytearray()
    w.append(0x00)
    w += str(pkgid).encode() + b"\x00"
    for k in kids:
        ser_node(k, w)
    w.append(0x08)  # Closes package section
    w.append(0x08)  # Closes root map of binary KeyValues
    return bytes(w)


def has_forged_package(path):
    """Checks whether the forged FORGE_ID package is present in the file."""
    try:
        marker = struct.pack("<I", FORGE_ID)
        with open(path, "rb") as f:
            data = f.read()
        return marker in data
    except Exception:
        return False



def _remove_forged(out):
    marker = struct.pack("<I", FORGE_ID)
    tag = b"\x00" + str(FORGE_ID).encode() + b"\x00"
    probe = 0
    while True:
        at = out.find(marker, probe)
        if at < 0:
            return out, False
        if out[at + 36:at + 36 + len(tag)] == tag:
            term = out.rfind(b"\xff\xff\xff\xff")
            return out[:at] + out[term:], True
        probe = at + 4


def forge(path, appids, depots):
    """Rebuilds the forged package; with empty lists it removes it cleanly.

    Idempotent: if resulting content is identical to disk, does not rewrite
    (avoids unnecessary churn on packageinfo.vdf on every ensure).
    Atomic write: Steam can never observe a partially written file.
    """
    with open(path, "rb") as f:
        orig = f.read()
    out, removed = _remove_forged(orig)
    appids, depots = sorted(appids), sorted(depots)
    if appids:
        term = out.rfind(b"\xff\xff\xff\xff")
        if term < 0:
            raise ValueError("packageinfo terminator missing")
        kv = _build_kv(FORGE_ID, appids, depots)
        entry = struct.pack("<I", FORGE_ID) + hashlib.sha1(kv).digest() \
            + _OPAQUE12 + kv
        out = out[:term] + entry + out[term:]
    elif not removed:
        return
    if out == orig:
        return
    atomic_write(path, out, mode=0o755)

