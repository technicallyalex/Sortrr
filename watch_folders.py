"""Persistent, non-destructive watch-folder discovery and background identification."""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer
import core


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def inventory(root, excluded=()):
    """Reconcile recursively, including changes missed while the app was closed."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise OSError("Folder unavailable")
    excluded = [Path(p).resolve() for p in excluded if p]
    found = {}
    def ignored(path):
        return any(path == p or path.is_relative_to(p) for p in excluded)
    def fail(error):
        raise error
    for directory, folders, files in os.walk(root, followlinks=False, onerror=fail):
        directory = Path(directory)
        folders[:] = [name for name in folders
                      if not name.startswith(".sortrr") and not core.is_link(directory / name)
                      and not ignored(directory / name)]
        for name in files:
            path = directory / name
            if path.suffix.lower() not in core.VIDEO or core.is_link(path) or ignored(path):
                continue
            if any(token in name.lower() for token in (".part.", ".partial.", ".tmp.")):
                continue
            try:
                stat = path.stat()
                if stat.st_size > 0:
                    found[str(path)] = [stat.st_size, stat.st_mtime_ns]
            except OSError:
                continue
    return found


class StableIndex:
    def __init__(self, seen=None, quiet_seconds=60):
        self.seen = dict(seen or {})
        self.observed = {}
        self.quiet_seconds = quiet_seconds

    def ready(self, snapshot, now, wall_time, scope=None):
        ready = []
        for path, signature in snapshot.items():
            if self.seen.get(path) == signature:
                self.observed.pop(path, None)
                continue
            previous = self.observed.get(path)
            if previous is None or previous[0] != signature:
                self.observed[path] = (signature, now)
                continue
            if now - previous[1] >= self.quiet_seconds and wall_time - signature[1] / 1e9 >= self.quiet_seconds:
                ready.append(path)
        # Each root is reconciled separately. Retain stability timers for
        # other roots rather than restarting them on every polling pass.
        self.observed = {p: value for p, value in self.observed.items()
                         if p in snapshot or (scope is not None
                         and not Path(p).is_relative_to(Path(scope)))}
        return ready

    def acknowledge(self, path, signature):
        self.seen[path] = signature
        self.observed.pop(path, None)


def folder_counts(pending, activity):
    """Keep the review inbox distinct from files still waiting or scanning."""
    pending = set(pending)
    if "present" in activity:
        pending.intersection_update(activity["present"])
    ready = pending.difference(activity.get("unprocessed", ())) | set(activity.get("completed", []))
    return dict(waiting=activity.get("waiting", 0), queued=activity.get("queued", 0),
                scanning=activity.get("scanning", 0), readyToReview=len(ready), pending=len(ready))


class WatchFolders(QObject):
    changed = Signal()
    notification = Signal(str, str)
    completed = Signal(object)
    progress = Signal(str, object)

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = Path(data)
        self.config_path = self.data / "watch-folders.json"
        self.state_path = self.data / "watch-index.json"
        self.config = {"folders": [], "background": False, "launch_in_tray": False, "notifications": True, "paused": False}
        self.message = ""
        self.busy = False
        self.closed = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sortrr-watch")
        try:
            saved = json.loads(self.config_path.read_text(encoding="utf-8"))
            self.config.update({key: saved[key] for key in self.config if key in saved})
            self.config["folders"] = [row for row in self.config["folders"]
                                      if isinstance(row, dict) and isinstance(row.get("path"), str)]
        except (OSError, ValueError, TypeError):
            pass
        if not isinstance(self.config.get("folders"), list):
            self.config["folders"] = []
        for name in ("background", "launch_in_tray", "notifications", "paused"):
            self.config[name] = self.config[name] is True
        for row in self.config["folders"]:
            row["enabled"] = row.get("enabled", True) is True
            row["pending_files"] = [p for p in row.get("pending_files", []) if isinstance(p, str)] if isinstance(row.get("pending_files", []), list) else []
            row["pending"] = len(row["pending_files"])
        try:
            seen = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            seen = {}
        self.index = StableIndex(seen if isinstance(seen, dict) else {})
        self.statuses = {}
        self.activity = {}
        self.exclusions = lambda: []
        self.blocked = lambda: False
        self.completed.connect(self.finish)
        self.progress.connect(self.set_status)
        self.timer = QTimer(self)
        self.timer.setInterval(15000)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    def save(self):
        atomic_json(self.config_path, self.config)

    def state(self):
        return dict(self.config, busy=self.busy, message=self.message, folders=[
            dict(row, status=self.statuses.get(row["path"],
                 "Watching" if row.get("enabled", True) else "Paused"),
                 **folder_counts(row.get("pending_files", []), self.activity.get(row["path"], {})))
                 for row in self.config["folders"]])

    def add(self, path):
        root = Path(path).expanduser().resolve()
        if not root.is_dir() or core.is_link(root):
            raise ValueError("Choose an existing folder, not a link.")
        for row in self.config["folders"]:
            other = Path(row["path"])
            if root == other or root.is_relative_to(other) or other.is_relative_to(root):
                raise ValueError("This folder overlaps an existing watch folder.")
        self.config["folders"].append({"path": str(root), "enabled": True, "pending": 0})
        self.save()
        self.changed.emit()
        self.poll()

    def remove(self, path):
        self.config["folders"] = [r for r in self.config["folders"] if r["path"] != path]
        self.save()
        self.changed.emit()

    def option(self, name, value):
        if name not in {"background", "notifications", "paused"}:
            return
        self.config[name] = bool(value)
        if name == "background" and not value:
            self.config["launch_in_tray"] = False
        self.save()
        self.changed.emit()
        if name == "paused" and not value:
            self.poll()

    def enable(self, path, enabled):
        for row in self.config["folders"]:
            if row["path"] == path:
                row["enabled"] = bool(enabled)
                self.statuses.pop(path, None)
        self.save()
        self.changed.emit()
        if enabled:
            self.poll()

    def reviewed(self, path):
        for row in self.config["folders"]:
            if row["path"] == path:
                row["pending"] = 0
                row["pending_files"] = []
        self.save()
        self.changed.emit()

    def set_status(self, path, text):
        if self.closed.is_set():
            return
        if isinstance(text, dict):
            self.statuses[path] = text["status"]
            self.activity[path] = {key: value for key, value in text.items() if key != "status"}
        else:
            self.statuses[path] = text
        self.changed.emit()

    def poll(self):
        if self.closed.is_set() or self.busy or self.config["paused"] or self.blocked():
            return
        folders = [dict(row) for row in self.config["folders"] if row.get("enabled", True)]
        if not folders:
            return
        exclusions = self.exclusions()
        self.busy = True
        self.changed.emit()
        def job():
            result = []
            for row in folders:
                if self.closed.is_set():
                    break
                root = row["path"]
                try:
                    self.progress.emit(root, "Checking for new or changed media...")
                    snapshot = inventory(root, exclusions)
                    ready = self.index.ready(snapshot, time.monotonic(), time.time(), scope=root)
                    paths = ready[:32]
                    unprocessed = frozenset(p for p, sig in snapshot.items() if self.index.seen.get(p) != sig)
                    present = frozenset(snapshot)
                    waiting = len(unprocessed) - len(ready)
                    active, started, completed = set(), set(), set()
                    def publish(status):
                        self.progress.emit(root, dict(status=status, waiting=waiting,
                            queued=len(ready) - len(started), scanning=len(active),
                            completed=tuple(completed), unprocessed=unprocessed, present=present))
                    if not paths:
                        status = "Waiting for files to settle" if waiting else "Watching"
                        publish(status)
                        result.append((root, [], status))
                        continue
                    media = []
                    for path in paths:
                        try:
                            media.append(core.parse(Path(path)))
                        except OSError:
                            pass
                    publish("Scanning new or updated files")
                    lock = threading.Lock()
                    def began(uid):
                        with lock:
                            path = str(media[uid].source)
                            active.add(path)
                            started.add(path)
                            publish("Scanning new or updated files")
                    def report(uid, item):
                        nonlocal waiting
                        with lock:
                            path = str(item.source)
                            active.discard(path)
                            try:
                                stat = item.source.stat()
                                if [stat.st_size, stat.st_mtime_ns] == snapshot[path]:
                                    completed.add(path)
                                else:
                                    waiting += 1
                            except OSError:
                                pass
                            publish("Scanned: " + item.source.name)
                    closing = self.closed
                    class CancellableCatalog(core.Catalog):
                        def identify(self, item):
                            if closing.is_set():
                                raise InterruptedError("Background scan stopped")
                            return super().identify(item)
                    core.identify_batch(enumerate(media), CancellableCatalog(), core.History(),
                                        started=began, report=report, finish_scan_on_setup=True)
                    if self.closed.is_set():
                        break
                    previous_seen = dict(self.index.seen)
                    accepted = []
                    for item in media:
                        try:
                            stat = item.source.stat()
                            signature = [stat.st_size, stat.st_mtime_ns]
                            if signature == snapshot[str(item.source)]:
                                self.index.acknowledge(str(item.source), signature)
                                accepted.append(str(item.source))
                        except OSError:
                            pass
                    try:
                        atomic_json(self.state_path, self.index.seen)
                    except OSError:
                        self.index.seen = previous_seen
                        raise
                    unprocessed = unprocessed.difference(accepted)
                    completed.intersection_update(accepted)
                    active.clear()
                    status = ("Waiting for files to settle" if waiting else
                              "Files queued for scanning" if len(ready) > len(started) else "Watching")
                    publish(status)
                    result.append((root, accepted, status))
                except Exception as exc:
                    status = "Could not check folder: " + str(exc)
                    self.progress.emit(root, dict(status=status, waiting=0, queued=0,
                        scanning=0, completed=[], unprocessed=[]))
                    result.append((root, [], status))
            return result
        future = self.pool.submit(job)
        def finished(future):
            try:
                result = future.result()
            except Exception as exc:
                result = [("", 0, "Watch scan failed: " + str(exc))]
            if not self.closed.is_set():
                self.completed.emit(result)
        future.add_done_callback(finished)

    def finish(self, result):
        self.busy = False
        for path, paths, status in result:
            row = next((r for r in self.config["folders"] if r["path"] == path), None)
            if row is None:
                continue
            self.statuses[path] = status
            self.activity.get(path, {}).update(completed=())
            if paths:
                row["pending_files"] = sorted(set(row.get("pending_files", [])) | set(paths))
                row["pending"] = len(row["pending_files"])
                self.notification.emit(path, f"{len(paths)} new or updated media files scanned. Open Sortrr to review matches.")
        try:
            self.save()
        except OSError as exc:
            self.message = "Could not save watch settings: " + str(exc)
        self.changed.emit()

    def close(self):
        self.closed.set()
        self.timer.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
