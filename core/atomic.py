"""Atomic writes safe under concurrency + inter-process file locking.

Why this module exists: MacLua runs `ensure` concurrently from multiple points
(LaunchAgent `com.maclua.ensure`, bridge watchdog, RPC requests, CLI).
With fixed temporary filenames, two processes writing to the same file collide:
one rename fails (ENOENT) or, worse, one renames a half-written temporary file,
leaving the destination file corrupted.
A partial `packageinfo.vdf` = "No licenses" in the Steam client.

Rules:
- every write goes through `atomic_write`: UNIQUE per-process temporary file
  (tempfile.mkstemp), fsync, atomic `os.replace`;
- sections that must not run concurrently use `FileLock`
  (fcntl.flock, automatically released if the process terminates).
"""
import errno
import fcntl
import os
import tempfile
import time


def atomic_write(path, data, mode=None):
    """Writes `data` (bytes or str) to `path` atomically.

    - temporary file is created in the same destination directory (atomic rename
      on the same filesystem) with a unique per-process name;
    - `os.replace` guarantees readers see either the old or new complete content,
      never partial bytes;
    - optional `mode` permissions are applied before replacing.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent,
                               prefix="." + os.path.basename(path) + ".",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


class FileLock:
    """Exclusive inter-process lock based on fcntl.flock.

    The lock is tied to the open file descriptor: it serializes threads within
    the same process and is automatically released by the kernel if the process
    dies, without leaving stale lockfiles requiring manual cleanup.
    """

    def __init__(self, path):
        self.path = path
        self._fd = None

    def acquire(self, timeout=10.0):
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fd = fd
                return True
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                    os.close(fd)
                    raise
                if timeout <= 0 or time.monotonic() >= deadline:
                    os.close(fd)
                    return False
                time.sleep(0.1)

    def release(self):
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
