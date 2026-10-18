"""Atomic writes and inter-process locking: direct proof for the 'No license' bug.

Historical bug: multiple concurrent `ensure` runs wrote to the same file using
a fixed temporary file name (shared `file.tmp`). Renaming one failed
(ENOENT in /tmp/maclua-ensure.log) or another process renamed a half-written file
leading to partial packageinfo.vdf and lost licenses.
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
    """N processes write the same file concurrently: the final content
    must be EXACTLY one of the complete payloads, never interleaved or truncated."""
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
        # flock is per file-descriptor: even within the same process a second
        # attempt on the same file remains excluded.
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
