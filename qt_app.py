"""Qt Quick startup for the Sortrr desktop app."""
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from qt_backend import Controller
from app_version import VERSION
from background_mode import BackgroundMode, InstanceGate
from app_paths import data_directory


def create_engine(controller):
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("controller", controller)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parent / "ui" / "Main.qml")))
    return engine


def main():
    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    app.setApplicationName("Sortrr")
    app.setApplicationVersion(VERSION)
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "ui" / "assets" / "sortrr.png")))
    instance = InstanceGate(data_directory())
    if instance.forwarded:
        return 0
    controller = Controller()
    app.aboutToQuit.connect(controller.shutdown)
    app.setQuitOnLastWindowClosed(False)
    engine = create_engine(controller)
    if not engine.rootObjects():
        controller.shutdown()
        return 1
    app.setQuitOnLastWindowClosed(False)
    background = BackgroundMode(controller, engine.rootObjects()[0])
    instance.requested.connect(background.show)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
