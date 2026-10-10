"""Coda di download multi-gioco con calcolo di velocità (MB/s), ETA e cronologia.
Garantisce che i download avvengano ordinatamente in background senza bloccare la UI.
"""
import os
import time
import json
import threading
from collections import deque
from core import paths, install, config

HISTORY_FILE = os.path.expanduser("~/Library/Application Support/MacLua/queue_history.json")


class DownloadQueue:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def shared(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self, auto_start=True):
        self.queue = deque()
        self.current_job = None
        self.history = self._load_history()
        self.workers_thread = None
        self.running = False
        self.auto_start = auto_start
        self.cancel_requested = set()
        self.listeners = []

    def _load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_history(self):
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        tmp = HISTORY_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.history[-50:], f, indent=2)
        os.replace(tmp, HISTORY_FILE)

    def enqueue(self, appid, name=None):
        with self._lock:
            # Non ri-accodare se già presente
            if any(item["appid"] == appid for item in self.queue):
                return False
            if self.current_job and self.current_job["appid"] == appid:
                return False

            item = {
                "appid": appid,
                "name": name or f"Gioco {appid}",
                "status": "queued",
                "bytes": 0,
                "total_bytes": 0,
                "mb": 0.0,
                "total_mb": 0.0,
                "fraction": 0.0,
                "speed_mbps": 0.0,
                "eta_sec": 0,
                "enqueued_at": time.time(),
                "error": None
            }
            self.queue.append(item)
            if self.auto_start:
                self._start_worker_if_needed()
            return True

    def cancel(self, appid):
        with self._lock:
            self.cancel_requested.add(appid)
            # Rimuovi dalla coda se in attesa
            self.queue = deque([item for item in self.queue if item["appid"] != appid])
            if self.current_job and self.current_job["appid"] == appid:
                self.current_job["status"] = "cancelled"
            return True

    def get_status(self):
        with self._lock:
            return {
                "active": dict(self.current_job) if self.current_job else None,
                "queued": [dict(x) for x in self.queue],
                "history": list(self.history[-10:])
            }

    def _start_worker_if_needed(self):
        if self.workers_thread is None or not self.workers_thread.is_alive():
            self.running = True
            self.workers_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.workers_thread.start()

    def _worker_loop(self):
        while self.running:
            item = None
            with self._lock:
                if self.queue:
                    item = self.queue.popleft()
                    self.current_job = item
                    self.current_job["status"] = "downloading"
                else:
                    self.current_job = None
                    break

            if item:
                self._execute_download(item)

    def _execute_download(self, item):
        appid = item["appid"]
        home = os.path.expanduser("~")
        stplug = paths.stplug_in(home)
        cache_dir = paths.sls_cache(home)
        store_dir = paths.sls_manifests(home)
        steamapps_dir = paths.steamapps(home)

        last_time = [time.time()]
        last_bytes = [0]

        def progress_cb(n):
            if appid in self.cancel_requested:
                raise InterruptedError("Download annullato dall'utente")
            item["bytes"] += n
            now = time.time()
            dt = now - last_time[0]
            if dt >= 0.5:
                db = item["bytes"] - last_bytes[0]
                speed = (db / (1024 * 1024)) / dt if dt > 0 else 0
                item["speed_mbps"] = round(speed, 2)
                item["mb"] = round(item["bytes"] / (1024 * 1024), 1)
                if item["total_bytes"] > 0:
                    item["fraction"] = min(1.0, item["bytes"] / item["total_bytes"])
                    rem_mb = (item["total_bytes"] - item["bytes"]) / (1024 * 1024)
                    item["eta_sec"] = int(rem_mb / speed) if speed > 0 else 0
                last_time[0] = now
                last_bytes[0] = item["bytes"]

        try:
            # Calcolo dimensione totale se nota
            install.fetch_app(
                appid,
                stplug_dir=stplug,
                cache_dir=cache_dir,
                store_dir=store_dir,
                steamapps_dir=steamapps_dir,
                progress=progress_cb,
                workers=8
            )
            item["status"] = "completed"
            item["fraction"] = 1.0
        except InterruptedError:
            item["status"] = "cancelled"
        except Exception as e:
            item["status"] = "failed"
            item["error"] = str(e)
        finally:
            with self._lock:
                item["completed_at"] = time.time()
                self.history.append(dict(item))
                self._save_history()
                if appid in self.cancel_requested:
                    self.cancel_requested.remove(appid)
                self.current_job = None
