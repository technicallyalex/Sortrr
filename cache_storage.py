"""Storage and relocation for disposable artwork, previews, and API responses."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

CATEGORIES = ("cache", "posters", "previews")


def root(data):
    data = Path(data).resolve()
    try:
        location = json.loads((data / "cache-location.json").read_text(encoding="utf-8"))
        if isinstance(location, str) and Path(location).is_absolute():
            return Path(location).resolve()
    except (OSError, ValueError, TypeError):
        pass
    return data


def is_link(path):
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def inventory(location):
    location = Path(location).resolve()
    files = []
    def onerror(error):
        raise error
    for category in CATEGORIES:
        directory = location / category
        if is_link(directory):
            raise ValueError("Cache folders must not be links or junctions.")
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise ValueError(f"The cache path is not a folder: {directory}")
        for folder, dirs, names in os.walk(directory, followlinks=False, onerror=onerror):
            folder = Path(folder)
            if any(is_link(folder / name) for name in dirs):
                raise ValueError("A cache folder contains a link or junction.")
            for name in names:
                path = folder / name
                if is_link(path):
                    raise ValueError("A cache file is a link.")
                stat = path.stat()
                files.append((path, stat.st_size, stat.st_mtime_ns))
    return files


def measure(location):
    files = inventory(location)
    return sum(size for _, size, _ in files), len(files)


def format_size(size):
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def checksum(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").digest()


def save_location(data, location):
    data = Path(data)
    data.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=data, delete=False) as file:
        temporary = Path(file.name)
        json.dump(str(location), file)
        file.flush()
        os.fsync(file.fileno())
    try:
        os.replace(temporary, data / "cache-location.json")
    finally:
        temporary.unlink(missing_ok=True)


def remove_empty_tree(directory):
    for folder, dirs, files in os.walk(directory, topdown=False, followlinks=False):
        try:
            Path(folder).rmdir()
        except OSError:
            pass


def relocate(data, destination, progress=lambda done, total: None):
    data = Path(data).resolve()
    source = root(data)
    destination = Path(destination).expanduser().absolute()
    if is_link(destination):
        raise ValueError("Choose a cache folder that is not a link or junction.")
    destination = destination.resolve()
    if source == destination:
        return 0
    if destination == Path(destination.anchor) or (destination != data and data.is_relative_to(destination)):
        raise ValueError("Choose a dedicated cache folder.")
    for old in (source / category for category in CATEGORIES):
        for new in (destination / category for category in CATEGORIES):
            if old == new or old.is_relative_to(new) or new.is_relative_to(old):
                raise ValueError("The new folder overlaps the current cache.")
    destination.mkdir(parents=True, exist_ok=True)
    for category in CATEGORIES:
        path = destination / category
        if path.exists() or is_link(path):
            if is_link(path) or not path.is_dir() or any(path.iterdir()):
                raise ValueError("The destination already contains cache files. Choose an empty cache folder.")
    files = inventory(source)
    total = sum(size for _, size, _ in files)
    stage = Path(tempfile.mkdtemp(prefix=".sortrr-cache-move-", dir=destination)).resolve()
    if stage.parent != destination or not stage.name.startswith(".sortrr-cache-move-"):
        raise ValueError("The cache staging path is outside the destination.")
    committed = False
    published = []
    try:
        for category in CATEGORIES:
            (stage / category).mkdir()
        copied = []
        done = 0
        for path, size, mtime in files:
            current = path.stat()
            if (current.st_size, current.st_mtime_ns) != (size, mtime):
                raise ValueError("The cache changed during the move. Try again.")
            target = stage / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            digest = checksum(path)
            if checksum(target) != digest or (path.stat().st_size, path.stat().st_mtime_ns) != (size, mtime):
                raise ValueError("A cache file changed during verification. Try again.")
            copied.append((path, size, mtime, digest))
            done += size
            progress(done, total)
        for category in CATEGORIES:
            target = destination / category
            if target.exists():
                target.rmdir()
            (stage / category).rename(target)
            published.append(target)
        save_location(data, destination)
        committed = True
        remaining = 0
        for path, size, mtime, digest in copied:
            try:
                stat = path.stat()
                if (stat.st_size, stat.st_mtime_ns) == (size, mtime) and checksum(path) == digest:
                    path.unlink()
                else:
                    remaining += 1
            except OSError:
                remaining += 1
        for category in CATEGORIES:
            remove_empty_tree(source / category)
        return remaining
    finally:
        # Only generated staging folders and cache category trees are removed here.
        if not committed:
            for target in published:
                if target.parent == destination and target.name in CATEGORIES and not is_link(target):
                    shutil.rmtree(target)
        if stage.parent == destination and stage.name.startswith(".sortrr-cache-move-"):
            shutil.rmtree(stage)


def clear(location):
    location = Path(location).resolve()
    # Validate every entry before any recursive removal.
    inventory(location)
    for category in CATEGORIES:
        path = location / category
        if path.parent != location or path.name not in CATEGORIES or is_link(path):
            raise ValueError("Invalid cache path.")
        if path.exists():
            shutil.rmtree(path)
