"""The Stokes shown ("Stokes I", Q, U, V) at a view's top left, where it is read: on each panel of the 2x2 view
(ui.stokesgrid), and on the image and lambda-t of every cube (ui.cube). Only for a cube with the four Stokes: with one
plane along the axis, or none, nothing says whether it is Stokes I, a magnetic field or anything else. One look for
all: the theme's ink, POS px into the view box, a child of the box and not of its data (it neither moves with a zoom
nor counts in the box's range). Made hidden; the same words on every view.

    label = StokesLabel(vb, light); label.show_stokes(s, ns); label.show_stokes(None, ns); label.set_light(light)
"""
import pyqtgraph as pg
from PySide6 import QtGui

from ..data.axes import STOKES

POS = (8, 6)                                            # px from the view box's top left
INK = {False: QtGui.QColor(235, 235, 240), True: QtGui.QColor(30, 30, 34)}   # dark, light: glass's INK


class StokesLabel(pg.TextItem):
    def __init__(self, vb: pg.ViewBox, light: bool):
        super().__init__("", anchor=(0, 0))
        self.setParentItem(vb)
        self.setPos(*POS)
        self.set_light(light)
        self.hide()

    def set_light(self, light: bool) -> None:
        self.setColor(INK[bool(light)])

    def show_stokes(self, s: int | None, ns: int) -> None:
        """The words "Stokes <s's letter>" on the view of a cube with ns Stokes, when ns is 4; else, or for s None (the
        Stokes named by something else in that corner), nothing."""
        text = f"Stokes {STOKES[s]}" if s is not None and ns == len(STOKES) else None
        if text is not None and text != self.toPlainText():
            self.setText(text)
        self.setVisible(text is not None)
