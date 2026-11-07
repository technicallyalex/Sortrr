"""Qt Quick startup for the Sortrr desktop app."""
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from qt_backend import Controller


def create_engine(controller):
    app = QApplication.instance()

    def apply_appearance():
        scheme = Qt.ColorScheme.Dark if controller.darkMode else Qt.ColorScheme.Light
        app.styleHints().setColorScheme(scheme)

    controller.darkModeChanged.connect(apply_appearance)
    apply_appearance()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("controller", controller)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parent / "ui" / "Main.qml")))
    return engine


def main():
    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    app.setApplicationName("Sortrr")
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "ui" / "assets" / "sortrr.png")))
    controller = Controller()
    app.aboutToQuit.connect(controller.shutdown)
    engine = create_engine(controller)
    return app.exec() if engine.rootObjects() else 1


if __name__ == "__main__":
    raise SystemExit(main())
