"""The image panel on pyqtgraph ("pgr", docs/decisions/0008): never hand pyqtgraph more pixels than the view shows.

From the prototype's viewer/backend_pgr.py and backend_pg.py, with the reduction app/viewer.py patched in, and its
ViewGuard. On every new image and every zoom or pan, the visible region is cropped, bin-averaged down to the view's
physical pixels and scaled to uint8 in one pass (explorer.data.kernels.reduce_u8, in row strips): pyqtgraph then
paints a screen-sized uint8 image, with no levels or colour work on the whole frame (a step in t 23.9 -> 15.5 ms on
the Mac; over ssh -Y the drawing 42 -> 4.4-4.9 ms, docs/measured.md). Level 0 is "no data" (NaN padding), the data
go on 1..255, so the colour table decides how padding looks. Zooming in renders the visible region again with more
detail, down to full resolution; range changes in a burst render once (a 0-ms timer).
The mouse over the image gives (y, x) in data pixels to on_hover; the crosshair is drawn where the core's cursor is.
"""
from collections.abc import Callable

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore

from ..data.kernels import reduce_u8

pg.setConfigOptions(imageAxisOrder="row-major", antialias=False, useNumba=False)
# pyqtgraph's numba image conversion cost a fixed ~22 ms per call even on a 186x14 image (22.4 -> 0.17 ms with it
# off, bellatrix); the image here is uint8 already, reduced by explorer's own kernel

CURSOR_PEN = pg.mkPen((255, 80, 80), width=1)


class ImageView:
    def __init__(self, on_hover: Callable[[float, float], None] | None = None, strips=None, parts: int = 1):
        """on_hover(y, x): the mouse over the image, in data pixels; strips, parts: the pool and the number of row
        strips the reduction runs in (Executors.strips)."""
        self.on_hover = on_hover
        self.strips, self.parts = strips, parts
        self.widget = pg.GraphicsLayoutWidget()
        self.vb = self.widget.addViewBox(lockAspect=True)
        self.img = pg.ImageItem()
        self.vb.addItem(self.img)
        self.hl, self.vl = pg.InfiniteLine(angle=0, pen=CURSOR_PEN), pg.InfiniteLine(angle=90, pen=CURSOR_PEN)
        self.vb.addItem(self.hl)
        self.vb.addItem(self.vl)
        self.widget.scene().sigMouseMoved.connect(self._moved)
        self._full: np.ndarray | None = None
        self._lim = (0.0, 1.0)
        self._first = True
        self.guard: ViewGuard | None = None
        self._pending = QtCore.QTimer(self.widget)
        self._pending.setSingleShot(True)
        self._pending.setInterval(0)
        self._pending.timeout.connect(self.render)     # a burst of range changes renders once
        self.vb.sigRangeChanged.connect(lambda *a: self._pending.start())
        self.last_render: dict = {}

    # ---------------------------------------------------------------- input
    def _moved(self, pos) -> None:
        if self.on_hover is not None and self.vb.sceneBoundingRect().contains(pos):
            p = self.vb.mapSceneToView(pos)
            self.on_hover(p.y(), p.x())

    # ---------------------------------------------------------------- drawing
    def set_image(self, img: np.ndarray, levels) -> None:
        self._full, self._lim = img, (float(levels[0]), float(levels[1]))
        if self._first:
            ny, nx = img.shape
            self.vb.setRange(QtCore.QRectF(0, 0, nx, ny), padding=0)
            self.guard = ViewGuard(self.vb, nx, ny)
            self._first = False
        self.render()

    def set_crosshair(self, y: int, x: int) -> None:
        self.hl.setValue(y + 0.5)
        self.vl.setValue(x + 0.5)

    def show_all(self) -> None:
        """The whole image in view (the double click on the image)."""
        if self._full is not None:
            ny, nx = self._full.shape
            self.vb.setRange(QtCore.QRectF(0, 0, nx, ny), padding=0)

    def render(self) -> None:
        if self._full is None:
            return
        img = self._full
        ny, nx = img.shape
        (vx0, vx1), (vy0, vy1) = self.vb.viewRange()
        x0, x1 = max(0, int(np.floor(vx0))), min(nx, int(np.ceil(vx1)))
        y0, y1 = max(0, int(np.floor(vy0))), min(ny, int(np.ceil(vy1)))
        if x1 - x0 < 2 or y1 - y0 < 2:
            return
        vp = self.widget.viewport()
        dpr = vp.devicePixelRatioF()
        f = max(1, int(min((x1 - x0) / max(1.0, vp.width() * dpr), (y1 - y0) / max(1.0, vp.height() * dpr))))
        h, w = (y1 - y0) // f, (x1 - x0) // f
        out = np.empty((h, w), np.uint8)
        reduce_u8(img, y0, x0, f, self._lim[0], self._lim[1], out, self.strips, self.parts)
        self.img.setImage(out, levels=(0, 255), autoDownsample=False)
        self.img.setRect(QtCore.QRectF(x0, y0, w * f, h * f))      # keep data-pixel coordinates
        self.last_render = dict(factor=f, shape=(h, w), region=(y0, y1, x0, x1))


class ViewGuard(QtCore.QObject):
    """Keeps the image in sight: without limits one zooms or drags it out of view and is lost.
    - zoom out down to ZOOM_OUT of the whole-image fit: 1, the whole image and no further, as CRISPEX (0.25 and 0.5
      were tried and had no use);
    - zoom in until MIN_PIXELS x MIN_PIXELS data pixels fill the view;
    - each zoom-out step moves the view's centre towards the image's centre by the share of the way to the fit that
      the step covers, in log scale as the wheel steps: at 1x the image is centred, and below it stays centred.
      Zooming in keeps following the mouse (pyqtgraph's own scaling about the pointer);
    - the view's centre never leaves the image, however far one drags: some of the image is always in sight.
    CRISPEX did not zoom out below the fit (factors 1-8 over it, crispex.pro L23047, L21919) and panned with sliders
    that stopped at the image's edges. A resize is not a zoom: recentring only while the panel keeps its size.
    From the prototype's app/viewer.py ViewGuard."""
    ZOOM_OUT = 1.0
    MIN_PIXELS = 3

    def __init__(self, vb, nx, ny):
        super().__init__(vb)
        self.vb, self.nx, self.ny = vb, nx, ny
        self._busy = False
        self._last = None                               # (scale, panel width, panel height, centre x, centre y)
        vb.sigRangeChanged.connect(self._check)

    def _check(self, *args):
        if self._busy:
            return
        vb = self.vb
        W, H = vb.width(), vb.height()
        (x0, x1), (y0, y1) = vb.viewRange()
        w, h = x1 - x0, y1 - y0
        if W < 2 or H < 2 or w <= 0 or h <= 0:
            return
        s = min(W / w, H / h)                           # screen px per data px (the aspect is locked)
        fit = min(W / self.nx, H / self.ny)
        new = min(max(s, fit * self.ZOOM_OUT), min(W, H) / self.MIN_PIXELS)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        last = self._last
        same = last is not None and abs(last[1] - W) < 1 and abs(last[2] - H) < 1
        # what was asked (s against the last scale), not what the clamp makes of it: at a limit the scale no longer
        # changes, and pyqtgraph's shift about the pointer would go through as a pan
        if last is not None and same and s < last[0] * 0.999:   # zoom out
            if new <= fit:
                cx, cy = self.nx / 2, self.ny / 2
            else:                                       # this step's share of the (log) way to the fit
                # from the last centre, not from pyqtgraph's: zooming out about the pointer already pushes the view
                # away from it, and the two added up overshot the image's centre
                f = (np.log(last[0]) - np.log(new)) / (np.log(last[0]) - np.log(fit))
                cx, cy = last[3] + (self.nx / 2 - last[3]) * f, last[4] + (self.ny / 2 - last[4]) * f
        elif last is not None and same and s > last[0] * 1.001 and new < s:   # zoom in, at the limit
            # pyqtgraph's centre is for scale s about the pointer m: c = m + (c0 - m) r, r = s0 / s. Find m, then
            # scale about it to the limit only (at the limit already: c0, nothing moves)
            r = last[0] / s
            mx, my = (cx - last[3] * r) / (1 - r), (cy - last[4] * r) / (1 - r)
            q = last[0] / new
            cx, cy = mx + (last[3] - mx) * q, my + (last[4] - my) * q
        cx, cy = min(max(cx, 0.0), float(self.nx)), min(max(cy, 0.0), float(self.ny))
        self._last = (new, W, H, cx, cy)
        if abs(new - s) > 1e-6 * s or abs(cx - (x0 + x1) / 2) > 1e-6 or abs(cy - (y0 + y1) / 2) > 1e-6:
            self._busy = True
            try:
                vb.setRange(QtCore.QRectF(cx - W / new / 2, cy - H / new / 2, W / new, H / new), padding=0)
            finally:
                self._busy = False
