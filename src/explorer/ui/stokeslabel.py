"""The Stokes shown ("Stokes I", Q, U, V) at a view's top left, where it is read: on the image and lambda-t of every
cube (ui.cube); not on the panels of the 2x2 view, whose keys name them (ui.scalekey). Only for a cube with the four
Stokes: with one plane along the axis, or none, nothing says whether it is Stokes I, a magnetic field or anything
else. One look for all: the theme's ink over a halo of the other end (dark under light text, light under dark), as
the reticle's (overlays.Reticle): the plain text read at 1.2-1.9:1 over bright granulation in the dark theme. POS px
into the view box, a child of the box and not of its data (it neither moves with a zoom nor counts in the box's
range). Made hidden; the same words on every view.

    label = StokesLabel(vb, light); label.show_stokes(s, ns); label.show_stokes(None, ns); label.set_light(light)
"""
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from ..data.axes import STOKES

POS = (8, 6)                                            # px from the view box's top left
INK = {False: QtGui.QColor(235, 235, 240), True: QtGui.QColor(30, 30, 34)}   # dark, light: glass's INK
HALO = {False: QtGui.QColor(0, 0, 0, 170), True: QtGui.QColor(255, 255, 255, 200)}
HALO_PX = 3.0                                           # the halo's stroke: 1.5 px each side of the letters
PAD = 2                                                 # px round the letters, as a text item's own margin


class StokesLabel(pg.GraphicsObject):
    def __init__(self, vb: pg.ViewBox, light: bool):
        super().__init__()
        self._text = ""
        self._path = QtGui.QPainterPath()
        self._font = QtGui.QFont(QtWidgets.QApplication.font())
        self.setParentItem(vb)
        self.setPos(*POS)
        self.setZValue(1000)
        self.set_light(light)
        self.hide()

    def set_light(self, light: bool) -> None:
        self.color, self.halo = INK[bool(light)], HALO[bool(light)]
        self.update()

    def toPlainText(self) -> str:                      # the words shown, as a text item says them
        return self._text

    def show_stokes(self, s: int | None, ns: int) -> None:
        """The words "Stokes <s's letter>" on the view of a cube with ns Stokes, when ns is 4; else, or for s None (the
        Stokes named by something else in that corner), nothing."""
        text = f"Stokes {STOKES[s]}" if s is not None and ns == len(STOKES) else None
        if text is not None and text != self._text:
            self.prepareGeometryChange()
            self._text = text
            path = QtGui.QPainterPath()
            path.addText(PAD, PAD + QtGui.QFontMetricsF(self._font).ascent(), self._font, text)
            self._path = path
            self.update()
        self.setVisible(text is not None)

    def boundingRect(self) -> QtCore.QRectF:
        if not self._text:
            return QtCore.QRectF()
        fm = QtGui.QFontMetricsF(self._font)
        return QtCore.QRectF(0, 0, fm.horizontalAdvance(self._text) + 2 * PAD, fm.height() + 2 * PAD)

    def paint(self, p, *args) -> None:
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(self.halo, HALO_PX)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        p.strokePath(self._path, pen)                   # the halo first, then the letters on it
        p.fillPath(self._path, self.color)
