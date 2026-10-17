"""The lambda-t panel (ROADMAP E4.4): the cursor's pixel over all t and lambda, one cell per measured (t, lambda) on
the index grid (tunings are not evenly spaced), with the current t and lambda as lines; delta-lambda [Å] below when
the header gives the wavelengths (round values placed between the tunings), the tuning index otherwise; t in UT
when the header gives the times, the frame index otherwise. No zoom and no pan: the whole grid is always in view.
The Stokes it shows ("Stokes Q") at the top left, when the cube has the four (set_stokes, ui.stokeslabel).

A cube with one plane along its other axis (a map, a single tuning: data.names.SliceNames.mapped) has a lambda-t one
cell wide: TimeCurve draws it as what it is, the cursor's value against t, the current t as a line; a click picks t.

Fewer rows than t (a cap on the t steps, data.tsample): each row is drawn over the t it stands for, the axes and the
current t's line stay in the cube's own t, and a click picks the nearest t shown.

Its levels are the core's (levels.panel_levels: Q U V symmetric about 0). From the prototype's app/viewer.py: the
lambda-t dock (846-866), TuningAxis (315), IndexAxis (384), _lam_label and _t_label (1099-1104), _set_lt (2165).
"""
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from ..core.levels import gamma_panel
from ..data.axes import dlam_label, fmt_signed, tunings
from ..data.tsample import nearest_sample, time_samples
from . import pens, style
from .imageview import CURSOR_PEN
from .spectra import SignedAxis
from .stokeslabel import StokesLabel

MARGIN = 9                                              # px round the plot, as the spectra's layout keeps


class TuningAxis(SignedAxis):
    """lambda-t's x axis. The image stays on the tuning index grid, but its ticks are round delta-lambda values, as
    on the spectra, each placed where it falls between two tunings' centres (piecewise linear). Ticks at the
    tunings themselves read -0.33 -0.17 -0.09 -0.01 +0.07 under the spectra's -0.2 0 +0.2."""

    def __init__(self, orientation, xl):
        super().__init__(orientation, plus=True)
        xl = np.asarray(xl, float)
        c = np.arange(len(xl)) + 0.5                    # cell centres on the index grid
        order = np.argsort(xl)
        self.xl, self.c = xl[order], c[order]           # np.interp needs it increasing

    def _to_lambda(self, v):
        cs = np.sort(self.c)
        ls = self.xl if self.c[0] < self.c[-1] else self.xl[::-1]
        return float(np.interp(v, cs, ls))

    def tickValues(self, minVal, maxVal, size):
        lo, hi = sorted((minVal, maxVal))
        a, b = sorted((self._to_lambda(lo), self._to_lambda(hi)))
        fm = QtGui.QFontMetrics(self.style.get("tickFont") or QtGui.QFont())
        room = fm.horizontalAdvance("−0.00") + 10  # px a label needs along the axis
        out: list = []
        placed: list = []
        for sp, vs in super().tickValues(a, b, size):
            pos = []
            for u in vs:
                if not self.xl[0] - 1e-9 <= u <= self.xl[-1] + 1e-9:
                    continue
                q = float(np.interp(u, self.xl, self.c))
                px = (q - lo) / (hi - lo) * size if hi > lo else 0
                # the wide-spaced tunings (towards the continuum) take few cells: two round values can land a few
                # px apart ("+0.4+0.6"). A tick is kept only with room for its label from every label already
                # placed, of any level: checked per level, as the prototype did, a minor +0.3 landed on a major +0.4
                # (the 6173 cube's continuum side)
                if all(abs(px - o) >= room for o in placed):
                    pos.append(q)
                    placed.append(px)
            out.append((sp, pos))
        return out

    def tickStrings(self, values, scale, spacing):
        return super().tickStrings([self._to_lambda(v) for v in values], scale, spacing)


class IndexAxis(pg.AxisItem):
    """An axis on the index grid, labelled with physical values: ticks at cell centres (i + 0.5) every 1, 2, 5, 10,
    20... cells, as many as the labels leave room for, each cell labelled once (pyqtgraph's own ticks sat on cell
    edges and read 0 2 2 4 4 6 6 8 8 under a 10-tuning axis). fine_of: finer labels, taken when label_of's would
    repeat (times to the minute with ticks 20 s apart read 08:17 08:17 08:16)."""
    GAP = 14                                            # px between two labels along the axis

    def __init__(self, orientation, label_of, n, fine_of=None, **kw):
        super().__init__(orientation, **kw)
        self.label_of, self.n, self.fine_of = label_of, n, fine_of
        self.enableAutoSIPrefix(False)

    def _label_px(self):
        fm = QtGui.QFontMetrics(self.style.get("tickFont") or QtGui.QFont())
        if self.orientation in ("left", "right"):
            return fm.height() + self.GAP
        return max(fm.horizontalAdvance(self.label_of(i)) for i in {0, self.n // 2, self.n - 1}) + self.GAP

    def tickValues(self, minVal, maxVal, size):
        lo, hi = sorted((minVal, maxVal))
        i0, i1 = max(0, int(np.ceil(lo - 0.5))), min(self.n - 1, int(np.floor(hi - 0.5)))
        if self.n < 1 or i1 < i0 or size <= 0:
            return []
        fit = max(1, int(size / self._label_px()))      # labels the axis has room for over [lo, hi]
        step = next(m * 10 ** e for e in range(12) for m in (1, 2, 5) if (hi - lo) / (m * 10 ** e) <= fit)
        return [(step, [i + 0.5 for i in range(-(-i0 // step) * step, i1 + 1, step)])]

    def tickStrings(self, values, scale, spacing):
        cells = [int(np.floor(v)) for v in values]
        out = [self.label_of(i) if 0 <= i < self.n else "" for i in cells]
        shown = [x for x in out if x]
        if self.fine_of is not None and len(set(shown)) < len(shown):
            out = [self.fine_of(i) if 0 <= i < self.n else "" for i in cells]
        return out


def fixed_plot(pi) -> None:
    """A panel's plot as a control: no zoom, no pan, no pyqtgraph menu nor its buttons; a click picks."""
    pi.setMouseEnabled(x=False, y=False)
    pi.setMenuEnabled(False)
    pi.vb.setMenuEnabled(False)
    pi.hideButtons()


def axis_style(a: pg.AxisItem) -> None:
    """Ticks out of the image, to the labels (pyqtgraph's 5 px went in); cached: a range change re-renders only the
    axes that moved."""
    a.setStyle(tickLength=4)
    a.setCacheMode(QtWidgets.QGraphicsItem.CacheMode.DeviceCoordinateCache)


class GridAxes:
    """t and lambda of a panel on the index grid and their axes' labels: lambda-t's, TimeCurve's and the slit
    panel's. tax: the axes whose times label t; xl: each tuning's delta-lambda [Å] when physical, else its index."""

    def _grid_axes(self, nl: int, axes, times=None) -> None:
        self.physical, self.xl = tunings(axes, nl)
        self.tax = times if times is not None else axes
        self.timed = self.tax is not None and getattr(self.tax, "t_sec", None) is not None

    @property
    def t_title(self) -> str:
        return "t [UT]" if self.timed else "t index"

    def lam_label(self, i: int) -> str:
        return fmt_signed(self.xl[i], 2) if self.physical else str(i)

    def t_label(self, i: int) -> str:
        u = self.tax.utc_str(i, seconds=False) if self.timed else None
        return u or str(i)

    def t_label_fine(self, i: int) -> str:
        u = self.tax.utc_str(i, seconds=True) if self.timed else None
        return u or str(i)


class LambdaTPanel(GridAxes):
    """widget: what goes in the dock."""

    def __init__(self, nt: int, nl: int, axes, label: str = "λ index"):
        """label: its axis other than t in index units, when not in Å (data.names.slice_names)."""
        self.nt, self.nl, self.ax = nt, nl, axes
        self._grid_axes(nl, axes)
        bottom = TuningAxis("bottom", self.xl) if self.physical else IndexAxis("bottom", self.lam_label, nl)
        left = IndexAxis("left", self.t_label, nt, fine_of=self.t_label_fine)
        self.w = pg.PlotWidget(axisItems={"bottom": bottom, "left": left})
        self.img = pg.ImageItem()
        self.gamma = 1.0                                # its cube's at the Stokes shown (Session.gamma)
        self._shown: tuple | None = None                # (lt, levels) as the core gave them
        self.steps: np.ndarray | None = None            # the t of its rows when fewer than nt (data.tsample)
        self.w.addItem(self.img)
        pi = self.w.getPlotItem()
        fixed_plot(pi)                                  # the whole (t, lambda) grid always in view
        self.w.setLabel("bottom", dlam_label(axes) if self.physical else label)
        self.w.setLabel("left", self.t_title)
        self.t_line = pg.InfiniteLine(angle=0)
        self.l_line = pg.InfiniteLine(angle=90)
        for ln in (self.t_line, self.l_line):           # markers, as the spectra's lambda line (pens.mark)
            pens.mark(ln, CURSOR_PEN.color())
        self.w.addItem(self.t_line)
        self.w.addItem(self.l_line)
        self.w.disableAutoRange()
        self.stokes = StokesLabel(pi.vb, style.is_light())
        self.reset_view()
        pi.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        for side in ("left", "bottom"):
            axis_style(pi.getAxis(side))
        self.widget = self.w

    def set_light(self, light: bool) -> None:
        """The axes and the Stokes label in this theme's ink; the background is the shell's (a card, or the plots'
        own)."""
        style.default_axes(self.w)
        self.stokes.set_light(light)

    def set_stokes(self, s: int | None, ns: int) -> None:
        """The label of Stokes s of ns ("Stokes Q") at the top left, when ns is 4 (ui.stokeslabel); s None: nothing."""
        self.stokes.show_stokes(s, ns)

    def show(self, lt: np.ndarray, levels, gamma: float | None = None) -> None:
        """lt: (nt, nl), or fewer rows: the t steps of data.tsample; levels: the core's; gamma: its cube's at its
        Stokes (None: the one it has). With nothing finite (padding), an empty grid."""
        self._shown = (lt, levels)
        if gamma is not None:
            self.gamma = float(gamma)
        n, nl = lt.shape
        self.steps = time_samples(self.nt, n) if n < self.nt else None
        if not np.isfinite(lt).any():
            self.img.setImage(np.zeros((n, nl), np.float32), levels=(0, 1))
        else:
            a, lv = gamma_panel(lt, levels, self.gamma)
            self.img.setImage(a, levels=(float(lv[0]), float(lv[1])))
        self.img.setRect(QtCore.QRectF(0, 0, nl, max(n, self.nt)))   # the rows over every t

    def set_gamma(self, gamma: float) -> None:
        """What it shows drawn again with this gamma; nothing when it already has it."""
        if float(gamma) == self.gamma:
            return
        self.gamma = float(gamma)
        if self._shown is not None:
            self.show(*self._shown)

    def clear(self) -> None:
        self._shown = None
        self.img.clear()

    def set_lut(self, lut) -> None:
        """The colour table of the lambda-t image (the modern look's colour part); None: grey."""
        self.img.setLookupTable(lut)

    def set_marks(self, colour) -> None:
        """The t and lambda markers in colour (pens.mark: 1.4 px came out 1 px and grey at 1x), above the image."""
        for ln in (self.t_line, self.l_line):
            ln.setZValue(max(ln.zValue(), 10.0) + 1)
            pens.mark(ln, colour)

    def clear_marks(self) -> None:
        """The classic look's red markers again."""
        for ln in (self.t_line, self.l_line):
            pens.mark(ln, CURSOR_PEN.color())

    def set_markers(self, t: int, l: int) -> None:  # noqa: E741
        self.t_line.setValue(t + 0.5)
        self.l_line.setValue(l + 0.5)

    def pick(self, q) -> dict:
        """The indices under q, a point in the plot's coordinates: t from y (the nearest shown), lambda from x."""
        t = (int(np.clip(int(q.y()), 0, self.nt - 1)) if self.steps is None else nearest_sample(self.steps, q.y()))
        return {"l": int(np.clip(int(q.x()), 0, self.nl - 1)), "t": t}

    def reset_view(self) -> None:
        self.w.setRange(xRange=(0, max(1, self.nl)), yRange=(0, max(1, self.nt)), padding=0)


class TimeCurve(GridAxes):
    """lambda-t of a cube with one plane along its other axis: the cursor's value against t, t along x on the index
    grid (t's ticks and labels as lambda-t's), the current t as a vertical line; value: the y axis's label
    (data.names.SliceNames.value). The same calls as LambdaTPanel: what the core gives is (nt, 1), or (nt,)."""

    def __init__(self, nt: int, axes, value: str = "value", light: bool | None = None):
        """axes: whose times label t (a map's own, else the main cube's when its frames are the main cube's t)."""
        self.nt, self.nl, self.ax = nt, 1, axes
        self._grid_axes(1, None, axes)
        self.w = pg.PlotWidget(axisItems={"bottom": IndexAxis("bottom", self.t_label, nt, fine_of=self.t_label_fine)})
        pi = self.w.getPlotItem()
        fixed_plot(pi)                                  # the whole t range always in view
        self.w.setLabel("bottom", self.t_title)
        self.w.setLabel("left", value)
        pi.getAxis("left").enableAutoSIPrefix(False)    # its "(x1e-08)" ran off the panel; the ticks say it
        light = style.is_light() if light is None else light
        self.curve = self.w.plot(pen=pg.mkPen(self._ink(light), width=1.5), antialias=True)
        self.t_line = pg.InfiniteLine(angle=90)
        pens.mark(self.t_line, CURSOR_PEN.color())
        self.w.addItem(self.t_line)
        self.x = np.arange(nt) + 0.5                    # cell centres, where t's ticks are
        self.steps: np.ndarray | None = None            # the t of its points when fewer than nt (data.tsample)
        self.stokes = StokesLabel(pi.vb, light)
        self.reset_view()
        pi.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        for side in ("left", "bottom"):
            axis_style(pi.getAxis(side))
        self.widget = self.w

    @staticmethod
    def _ink(light: bool) -> QtGui.QColor:
        return QtGui.QColor(30, 30, 34) if light else QtGui.QColor(255, 255, 255)     # the spectra's classic curves'

    def set_light(self, light: bool) -> None:
        style.default_axes(self.w)
        self.curve.setPen(pg.mkPen(self._ink(light), width=1.5))
        self.stokes.set_light(light)

    def set_stokes(self, s: int | None, ns: int) -> None:
        self.stokes.show_stokes(s, ns)

    def show(self, lt: np.ndarray, levels=None, gamma: float | None = None) -> None:
        """lt: (nt, 1) or (nt,), or fewer: the t steps of data.tsample, each at its t; the y range its finite values'
        (nothing finite: the curve empty). A curve has no gamma."""
        v = np.asarray(lt, float).reshape(-1)[:self.nt]
        self.steps = time_samples(self.nt, len(v)) if len(v) < self.nt else None
        ok = np.isfinite(v)
        if not ok.any():
            self.curve.setData([], [])
            return
        self.curve.setData(self.x[:len(v)] if self.steps is None else self.steps + 0.5, v, connect="finite")
        lo, hi = float(v[ok].min()), float(v[ok].max())
        pad = (hi - lo) * 0.05 if hi > lo else max(abs(lo) * 0.05, 1e-12)
        self.w.setYRange(lo - pad, hi + pad, padding=0)

    def clear(self) -> None:
        self.curve.setData([], [])

    def set_lut(self, lut) -> None:
        """A curve has no colour table."""

    def set_gamma(self, gamma: float) -> None:
        """Nor a gamma: its values are drawn as they are."""

    def set_marks(self, colour) -> None:
        self.t_line.setZValue(max(self.t_line.zValue(), 10.0) + 1)
        pens.mark(self.t_line, colour)

    def clear_marks(self) -> None:
        pens.mark(self.t_line, CURSOR_PEN.color())

    def set_markers(self, t: int, l: int = 0) -> None:  # noqa: E741
        self.t_line.setValue(t + 0.5)

    def pick(self, q) -> dict:
        """t under q, a point in the plot's coordinates (from x; the nearest shown)."""
        if self.steps is not None:
            return {"t": nearest_sample(self.steps, q.x())}
        return {"t": int(np.clip(int(q.x()), 0, self.nt - 1))}

    def reset_view(self) -> None:
        self.w.setXRange(0, max(1, self.nt), padding=0)
