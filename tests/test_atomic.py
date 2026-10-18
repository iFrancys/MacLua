"""Scritture atomiche e lock inter-processo: prova diretta del bug 'Nessuna licenza'.

Il bug storico: più processi `ensure` scrivevano lo stesso file con un
temporaneo a nome fisso (`file.tmp` condiviso). Il rename di uno falliva
(ENOENT, visto in /tmp/maclua-ensure.log) oppure l'altro rinomina un file
scritto a metà -> packageinfo.vdf parziale -> licenze perse.
"""
import os
import stat
import subprocess
import sys

from core.atomic import FileLock, atomic_write

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_atomic_write_applies_mode(tmp_path):
    p = tmp_path / "f.bin"
    atomic_write(str(p), b"ciao", mode=0o600)
    assert p.read_bytes() == b"ciao"
    assert stat.S_IMODE(os.stat(str(p)).st_mode) == 0o600


def test_atomic_write_str_and_bytes(tmp_path):
    p = tmp_path / "f.txt"
    atomic_write(str(p), "testo")
    assert p.read_text(encoding="utf-8") == "testo"
    atomic_write(str(p), b"bytes")
    assert p.read_bytes() == b"bytes"


def test_atomic_write_leaves_no_temp_files(tmp_path):
    p = tmp_path / "f.bin"
    atomic_write(str(p), b"x" * 100)
    leftovers = [fn for fn in os.listdir(str(tmp_path)) if fn != "f.bin"]
    assert leftovers == []


def test_atomic_write_concurrent_processes_never_corrupt(tmp_path):
    """N processi scrivono lo stesso file in parallelo: il contenuto finale
    deve essere ESATTAMENTE uno dei payload completi, mai un misto o troncato."""
    target = str(tmp_path / "packageinfo.vdf")
    payload_a = "A" * 200000
    payload_b = "B" * 200000
    code = (
        "import sys; sys.path.insert(0, sys.argv[3]);"
        "from core.atomic import atomic_write;"
        "payload = sys.argv[2] * 200000;"
        "atomic_write(sys.argv[1], payload)"
    )
    procs = []
    for _ in range(6):
        for payload in (payload_a[:1], payload_b[:1]):
            procs.append(subprocess.Popen(
                [sys.executable, "-c", code, target, payload, REPO_ROOT],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    errors = []
    for p in procs:
        _, err = p.communicate(timeout=60)
        if p.returncode != 0:
            errors.append(err.decode("utf-8", "replace"))
    assert errors == [], errors
    final = open(target).read()
    assert final == payload_a or final == payload_b


def test_file_lock_excludes_concurrent_acquirers(tmp_path):
    lock_path = str(tmp_path / "ensure.lock")
    lk1 = FileLock(lock_path)
    lk2 = FileLock(lock_path)
    assert lk1.acquire(timeout=0.1) is True
    try:
        # flock è per descrittore: anche nello stesso processo il secondo
        # tentativo sullo stesso file resta escluso.
        assert lk2.acquire(timeout=0.3) is False
    finally:
        lk1.release()
    assert lk2.acquire(timeout=0.3) is True
    lk2.release()


def test_file_lock_release_allows_reacquire(tmp_path):
    lock_path = str(tmp_path / "ensure.lock")
    lk = FileLock(lock_path)
    assert lk.acquire(timeout=0.1) is True
    lk.release()
    assert lk.acquire(timeout=0.1) is True
    lk.release()
