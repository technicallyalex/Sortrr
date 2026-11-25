"""Native hit-test region for Sortrr's folder-shaped windows."""
from PySide6.QtCore import QObject, Property, Signal
from PySide6.QtGui import QPainterPath, QRegion
from PySide6.QtQml import QmlElement

QML_IMPORT_NAME = "Sortrr.Native"
QML_IMPORT_MAJOR_VERSION = 1


def folder_path(width, height, tab_width, tab_height):
    """Shared contour in logical pixels, including the raised caption tab."""
    w, h, t = float(width), float(height), float(tab_height)
    x = w - float(tab_width)
    p = QPainterPath()
    p.moveTo(8, t)
    p.lineTo(x - 18, t)
    p.cubicTo(x - 4, t, x - 8, 0, x + 10, 0)
    p.lineTo(w - 8, 0)
    p.quadTo(w, 0, w, 8)
    p.lineTo(w, h - 8)
    p.quadTo(w, h, w - 8, h)
    p.lineTo(8, h)
    p.quadTo(0, h, 0, h - 8)
    p.lineTo(0, t + 8)
    p.quadTo(0, t, 8, t)
    p.closeSubpath()
    return p


@QmlElement
class WindowShape(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._window = None
        self._tab_width = 184.0
        self._tab_height = 40.0

    def update_mask(self):
        if self._window is not None:
            w, h = self._window.width(), self._window.height()
            if w > 0 and h > 0:
                self._window.setMask(QRegion(folder_path(
                    w, h, self._tab_width, self._tab_height
                ).toFillPolygon().toPolygon()))

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

    def get_tab_width(self):
        return self._tab_width

    def set_tab_width(self, value):
        if self._tab_width != value:
            self._tab_width = value
            self.update_mask()
            self.changed.emit()

    tabWidth = Property(float, get_tab_width, set_tab_width, notify=changed)

    def get_tab_height(self):
        return self._tab_height

    def set_tab_height(self, value):
        if self._tab_height != value:
            self._tab_height = value
            self.update_mask()
            self.changed.emit()

    tabHeight = Property(float, get_tab_height, set_tab_height, notify=changed)
