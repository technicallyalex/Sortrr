"""Collect the Qt Quick modules imported by Sortrr instead of all installed QML plugins."""
import json
from pathlib import Path
import subprocess

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
qml = Path(pyside6_library_info.location["QmlImportsPath"])
ui = Path(__file__).resolve().parents[2] / "ui"
result = subprocess.run(
    [str(qml.parent / "qmlimportscanner.exe"), "-rootPath", str(ui), "-importPath", str(qml)],
    capture_output=True, check=True, text=True, encoding="utf-8",
)
modules = {entry["relativePath"] for entry in json.loads(result.stdout) if entry.get("relativePath")}
# Qt Quick Controls may resolve its base module at runtime when creating popups.
modules.add("QtQuick/Controls")
target = Path(pyside6_library_info.qt_rel_dir) / "qml"
for name in sorted(modules):
    module = qml / name
    libraries, files = pyside6_library_info._process_qml_plugin(module / "qmldir")
    for src, output in ((libraries, binaries), (files, datas)):
        for path in src:
            directory = path if path.is_dir() else path.parent
            output.append((str(path), str(target / directory.relative_to(qml))))
