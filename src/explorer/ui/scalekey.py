"""The image's levels and gamma set on the image itself (ROADMAP E5, the scale's interface): the colour key of every
image made interactive, and a card with the numbers.

- ScaleKey: the colour key (ui.overlays.ColourKey) of one cube's image, the same at rest. Under the pointer it grows
  into the histogram of the frame (its [::8, ::8] subsample, the one the automatic levels read: data.stats.limits)
  with the transfer curve over it, so gamma shows, and a handle at each limit.
  An overlay of its image (ui.overlays.OverImage): the pointer over it is off the image. Dragging a handle fixes that
  limit (Session.set_scale "fixed"; Q U V move both ends, symmetric about 0); the wheel steps gamma as G and Shift+G
  do; a double click gives the image its automatic levels and gamma 1 again. It takes the image's width when narrower
  than its own. A right click on it opens nothing for now (KEY_MENU): it reaches the image below, which releases the
  cursor.
- scale_menu: on a right click over the Stokes label of a panel of the 2x2 view (and over a key, with KEY_MENU): the
  limit rule, gamma presets, "Scale...", and a reset.
- ScaleCard: from "Scale...": min and max typed, CRISPEX's logarithmic gamma slider (0.1-10, 10^(v/500 - 1),
  crispex.pro:24436-24441), the limit rule and a reset. A child of the window (one X window less through the bridge);
  Esc or a click outside closes it.

Everything goes through the session (Session.set_scale, Session.set_gamma): per cube and Stokes, saved with the
layout (ui.layout.LayoutStore.save_scale).
"""
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ..core.levels import RULE_DEFAULT, gamma_step
from . import style
from .overlays import GAMMA, ColourKey, _num, _sci, draw_text, gamma_font, gamma_number, gamma_text

STOKES = "IQUV"
RULE_TEXT = {"p1": "Automatic, 1–99 % per frame", "p05": "0.5–99.5 % per frame",
             "minmax": "Min–max per frame", "fixed": "Frozen to this frame"}
RULE_SHORT = {"p1": "auto 1–99 %", "p05": "auto 0.5–99.5 %", "minmax": "min–max", "fixed": "fixed"}
# Q U V, symmetric about 0: each rule keeps its upper percentile, of |value| (data.stats.limits)
RULE_TEXT_SYM = {"p1": "Automatic, 99 % of |value| per frame", "p05": "99.5 % of |value| per frame",
                 "minmax": "Max |value| per frame", "fixed": "Frozen to this frame"}
RULE_SHORT_SYM = {"p1": "auto |x| 99 %", "p05": "auto |x| 99.5 %", "minmax": "max |x|", "fixed": "fixed"}
# the hot key's last line, the longest that fits its width (a cube's window may be 230 px wide); none: left out
HINTS = ("drag ▲ · wheel γ · double click: automatic, γ = 1", "drag ▲ · wheel γ · double click: reset",
         "double click: reset")
KEY_MENU = False                                        # the menu on a right click over a key: off for now
GAMMAS = (1.0, 0.7, 0.5, 0.3)
HIST_BINS = 128


def gamma_of_slider(v: int) -> float:
    """CRISPEX's gamma slider, 0..1000: 10^(v/500 - 1), 0.1 .. 10 (crispex.pro:17215-17225)."""
    return float(10.0 ** (int(v) / 500.0 - 1.0))


def slider_of_gamma(g: float) -> int:
    return int(round(500.0 * (np.log10(g) + 1.0)))


def rule_texts(sym: bool) -> dict[str, str]:
    """The limit rules as the menu and the card list them: of |value| for Q U V (sym)."""
    return RULE_TEXT_SYM if sym else RULE_TEXT


def hint(fm: QtGui.QFontMetrics, width: float) -> str:
    """The longest of HINTS that fits width in fm, else ""."""
    return next((h for h in HINTS if fm.horizontalAdvance(h) <= width), "")


def transfer(v, lo: float, hi: float, g: float, sym: bool):
    """Where value v goes between the darkest and the brightest, 0..1, as the reduce kernel's gamma table puts it
    (data.kernels.gamma_table): sign kept about 0 for symmetric levels."""
    if sym:
        u = np.clip(np.asarray(v, float) / hi, -1.0, 1.0)
        return 0.5 + 0.5 * np.sign(u) * np.abs(u) ** g
    u = np.clip((np.asarray(v, float) - lo) / (hi - lo), 0.0, 1.0)
    return u ** g


def sample(frame) -> np.ndarray:
    """The frame's finite non-zero values on [::8, ::8], as the automatic levels see it (data.stats.limits)."""
    if frame is None:
        return np.zeros(0, np.float32)
    a = np.asarray(frame)[::8, ::8].ravel()
    return a[np.isfinite(a) & (a != 0)]


def axis_range(a: np.ndarray, lo: float, hi: float, sym: bool) -> tuple[float, float]:
    """The data axis the histogram and the handles share: the sample's 0.05-99.95 percentiles and the limits, with
    a margin; symmetric about 0 for symmetric levels."""
    if sym:
        m = max(float(np.percentile(np.abs(a), 99.95)) if a.size else 0.0, abs(hi)) * 1.1 or 1.0
        return -m, m
    p0, p1 = (float(x) for x in np.percentile(a, (0.05, 99.95))) if a.size else (lo, hi)
    a0, a1 = min(p0, lo), max(p1, hi)
    pad = 0.05 * (a1 - a0) or 1.0
    return a0 - pad, a1 + pad


class ScaleKey(ColourKey):
    """The colour key of one cube's image (any cube, any look), interactive: see the module."""
    H_HOT = 112
    W_HOT = 320                                         # wider while hot, as the image allows
    GRAB = 8                                            # px either side of a handle that grab it
    MIN_W = 120

    def __init__(self, cube, unit: str = ""):
        super().__init__(cube.view.widget, unit)
        self.cube, self.shell = cube, cube.shell
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)   # its own, on the right press
        self.setMouseTracking(True)
        self.hot = False
        self.drag: str | None = None                    # "lo" or "hi" while dragged
        self.near: str | None = None                    # the handle under the pointer
        self._axis: tuple[float, float] | None = None   # held while dragging: the handle stays under the pointer
        self._hist: tuple | None = None                 # (frame id, axis, symmetric, counts)
        self.name = ""                                  # what it names (set), without the gamma the rest key adds
        self._fit(cube.view.widget)
        cube.view.over.add(self)                        # over the image (ui.overlays)

    # ---------------------------------------------------------------- what it describes
    def target(self) -> tuple[int, int]:
        """(cube, Stokes) of its image now."""
        return self.cube.k, self.shell.session.member_state(self.cube.k).s

    def frame(self):
        return self.cube.view._full

    def levels(self) -> tuple[float, float]:
        lo, hi = self.cube.view._lim
        return float(lo), float(hi)

    # ---------------------------------------------------------------- size and place
    def set(self, name, lim, lut, cmap=None, gamma: float = 1.0):
        self.name = name
        super().set(name, lim, lut, cmap, gamma)

    def eventFilter(self, obj, e):
        if e.type() == QtCore.QEvent.Type.Resize:
            self._fit(obj)
        return super().eventFilter(obj, e)

    def _fit(self, view) -> None:
        """Its own width, or the image's less the margins when narrower (a cube's window may be 270 px wide)."""
        w = max(self.MIN_W, min(self.W_HOT if self.hot else self.W, view.width() - 24))
        h = self.H_HOT if self.hot else self.H
        if (w, h) != (self.width(), self.height()):
            self.resize(w, h)

    def set_hot(self, on: bool) -> None:
        if on == self.hot:
            return
        self.hot = on
        view = self.parentWidget()
        if view is not None:
            self._fit(view)
            self._place(view)                           # bottom left grows upwards, glass's top left downwards
        if on:
            self.raise_()
        self.update()

    # ---------------------------------------------------------------- the histogram band
    def _band(self) -> QtCore.QRectF:
        return QtCore.QRectF(12, 22, self.width() - 24, self.H_HOT - 22 - 46)

    def _bar(self) -> QtCore.QRectF:
        b = self._band()
        return QtCore.QRectF(b.left(), b.bottom() + 2, b.width(), 7)

    def axis(self) -> tuple[float, float]:
        if self._axis is not None:
            return self._axis
        lo, hi = self.levels()
        return axis_range(sample(self.frame()), lo, hi, self.symmetric())

    def symmetric(self) -> bool:
        return self.target()[1] > 0

    def x_of(self, v: float) -> float:
        a0, a1 = self.axis()
        r = self._bar()
        return r.left() + r.width() * (v - a0) / (a1 - a0)

    def value_at(self, x: float) -> float:
        a0, a1 = self.axis()
        r = self._bar()
        return a0 + (a1 - a0) * (x - r.left()) / r.width()

    def _counts(self, axis) -> np.ndarray:
        f = self.frame()
        key = (id(f), axis, self.symmetric())
        if self._hist is None or self._hist[0:3] != key:
            h, _ = np.histogram(sample(f), np.linspace(axis[0], axis[1], HIST_BINS + 1))
            h = np.log1p(h.astype(float))
            self._hist = (*key, h / h.max() if h.max() > 0 else h)
        return self._hist[3]

    # ---------------------------------------------------------------- input
    def enterEvent(self, e):
        self.set_hot(True)

    def leaveEvent(self, e):
        if self.drag is None:
            self.near = None
            self.set_hot(False)

    def _handle_near(self, x: float) -> str | None:
        lo, hi = self.levels()
        d = {w: abs(x - self.x_of(v)) for w, v in (("lo", lo), ("hi", hi))}
        w = min(d, key=lambda k: d[k])
        return w if d[w] <= self.GRAB else None

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MouseButton.RightButton:
            if KEY_MENU:
                self.open_menu(e.globalPosition().toPoint())
            else:
                e.ignore()                              # to the image below: it releases the cursor
            return
        if e.button() != QtCore.Qt.MouseButton.LeftButton or not self.hot:
            return
        x = e.position().x()
        w = self._handle_near(x)
        if w is None and self._band().adjusted(0, 0, 0, 20).contains(e.position()):
            lo, hi = self.levels()                     # a press on the band: the nearer handle jumps there
            w = "lo" if abs(x - self.x_of(lo)) < abs(x - self.x_of(hi)) else "hi"
        if w is not None:
            self._axis = self.axis()
            self.drag = w
            self.drag_to(self.value_at(x))

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self.drag is not None:
            self.drag_to(self.value_at(x))
            return
        near = self._handle_near(x) if self.hot else None
        if near != self.near:
            self.near = near
            self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor if near else QtCore.Qt.CursorShape.ArrowCursor)
            self.update()

    def mouseReleaseEvent(self, e):
        if self.drag is None:
            return
        self.drag, self._axis = None, None
        if not self.underMouse():
            self.set_hot(False)
        self.update()

    def drag_to(self, v: float) -> None:
        """The dragged limit at v, fixed: the image follows at the state's next notice (one per pass of the event
        loop, whatever the mouse sent meanwhile)."""
        k, s = self.target()
        lo, hi = self.levels()
        if self.symmetric():
            m = max(abs(v), 1e-30)
            lo, hi = -m, m
        elif self.drag == "lo":
            lo = min(v, hi - (hi - lo) * 1e-3)
        else:
            hi = max(v, lo + (hi - lo) * 1e-3)
        self.shell.session.set_scale(k, s, "fixed", lo, hi)
        self.update()

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if d:
            k, s = self.target()
            self.shell.set_gamma(k, s, gamma_step(self.shell.session.gamma(k, s), 1 if d > 0 else -1))
        e.accept()

    def mouseDoubleClickEvent(self, e):
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            self.drag, self._axis = None, None
            reset(self.shell, *self.target())          # automatic levels and gamma 1

    def open_menu(self, at: QtCore.QPoint) -> QtWidgets.QMenu:
        m = scale_menu(self.shell, *self.target())
        m.popup(at)
        return m

    # ---------------------------------------------------------------- paint
    def paintEvent(self, e):
        if not self.hot:
            super().paintEvent(e)
            return
        if self.state is None:
            return
        k, s = self.target()
        lo, hi = self.levels()
        sym = self.symmetric()
        g = self.shell.session.gamma(k, s)
        rule = self.shell.session.scale(k, s)[0]
        lt = style.is_light()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(255, 255, 255, 225) if lt else QtGui.QColor(0, 0, 0, 200))
        p.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        ink = QtGui.QColor(0, 0, 0, 217) if lt else QtGui.QColor(255, 255, 255, 215)
        faint = QtGui.QColor(ink)
        faint.setAlpha(130)
        acc = QtGui.QColor("#0063d1") if lt else QtGui.QColor("#0a84ff")
        f = QtGui.QFont(p.font())
        f.setPixelSize(self.TEXT_PX)
        p.setFont(f)
        AL = QtCore.Qt.AlignmentFlag
        W = self.width()
        kpow, pw = _sci(max(abs(lo), abs(hi)))
        name = self.name
        unit = (f"[{pw.replace(' ×', '')} {self.unit}]" if pw else f"[{self.unit}]") if self.unit else \
            pw.replace(" ×", "×")
        p.setPen(ink)
        fm = QtGui.QFontMetrics(f)
        # gamma only when not 1, as at rest (the transfer curve shows it): the title keeps its room for the rule
        gtext = gamma_text(g) if g != 1.0 else ""
        gw = QtGui.QFontMetrics(gamma_font(f)).horizontalAdvance(GAMMA) + fm.horizontalAdvance(gtext[1:]) + 8 \
            if gtext else 0
        title = "   ".join(t for t in (name, unit, (RULE_SHORT_SYM if sym else RULE_SHORT)[rule]) if t)
        # cut at its end (…) short of gamma: on a narrow key the two ran into each other
        title = fm.elidedText(title, QtCore.Qt.TextElideMode.ElideRight, W - 24 - gw)
        p.drawText(QtCore.QRectF(12, 3, W - 24, 16), AL.AlignLeft | AL.AlignVCenter, title)
        if gtext:
            draw_text(p, QtCore.QRectF(12, 3, W - 24, 16), AL.AlignRight | AL.AlignVCenter, gtext)
        band, bar = self._band(), self._bar()
        a0, a1 = self.axis()
        h = self._counts((a0, a1))
        n = h.size
        path = QtGui.QPainterPath(QtCore.QPointF(band.left(), band.bottom()))
        for i in range(n):                              # the histogram: one outline, steps per bin
            x0, x1 = band.left() + band.width() * i / n, band.left() + band.width() * (i + 1) / n
            y = band.bottom() - h[i] * band.height()
            path.lineTo(x0, y)
            path.lineTo(x1, y)
        path.lineTo(band.right(), band.bottom())
        path.closeSubpath()
        fill = QtGui.QColor(ink)
        fill.setAlpha(70)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawPath(path)
        xs = np.linspace(a0, a1, int(band.width()))     # the transfer curve: where gamma shows
        ys = transfer(xs, lo, hi, g, sym)
        curve = QtGui.QPolygonF([QtCore.QPointF(band.left() + i, band.bottom() - y * band.height())
                                 for i, y in enumerate(ys)])
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.setPen(QtGui.QPen(acc, 1.6))
        p.drawPolyline(curve)
        lut = self.lut if self.lut is not None else np.repeat(np.arange(256, dtype=np.uint8)[:, None], 3, 1)
        cols = np.asarray(lut)[(1 + np.round(254 * transfer(xs, lo, hi, g, sym))).astype(int), :3]
        cols = np.ascontiguousarray(cols, dtype=np.uint8)
        im = QtGui.QImage(cols.tobytes(), cols.shape[0], 1, 3 * cols.shape[0], QtGui.QImage.Format.Format_RGB888)
        p.drawImage(bar, im)                            # the bar along the data axis: each value its colour
        p.setPen(QtGui.QPen(faint, 1))
        p.drawRect(bar)
        for which, v in (("lo", lo), ("hi", hi)):
            x = self.x_of(v)
            on = which in (self.near, self.drag)
            c = acc if on else ink
            p.setPen(QtGui.QPen(c, 1, QtCore.Qt.PenStyle.DashLine))
            p.drawLine(QtCore.QPointF(x, band.top()), QtCore.QPointF(x, bar.top()))
            tri = QtGui.QPolygonF([QtCore.QPointF(x, bar.bottom() + 1), QtCore.QPointF(x - 5, bar.bottom() + 9),
                                   QtCore.QPointF(x + 5, bar.bottom() + 9)])
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255) if lt else QtGui.QColor(0, 0, 0, 160), 1))
            p.setBrush(c)
            p.drawPolygon(tri)
            p.setPen(ink)
            r = QtCore.QRectF(x - 40, bar.bottom() + 9, 80, 14)
            r.moveLeft(min(max(r.left(), 4), W - 84))
            p.drawText(r, AL.AlignHCenter | AL.AlignTop, ("+" if sym and which == "hi" else "") + _num(v / kpow))
        p.setPen(faint)
        draw_text(p, QtCore.QRectF(8, self.height() - 16, W - 16, 14), AL.AlignHCenter, hint(fm, W - 16))
        p.end()


# -------------------------------------------------------------------------------------------- the menu
def scale_menu(shell, k: int, s: int, parent: QtWidgets.QWidget | None = None) -> QtWidgets.QMenu:
    """The short menu of cube k's image at Stokes s. Each action's data names it, ("rule", r), ("gamma", g),
    ("card", None), ("reset", None), for whoever finds it without its text."""
    sess = shell.session
    m = QtWidgets.QMenu(parent or shell)
    m.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
    head = m.addAction(scale_title(shell, k, s))
    head.setEnabled(False)
    m.addSeparator()
    m.addAction("Limits").setEnabled(False)
    rule = sess.scale(k, s)[0]
    rules = QtGui.QActionGroup(m)
    for r, text in rule_texts(s > 0).items():
        a = m.addAction(text)
        a.setCheckable(True)
        a.setChecked(r == rule)
        a.setActionGroup(rules)
        a.setData(("rule", r))
        a.triggered.connect(lambda _=False, r=r: set_rule(shell, k, s, r))
    m.addSeparator()
    m.addAction("Contrast γ").setEnabled(False)
    g_now = sess.gamma(k, s)
    gs = QtGui.QActionGroup(m)
    for g in GAMMAS:
        a = m.addAction(gamma_number(g) + ("  (linear)" if g == 1 else ""))
        a.setCheckable(True)
        a.setChecked(abs(g - g_now) < 0.02)
        a.setActionGroup(gs)
        a.setData(("gamma", g))
        a.triggered.connect(lambda _=False, g=g: shell.set_gamma(k, s, g))
    m.addAction("Lower, higher\tG  ⇧G").setEnabled(False)
    m.addSeparator()
    a = m.addAction("Scale…")
    a.setData(("card", None))
    a.triggered.connect(lambda: shell.open_scale_card(k, s))
    a = m.addAction("Reset this image")
    a.setData(("reset", None))
    a.triggered.connect(lambda: reset(shell, k, s))
    return m


def scale_title(shell, k: int, s: int) -> str:
    c = shell.cubes[k]
    return " · ".join(t for t in (c.name if shell.linked or c.ns != len(STOKES) else "",
                                       f"Stokes {STOKES[s]}" if c.ns == len(STOKES) else "") if t) or "Image"


def set_rule(shell, k: int, s: int, rule: str) -> None:
    """The limit rule of cube k at Stokes s; "fixed" freezes the levels shown now."""
    if rule == "fixed":
        if shell.session.scale(k, s)[0] != "fixed":
            shell.session.set_scale(k, s, "fixed", *shell.scale_levels(k, s))
        return
    shell.session.set_scale(k, s, rule)


def reset(shell, k: int, s: int) -> None:
    """Cube k's image at Stokes s as at start: automatic levels, gamma 1."""
    shell.session.set_scale(k, s, RULE_DEFAULT)
    shell.set_gamma(k, s, 1.0)


# -------------------------------------------------------------------------------------------- the card
class ScaleCard(QtWidgets.QFrame):
    """The numbers of cube k's image at Stokes s: see the module. It follows the session while open (the key dragged,
    G pressed), and closes with Esc or a click outside it."""

    def __init__(self, shell, k: int, s: int):
        super().__init__(shell)
        self.shell, self.k, self.s = shell, k, s
        self.setObjectName("scalecard")
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        lt = style.is_light()
        bg, fg, ln = ("#f5f5f7", "#1d1d1f", "#c7c7cc") if lt else ("#2c2c2e", "#f2f2f7", "#48484a")
        self.setStyleSheet(f"#scalecard {{ background: {bg}; border: 1px solid {ln}; border-radius: 10px; }}"
                           f"#scalecard QLabel {{ color: {fg}; }}")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        lay.addWidget(QtWidgets.QLabel(f"<b>{scale_title(shell, k, s)}</b>"))
        row = QtWidgets.QHBoxLayout()
        self.lo, self.hi = QtWidgets.QLineEdit(), QtWidgets.QLineEdit()
        for lab, e in (("min", self.lo), ("max", self.hi)):
            row.addWidget(QtWidgets.QLabel(lab))
            e.setFixedWidth(96)
            e.setValidator(QtGui.QDoubleValidator(e))
            e.editingFinished.connect(lambda e=e: self._typed(e))
            row.addWidget(e)
        row.addStretch(1)
        lay.addLayout(row)
        row = QtWidgets.QHBoxLayout()
        g_name = QtWidgets.QLabel(GAMMA)
        g_name.setFont(gamma_font(g_name.font()))
        row.addWidget(g_name)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setMinimumWidth(180)
        self.slider.valueChanged.connect(self._slid)
        row.addWidget(self.slider, 1)
        self.g_label = QtWidgets.QLabel()
        self.g_label.setMinimumWidth(40)
        row.addWidget(self.g_label)
        lay.addLayout(row)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("limits"))
        self.rule = QtWidgets.QComboBox()
        for r, text in rule_texts(s > 0).items():
            self.rule.addItem(text, r)
        self.rule.activated.connect(lambda i: set_rule(shell, k, s, self.rule.itemData(i)))
        row.addWidget(self.rule, 1)
        lay.addLayout(row)
        row = QtWidgets.QHBoxLayout()
        self.reset = QtWidgets.QPushButton("Reset")
        self.reset.clicked.connect(lambda: reset(shell, k, s))
        row.addWidget(self.reset)
        row.addStretch(1)
        hint = QtWidgets.QLabel("Esc or a click outside: close")
        hint.setStyleSheet("color: gray")
        row.addWidget(hint)
        lay.addLayout(row)
        self._quiet = False
        self.refresh()
        self.adjustSize()
        self._off = shell.session.store.subscribe(lambda st, ch: self.refresh() if ch & {"scale", "gamma", "s"}
                                                  else None)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def refresh(self) -> None:
        """The fields from the session and the levels shown, unless being typed in."""
        sess = self.shell.session
        lo, hi = self.shell.scale_levels(self.k, self.s)
        self._quiet = True
        for e, v in ((self.lo, lo), (self.hi, hi)):
            if not e.hasFocus():
                e.setText(f"{v:.6g}")
        g = sess.gamma(self.k, self.s)
        self.slider.setValue(slider_of_gamma(g))
        self.g_label.setText(gamma_number(g))
        self.rule.setCurrentIndex(self.rule.findData(sess.scale(self.k, self.s)[0]))
        self._quiet = False

    def _typed(self, e: QtWidgets.QLineEdit) -> None:
        try:
            lo, hi = float(self.lo.text()), float(self.hi.text())
        except ValueError:
            return
        if self.s > 0:                                  # Q U V: symmetric, the field typed gives m
            m = abs(float(e.text()))
            lo, hi = -m, m
        if hi > lo and (lo, hi) != tuple(self.shell.scale_levels(self.k, self.s)):
            self.shell.session.set_scale(self.k, self.s, "fixed", lo, hi)

    def _slid(self, v: int) -> None:
        if self._quiet:
            return
        g = gamma_of_slider(v)
        self.shell.set_gamma(self.k, self.s, 1.0 if abs(np.log10(g)) < 1e-9 else g)

    def keyPressEvent(self, e):
        if e.key() == QtCore.Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(e)

    def eventFilter(self, obj, e):
        """Esc closes it before the window's Esc (release the cursor) takes the key; a press outside it closes it
        (not one in a popup of its own, the rule's list)."""
        if e.type() in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress) and \
                e.key() == QtCore.Qt.Key.Key_Escape and self.isVisible():
            self.close()
            return True
        if e.type() == QtCore.QEvent.Type.MouseButtonPress and QtWidgets.QApplication.activePopupWidget() is None:
            w = obj if isinstance(obj, QtWidgets.QWidget) else None
            if w is not None and w is not self and not self.isAncestorOf(w):
                self.close()
        return False

    def closeEvent(self, e):
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        if self._off is not None:
            self._off()
            self._off = None
        if getattr(self.shell, "scale_card", None) is self:
            self.shell.scale_card = None
        self.deleteLater()
        super().closeEvent(e)
