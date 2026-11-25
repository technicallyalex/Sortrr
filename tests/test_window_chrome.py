import unittest
from PySide6.QtCore import QObject, QPoint, Signal
from PySide6.QtGui import QRegion
from window_chrome import WindowShape, folder_path


class WindowStub(QObject):
    widthChanged = Signal()
    heightChanged = Signal()

    def __init__(self):
        super().__init__()
        self.w, self.h = 1000, 700
        self.mask = QRegion()

    def width(self):
        return self.w

    def height(self):
        return self.h

    def setMask(self, mask):
        self.mask = mask


class WindowChromeTests(unittest.TestCase):
    def test_cutout_is_not_an_input_surface(self):
        region = QRegion(folder_path(1000, 700, 182, 40).toFillPolygon().toPolygon())
        self.assertFalse(region.contains(QPoint(20, 15)))
        self.assertFalse(region.contains(QPoint(700, 15)))
        self.assertTrue(region.contains(QPoint(950, 15)))
        self.assertTrue(region.contains(QPoint(20, 60)))
        self.assertTrue(region.contains(QPoint(500, 650)))

    def test_resize_keeps_the_tab_at_the_right_edge(self):
        window = WindowStub()
        shape = WindowShape()
        shape.targetWindow = window
        self.assertTrue(window.mask.contains(QPoint(950, 15)))
        window.w = 1400
        window.widthChanged.emit()
        self.assertFalse(window.mask.contains(QPoint(950, 15)))
        self.assertTrue(window.mask.contains(QPoint(1350, 15)))
        window.h = 950
        window.heightChanged.emit()
        self.assertTrue(window.mask.contains(QPoint(500, 900)))

    def test_settings_tab_and_window_replacement(self):
        old, current = WindowStub(), WindowStub()
        shape = WindowShape()
        shape.targetWindow = old
        shape.targetWindow = current
        shape.tabWidth = 86
        self.assertFalse(current.mask.contains(QPoint(870, 15)))
        self.assertTrue(current.mask.contains(QPoint(970, 15)))
        before = QRegion(current.mask)
        old.w = 1500
        old.widthChanged.emit()
        self.assertEqual(current.mask, before)
        shape.targetWindow = None
