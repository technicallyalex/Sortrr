"""Native hit-test region for Sortrr's rounded windows with a browser-style drag strip."""
from PySide6.QtCore import QObject, Property, Signal
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QRegion
from PySide6.QtQml import QmlElement

QML_IMPORT_NAME = "Sortrr.Native"
QML_IMPORT_MAJOR_VERSION = 1


def window_path(width, height):
    """Rounded outer frame; the entire top strip accepts window dragging."""
    from PySide6.QtCore import QRectF
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, float(width), float(height)), 8, 8)
    return path


@QmlElement
class WindowShape(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._window = None

    def update_mask(self):
        if self._window is not None:
            w, h = self._window.width(), self._window.height()
            if w > 0 and h > 0:
                path = window_path(w, h)
                # A native region has binary edges. Keep it just outside the
                # painted contour so it cannot clip the antialiased pixels.
                padding = QPainterPathStroker()
                padding.setWidth(4.0)
                hit_path = path.united(padding.createStroke(path))
                self._window.setMask(QRegion(hit_path.toFillPolygon().toPolygon()))

    def get_window(self):
        return self._window

    def set_window(self, window):
        if window is self._window:
            return
        if self._window is not None:
            self._window.widthChanged.disconnect(self.update_mask)
            self._window.heightChanged.disconnect(self.update_mask)
        self._window = window
        if window is not None:
            window.widthChanged.connect(self.update_mask)
            window.heightChanged.connect(self.update_mask)
        self.update_mask()
        self.changed.emit()

    targetWindow = Property(QObject, get_window, set_window, notify=changed)
