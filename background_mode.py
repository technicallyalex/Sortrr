"""Windows notification-area integration; no console or separate background process."""
from pathlib import Path
import hashlib
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QWindow
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


class InstanceGate(QObject):
    """Launching the EXE again opens the already-running background window."""
    requested = Signal()

    def __init__(self, data):
        super().__init__()
        from PySide6.QtNetwork import QLocalServer, QLocalSocket
        name = "Sortrr-" + hashlib.sha256(str(Path(data).resolve()).casefold().encode()).hexdigest()[:24]
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        socket = QLocalSocket()
        socket.connectToServer(name)
        self.forwarded = socket.waitForConnected(400)
        if self.forwarded:
            socket.disconnectFromServer()
            return
        if not self.server.listen(name):
            # Another launch may have won the race while we were connecting.
            socket.connectToServer(name)
            self.forwarded = socket.waitForConnected(1000)
            if not self.forwarded:
                raise OSError("Could not open Sortrr's local instance channel.")
            socket.disconnectFromServer()
            return
        self.server.newConnection.connect(self.accept)

    def accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.disconnectFromServer()
            socket.deleteLater()
            self.requested.emit()


class BackgroundMode(QObject):
    def __init__(self, controller, window):
        super().__init__(window)
        self.controller = controller
        self.window = window
        self.notification_root = ""
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray = QSystemTrayIcon(QIcon(str(Path(__file__).parent / "ui/assets/sortrr.png")), self)
        self.menu = QMenu()
        self.show_action = self.menu.addAction("Open Sortrr", self.show)
        self.review_action = self.menu.addAction("Review new files", self.review)
        self.menu.addSeparator()
        self.pause_action = QAction("Pause watch folders", self.menu)
        self.pause_action.setCheckable(True)
        self.pause_action.triggered.connect(lambda checked: controller.setWatchOption("paused", checked))
        self.menu.addAction(self.pause_action)
        self.menu.addAction("Check watch folders now", controller.checkWatchFolders)
        self.menu.addAction("Check for updates", self.check_updates)
        self.menu.addSeparator()
        self.menu.addAction("Quit Sortrr", self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.activated)
        self.tray.messageClicked.connect(self.review)
        controller.watch.changed.connect(self.sync)
        controller.stateChanged.connect(self.sync)
        controller.watch.notification.connect(self.notify)
        controller.tray_handler = self
        QApplication.instance().aboutToQuit.connect(self.close)
        self.sync()

    def sync(self):
        enabled = bool(self.controller.watch.config["background"]) and self.available
        self.tray.setVisible(enabled)
        self.pause_action.setChecked(self.controller.watch.config["paused"])
        total = sum(row["readyToReview"] for row in self.controller.watch.state()["folders"])
        self.review_action.setEnabled(total > 0 and not self.controller.busy and not self.controller.watch.busy)
        self.tray.setToolTip("Sortrr - Watch folders paused" if self.controller.watch.config["paused"] else f"Sortrr - {total} new or updated files to review" if total else "Sortrr - Watching media folders")
        # Disabling background mode must never strand a hidden window.
        if not enabled and not self.window.isVisible():
            self.show()

    def show(self):
        self.window.show()
        if self.window.visibility() == QWindow.Minimized:
            self.window.showNormal()
        self.window.raise_()
        self.window.requestActivate()

    def hide(self):
        if not self.available or not self.controller.watch.config["background"]:
            return False
        if self.controller.items and not self.controller.busy:
            if not self.save_progress():
                # Consume the close request while keeping the window visible.
                return True
        self.controller.player.pause()
        from PySide6.QtQuick import QQuickWindow
        settings = self.window.findChild(QQuickWindow, "settingsWindow")
        if settings:
            settings.hide()
        self.window.hide()
        return True

    def save_progress(self):
        stage = "wizard" if self.controller.w.get("open") else "organize" if self.window.property("step") == 2 else "review"
        return self.controller.saveProgress(stage, self.window.property("scope") or "all",
                                            self.window.property("rejectMode") or "leave")

    def activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show()

    def notify(self, path, message):
        if self.controller.watch.config["notifications"] and self.tray.isVisible():
            self.notification_root = path
            self.tray.showMessage("Sortrr: media ready to review", message, QSystemTrayIcon.Information, 8000)

    def review(self):
        self.show()
        roots = self.controller.watch.state()["folders"]
        path = self.notification_root if any(r["path"] == self.notification_root and r["readyToReview"] for r in roots) else next(
            (r["path"] for r in roots if r["readyToReview"]), "")
        if path:
            self.controller.reviewWatchFolder(path)

    def check_updates(self):
        self.show()
        self.controller.openSettingsRequested.emit()
        self.controller.checkForUpdates()

    def quit(self):
        if self.controller.busy:
            self.show()
            self.controller.toast.emit("Wait for the current operation to finish before quitting.")
            return
        if self.controller.items and not self.save_progress():
            self.show()
            return
        self.controller.shutdown()
        self.tray.hide()
        QApplication.instance().quit()

    def close(self):
        self.tray.hide()
        self.menu.close()
