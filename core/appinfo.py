"""Reads app entries from appcache/appinfo.vdf (binary VDF with numeric keys)."""
import os
import struct

from core import paths

_HEADER = 8
_ANCHOR = b"\x02\x01\x00\x00\x00"  # i32 node with key index 1 == "appid"


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
            raise ValueError("unexpected VDF type 0x%02x at 0x%x" % (t, off - 1))
    return out, off


_CACHE = {}


def _get_cache(path):
    if not os.path.exists(path):
        return None
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None

    entry_data = _CACHE.get(path)
    if entry_data and entry_data["mtime"] == mtime:
        return entry_data

    try:
        with open(path, "rb") as f:
            d = f.read()
    except OSError:
        return None

    names = _string_table(d)
    anchors = []
    i = 0
    while True:
        i = d.find(_ANCHOR, i)
        if i < 0:
            break
        anchors.append(i)
        i += 1

    index = {}
    for k, a in enumerate(anchors):
        if a + 9 <= len(d):
            aid = struct.unpack_from("<I", d, a + 5)[0]
            start = a - 5
            end = anchors[k + 1] - 5 if k + 1 < len(anchors) else len(d)
            index[aid] = (start, end)

    cached = {
        "mtime": mtime,
        "data": d,
        "names": names,
        "index": index,
        "parsed": {}
    }
    _CACHE[path] = cached
    return cached


def entry(appid, path=None):
    """Child branch of 'appinfo', or None if app is not cached (with mtime I/O cache)."""
    path = path or os.path.join(paths.appcache(), "appinfo.vdf")
    c = _get_cache(path)
    if not c:
        return None
    if appid in c["parsed"]:
        return c["parsed"][appid]
    span = c["index"].get(appid)
    if span is None:
        return None
    tree, _ = _parse(c["data"], c["names"], span[0], span[1])
    if not tree or tree[0][0] != "appinfo":
        c["parsed"][appid] = None
        return None
    res = tree[0][1]
    c["parsed"][appid] = res
    return res


def appinfo_of(appid, path=None):
    """Metadata dictionary for appid (extended, common, etc.)."""
    root = entry(appid, path)
    if not root:
        return {}

    def _convert(nodes):
        res = {}
        for k, v in nodes:
            if isinstance(v, list):
                res[k] = _convert(v)
            else:
                res[k] = v
        return res

    return _convert(root)



def _child(nodes, name):
    for k, v in nodes:
        if k == name:
            return v
    return None


def depots(appid, path=None):
    """[{id, oslist, gid, size, shared}] for public depots of the app."""
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
    """{'name','installdir'} from common/config, or {} if missing."""
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
    """buildid for public branch, or None."""
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
    """[dlc_appid, ...] from extended/listofdlc in appinfo.vdf."""
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
    """Parent appid if this app is a DLC, else None."""
    root = entry(appid, path)
    if not root:
        return None
    for sec_name in ("common", "extended"):
        sec = _child(root, sec_name) or []
        val = next((x for a, x in sec if a == "parent"), None)
        if val is not None and str(val).isdigit():
            return int(val)
    return None


