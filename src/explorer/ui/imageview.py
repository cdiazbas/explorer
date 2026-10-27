"""The image panel on pyqtgraph ("pgr", docs/decisions/0008): never hand pyqtgraph more pixels than the view shows.

From the prototype's viewer/backend_pgr.py and backend_pg.py, with the reduction app/viewer.py patched in, and its
ViewGuard. On every new image and every zoom or pan, the visible region is cropped, bin-averaged down to the view's
physical pixels and scaled to uint8 in one pass (explorer.data.kernels.reduce_u8, in row strips): pyqtgraph then
paints a screen-sized uint8 image, with no levels or colour work on the whole frame (a step in t 23.9 -> 15.5 ms on
the Mac; over ssh -Y the drawing 42 -> 4.4-4.9 ms, docs/measured.md). Level 0 is "no data" (NaN padding), the data
go on 1..255, so the colour table decides how padding looks. Zooming in renders the visible region again with more
detail, down to full resolution; range changes in a burst render once (a 0-ms timer).
The mouse over the image gives (y, x) in data pixels to on_hover, at every move the view receives (_Moves); the
crosshair is drawn where the core's cursor is; "Stokes Q" at the top left when its owner gives a Stokes (set_stokes).
What is drawn over the image registers in over (overlays.OverImage): a move over it is not one over the image.
"""
from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore

from ..core.levels import symmetric_levels
from ..data.axes import Planes
from ..data.kernels import gamma_table, reduce_u8
from . import pens
from .overlays import OverImage
from .stokeslabel import StokesLabel

if TYPE_CHECKING:
    from .overlays import Reticle

pg.setConfigOptions(imageAxisOrder="row-major", antialias=False, useNumba=False)
# pyqtgraph's numba image conversion cost a fixed ~22 ms per call even on a 186x14 image (22.4 -> 0.17 ms with it
# off, bellatrix); the image here is uint8 already, reduced by explorer's own kernel

CURSOR_PEN = pg.mkPen((255, 80, 80), width=1)
LOCK_PEN = pg.mkPen((255, 190, 60), width=1.5)          # the crosshair while the cursor is locked
# in the light theme: (255, 190, 60) on a white image stood at 1.66:1, under the 3:1 a line needs (WCAG 1.4.11); this
# one 3.19:1 on white, 6.59:1 on black
LOCK_PEN_LIGHT = pg.mkPen((217, 119, 6), width=1.5)
pens.keep(CURSOR_PEN, LOCK_PEN, LOCK_PEN_LIGHT)         # made before the screen is known


class _Moves(QtCore.QObject):
    """Every mouse move over the view's viewport, to ImageView._moved. pyqtgraph's scene drops a move that comes
    within 1/mouseRateLimit s (10 ms) of the one before and never delivers it later (sigMouseMoved), so a pointer
    that stops right after a quick move would leave the crosshair on the pixel before."""

    def __init__(self, view: "ImageView"):
        super().__init__(view.widget)
        self.view = view

    def eventFilter(self, obj, e) -> bool:
        if e.type() == QtCore.QEvent.Type.MouseMove:
            at = e.position().toPoint()
            if not self.view.over.covers(at):           # over the key, the label...: off the image
                self.view._moved(self.view.widget.mapToScene(at))
        return False


class ImageView:
    def __init__(self, on_hover: Callable[[float, float], None] | None = None, strips=None, parts: int = 1,
                 light: bool = False, reticle: bool = False):
        """on_hover(y, x): the mouse over the image, in data pixels; strips, parts: the pool and the number of row
        strips the reduction runs in (Executors.strips); light: the surround and the padding white (the light
        theme), else black; reticle: a short cross with a halo instead of two lines across the image (the modern
        look)."""
        self.on_hover = on_hover
        self.strips, self.parts = strips, parts
        self.widget = pg.GraphicsLayoutWidget()
        self.vb = self.widget.addViewBox(lockAspect=True)
        self.img = pg.ImageItem()
        self.vb.addItem(self.img)
        self.hl, self.vl = pg.InfiniteLine(angle=0, pen=CURSOR_PEN), pg.InfiniteLine(angle=90, pen=CURSOR_PEN)
        self.vb.addItem(self.hl)
        self.vb.addItem(self.vl)
        self.reticle: Reticle | None = None
        self._locked = False
        self.base_lut: np.ndarray | None = None          # the look's grey: pyqtgraph's own, or the light theme's
        self.over = OverImage(self.widget)              # what is drawn over the image (ui.overlays)
        self.stokes = StokesLabel(self.vb, light)       # the Stokes shown, once set_stokes gives it
        self.over.add(self.stokes)
        self.set_light(light)
        if reticle:
            self.set_reticle(True)
        self._moves = _Moves(self)
        self.widget.viewport().installEventFilter(self._moves)
        self._full: np.ndarray | None = None
        self._lim = (0.0, 1.0)
        self._gamma = 1.0                               # its cube's at its Stokes (Session.gamma); 1: straight
        self._first = True
        self.guard: ViewGuard | None = None
        # the lowest magnification (screen px per data pixel) its guard allows, when not its own fit: a linked image
        # takes the main one's (ViewSync), so that one magnification holds however large its panel is
        self.zoom_floor: Callable[[], float | None] | None = None
        self._pending = QtCore.QTimer(self.widget)
        self._pending.setSingleShot(True)
        self._pending.setInterval(0)
        self._pending.timeout.connect(self.render)     # a burst of range changes renders once
        self.vb.sigRangeChanged.connect(lambda *a: self._pending.start())
        self.last_render: dict = {}
        self.paused = False                             # covered (the 2x2 view over it): keeps images, draws none

    def set_light(self, light: bool) -> None:
        """The surround, the padding and the locked crosshair for this theme. The grey table goes on only if the image
        wears the old one: a look's colour map stays until the look sets it again."""
        self.light = light
        self.widget.setBackground("w" if light else "k")
        grey = None
        if light:                                       # data on 1..255 black to white, level 0 (padding) white
            grey = np.repeat(np.arange(256, dtype=np.uint8)[:, None], 3, 1)
            grey[1:] = grey[np.round(np.linspace(0, 255, 255)).astype(int)]
            grey[0] = 255
        if self.img.lut is self.base_lut:
            self.img.setLookupTable(grey)
            grey = self.img.lut                         # as pyqtgraph keeps it: compared by identity above
        self.base_lut = grey
        self.set_locked(self._locked)
        self.stokes.set_light(light)

    # ---------------------------------------------------------------- input
    def _moved(self, pos) -> None:
        if self.on_hover is not None and self.vb.sceneBoundingRect().contains(pos):
            p = self.vb.mapSceneToView(pos)
            self.on_hover(p.y(), p.x())

    # ---------------------------------------------------------------- drawing
    def set_image(self, img: np.ndarray, levels, gamma: float | None = None) -> None:
        """gamma: the image's (core.levels); None keeps the one it has."""
        self._full, self._lim = img, (float(levels[0]), float(levels[1]))
        if gamma is not None:
            self._gamma = float(gamma)
        if self._first:
            ny, nx = img.shape
            self.vb.setRange(QtCore.QRectF(0, 0, nx, ny), padding=0)
            self.guard = ViewGuard(self.vb, nx, ny, floor=self._floor)
            self._first = False
        self.render()

    def _floor(self) -> float | None:
        return None if self.zoom_floor is None else self.zoom_floor()

    def set_gamma(self, gamma: float) -> None:
        """The image drawn again with this gamma; nothing when it already has it."""
        if float(gamma) == self._gamma:
            return
        self._gamma = float(gamma)
        self.render()

    def set_crosshair(self, y: int, x: int) -> None:
        self.hl.setValue(y + 0.5)
        self.vl.setValue(x + 0.5)
        if self.reticle is not None:
            self.reticle.setPos(x + 0.5, y + 0.5)

    def set_locked(self, on: bool) -> None:
        """The cursor locked: the crosshair in its own colour (the reticle yellow with a ring)."""
        self._locked = on
        lock = LOCK_PEN_LIGHT if self.light else LOCK_PEN
        for ln in (self.hl, self.vl):
            ln.setPen(lock if on else CURSOR_PEN)
        if self.reticle is not None:
            self.reticle.set_locked(on)

    def set_reticle(self, on: bool) -> None:
        """The modern look's reticle in place of the two lines across the image, or the lines back. Made once, then
        shown or hidden."""
        if on and self.reticle is None:
            from .overlays import Reticle

            self.reticle = Reticle()
            self.vb.addItem(self.reticle, ignoreBounds=True)
            self.reticle.setPos(self.vl.value(), self.hl.value())
            self.reticle.set_locked(self._locked)
        if self.reticle is not None:
            self.reticle.setVisible(on)
        self.hl.setVisible(not on)
        self.vl.setVisible(not on)

    def set_stokes(self, s: int | None, ns: int, planes: Planes = "stokes") -> None:
        """The label of Stokes s of ns ("Stokes Q") at the view's top left, when ns is 4, or of a parameter
        (ui.stokeslabel); s None: nothing."""
        self.stokes.show_stokes(s, ns, planes)

    def below_stokes(self) -> int:
        """px from the widget's top to the bottom of the Stokes label's box (its text's margin included), where what
        goes under it starts (the slit's hint). From the layout's margin, not from the box's place on the scene, which
        lags a margin change until the layout runs (glass takes the margin off and gives it back)."""
        top = self.widget.ci.layout.getContentsMargins()[1]
        return int(np.ceil(top + self.stokes.pos().y() + self.stokes.boundingRect().height()))

    def set_lut(self, table) -> None:
        """The colour table of the uint8 image (level 0: padding); None: pyqtgraph's own grey (base_lut: the look's)."""
        self.img.setLookupTable(table)

    def show_all(self) -> None:
        """The whole image in view (the double click on the image)."""
        if self._full is not None:
            ny, nx = self._full.shape
            self.vb.setRange(QtCore.QRectF(0, 0, nx, ny), padding=0)

    def set_paused(self, on: bool) -> None:
        """Covered by another view (the 2x2 one): new images are kept, not drawn; drawn once, uncovered. Drawn while
        covered, each step in the 2x2 view cost a fifth render nobody saw."""
        self.paused = bool(on)
        if not self.paused:
            self.render()

    def render(self) -> None:
        if self._full is None or self.paused:
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
        # data pixels per screen pixel, from the view's range (the aspect is locked: the same in x and y). The
        # region clipped to the image undercounts it wherever the view is wider or taller than the image: a
        # 400x360 image in an 80x215 panel was rendered whole (factor 1), 4.5 times the pixels shown. The
        # prototype's backend_pgr.py:52-53 used the clipped region too.
        f = max(1, int(min((vx1 - vx0) / max(1.0, vp.width() * dpr), (vy1 - vy0) / max(1.0, vp.height() * dpr))))
        h, w = (y1 - y0) // f, (x1 - x0) // f
        out = np.empty((h, w), np.uint8)
        table = None if self._gamma == 1 else gamma_table(self._gamma, symmetric_levels(self._lim))
        reduce_u8(img, y0, x0, f, self._lim[0], self._lim[1], out, self.strips, self.parts, table=table)
        self.img.setImage(out, levels=(0, 255), autoDownsample=False)
        self.img.setRect(QtCore.QRectF(x0, y0, w * f, h * f))      # keep data-pixel coordinates
        self.last_render = dict(factor=f, shape=(h, w), region=(y0, y1, x0, x1))


class ViewGuard(QtCore.QObject):
    """Keeps the image in sight: without limits one zooms or drags it out of view and is lost.
    - zoom out down to ZOOM_OUT of the whole-image fit: 1, the whole image and no further, as CRISPEX (0.25 and 0.5
      were tried and had no use); with a floor (a linked image's: the main image's lowest), down to that instead,
      below its own fit when its panel is larger than the main one;
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

    def __init__(self, vb, nx, ny, floor: Callable[[], float | None] | None = None):
        super().__init__(vb)
        self.vb, self.nx, self.ny = vb, nx, ny
        self.floor = floor                              # a lower magnification it may go down to, below its own fit
        self._busy = False
        self._last: tuple | None = None                 # (scale, panel width, panel height, centre x, centre y)
        vb.sigRangeChanged.connect(self._check)

    def lowest(self) -> float | None:
        """The lowest magnification (screen px per data pixel) this view zooms out to on its own: its fit's."""
        W, H = self.vb.width(), self.vb.height()
        if W < 2 or H < 2:
            return None
        return min(W / self.nx, H / self.ny) * self.ZOOM_OUT

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
        # the floor lets a view zoom out below its own fit, never stops it short of it: a linked image smaller than
        # the main one still shows itself whole
        low = self.floor() if self.floor is not None else None
        own = fit * self.ZOOM_OUT
        new = min(max(s, own if low is None else min(low, own)), min(W, H) / self.MIN_PIXELS)
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
