"""GitHub release discovery and verified staging for the Windows portable updater."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

from app_paths import APP_DIR, FROZEN, RESOURCES, data_directory
from app_version import VERSION

REPOSITORY = "technicallyalex/Sortrr"
ASSET_NAME = "Sortrr-Windows-x64.zip"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=100"
MANAGED = ("Sortrr.exe", "_internal", "licenses", "Read me.txt", "version.json")
MAX_DOWNLOAD = 1024**3
MAX_EXPANDED = 4 * 1024**3


def version_key(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?", value)
    if not match or len(value) > 64:
        raise ValueError("Unrecognized release version.")
    major, minor, patch, stage, number = match.groups()
    return (int(major), int(minor), int(patch),
            {"alpha": 0, "beta": 1, "rc": 2, None: 3}[stage], int(number or 0))


class ReleaseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com",
            "github-releases.githubusercontent.com",
        }:
            raise ValueError("The update download redirected to an unexpected location.")
        return super().redirect_request(request, response, code, message, headers, url)


def open_url(url, accept="application/vnd.github+json"):
    request = urllib.request.Request(url, headers={
        "User-Agent": f"Sortrr/{VERSION}", "Accept": accept,
    })
    return urllib.request.build_opener(ReleaseRedirects()).open(request, timeout=30)


def select_release(releases, current=VERSION):
    installed = version_key(current)
    candidates = []
    for release in releases:
        try:
            key = version_key(release.get("tag_name", ""))
        except (ValueError, TypeError):
            continue
        if release.get("draft") or key <= installed:
            continue
        if installed[3] == 3 and (release.get("prerelease") or key[3] < 3):
            continue
        candidates.append((key, release))
    if not candidates:
        return None
    _, release = max(candidates, key=lambda pair: pair[0])
    tag = release["tag_name"]
    expected = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{ASSET_NAME}"
    asset = next((asset for asset in release.get("assets", []) if asset.get("name") == ASSET_NAME), None)
    if not asset or asset.get("state") != "uploaded" or asset.get("browser_download_url") != expected:
        raise ValueError("The newest release does not have a Windows update package ready.")
    digest = asset.get("digest", "")
    size = asset.get("size")
    if not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest or ""):
        raise ValueError("The update is missing its verification checksum. Try checking again later.")
    if type(size) is not int or not 0 < size <= MAX_DOWNLOAD:
        raise ValueError("The Windows update package has an invalid size.")
    return {"version": tag.lstrip("v"), "url": expected, "size": size,
            "sha256": digest[7:].lower()}


def check_updates():
    with open_url(RELEASES_API) as response:
        raw = response.read(5 * 1024**2 + 1)
    if len(raw) > 5 * 1024**2:
        raise ValueError("GitHub returned too much update information.")
    releases = json.loads(raw)
    if not isinstance(releases, list):
        raise ValueError("GitHub did not return a release list.")
    return select_release(releases)


def extract_package(archive, stage, version):
    stage = Path(stage).resolve()
    seen = set()
    total = 0
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) > 30000:
            raise ValueError("The update contains too many files.")
        for entry in entries:
            name = entry.filename.rstrip("/")
            parts = name.split("/")
            mode = entry.external_attr >> 16
            if (not parts or parts[0] != "Sortrr" or "\\" in name or ":" in name
                    or any(part in {"", ".", ".."} or part.endswith((" ", "."))
                           or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)
                           for part in parts)
                    or stat.S_ISLNK(mode) or entry.external_attr & 0x400):
                raise ValueError("The update contains an unsafe path or link.")
            if len(parts) > 1 and parts[1] not in MANAGED:
                raise ValueError("The update contains unexpected top-level files.")
            key = name.casefold()
            if key in seen:
                raise ValueError("The update contains duplicate paths.")
            seen.add(key)
            total += entry.file_size
            if total > MAX_EXPANDED:
                raise ValueError("The update is too large to extract.")
            target = stage.joinpath(*parts)
            if not target.resolve().is_relative_to(stage):
                raise ValueError("The update contains an unsafe path.")
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(entry) as source, target.open("xb") as destination:
                    shutil.copyfileobj(source, destination, 1024**2)
    package = stage / "Sortrr"
    if (not (package / "Sortrr.exe").is_file() or not (package / "_internal").is_dir()
            or not list((package / "_internal").glob("python3*.dll"))):
        raise ValueError("The download is not a complete Sortrr Windows package.")
    marker = package / "version.json"
    if marker.is_file() and json.loads(marker.read_text(encoding="utf-8")) != {"version": version}:
        raise ValueError("The package version does not match the selected release.")
    return package


def stage_update(release, install=APP_DIR, progress=lambda done, total: None):
    install = Path(install).resolve()
    if install == Path(install.anchor) or not (install / "Sortrr.exe").is_file():
        raise ValueError("Choose an extracted Sortrr Windows app to update.")
    data = data_directory().resolve()
    if any(data == install / name or data.is_relative_to(install / name) for name in MANAGED):
        raise ValueError("Move Sortrr's data folder outside its application files before updating.")
    stage = Path(tempfile.mkdtemp(prefix=".sortrr-update-", dir=install.parent)).resolve()
    if stage.parent != install.parent or not stage.name.startswith(".sortrr-update-"):
        raise ValueError("The update staging folder is outside the installation directory.")
    try:
        archive = stage / ASSET_NAME
        checksum = hashlib.sha256()
        size = 0
        with open_url(release["url"], "application/octet-stream") as response, archive.open("xb") as out:
            while chunk := response.read(1024**2):
                size += len(chunk)
                if size > release["size"]:
                    raise ValueError("The downloaded update is larger than expected.")
                checksum.update(chunk)
                out.write(chunk)
                progress(size, release["size"])
            out.flush()
            os.fsync(out.fileno())
        if size != release["size"] or checksum.hexdigest() != release["sha256"]:
            raise ValueError("Update verification failed. The installed app has been kept in place.")
        package = extract_package(archive, stage, release["version"])
        script = stage / "install-update.ps1"
        shutil.copyfile(RESOURCES / "packaging" / "install_update.ps1", script)
        manifest = stage / "install.json"
        manifest.write_text(json.dumps({
            "install": str(install), "package": str(package), "pid": os.getpid(),
            "version": release["version"],
        }), encoding="utf-8")
        return manifest
    except Exception:
        shutil.rmtree(stage)
        raise


def launch_installer(manifest):
    if os.name != "nt" or not FROZEN:
        raise ValueError("Automatic installation is available in the packaged Windows app.")
    windows = Path(os.environ["SYSTEMROOT"])
    powershell = windows / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("_PYI", "_MEI", "PYINSTALLER"))}
    process = subprocess.Popen([
        str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-WindowStyle", "Hidden", "-File", str(Path(manifest).parent / "install-update.ps1"),
        "-Manifest", str(manifest),
    ], cwd=Path(manifest).parent, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    ready = Path(manifest).parent / "ready"
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline and process.poll() is None:
        if ready.is_file():
            return process
        time.sleep(.05)
    if ready.is_file() and process.poll() is None:
        return process
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=5)
    raise RuntimeError("The installer could not start. Sortrr is still open. Try checking for updates again.")
