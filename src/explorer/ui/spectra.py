"""The spectra panel (ROADMAP E4.3): one plot per Stokes, the four of I Q U V as 2x2 (I Q / U V), any other number in
a column; x shared, delta-lambda [Å] below and the Doppler velocity above when the header gives the wavelengths,
the tuning index otherwise; the cursor's lambda as a line; Stokes I titled in its power of ten of BUNIT, Q U V in % of
I_c when the continuum tuning is known.

What is drawn and in which units is decided by the core: spectra in plot units (yrange.spectrum, plot_units), each
plot's y range (yrange: grows while the cursor moves, refits at rest, fixed by the padlock) and I's power of ten.
This panel only draws. From the prototype's app/viewer.py: the spectrum dock (813-844), the axes' caches (908-910),
_decimals (295), SignedAxis (302), VelocityAxis (351), _label_stokes (1205), the drawing part of _set_spectra (1923)
and ResizeFreezer (440).
"""
import os

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from .._name import APP_NAME
from ..data.axes import C_KMS, STOKES, SUP, fmt_signed, unit_text
from .imageview import CURSOR_PEN

X_PAD = 0.04                                            # of the lambda span, each side
AXIS_W = 56                                             # px: tick digits changing never re-lays out the plots
FREEZE_VAR = f"{APP_NAME.upper()}_RESIZE_FREEZE"


def decimals(spacing: float) -> int:
    """Enough decimals for ticks `spacing` apart: 0 down to 1, then as many as needed (a fixed 2 wrote 0.00 0.00
    −0.00 under Q U V)."""
    if not spacing > 0:
        return 2
    return 0 if spacing >= 1 else min(6, int(np.ceil(-np.log10(spacing) - 1e-9)))


class SignedAxis(pg.AxisItem):
    """Tick labels with a typographic minus and no automatic SI prefix ('x1e-09'); plus=True also writes '+'
    (offsets such as delta-lambda and velocity)."""

    def __init__(self, orientation, plus=False, **kw):
        super().__init__(orientation, **kw)
        self.plus = plus
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        nd = decimals(spacing)
        if self.plus:
            return [fmt_signed(v, nd) if abs(v) > 1e-12 else "0" for v in values]
        return [f"{v:.{nd}f}".replace("-", "−") for v in values]


class VelocityAxis(SignedAxis):
    """Doppler velocity over a delta-lambda [Å] axis: ticks at round velocities. k: km/s per Å."""

    def __init__(self, orientation, k):
        super().__init__(orientation, plus=True)
        self.k = k

    def tickValues(self, minVal, maxVal, size):
        return [(sp / self.k, [v / self.k for v in vs])
                for sp, vs in super().tickValues(minVal * self.k, maxVal * self.k, size)]

    def tickStrings(self, values, scale, spacing):
        nd = decimals(spacing * self.k)
        return [fmt_signed(v * self.k, nd) if abs(v * self.k) > 1e-9 else "0" for v in values]


class ResizeFreezer(QtCore.QObject):
    """While the panel is resized (a window edge or a dock splitter dragged), a scaled snapshot of it stands in, and
    the plots are laid out once when resizing pauses for QUIET_MS: the four plots cost 60-75 ms per resize step on
    bellatrix (12 axes re-laid out). EXPLORER_RESIZE_FREEZE=0 turns it off."""
    QUIET_MS = 150
    READY_MS = 1000                                     # not during the start-up layout

    def __init__(self, panel: QtWidgets.QWidget):
        super().__init__(panel)
        self.panel = panel
        self.stack = QtWidgets.QStackedWidget()
        self.snap = QtWidgets.QLabel()
        self.snap.setScaledContents(True)
        self.snap.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Ignored)
        self.stack.addWidget(panel)
        self.stack.addWidget(self.snap)
        self.timer = QtCore.QTimer(self, singleShot=True, interval=self.QUIET_MS)
        self.timer.timeout.connect(lambda: self.stack.setCurrentWidget(self.panel))
        self.enabled = os.environ.get(FREEZE_VAR, "1") != "0"
        self.stack.installEventFilter(self)
        self._ready = False
        QtCore.QTimer.singleShot(self.READY_MS, lambda: setattr(self, "_ready", True))

    def eventFilter(self, obj, e):
        if e.type() == QtCore.QEvent.Type.Resize and self.enabled and self._ready and obj.isVisible():
            if self.stack.currentWidget() is self.panel and self.panel.width() > 0:
                self.snap.setPixmap(self.panel.grab())
                self.stack.setCurrentWidget(self.snap)
            self.timer.start()
        return False


class SpectraPanel:
    """ns plots in a GraphicsLayoutWidget; widget: what goes in the dock."""

    def __init__(self, ns: int, nl: int, axes, light: bool = False):
        """axes: the cube's physical axes (data.axes.Axes); light: dark ink on a light background."""
        self.ns, self.nl, self.ax = ns, nl, axes
        dl = axes.dlam_A() if axes is not None else None
        self.physical = dl is not None and len(dl) == nl
        self.xl = np.asarray(dl, float) if self.physical else np.arange(nl, dtype=float)
        vk = C_KMS / (axes.lam0_nm * 10.0) if self.physical and axes.lam0_nm else None     # km/s per Å
        pad = X_PAD * (float(self.xl.max() - self.xl.min()) or 1.0)
        self.x_range = (float(self.xl.min()) - pad, float(self.xl.max()) + pad)
        self.iscale: float | None = None
        self.w = pg.GraphicsLayoutWidget()
        self.plots, self.curves, self.lines = [], [], []
        ncol = 2 if ns == 4 else 1
        for k in range(ns):
            axis_items = {"bottom": SignedAxis("bottom", plus=self.physical), "left": SignedAxis("left")}
            if vk:
                axis_items["top"] = VelocityAxis("top", vk)
            p = self.w.addPlot(row=k // ncol, col=k % ncol, axisItems=axis_items)
            p.showGrid(x=True, y=True, alpha=0.2)
            p.getAxis("left").setWidth(AXIS_W)
            if k:
                p.setXLink(self.plots[0])
            p.disableAutoRange()
            p.setXRange(*self.x_range, padding=0)
            p.setMenuEnabled(False)                     # no pyqtgraph menu (the prototype turned it off)
            p.vb.setMenuEnabled(False)
            if not self.physical:
                p.getAxis("bottom").setTickSpacing(major=max(1, -(-nl // 7)), minor=1)
            c = p.plot(pen=pg.mkPen((30, 30, 34) if light else "w", width=1.5), symbol="o", symbolSize=3)
            ln = pg.InfiniteLine(angle=90, pen=CURSOR_PEN)
            p.addItem(ln)
            for side in ("left", "bottom", "top"):      # a range change re-renders only the axes that moved
                p.getAxis(side).setCacheMode(QtWidgets.QGraphicsItem.CacheMode.DeviceCoordinateCache)
            self.plots.append(p)
            self.curves.append(c)
            self.lines.append(ln)
        for p in self.plots[-ncol:]:
            p.setLabel("bottom", "Δλ [Å]" if self.physical else "λ index")
        if vk:
            for p in self.plots[:ncol]:
                p.showAxis("top")
                p.setLabel("top", "v [km s<sup>−1</sup>]")
        self.label_stokes()
        self.freezer = ResizeFreezer(self.w)
        self.widget = self.freezer.stack

    def label_stokes(self) -> None:
        """Stokes I in powers of ten of BUNIT; Q U V in % of I_c when the continuum tuning is known."""
        cont = getattr(self.ax, "cont", None)
        bunit = getattr(self.ax, "bunit", None)
        for k, p in enumerate(self.plots):
            name = STOKES[k] if self.ns > 1 else "I"
            if k == 0 or cont is None:
                e = f"10{str(int(np.log10(self.iscale))).translate(SUP)} " if self.iscale else ""
                u = unit_text(bunit) if bunit else ""
                p.setLabel("left", f"{name} [{e}{u}]" if (e or u) else name)
            else:
                p.setLabel("left", f"{name}/I<sub>c</sub> [%]")

    def set_units(self, iscale: float | None) -> None:
        self.iscale = iscale
        self.label_stokes()

    def show(self, spec: np.ndarray) -> None:
        """spec: (ns, nl) in plot units; a Stokes with nothing finite (padding) is left empty, without warnings."""
        for k in range(self.ns):
            y = spec[k]
            if not np.isfinite(y).any():
                self.curves[k].setData([], [])
                continue
            self.curves[k].setData(self.xl, y, skipFiniteCheck=True)

    def clear(self) -> None:
        for c in self.curves:
            c.setData([], [])

    def set_range(self, k: int, r) -> None:
        self.plots[k].setYRange(*r, padding=0)

    def set_lambda(self, l: int) -> None:  # noqa: E741
        x = float(self.xl[l])
        for ln in self.lines:
            ln.setValue(x)

    def reset_view(self) -> None:
        self.plots[0].setXRange(*self.x_range, padding=0)      # the others are x-linked to it
