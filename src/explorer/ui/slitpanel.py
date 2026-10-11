"""The slit panel (ROADMAP E7.2): two slices along the slit drawn on the image, side by side, sharing the x axis
"along the slit [px]": the time slice (t up, at this Stokes and lambda) and the spectral slice (lambda up, at this
Stokes and t), as CRISPEX's loop path time slice and its spectrum along a slit. A cube with one plane along lambda
or none, main or linked (set_cube, mapped): the time slice alone, its one-row spectral slice saying nothing; with a
single t too (a 2D map), the one row it has drawn as what it is, a curve along the slit. The t and lambda markers;
a vertical line on both where the cursor's pixel lies on the slit, hidden when it is off it. No zoom, no pan, no
pyqtgraph menu (the prototype's F20g): a click or drag picks t (or lambda) from y and the slit's point from x.

What it shows is the core's (core.slitreads): the pixels along the slit, then the slices and their levels. From the
prototype's app/viewer.py: the slit dock (1023-1048), _slit_mark (1922), _slit_pick (1932), _paint_slice (1893).

    panel = SlitPanel(nt, nl, axes); dock it as panel.widget; panel.set_cube(nt, nl, axes): another cube's slices
    panel.set_path((iy, ix)); panel.show(ts, sl, ts_levels, sl_levels); panel.set_markers(t, l); panel.set_cursor(y, x)
"""
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from ..core.levels import gamma_panel
from ..data.axes import dlam_label, fmt_signed
from ..data.tsample import nearest_sample, time_samples
from . import pens, style
from .imageview import CURSOR_PEN
from .lambda_t import MARGIN, IndexAxis, TimeCurve, TuningAxis

ALONG = "along the slit [px]"


class SlitPanel:
    """widget: what goes in the dock. ts, sl: the two plots; ts_img, sl_img: their images."""

    def __init__(self, nt: int, nl: int, axes):
        self._cube(nt, nl, axes)
        self.flat = False                               # a 2D map's slice: a curve (set_cube)
        self.value = "value"                            # its y axis's label
        self.w = pg.GraphicsLayoutWidget()
        self.w.ci.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)     # as lambda-t's: off the panel's edges
        self.ts = self.w.addPlot(row=0, col=0, axisItems={"left": self._t_axis()})
        self.sl = self.w.addPlot(row=0, col=1, axisItems={"left": self._l_axis()})
        self.sl.setXLink(self.ts)
        self.ts_img, self.sl_img = pg.ImageItem(), pg.ImageItem()
        self.ts.addItem(self.ts_img)
        self.sl.addItem(self.sl_img)
        self._left_labels()
        for pl in (self.ts, self.sl):
            pl.setLabel("bottom", ALONG)
            for side in ("left", "bottom"):
                self._axis_style(pl.getAxis(side))
            pl.setMouseEnabled(x=False, y=False)
            pl.hideButtons()
            pl.setMenuEnabled(False)
            pl.vb.setMenuEnabled(False)
            pl.disableAutoRange()
        self.t_line = pg.InfiniteLine(angle=0)
        self.l_line = pg.InfiniteLine(angle=0)
        self.cur_lines = [pg.InfiniteLine(angle=90) for _ in range(2)]     # the cursor, when it is on the slit
        self.ts.addItem(self.t_line)
        self.sl.addItem(self.l_line)
        for pl, ln in zip((self.ts, self.sl), self.cur_lines, strict=True):
            pl.addItem(ln)
            ln.hide()
        # a 2D map's slice: one row, drawn as a curve of its values along the slit (set_cube)
        self.curve = pg.PlotDataItem(pen=pg.mkPen(self._ink(style.is_light()), width=1.5), antialias=True)
        self.ts.addItem(self.curve)
        self.curve.hide()
        self.clear_marks()
        self.spectral = True                            # the spectral slice shown (not for a map: set_cube)
        self.pix: tuple[np.ndarray, np.ndarray] | None = None
        self.on: dict = {}                              # (y, x) -> the first point of the slit on that pixel
        self.cursor: tuple[int, int] | None = None
        self._shown: list = [None, None]                # the arrays on screen: the same one again is not drawn again
        self._raw: list = [(None, None), (None, None)]  # (array, levels) of each as the core gave them
        self.gamma = 1.0                                # their cube's at their Stokes (Session.gamma)
        self._ranges(1)
        self.widget = self.w

    def _cube(self, nt: int, nl: int, axes, times=None, label: str = "λ index") -> None:
        self.nt, self.nl, self.ax, self.label = max(1, nt), max(1, nl), axes, label
        self.steps: np.ndarray | None = None            # the time slice's t when fewer than nt (data.tsample)
        self.tax = times if times is not None else axes  # whose times label t
        dl = axes.dlam_A() if axes is not None else None
        self.physical = dl is not None and len(dl) == nl
        self.xl = np.asarray(dl, float) if self.physical else np.arange(self.nl, dtype=float)
        self.timed = self.tax is not None and getattr(self.tax, "t_sec", None) is not None

    def _t_axis(self) -> pg.AxisItem:
        if self.flat:                                   # a curve's values
            a = pg.AxisItem("left")
            a.enableAutoSIPrefix(False)
            return a
        return IndexAxis("left", self.t_label, self.nt, fine_of=self.t_label_fine)

    @staticmethod
    def _ink(light: bool):
        return TimeCurve._ink(light)                    # a curve's ink, as lambda-t's

    def _l_axis(self) -> pg.AxisItem:
        return TuningAxis("left", self.xl) if self.physical else IndexAxis("left", self.lam_label, self.nl)

    def _left_labels(self) -> None:
        self.ts.setLabel("left", self.value if self.flat else "t [UT]" if self.timed else "t index")
        self.sl.setLabel("left", dlam_label(self.ax) if self.physical else self.label)

    @staticmethod
    def _axis_style(a: pg.AxisItem) -> None:
        a.setStyle(tickLength=4)                        # out of the image, as lambda-t's
        a.setCacheMode(QtWidgets.QGraphicsItem.CacheMode.DeviceCoordinateCache)

    def set_cube(self, nt: int, nl: int, axes, times=None, label: str = "λ index", mapped: bool = False,
                 value: str = "value") -> None:
        """The slices of another cube from now on (a linked cube's slit, Session.set_path): its t and lambda axes;
        times: the axes whose times label its t, when not its own (a map with the main cube's times); label: its axis
        other than t in index units (data.names.slice_names); mapped: a map, whose spectral slice (one row) says
        nothing and is left out, the time slice taking the panel; a map with a single t too, its slice a curve along
        the slit, value its y axis's label (data.names.SliceNames.value). The slices shown go, the next slit's come.
        The same cube again changes nothing."""
        times = times if times is not None else axes
        if ((max(1, nt), max(1, nl), label, mapped, value) == (self.nt, self.nl, self.label, not self.spectral,
                                                                self.value)
                and axes is self.ax and times is self.tax):
            return
        self._cube(nt, nl, axes, times, label)
        self.flat, self.value = mapped and self.nt == 1, value
        self.ts_img.setVisible(not self.flat)
        self.t_line.setVisible(not self.flat)
        self.curve.setVisible(self.flat)
        if mapped and self.spectral:
            self.w.ci.removeItem(self.sl)
        elif not mapped and not self.spectral:
            self.w.ci.addItem(self.sl, row=0, col=1)
        self.spectral = not mapped
        self.ts.setAxisItems({"left": self._t_axis()})
        self.sl.setAxisItems({"left": self._l_axis()})
        self._left_labels()
        for pl in (self.ts, self.sl):
            self._axis_style(pl.getAxis("left"))
        style.default_axes(self.w)                      # the new axes in this theme's ink
        self.clear()
        self._ranges(max(1, self.n))

    # ---------------------------------------------------------------- labels (as lambda-t's)
    def lam_label(self, i: int) -> str:
        return fmt_signed(self.xl[i], 2) if self.physical else str(i)

    def t_label(self, i: int) -> str:
        u = self.tax.utc_str(i, seconds=False) if self.timed else None
        return u or str(i)

    def t_label_fine(self, i: int) -> str:
        u = self.tax.utc_str(i, seconds=True) if self.timed else None
        return u or str(i)

    # ---------------------------------------------------------------- what the core gives
    @property
    def n(self) -> int:
        return 0 if self.pix is None else len(self.pix[0])

    def set_path(self, pix) -> None:
        """The pixels along the slit, (iy, ix) one per point, or None: no slit, the panel empty."""
        if pix is None:
            self.pix, self.on = None, {}
            self.clear()
        else:
            iy, ix = (np.asarray(a, np.int64) for a in pix)
            self.pix, self.on = (iy, ix), {}
            for i, yx in enumerate(zip(iy.tolist(), ix.tolist(), strict=True)):
                self.on.setdefault(yx, i)
            self._ranges(len(iy))
        self._mark()

    def _ranges(self, n: int) -> None:
        if self.flat:                                   # its y range is its values' (show)
            self.ts.setXRange(0, max(1, n), padding=0)
        else:
            self.ts.setRange(xRange=(0, max(1, n)), yRange=(0, self.nt), padding=0)
        self.sl.setYRange(0, self.nl, padding=0)

    def show(self, ts, sl, ts_levels=None, sl_levels=None, gamma: float | None = None) -> None:
        """ts: (nt, n) and sl: (nl, n), None to keep the one shown; their levels the core's (levels.panel_levels);
        gamma: their cube's at their Stokes (None: the one it has; a new one draws both again)."""
        if gamma is not None and float(gamma) != self.gamma:
            self.gamma, self._shown = float(gamma), [None, None]
            if ts is None:
                ts, ts_levels = self._raw[0]
            if sl is None:
                sl, sl_levels = self._raw[1]
        for k, (item, a, lv) in enumerate(((self.ts_img, ts, ts_levels), (self.sl_img, sl, sl_levels))):
            if a is None or a is self._shown[k]:
                continue
            self._shown[k] = a
            self._raw[k] = (a, lv)
            if k == 0 and self.flat:
                self._show_curve(a)
                continue
            lv = lv if lv is not None else (0.0, 1.0)
            if not np.isfinite(a).any():                # nothing read yet, or padding all along
                item.setImage(np.zeros(a.shape, np.float32), levels=(0, 1))
            else:
                a, lv = gamma_panel(a, lv, self.gamma)
                item.setImage(a, levels=(float(lv[0]), float(lv[1])))
            # the time slice's rows over every t: fewer rows than t are the t steps of data.tsample
            if k == 0:
                self.steps = time_samples(self.nt, a.shape[0]) if a.shape[0] < self.nt else None
            item.setRect(QtCore.QRectF(0, 0, a.shape[1], max(a.shape[0], self.nt) if k == 0 else a.shape[0]))

    def _show_curve(self, a) -> None:
        """A 2D map's one-row slice: its values along the slit, the y range theirs."""
        v = np.asarray(a, float).reshape(-1)
        ok = np.isfinite(v)
        if not ok.any():
            self.curve.setData([], [])
            return
        self.curve.setData(np.arange(len(v)) + 0.5, v, connect="finite")
        lo, hi = float(v[ok].min()), float(v[ok].max())
        pad = (hi - lo) * 0.05 if hi > lo else max(abs(lo) * 0.05, 1e-12)
        self.ts.setYRange(lo - pad, hi + pad, padding=0)

    def clear(self) -> None:
        self.curve.setData([], [])
        self._shown = [None, None]
        self._raw = [(None, None), (None, None)]
        self.ts_img.clear()
        self.sl_img.clear()

    def set_markers(self, t: int, l: int) -> None:  # noqa: E741
        self.t_line.setValue(t + 0.5)
        self.l_line.setValue(l + 0.5)

    def set_cursor(self, y: int, x: int) -> None:
        self.cursor = (int(y), int(x))
        self._mark()

    def _mark(self) -> None:
        """A vertical line where the cursor's pixel lies on the slit, hidden elsewhere (the prototype's _slit_mark)."""
        i = self.on.get(self.cursor) if self.cursor is not None else None
        for ln in self.cur_lines:
            if i is None:
                ln.hide()
            else:
                ln.setValue(i + 0.5)
                ln.show()

    def point_at(self, pos) -> tuple[int, str, int] | None:
        """(point along the slit, "t" or "l", its index) under a scene position, or None off both plots."""
        if self.pix is None:
            return None
        for pl, axis, n in ((self.ts, "t", self.nt), (self.sl, "l", self.nl)):
            if (pl is self.ts or self.spectral) and pl.vb.sceneBoundingRect().contains(pos):
                q = pl.vb.mapSceneToView(pos)
                v = (nearest_sample(self.steps, q.y()) if axis == "t" and self.steps is not None
                     else int(np.clip(int(q.y()), 0, n - 1)))
                return int(np.clip(int(q.x()), 0, self.n - 1)), axis, v
        return None

    # ---------------------------------------------------------------- the look and the theme
    def set_lut(self, lut) -> None:
        """The colour table of both slices (the modern look's, the Stokes shown's, as lambda-t's); None: grey."""
        self.ts_img.setLookupTable(lut)
        self.sl_img.setLookupTable(lut)

    def set_marks(self, colour) -> None:
        """The markers in colour (pens.mark), above the images."""
        for ln in (self.t_line, self.l_line, *self.cur_lines):
            ln.setZValue(max(ln.zValue(), 10.0) + 1)
            pens.mark(ln, colour)

    def clear_marks(self) -> None:
        """The classic look's red markers."""
        for ln in (self.t_line, self.l_line, *self.cur_lines):
            pens.mark(ln, CURSOR_PEN.color())

    def set_light(self, light: bool) -> None:
        """The axes and a map's curve in this theme's ink; the background is the shell's (a card, or the plots' own)."""
        style.default_axes(self.w)
        self.curve.setPen(pg.mkPen(self._ink(light), width=1.5))

    def set_background(self, colour) -> None:
        self.w.setBackground(colour)
