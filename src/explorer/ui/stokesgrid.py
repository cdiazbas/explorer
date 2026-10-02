"""The 2x2 view (ROADMAP E5.11): I, Q, U and V side by side over the image panel, at this t and lambda.

Four ImageViews, one per Stokes, their views linked: a zoom or a pan in one moves all four (_follow). Each renders
what it shows only, at the resolution it is shown (ImageView.render: the visible region reduced to the screen's
pixels), with its own levels (Q U V symmetric about 0) and its Stokes's colour table. The cursor's crosshair is
drawn in all four; the mouse over any of them moves the cursor, a click locks it there and makes that panel's Stokes
the session's (so lambda-t shows it), a right click releases it, a double click shows the whole image. The core
reads the frames (Scheduler.set_grid). From the prototype's app/look_glass.py StokesGrid (221-315) and set_grid
(600-614), on explorer's ImageView (crop and reduce_u8, where the prototype strided down).

    grid = StokesGrid(parent, ns, on_hover, on_click, light=..., strips=..., parts=...)
    grid.set_image(s, img, levels); grid.set_crosshair(y, x); grid.set_locked(on); grid.set_lut(s, table)
    grid.set_region(rect); grid.region()
"""
from collections.abc import Callable

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from ..data.axes import STOKES
from .imageview import ImageView, ViewGuard

SPACING = 4                                             # px between the panels


class StokesGrid(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget, ns: int, on_hover: Callable[[float, float], None],
                 on_click: Callable[[int, object], None], light: bool = False, strips=None, parts: int = 1):
        """on_hover(y, x): the mouse over any panel, in data pixels; on_click(s, ev): a click on panel s (the
        scene's event; its position in that panel's view by panel_point)."""
        super().__init__(parent)
        self.setObjectName("stokes_grid")
        self.setAutoFillBackground(True)
        lay = QtWidgets.QGridLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(SPACING)
        self.views: list[ImageView] = []
        self._following = False
        ink = QtGui.QColor(30, 30, 34) if light else QtGui.QColor(235, 235, 240)
        cols = 1 if ns == 1 else 2
        for k in range(ns):
            v = ImageView(on_hover=on_hover, strips=strips, parts=parts, light=light)
            v._first = False                            # the region comes from the single view, not the whole image
            v.vb.setMenuEnabled(False)
            v.widget.viewport().setCursor(QtCore.Qt.CursorShape.CrossCursor)
            v.vb.sigRangeChanged.connect(lambda *_a, v=v: self._follow(v))
            label = pg.TextItem(STOKES[k], color=ink, anchor=(0, 0))
            label.setParentItem(v.vb)
            label.setPos(8, 6)
            v.widget.scene().sigMouseClicked.connect(lambda ev, k=k: on_click(k, ev))
            lay.addWidget(v.widget, k // cols, k % cols)
            self.views.append(v)
        self.hide()

    def _follow(self, src: ImageView) -> None:
        """A zoom or pan in one panel: the same region in the others. Not pyqtgraph's setXLink/setYLink, which lines
        linked views up by where they are on the screen (ViewBox.linkedViewChanged, for plots sharing an axis): on
        Linux the bottom row showed y 56-184 while the top row showed 136-264."""
        if self._following:
            return
        self._following = True
        try:
            r = src.vb.viewRect()
            for v in self.views:
                if v is not src:
                    v.vb.setRange(r, padding=0)
        finally:
            self._following = False

    def panel_point(self, s: int, ev):
        """(y, x) in data pixels of a click on panel s, or None when it is outside the image's view box."""
        vb = self.views[s].vb
        if not vb.sceneBoundingRect().contains(ev.scenePos()):
            return None
        p = vb.mapSceneToView(ev.scenePos())
        return p.y(), p.x()

    def set_image(self, s: int, img, levels) -> None:
        v = self.views[s]
        # a guard on every panel: the wheel turns the one under the pointer, and a guard on the first alone let the
        # others go out past the whole image (11x, the user saw it). The four are the same size and show the same
        # region, so their guards agree
        if v.guard is None:
            v.guard = ViewGuard(v.vb, img.shape[1], img.shape[0])
        v.set_image(img, levels)

    def set_crosshair(self, y: int, x: int) -> None:
        for v in self.views:
            v.set_crosshair(y, x)

    def set_locked(self, on: bool) -> None:
        for v in self.views:
            v.set_locked(on)

    def set_reticle(self, on: bool) -> None:
        for v in self.views:
            v.set_reticle(on)

    def set_lut(self, s: int, table) -> None:
        self.views[s].set_lut(table if table is not None else self.views[s].base_lut)

    def set_region(self, rect: QtCore.QRectF) -> None:
        self.views[0].vb.setRange(rect, padding=0)

    def region(self) -> QtCore.QRectF:
        return self.views[0].vb.viewRect()

    def show_all(self) -> None:
        full = self.views[0]._full
        if full is not None:
            self.views[0].vb.setRange(QtCore.QRectF(0, 0, full.shape[1], full.shape[0]), padding=0)
