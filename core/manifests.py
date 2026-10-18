"""Staging manifest: SLSsteam/manifests/*.manifest -> Steam/depotcache/.

Solo nomi <depot>_<gid>.manifest (tutto numerico); nient'altro viene
copiato. Idempotente a parità di size (i manifest sono immutabili per gid).
"""
import os

from core.atomic import atomic_write


def valid_name(name):
    if not name.endswith(".manifest"):
        return False
    stem = name[:-9]
    depot, sep, gid = stem.partition("_")
    return bool(sep) and depot.isdigit() and gid.isdigit()


def stage_all(src_dir, dst_dir):
    """Ritorna (copiati, già_presenti) come liste di nomi file."""
    try:
        names = sorted(os.listdir(src_dir))
    except OSError:
        return [], []
    os.makedirs(dst_dir, exist_ok=True)
    copied, present = [], []
    for fn in names:
        if not valid_name(fn):
            continue
        src = os.path.join(src_dir, fn)
        dst = os.path.join(dst_dir, fn)
        try:
            if (os.path.exists(dst)
                    and os.path.getsize(dst) == os.path.getsize(src)):
                present.append(fn)
                continue
            with open(src, "rb") as f:
                data = f.read()
            atomic_write(dst, data, mode=0o644)
            copied.append(fn)
        except OSError:
            continue
    return copied, present
