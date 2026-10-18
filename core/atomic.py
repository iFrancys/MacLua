"""Scritture atomiche sicure in caso di concorrenza + lock inter-processo.

Perché esiste questo modulo: MacLua esegue `ensure` da più punti in parallelo
(LaunchAgent `com.maclua.ensure`, sentinella del bridge, richieste RPC, CLI).
Con file temporanei a nome fisso due processi che scrivono lo stesso file
collidono: il rename di uno fallisce (ENOENT) o, peggio, l'altro rinomina un
file temporaneo scritto a metà, lasciando il file di destinazione corrotto.
Un `packageinfo.vdf` parziale = "Nessuna licenza" nel client Steam.

Regole:
- ogni scrittura passa da `atomic_write`: file temporaneo UNICO per processo
  (tempfile.mkstemp), fsync, `os.replace` atomico;
- le sezioni che non vanno eseguite in parallelo passano da `FileLock`
  (fcntl.flock, rilasciato automaticamente alla morte del processo).
"""
import errno
import fcntl
import os
import tempfile
import time


def atomic_write(path, data, mode=None):
    """Scrive `data` (bytes o str) su `path` in modo atomico.

    - il temporaneo è creato nella stessa directory di destinazione (rename
      atomico sullo stesso filesystem) con nome univoco per processo;
    - `os.replace` garantisce che i lettori vedano sempre o il vecchio o il
      nuovo contenuto completo, mai un parziale;
    - con `mode` i permessi vengono applicati al file prima della sostituzione.
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
    """Lock esclusivo inter-processo basato su fcntl.flock.

    Il lock è legato al descrittore aperto: si serializza anche tra thread
    dello stesso processo e viene rilasciato dal kernel se il processo muore,
    senza file di stato da pulire a mano.
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
