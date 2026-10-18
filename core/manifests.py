"""Manifest staging: SLSsteam/manifests/*.manifest -> Steam/depotcache/.

Only <depot>_<gid>.manifest filenames (strictly numeric); nothing else is
copied. Idempotent based on matching file size (manifests are immutable by gid).
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
    """Returns (copied, already_present) as lists of filenames."""
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
