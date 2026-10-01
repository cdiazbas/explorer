"""The lambda-t panel (ROADMAP E4.4): the cursor's pixel over all t and lambda, one cell per measured (t, lambda) on
the index grid (tunings are not evenly spaced), with the current t and lambda as lines; delta-lambda [Å] below when
the header gives the wavelengths (round values placed between the tunings), the tuning index otherwise; t in UT
when the header gives the times, the frame index otherwise. No zoom and no pan: the whole grid is always in view.

Its levels are the core's (levels.panel_levels: Q U V symmetric about 0). From the prototype's app/viewer.py: the
lambda-t dock (846-866), TuningAxis (315), IndexAxis (384), _lam_label and _t_label (1099-1104), _set_lt (2165).
"""
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from ..data.axes import fmt_signed
from .imageview import CURSOR_PEN
from .spectra import SignedAxis

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
        out, placed = [], []
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
    edges and read 0 2 2 4 4 6 6 8 8 under a 10-tuning axis)."""
    GAP = 14                                            # px between two labels along the axis

    def __init__(self, orientation, label_of, n, **kw):
        super().__init__(orientation, **kw)
        self.label_of, self.n = label_of, n
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
        out = []
        for v in values:
            i = int(np.floor(v))
            out.append(self.label_of(i) if 0 <= i < self.n else "")
        return out


class LambdaTPanel:
    """widget: what goes in the dock."""

    def __init__(self, nt: int, nl: int, axes):
        self.nt, self.nl, self.ax = nt, nl, axes
        dl = axes.dlam_A() if axes is not None else None
        self.physical = dl is not None and len(dl) == nl
        self.xl = np.asarray(dl, float) if self.physical else np.arange(nl, dtype=float)
        self.timed = axes is not None and getattr(axes, "t_sec", None) is not None
        bottom = TuningAxis("bottom", self.xl) if self.physical else IndexAxis("bottom", self.lam_label, nl)
        self.w = pg.PlotWidget(axisItems={"bottom": bottom, "left": IndexAxis("left", self.t_label, nt)})
        self.img = pg.ImageItem()
        self.w.addItem(self.img)
        pi = self.w.getPlotItem()
        pi.setMouseEnabled(x=False, y=False)            # the whole (t, lambda) grid always in view; a click picks
        pi.setMenuEnabled(False)
        pi.vb.setMenuEnabled(False)
        pi.hideButtons()
        self.w.setLabel("bottom", "Δλ [Å]" if self.physical else "λ index")
        self.w.setLabel("left", "t [UT]" if self.timed else "t index")
        self.t_line = pg.InfiniteLine(angle=0, pen=CURSOR_PEN)
        self.l_line = pg.InfiniteLine(angle=90, pen=CURSOR_PEN)
        self.w.addItem(self.t_line)
        self.w.addItem(self.l_line)
        self.w.disableAutoRange()
        self.reset_view()
        pi.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        for side in ("left", "bottom"):
            pi.getAxis(side).setCacheMode(QtWidgets.QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.widget = self.w

    def lam_label(self, i: int) -> str:
        return fmt_signed(self.xl[i], 2) if self.physical else str(i)

    def t_label(self, i: int) -> str:
        u = self.ax.utc_str(i, seconds=False) if self.timed else None
        return u or str(i)

    def show(self, lt: np.ndarray, levels) -> None:
        """lt: (nt, nl); levels: the core's. With nothing finite (padding), an empty grid."""
        nt, nl = lt.shape
        if not np.isfinite(lt).any():
            self.img.setImage(np.zeros((nt, nl), np.float32), levels=(0, 1))
        else:
            self.img.setImage(lt, levels=(float(levels[0]), float(levels[1])))
        self.img.setRect(QtCore.QRectF(0, 0, nl, nt))

    def clear(self) -> None:
        self.img.clear()

    def set_lut(self, lut) -> None:
        """The colour table of the lambda-t image (the modern look's colour part); None: grey."""
        self.img.setLookupTable(lut)

    def set_marks(self, colour) -> None:
        """The t and lambda markers in colour, 2 px (1.4 px came out 1 px and grey at 1x), above the image."""
        for ln in (self.t_line, self.l_line):
            ln.setZValue(max(ln.zValue(), 10.0) + 1)
            ln.setPen(pg.mkPen(colour, width=2.0))

    def set_markers(self, t: int, l: int) -> None:  # noqa: E741
        self.t_line.setValue(t + 0.5)
        self.l_line.setValue(l + 0.5)

    def reset_view(self) -> None:
        self.w.setRange(xRange=(0, max(1, self.nl)), yRange=(0, max(1, self.nt)), padding=0)
