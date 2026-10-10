"""Lettura voce app da appcache/appinfo.vdf (VDF binario, chiavi numeriche)."""
import os
import struct

from core import paths

_HEADER = 8
_ANCHOR = b"\x02\x01\x00\x00\x00"  # nodo i32 con indice chiave 1 == "appid"


def _string_table(d):
    start = struct.unpack_from("<I", d, _HEADER)[0]
    count = struct.unpack_from("<I", d, start)[0]
    off = start + 4
    out = []
    for _ in range(count):
        end = d.index(b"\x00", off)
        out.append(d[off:end].decode("utf-8", "replace"))
        off = end + 1
    return out


def _parse(d, names, off, end):
    out = []
    while off < end:
        t = d[off]
        off += 1
        if t == 0x08:
            return out, off
        if off + 4 > end:
            return out, off
        idx = struct.unpack_from("<I", d, off)[0]
        off += 4
        key = names[idx] if idx < len(names) else "?%d" % idx
        if t == 0x00:
            kids, off = _parse(d, names, off, end)
            out.append((key, kids))
        elif t == 0x01:
            stop = d.index(b"\x00", off)
            out.append((key, d[off:stop].decode("utf-8", "replace")))
            off = stop + 1
        elif t == 0x02:
            out.append((key, struct.unpack_from("<i", d, off)[0]))
            off += 4
        elif t == 0x07:
            out.append((key, struct.unpack_from("<q", d, off)[0]))
            off += 8
        else:
            raise ValueError("tipo VDF non previsto 0x%02x a 0x%x" % (t, off - 1))
    return out, off


def _find(d, appid):
    anchors = []
    i = 0
    while True:
        i = d.find(_ANCHOR, i)
        if i < 0:
            break
        anchors.append(i)
        i += 1
    for k, a in enumerate(anchors):
        if struct.unpack_from("<I", d, a + 5)[0] == appid:
            start = a - 5
            end = anchors[k + 1] - 5 if k + 1 < len(anchors) else len(d)
            return start, end
    return None


def entry(appid, path=None):
    """Ramo figlio di 'appinfo', o None se l'app non è in cache."""
    path = path or os.path.join(paths.appcache(), "appinfo.vdf")
    with open(path, "rb") as f:
        d = f.read()
    span = _find(d, appid)
    if span is None:
        return None
    names = _string_table(d)
    tree, _ = _parse(d, names, span[0], span[1])
    if not tree or tree[0][0] != "appinfo":
        return None
    return tree[0][1]


def _child(nodes, name):
    for k, v in nodes:
        if k == name:
            return v
    return None


def depots(appid, path=None):
    """[{id, oslist, gid, size, shared}] per i depot pubblici dell'app."""
    root = entry(appid, path)
    if root is None:
        return []
    blocks = _child(root, "depots") or []
    out = []
    for k, v in blocks:
        if not k.isdigit() or not isinstance(v, list):
            continue
        cfg = _child(v, "config") or []
        oslist = next((x for a, x in cfg if a == "oslist"), "")
        shared = any(a in ("depotfromapp", "sharedinstall") for a, _ in v)
        man = _child(v, "manifests")
        gid = size = None
        if isinstance(man, list):
            pub = _child(man, "public")
            if isinstance(pub, list):
                gid = next((x for a, x in pub if a == "gid"), None)
                size = next((x for a, x in pub if a == "size"), None)
        out.append({"id": int(k), "oslist": oslist, "gid": gid, "size": size,
                    "shared": shared})
    return out


def depot_ids(appid, path=None):
    return [x["id"] for x in depots(appid, path)]


def config(appid, path=None):
    """{'name','installdir'} da common/config, o {} se assenti."""
    root = entry(appid, path)
    if root is None:
        return {}
    out = {}
    common = _child(root, "common") or []
    name = next((x for a, x in common if a == "name"), None)
    if name:
        out["name"] = name
    cfg = _child(root, "config") or []
    inst = next((x for a, x in cfg if a == "installdir"), None)
    if inst:
        out["installdir"] = inst
    return out


def public_buildid(appid, path=None):
    """buildid del branch public, o None."""
    root = entry(appid, path)
    if root is None:
        return None
    depots_node = _child(root, "depots") or []
    branches = _child(depots_node, "branches")
    if not isinstance(branches, list):
        return None
    public = _child(branches, "public")
    if not isinstance(public, list):
        return None
    buildid = next((x for a, x in public if a == "buildid"), None)
    return buildid if isinstance(buildid, int) else None


def listofdlc(appid, path=None):
    """[dlc_appid, ...] da extended/listofdlc in appinfo.vdf."""
    root = entry(appid, path)
    if not root:
        return []
    ext = _child(root, "extended") or []
    val = next((x for a, x in ext if a == "listofdlc"), "")
    if not val:
        return []
    out = []
    for part in str(val).split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def parent(appid, path=None):
    """Parent appid se questa app è un DLC, altrimenti None."""
    root = entry(appid, path)
    if not root:
        return None
    for sec_name in ("common", "extended"):
        sec = _child(root, sec_name) or []
        val = next((x for a, x in sec if a == "parent"), None)
        if val is not None and str(val).isdigit():
            return int(val)
    return None

