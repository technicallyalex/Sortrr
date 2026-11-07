"""Build the portable Windows x64 release from the project checkout."""
import argparse
import importlib.metadata
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build" / "windows"


def checked_output_path(path):
    if path.resolve() != path or not path.is_relative_to(ROOT):
        raise SystemExit(f"Build output must remain inside {ROOT}: {path}")


def build(dist):
    package = dist / "Sortrr"
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"} or sys.maxsize <= 2**32:
        raise SystemExit("Use 64-bit Python on Windows to build the x64 release.")
    for path in (dist, BUILD, BUILD / "work", BUILD / "cache", package, dist / "Sortrr-Windows-x64.zip"):
        checked_output_path(path)
    tools = []
    for name in ("ffmpeg", "ffprobe"):
        location = shutil.which(name)
        if not location:
            raise SystemExit(f"{name}.exe must be available on the build machine's PATH.")
        tools.append(Path(location).resolve())
    ffmpeg_root = tools[0].parent.parent
    if tools[0].parent != tools[1].parent or not all((ffmpeg_root / name).is_file() for name in ("LICENSE", "README.txt")):
        raise SystemExit("Build with FFmpeg and ffprobe from the same Windows distribution, with its LICENSE and README.txt.")
    BUILD.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "Sortrr", "--icon", str(ROOT / "ui" / "assets" / "sortrr.ico"),
        "--distpath", str(dist), "--workpath", str(BUILD / "work"),
        "--specpath", str(BUILD), "--hidden-import", "PySide6.QtQuick",
        "--additional-hooks-dir", str(ROOT / "packaging" / "hooks"),
        "--add-data", f"{ROOT / 'ui'}:ui",
    ]
    for tool in tools:
        command.extend(("--add-data", f"{tool}:tools"))
    # Keep unrelated programs on the build machine's PATH out of Windows DLL discovery.
    windows = Path(os.environ["SYSTEMROOT"])
    env = {name: value for name, value in os.environ.items()
           if not name.upper().startswith(("PYTHON", "QT_", "QML"))}
    env["PATH"] = os.pathsep.join(map(str, (Path(sys.base_prefix), windows / "System32", windows)))
    env["PYINSTALLER_CONFIG_DIR"] = str(BUILD / "cache")
    subprocess.run([*command, str(ROOT / "Start-Sortrr.pyw")], cwd=ROOT, env=env, check=True)

    licenses = package / "licenses"
    licenses.mkdir(exist_ok=True)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copyfile(python_license, licenses / "Python-LICENSE.txt")
    shutil.copyfile(ffmpeg_root / "LICENSE", licenses / "FFmpeg-LICENSE.txt")
    shutil.copyfile(ffmpeg_root / "README.txt", licenses / "FFmpeg-build-and-source.txt")
    qt_version = importlib.metadata.version("PySide6")
    (licenses / "Third-party.txt").write_text(
        f"Python {platform.python_version()} (PSF license)\n"
        f"PySide6 / Qt {qt_version}, bundled as separate libraries\n"
        "Qt licensing: https://www.qt.io/licensing/open-source-lgpl-obligations\n"
        f"Qt for Python source: https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v{qt_version}\n"
        f"Qt source releases: https://download.qt.io/official_releases/qt/{'.'.join(qt_version.split('.')[:2])}/{qt_version}/single/\n"
        "FFmpeg tools: see FFmpeg-build-and-source.txt and FFmpeg-LICENSE.txt.\n"
        "Qt Multimedia FFmpeg information: https://doc.qt.io/qt-6/qtmultimedia-attribution-ffmpeg.html\n"
        "PyInstaller bootloader exception: https://pyinstaller.org/en/stable/license.html\n",
        encoding="utf-8",
    )
    (package / "Read me.txt").write_text(
        "Sortrr for 64-bit Windows\n\n"
        "Extract the entire ZIP. Open Sortrr.exe and keep the _internal folder beside it.\n"
        "Python, Qt, FFmpeg and ffprobe are bundled.\n"
        "Settings, match history and logs are stored under %LOCALAPPDATA%\\Sortrr.\n"
        "See licenses for third-party notices.\n",
        encoding="utf-8",
    )
    archive = dist / "Sortrr-Windows-x64.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as output:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                output.write(path, path.relative_to(dist))
    print(f"Executable: {package / 'Sortrr.exe'}")
    print(f"Portable ZIP: {archive} ({archive.stat().st_size / 1024**2:.1f} MiB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=DIST, help="Output folder within the project")
    build(ROOT / parser.parse_args().dist_dir)
