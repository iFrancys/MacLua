"""Download chunk da CDN Steam + assemblaggio file con resume.

URL: {base}/depot/<id>/chunk/<sha1hex>, GET semplice senza auth; il token
CDN serve solo dopo 403 e non lo abbiamo, quindi 403 passa all'host dopo.
Ogni chunk è verificato (lunghezza LZMA/Adler) prima della scrittura.
"""
import os

DEFAULT_CDN_BASES = [
    # Rilevato via DepotDownloader -debug anonimo (app gratuita).
    # Aggiornare se muore: stessa procedura, un host SteamCache basta.
    "https://cache10-fra2.steamcontent.com",
]

CHUNK_TIMEOUT = 30

FLAG_DIRECTORY = 64
FLAG_EXECUTABLE = 32
FLAG_SYMLINK = 512


def _norm_path(name):
    parts = name.replace("\\", "/").split("/")
    clean = [p for p in parts if p not in ("", ".")]
    if not clean or any(p == ".." for p in parts):
        raise ValueError("percorso non sicuro %r" % (name,))
    return os.path.join(*clean)


def fetch_chunk(depot, sha20, expect_len, bases, timeout=CHUNK_TIMEOUT,
                retries=3):
    """Scarica un chunk; ruota le basi e riprova i transienti."""
    import time as _time
    import urllib.error
    import urllib.request
    hexid = bytes(sha20).hex()
    last_err = None
    for _ in range(max(1, retries)):
        for base in bases:
            url = "%s/depot/%s/chunk/%s" % (base.rstrip("/"), depot, hexid)
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "Valve/Steam HTTP Client 1.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status != 200:
                        last_err = "%s: HTTP %s" % (base, resp.status)
                        continue
                    data = resp.read()
                if len(data) != expect_len:
                    last_err = "%s: %d != %d byte" % (base, len(data), expect_len)
                    continue
                return data
            except (urllib.error.HTTPError, urllib.error.URLError,
                    TimeoutError, OSError) as e:
                last_err = "%s: %s" % (base, e)
                continue
        _time.sleep(1)
    raise ValueError("chunk %s fallito (%s)" % (hexid, last_err))


def download_file(depot, entry, key, bases, out_root, workers=8, progress=None):
    """Scarica+verifica tutti i chunk di una entry manifest. Ritorna (kind, rel).

    Resume: se il file esiste con size giusta, valida ogni chunk su disco
    (Adler) e riscarica solo i mancati/corrotti.
    """
    import concurrent.futures
    from core.manifest import adler0, decrypt_chunk, decompress_chunk
    rel = _norm_path(entry["name"])
    dest = os.path.join(out_root, rel)
    flags = entry.get("flags", 0)
    if flags & FLAG_DIRECTORY:
        os.makedirs(dest, exist_ok=True)
        return ("dir", rel)
    if flags & FLAG_SYMLINK:
        target = (entry.get("linktarget") or "").replace("\\", "/")
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if os.path.islink(dest) or os.path.exists(dest):
            os.remove(dest)
        os.symlink(target, dest)
        return ("link", rel)
    parent = os.path.dirname(dest)
    if parent:
        os.makedirs(parent, exist_ok=True)
    chunks = entry["chunks"]

    def _get(i):
        c = chunks[i]
        try:
            raw = fetch_chunk(depot, c["sha"], c["cb_compressed"], bases)
        except ValueError as e:
            raise ValueError("fetch chunk %d di %s: %s" % (i, rel, e))
        try:
            dec = decrypt_chunk(raw, key)
        except ValueError as e:
            raise ValueError("decrypt chunk %d di %s: %s" % (i, rel, e))
        try:
            plain = decompress_chunk(dec)
        except ValueError as e:
            raise ValueError("decompress chunk %d di %s: %s" % (i, rel, e))
        if len(plain) != c["cb_original"]:
            raise ValueError("chunk %d di %s: %d != %d byte"
                             % (i, rel, len(plain), c["cb_original"]))
        if adler0(plain) != c["crc"]:
            raise ValueError("checksum chunk %d di %s" % (i, rel))
        return c["offset"], plain

    needed = list(range(len(chunks)))
    sized_ok = os.path.exists(dest) and os.path.getsize(dest) == entry["size"]
    if sized_ok:
        try:
            with open(dest, "rb") as f:
                present = f.read()
            needed = []
            for i, c in enumerate(chunks):
                seg = present[c["offset"]:c["offset"] + c["cb_original"]]
                if len(seg) != c["cb_original"] or adler0(seg) != c["crc"]:
                    needed.append(i)
        except OSError:
            needed = list(range(len(chunks)))
    if not needed:
        if progress:
            progress(entry["size"])
        if flags & FLAG_EXECUTABLE:
            os.chmod(dest, 0o755)
        return ("file", rel)

    with open(dest, "r+b" if sized_ok else "wb") as f:
        if not sized_ok:
            f.truncate(entry["size"])
        if len(needed) == 1:
            off, data = _get(needed[0])
            f.seek(off)
            f.write(data)
            if progress:
                progress(len(data))
        else:
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=max(1, workers)) as ex:
                futs = {ex.submit(_get, i): i for i in needed}
                results = {}
                for fut in concurrent.futures.as_completed(futs):
                    off, data = fut.result()
                    results[off] = data
                    if progress:
                        progress(len(data))
                for off in sorted(results):
                    f.seek(off)
                    f.write(results[off])
    if flags & FLAG_EXECUTABLE:
        os.chmod(dest, 0o755)
    return ("file", rel)
