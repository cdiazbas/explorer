"""The spectra panel (ROADMAP E4.3): one plot per Stokes, the four of I Q U V as 2x2 (I Q / U V), any other number in
a column; x shared, delta-lambda [Å] below and the Doppler velocity above when the header gives the wavelengths,
the tuning index otherwise; the cursor's lambda as a line; Stokes I titled in its power of ten of BUNIT, Q U V in % of
I_c when the continuum tuning is known, with their noise level at +-sigma: lines or a band, as the look says.

What is drawn and in which units is decided by the core: spectra in plot units (yrange.spectrum, plot_units), each
plot's y range (yrange: grows while the cursor moves, refits at rest, fixed by the padlock) and I's power of ten.
This panel only draws. From the prototype's app/viewer.py: the spectrum dock (813-844), the axes' caches (908-910),
_decimals (295), SignedAxis (302), VelocityAxis (351), _label_stokes (1205), the drawing part of _set_spectra (1923)
and ResizeFreezer (440).
"""
import os

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from .._name import APP_NAME
from ..data.axes import C_KMS, STOKES, SUP, dlam_label, fmt_signed, tunings, unit_text
from . import pens, style
from .imageview import CURSOR_PEN
from .padlock import PanelLock

GRID = 0.07                                             # the grid's alpha: at 0.2 its lines read as a mesh
# the lambda line: at 1 px (CURSOR_PEN) its red was there, (243, 89, 89), but over the black plot and its grid it read
# grey; as a marker (pens.mark: 2 px at 1x, 1.5 on Retina), the same as lambda-t's. The image's crosshair stays 1 px
DOT, RING = 4, 9                                        # px: each measured point; the ring round the one read

X_PAD = 0.04                                            # of the lambda span, each side
AXIS_W = 56                                             # px: tick digits changing never re-lays out the plots
FREEZE_VAR = f"{APP_NAME.upper()}_RESIZE_FREEZE"
# Q U V's +-sigma (core.noise): CRISPEX's dashed lines at +-1 sigma in the curves' colour (crispex.pro L8554-8562), or
# a band between them; which, the look says (its part "band": modern and glass)
NOISE_STYLES = ("lines", "band")
NOISE_ALPHA = {"lines": 150, "band": 34}                # of the curves' ink: the lines', the band's fill
NOISE_DASH = [5, 3]                                     # longer than the modern look's zero line, which is dashed too


def decimals(spacing: float) -> int:
    """Enough decimals for ticks `spacing` apart: 0 down to 1, then as many as needed (a fixed 2 wrote 0.00 0.00
    −0.00 under Q U V)."""
    if not spacing > 0:
        return 2
    return 0 if spacing >= 1 else min(6, int(np.ceil(-np.log10(spacing) - 1e-9)))


class SignedAxis(pg.AxisItem):
    """Tick labels with a typographic minus and no automatic SI prefix ('x1e-09'); plus=True also writes '+'
    (offsets such as delta-lambda and velocity).

    One level of ticks, every 1, 2 or 5 x 10^k: pyqtgraph's own two levels (major 1, minor 0.5) were labelled apart,
    so one axis read 2.5 2 1.5 1, and the decimals of a minor level it did not label gave 0.0 and +0.50. The finest
    step that leaves GAP px between each two neighbouring labels, measured in the axis's font: counted against a
    guessed label, a 190-px plot got 0 +0.5 where -0.2 0 +0.2 +0.4 +0.6 fitted, 9.5 px apart."""
    GAP = (8, 8)                                        # px between two labels: stacked (y), side by side (x)

    def __init__(self, orientation, plus=False, **kw):
        super().__init__(orientation, **kw)
        self.plus = plus
        self.enableAutoSIPrefix(False)
        self.finest: float | None = None                # the step of the ticks last chosen: their labels' decimals

    def fmt(self, values, step):
        nd = decimals(step)
        if self.plus:
            return [fmt_signed(v, nd) if abs(v) > 1e-12 else "0" for v in values]
        return [f"{v:.{nd}f}".replace("-", "−") for v in values]

    def tickValues(self, minVal, maxVal, size):
        lo, hi = sorted((minVal, maxVal))
        if not (hi > lo) or size <= 0:
            return []
        fm = QtGui.QFontMetrics(self.style.get("tickFont") or self.font())
        across = self.orientation in ("left", "right")
        e = int(np.floor(np.log10((hi - lo) * 10 / size)))     # a step of about 10 px
        for k in range(e, e + 12):
            for m in (1, 2, 5):
                step = m * 10.0 ** k
                px = step / (hi - lo) * size
                if px < 10:
                    continue
                first = np.ceil(lo / step - 1e-9) * step
                values = [round(float(v), 12) for v in np.arange(first, hi + step * 1e-9, step)]
                if across:
                    need = float(fm.height() + self.GAP[0])
                else:
                    w = [fm.horizontalAdvance(t) for t in self.fmt(values, step)]
                    need = max(((a + b) / 2 for a, b in zip(w, w[1:], strict=False)), default=0) + self.GAP[1]
                if px >= need:
                    self.finest = step
                    return [(step, values)]
        return []

    def tickStrings(self, values, scale, spacing):
        return self.fmt(values, self.finest if self.finest else spacing)


class VelocityAxis(SignedAxis):
    """Doppler velocity over a delta-lambda [Å] axis: ticks at round velocities. k: km/s per Å.

    No grid of its own: with showGrid(x=True) the top axis drew its lines too, at the velocities' places, beside the
    bottom axis's at the delta-lambdas', so the grid came in near pairs (+10 by +0.2, +20 by +0.4). Its ticks take
    the pen's alpha: pyqtgraph draws them at 255 unless told, and under the glass look's frame (white at alpha 60)
    they stood out bright white. bare: the box's edge only, no ticks (a lower row's top, under the row that has
    the labels)."""

    def __init__(self, orientation, k):
        super().__init__(orientation, plus=True)
        self.k = k
        self.bare = False

    def setGrid(self, grid):
        super().setGrid(False)

    def setPen(self, *args, **kwargs):
        super().setPen(*args, **kwargs)
        if hasattr(self, "style"):                      # AxisItem's __init__ sets its pen before its style
            self.setStyle(tickAlpha=self.pen().color().alpha())

    def tickValues(self, minVal, maxVal, size):
        if self.bare:
            return []
        return [(sp / self.k, [v / self.k for v in vs])
                for sp, vs in super().tickValues(minVal * self.k, maxVal * self.k, size)]

    def tickStrings(self, values, scale, spacing):
        return self.fmt([v * self.k for v in values], self.finest if self.finest else spacing * self.k)


class FrameAxis(pg.AxisItem):
    """A side of the plot's box with nothing on it: no values, no ticks, no grid. The box was open on the right; a
    plain AxisItem there drew its own grid too, at pyqtgraph's tick places, between the left axis's lines, and ticks
    of length 0 still drew as dots of the pen's width."""

    def __init__(self, orientation, **kw):
        super().__init__(orientation, **kw)
        self.setStyle(showValues=False, tickLength=0)

    def setGrid(self, grid):
        super().setGrid(False)

    def tickValues(self, minVal, maxVal, size):
        return []


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

    def __init__(self, ns: int, nl: int, axes, light: bool = False, label: str | None = None,
                 value: str | None = None):
        """axes: the cube's physical axes (data.axes.Axes); light: dark ink on a light background; label: the x axis
        in index units of an axis not known to be lambda ("Blos index", data.names.slice_names), "λ index" without;
        value: what a cube without Stokes holds when it is not intensity along lambda ("Blos"), "I" without."""
        self.ns, self.nl, self.ax = ns, nl, axes
        self.value = value or "I"
        self.physical, self.xl = tunings(axes, nl)
        vk = C_KMS / (axes.lam0_nm * 10.0) if self.physical and axes.lam0_nm else None     # km/s per Å
        pad = X_PAD * (float(self.xl.max() - self.xl.min()) or 1.0)
        self.x_range = (float(self.xl.min()) - pad, float(self.xl.max()) + pad)
        self.iscale: float | None = None
        self.w = pg.GraphicsLayoutWidget()
        self.plots: list = []
        self.curves: list = []
        self.lines: list = []
        self.rings: list = []                           # the point read at this lambda, on each profile
        self._y: dict[int, np.ndarray] = {}             # Stokes -> the profile shown
        self._l = 0
        ncol = 2 if ns == 4 else 1
        for k in range(ns):
            axis_items = {"bottom": SignedAxis("bottom", plus=self.physical), "left": SignedAxis("left"),
                          "right": FrameAxis("right"), "top": VelocityAxis("top", vk) if vk else FrameAxis("top")}
            p = self.w.addPlot(row=k // ncol, col=k % ncol, axisItems=axis_items)
            p.showGrid(x=True, y=True, alpha=GRID)
            p.getAxis("left").setWidth(AXIS_W)
            if k:
                p.setXLink(self.plots[0])
            p.disableAutoRange()
            p.setXRange(*self.x_range, padding=0)
            p.setMouseEnabled(x=False, y=False)             # a control: click or drag picks lambda (gestures)
            p.setMenuEnabled(False)                     # no pyqtgraph menu (the prototype turned it off)
            p.vb.setMenuEnabled(False)
            if not self.physical:
                p.getAxis("bottom").setTickSpacing(major=max(1, -(-nl // 7)), minor=1)
            # antialiased (a 1.5-px line drew stairs at dpr 1 and over X11: greys only, so grey tiles still), each
            # measured point a dot of the line's own ink
            ink = QtGui.QColor(30, 30, 34) if light else QtGui.QColor(255, 255, 255)
            dot = QtGui.QColor(ink)
            dot.setAlpha(225)
            c = p.plot(pen=pg.mkPen(ink, width=1.5), symbol="o", symbolSize=DOT, symbolPen=None, symbolBrush=dot,
                       antialias=True)
            ln = pg.InfiniteLine(angle=90)
            pens.mark(ln, CURSOR_PEN.color())
            p.addItem(ln)
            # the point read at this lambda, ringed in the markers' colour: the line says where, the ring which value
            ring = pg.ScatterPlotItem(size=RING, pen=pg.mkPen(CURSOR_PEN.color(), width=1.5), brush=None,
                                      antialias=True)
            ring.setZValue(20)
            p.addItem(ring, ignoreBounds=True)
            for side in ("left", "bottom", "top", "right"):     # a range change re-renders only the axes that moved
                p.getAxis(side).setCacheMode(QtWidgets.QGraphicsItem.CacheMode.DeviceCoordinateCache)
            self.plots.append(p)
            self.curves.append(c)
            self.lines.append(ln)
            self.rings.append(ring)
        # the classic look's curves, to come back to after the modern marks
        self._classic = [(c.opts["pen"], c.opts["symbolPen"], c.opts["symbolBrush"]) for c in self.curves]
        self._zeros: list = []
        self.light = light
        self.noise_style = "lines"                      # until the look says (set_noise_style)
        self._noise: dict[int, list] = {}               # Stokes -> its +-sigma: two lines, or one band
        self._sigma: dict = {}                          # the sigma drawn, for a change of style
        # the x axes are linked: their values once, on the outer edges (delta-lambda under the bottom row, v over the
        # top one), as two rows of the same numbers between the plots read as a third axis. Inner axes keep their
        # line, the box's edge. The velocity ticks point out, to their labels: it has no grid, and inward they hung
        # into the data. The box closed on the right and, without velocities, on top
        for k, p in enumerate(self.plots):
            p.showAxis("right")
            p.showAxis("top")
            if k + ncol < ns:
                p.getAxis("bottom").setStyle(showValues=False)
            if vk:
                top = p.getAxis("top")
                top.setStyle(showValues=k < ncol, tickLength=4 if k < ncol else 0)
                top.bare = k >= ncol
        # the padlock (ui.padlock, put on by the shell) in its own strip on the right: over the plots it covered the
        # last velocity label and the top-right axis title
        self.w.ci.setContentsMargins(9, 9, PanelLock.SIZE + PanelLock.MARGIN, 9)
        for p in self.plots[-ncol:]:
            p.setLabel("bottom", dlam_label(self.ax) if self.physical else label or "λ index")
        if vk:
            for p in self.plots[:ncol]:
                p.setLabel("top", "v [km s⁻¹]")      # Unicode, as every other unit: <sup> drew thinner digits
        self.label_stokes()
        self.freezer = ResizeFreezer(self.w)
        self.widget = self.freezer.stack

    def label_stokes(self) -> None:
        """Stokes I in powers of ten of BUNIT; Q U V in % of I_c when the continuum tuning is known."""
        cont = getattr(self.ax, "cont", None)
        bunit = getattr(self.ax, "bunit", None)
        for k, p in enumerate(self.plots):
            name = STOKES[k] if self.ns > 1 else self.value
            if k == 0 or cont is None:
                e = f"10{str(int(np.log10(self.iscale))).translate(SUP)} " if self.iscale else ""
                u = unit_text(bunit) if bunit else ""
                p.setLabel("left", f"{name} [{e}{u}]" if (e or u) else name)
            else:
                p.setLabel("left", f"{name}/I<sub>c</sub> [%]")

    def set_light(self, light: bool) -> None:
        """The classic curves, the zero lines and the axes in this theme's ink. The curves change when the look puts
        its marks on again (set_marks, clear_marks); the background is the shell's (a card, or the plots' own)."""
        self.light = light
        ink = QtGui.QColor(30, 30, 34) if light else QtGui.QColor(255, 255, 255)
        dot = QtGui.QColor(ink)
        dot.setAlpha(225)
        self._classic = [(pg.mkPen(ink, width=1.5), None, pg.mkBrush(dot)) for _ in self.curves]
        zero = QtGui.QColor(0, 0, 0, 70) if light else QtGui.QColor(255, 255, 255, 70)
        for ln in self._zeros:
            ln.setPen(pg.mkPen(zero, width=1, style=QtCore.Qt.PenStyle.DashLine))
        for items in self._noise.values():
            self._style_noise(items)
        style.default_axes(self.w)

    def set_marks(self, colour, light: bool) -> None:
        """The modern look's marks: the lambda markers and rings in colour, quieter curves, and a dashed zero line on
        Q U V, where zero is at a glance."""
        for ln in self.lines:
            pens.mark(ln, colour)
        for ring in self.rings:
            ring.setPen(pg.mkPen(colour, width=1.5))
        ink = QtGui.QColor(30, 30, 34) if light else QtGui.QColor(235, 235, 240)
        dot = QtGui.QColor(ink)
        dot.setAlpha(225)
        for c in self.curves:
            c.setPen(pg.mkPen(ink, width=1.5))
            c.setSymbolSize(DOT)
            c.setSymbolPen(None)
            c.setSymbolBrush(dot)
        if not self._zeros:
            zero = QtGui.QColor(0, 0, 0, 70) if light else QtGui.QColor(255, 255, 255, 70)
            pen = pg.mkPen(zero, width=1, style=QtCore.Qt.PenStyle.DashLine)
            for p in self.plots[1:]:
                ln = pg.InfiniteLine(pos=0, angle=0, pen=pen)
                p.addItem(ln, ignoreBounds=True)
                self._zeros.append(ln)
        for ln in self._zeros:
            ln.setVisible(True)

    def clear_marks(self) -> None:
        """The classic look's marks again: red lambda markers, the curves as built, no zero lines."""
        for ln in self.lines:
            pens.mark(ln, CURSOR_PEN.color())
        for ring in self.rings:
            ring.setPen(pg.mkPen(CURSOR_PEN.color(), width=1.5))
        for c, (pen, spen, sbrush) in zip(self.curves, self._classic, strict=True):
            c.setPen(pen)
            c.setSymbolPen(spen)
            c.setSymbolBrush(sbrush)
        for ln in self._zeros:
            ln.setVisible(False)

    def set_units(self, iscale: float | None) -> None:
        self.iscale = iscale
        self.label_stokes()

    # ---------------------------------------------------------------- Q U V's +-sigma
    def set_noise(self, sigma: dict) -> None:
        """Q U V's noise levels (Stokes -> sigma in % of I_c, core.noise) at +-sigma, as lines or a band (the look's:
        set_noise_style); in data coordinates, so they follow each plot's y range. Only on Q U V of a panel of the 4
        Stokes; a Stokes without a sigma has none. They never take the mouse: a click on them picks lambda as anywhere
        on the plot."""
        if self.ns != len(STOKES):
            return
        self._sigma = dict(sigma)
        for k in range(1, len(STOKES)):
            sig = sigma.get(k)
            items = self._noise.get(k)
            if items is None:
                if sig is None:
                    continue
                items = self._noise[k] = self._make_noise(k)
            for it in items:
                it.setVisible(sig is not None)
            if sig is None:
                continue
            if self.noise_style == "band":
                items[0].setRegion((-sig, sig))
            else:
                items[0].setValue(sig)
                items[1].setValue(-sig)

    def set_noise_style(self, style: str) -> None:
        """Lines or band (NOISE_STYLES), as the look says (ui.cube CubeView.set_look): the items of the other style
        leave the plots, and the sigma shown is drawn again in this one."""
        if style not in NOISE_STYLES:
            raise ValueError(f"sigma style {style!r}: one of {', '.join(NOISE_STYLES)}")
        if style == self.noise_style:
            return
        for k, items in self._noise.items():
            for it in items:
                self.plots[k].removeItem(it)
        self._noise.clear()
        self.noise_style = style
        if self._sigma:
            self.set_noise(self._sigma)

    def noise_items(self) -> list:
        """Every +-sigma item on the plots now, of either style (as the plots hold them, not as this panel does)."""
        return [it for p in self.plots for it in p.items if getattr(it, "is_noise", False)]

    def noise_at(self, k: int) -> tuple[float, float] | None:
        """(-sigma, +sigma) as plot k draws it, or None when it draws none."""
        items = self._noise.get(k)
        if not items or not items[0].isVisible():
            return None
        if self.noise_style == "band":
            lo, hi = items[0].getRegion()
            return float(lo), float(hi)
        return float(items[1].value()), float(items[0].value())

    def _make_noise(self, k: int) -> list:
        p = self.plots[k]
        items: list
        if self.noise_style == "band":
            items = [pg.LinearRegionItem(orientation="horizontal", movable=False)]
            items[0].setZValue(-10)                     # under the curve and the markers
        else:
            items = [pg.InfiniteLine(angle=0, movable=False), pg.InfiniteLine(angle=0, movable=False)]
            for ln in items:
                ln.setZValue(-1)
        for it in items:
            it.is_noise = True                          # noise_items
            for part in [it, *getattr(it, "lines", [])]:
                part.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
                part.setAcceptHoverEvents(False)
            p.addItem(it, ignoreBounds=True)
        self._style_noise(items)
        return items

    def _style_noise(self, items: list) -> None:
        """In the curves' ink, as CRISPEX draws them in its plot colour: dashed lines, or a faint band without
        edges."""
        ink = QtGui.QColor(30, 30, 34) if self.light else QtGui.QColor(255, 255, 255)
        ink.setAlpha(NOISE_ALPHA[self.noise_style])
        if self.noise_style == "band":
            band = items[0]
            band.setBrush(pg.mkBrush(ink))
            band.setHoverBrush(pg.mkBrush(ink))
            for ln in band.lines:
                ln.setPen(pg.mkPen(None))
                ln.setHoverPen(pg.mkPen(None))
            return
        pen = pg.mkPen(ink, width=1)
        pen.setDashPattern(NOISE_DASH)
        for ln in items:
            ln.setPen(pen)

    def show(self, spec: np.ndarray) -> None:
        """spec: (ns, nl) in plot units; a Stokes with nothing finite (padding) is left empty, without warnings."""
        for k in range(self.ns):
            y = spec[k]
            if not np.isfinite(y).any():
                self.curves[k].setData([], [])
                self._y.pop(k, None)
            else:
                self.curves[k].setData(self.xl, y, skipFiniteCheck=True)
                self._y[k] = y
            self._ring(k)

    def clear(self) -> None:
        for c in self.curves:
            c.setData([], [])
        self._y.clear()
        for k in range(self.ns):
            self._ring(k)

    def _ring(self, k: int) -> None:
        """Stokes k's ring on its profile at this lambda; none on padding or a NaN."""
        y, ring, l = self._y.get(k), self.rings[k], self._l  # noqa: E741
        if y is None or not 0 <= l < len(y) or not np.isfinite(y[l]):
            ring.setData([], [])
        else:
            ring.setData([float(self.xl[l])], [float(y[l])])

    def set_range(self, k: int, r) -> None:
        self.plots[k].setYRange(*r, padding=0)

    def set_lambda(self, l: int) -> None:  # noqa: E741
        x = float(self.xl[l])
        self._l = l
        for ln in self.lines:
            ln.setValue(x)
        for k in range(self.ns):
            self._ring(k)

    def reset_view(self) -> None:
        self.plots[0].setXRange(*self.x_range, padding=0)      # the others are x-linked to it


class AxisDrag(QtCore.QObject):
    """The y range of a spectrum by hand, on the strip of its y axis (ROADMAP E4.1): a drag moves
    the range, the wheel or a drag with the right button stretches it about its middle, a double click gives it
    back to the automatic rules. The range then stays on that plot until F, reset or the double click (the core's
    YRange.manual and auto). Over the curves a drag still picks lambda (gestures): only the axis strip is taken.
    set_range(k, (lo, hi)) and auto(k) are the core's; installed after the gestures, so it sees the events first."""
    STRETCH_PX = 100.0                                  # px of right-button drag per factor e
    WHEEL = 0.85                                        # the range per wheel notch (in: narrower)

    def __init__(self, panel: "SpectraPanel", set_range, auto):
        super().__init__(panel.w)
        self.panel, self.set_range, self.auto = panel, set_range, auto
        self.drag: tuple | None = None                  # (k, button, press y px, range at the press)
        vp = panel.w.viewport()
        vp.setMouseTracking(True)
        vp.installEventFilter(self)

    def axis_at(self, scene_pos) -> int | None:
        """The plot whose y axis strip is under scene_pos. The strip is the axis widget's own rectangle: its
        bounding rect also covers the grid it draws over the whole plot."""
        for k, p in enumerate(self.panel.plots):
            ax = p.getAxis("left")
            if ax.mapRectToScene(QtCore.QRectF(0, 0, ax.width(), ax.height())).contains(scene_pos):
                return k
        return None

    def eventFilter(self, obj, e):
        E, B = QtCore.QEvent.Type, QtCore.Qt.MouseButton
        t = e.type()
        if t not in (E.MouseButtonPress, E.MouseButtonRelease, E.MouseMove, E.MouseButtonDblClick, E.Wheel):
            return False
        pos = self.panel.w.mapToScene(e.position().toPoint())
        if self.drag is not None:
            k, button, y0, r0 = self.drag
            if t == E.MouseMove:
                dy = e.position().y() - y0
                h = max(1.0, self.panel.plots[k].vb.sceneBoundingRect().height())
                lo, hi = r0
                if button == B.LeftButton:              # the range follows the pointer, as dragging the data
                    d = dy / h * (hi - lo)
                    self.set_range(k, (lo + d, hi + d))
                else:                                   # down: wider, up: narrower, about the middle
                    f = float(np.exp(dy / self.STRETCH_PX))
                    mid, half = (lo + hi) / 2, (hi - lo) / 2 * f
                    self.set_range(k, (mid - half, mid + half))
                return True
            if t == E.MouseButtonRelease and e.button() == button:
                self.drag = None
                return True
            return True
        k = self.axis_at(pos)
        if k is None:
            if t == E.MouseMove and not e.buttons():
                obj.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)     # over the curves: lambda
            return False
        if t == E.MouseMove and not e.buttons():
            obj.setCursor(QtCore.Qt.CursorShape.SizeVerCursor)
            return False
        if t == E.MouseButtonDblClick and e.button() == B.LeftButton:
            self.drag = None
            self.auto(k)
            return True
        if t == E.MouseButtonPress and e.button() in (B.LeftButton, B.RightButton):
            self.drag = (k, e.button(), e.position().y(), tuple(self.panel.plots[k].vb.viewRange()[1]))
            return True
        if t == E.Wheel:
            lo, hi = self.panel.plots[k].vb.viewRange()[1]
            notches = e.angleDelta().y() / 120.0
            f = self.WHEEL ** notches
            y = self.panel.plots[k].vb.mapSceneToView(pos).y()     # about the value under the pointer
            self.set_range(k, (y - (y - lo) * f, y + (hi - y) * f))
            return True
        return False
