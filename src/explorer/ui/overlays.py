"""What the modern look draws over the views (ROADMAP E5.5), from the prototype's app/look.py: ColourKey (217) and
Reticle (390); and what every overlay on an image shares (OverImage).

An overlay on an image is anything drawn over it that is not the image: the colour key, the padlock, the Stokes label,
the slit's hint, and whatever comes next. Each one opts in once, through its image's ImageView.over (OverImage.add),
and gets two things:
- the pointer over it is off the image: the image's hover (the crosshair, the slit being drawn) stays where the
  pointer left the image, as when it leaves the image altogether, and follows it again once it is back on the image.
  An overlay that takes the mouse (the key, the padlock) keeps the moves from the image anyway; one that lets them
  through (the label, the hint) would otherwise move the crosshair under itself;
- a widget overlay that changes its size, place or visibility repaints the whole image. Its own change repaints only
  the area it uncovers, and an item of the scene moved in the same pass of the event loop (the crosshair, when the
  pointer leaves the hot key onto the image) could lose its own repaint there: the old crosshair stayed on screen.
    view.over.add(widget_or_item)
"""
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from . import style

SUP = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
LOCKED = QtGui.QColor("#ffd60a")                       # macOS systemYellow: the cursor while locked


def _sci(m):
    """(mantissa scale, ' ×10⁻¹⁰') for the key's labels: numbers of 1-3 digits and one shared power of ten."""
    if not np.isfinite(m) or m == 0:
        return 1.0, ""
    e = int(np.floor(np.log10(abs(m))))
    if -2 <= e <= 3:
        return 1.0, ""
    return 10.0 ** e, f" ×10{str(e).translate(SUP)}"


def _num(x):
    s = f"{x:.2g}" if abs(x) < 10 else f"{x:.0f}"
    return s.replace("-", "−")


def limits_text(lo: float, hi: float) -> tuple[str, str]:
    """A key's two limits as _num writes them, else with as many decimals as they need to differ (up to 6): 4.19 and
    4.22, not 4.2 and 4.2; 1016.4 and 1016.5, not 1016 twice."""
    a, b = _num(lo), _num(hi)
    for d in range(1, 7):
        if a != b or lo == hi:
            break
        a, b = (f"{v:.{d}f}".replace("-", "−") for v in (lo, hi))
    return a, b


# Gamma's letter, wherever the window writes a gamma. In the interface's sans (Noto Sans, DejaVu Sans, SF) γ at 11 px
# is a y with a short tail; an italic serif γ has the loop that makes it a gamma. STIX Two Text ships with macOS and
# Linux distributions alike, so both draw the same letter; the others are the serifs a Linux desktop has, Times New
# Roman a Mac's. A family that is missing falls through to the next, and with none the γ is the run's own font, italic.
GAMMA = "γ"
GAMMA_FAMILIES = ["STIX Two Text", "DejaVu Serif", "Noto Serif", "Times New Roman", "Liberation Serif"]
GAMMA_PX_MORE = 1                                       # its x-height is smaller than the sans's: one pixel larger


def gamma_number(g: float) -> str:
    """g with two significant figures: they tell every step of G apart (levels.GAMMA_STEP, 26 % each: 0.79, 0.63,
    1.3, 1.6); a third only when two would say 1 for a gamma that is not 1 (the Scale card's slider, 1.03)."""
    s = f"{g:.2g}"
    return f"{g:.3g}" if s == "1" and g != 1 else s


def gamma_text(g: float) -> str:
    """'γ = 0.79': the equals sign parts the letter from the digits it otherwise reads as one word with."""
    return f"{GAMMA} = {gamma_number(g)}"


def gamma_font(base: QtGui.QFont) -> QtGui.QFont:
    """The font of γ in a text drawn with base: GAMMA_FAMILIES, italic, GAMMA_PX_MORE larger, base's families last."""
    f = QtGui.QFont(base)
    f.setFamilies(GAMMA_FAMILIES + base.families())
    f.setItalic(True)
    if base.pixelSize() > 0:
        f.setPixelSize(base.pixelSize() + GAMMA_PX_MORE)
    else:
        f.setPointSizeF(base.pointSizeF() + GAMMA_PX_MORE)
    return f


def draw_text(p: QtGui.QPainter, r: QtCore.QRectF, align, text: str) -> None:
    """p.drawText(r, align, text) on one line, its γ in gamma_font on the line's baseline. Text without γ goes to
    drawText as it is, so its pixels are drawText's."""
    if GAMMA not in text:
        p.drawText(r, align, text)
        return
    base = p.font()
    gf = gamma_font(base)
    fm, gm = QtGui.QFontMetricsF(base), QtGui.QFontMetricsF(gf)
    runs = [(t, f, m) for part in text.split(GAMMA) for t, f, m in ((GAMMA, gf, gm), (part, base, fm))][1:]
    runs = [x for x in runs if x[0]]
    width = sum(m.horizontalAdvance(t) for t, _, m in runs)
    A = QtCore.Qt.AlignmentFlag
    x = r.right() - width if align & A.AlignRight else \
        r.center().x() - width / 2 if align & A.AlignHCenter else r.left()
    if align & A.AlignVCenter:
        y = r.top() + (r.height() - fm.height()) / 2 + fm.ascent()
    elif align & A.AlignBottom:
        y = r.bottom() - fm.descent()
    else:
        y = r.top() + fm.ascent()
    for t, f, m in runs:
        p.setFont(f)
        p.drawText(QtCore.QPointF(x, y), t)
        x += m.horizontalAdvance(t)
    p.setFont(base)


class ColourKey(QtWidgets.QWidget):
    """The colour scale in the image's bottom-left corner: the bar, its two ends and, for Q U V, the zero. Painted
    only when the limits, the Stokes or the map change, never with the cursor. After C the map's name takes the
    numbers' row for NOTE_MS, so the key keeps its size. The power of ten goes with the unit on the top row, as the
    spectra's axis titles write it; the numbers under the bar carry none (after the last one only it reads as that
    number's). Its text in pixels, 11 px: in points, max(7, size - 2) was 7 px on a Mac (72 dpi) and 9 over X11.
    zoom: the whole key drawn that many times its size, text included (W, H, TEXT_PX and the rest in its own units):
    a panel of the 2x2 view has its key smaller (ui.scalekey.GRID_ZOOM). fit_title: a title whose unit does not fit
    leaves the unit out, its power of ten kept, rather than cut it (a panel's key, set by ui.scalekey)."""
    W, H = 230, 50
    TEXT_PX = 11
    NOTE_MS = 1500
    fit_title = False

    def __init__(self, view: QtWidgets.QWidget, unit: str = "", zoom: float = 1.0):
        super().__init__(view)
        self.unit = unit
        self.zoom = float(zoom)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(round(self.W * self.zoom), round(self.H * self.zoom))
        self.state: tuple | None = None
        self.lut = None
        self.note = None
        self._note_t = QtCore.QTimer(self, singleShot=True, interval=self.NOTE_MS)
        self._note_t.timeout.connect(lambda: self.flash(None))
        view.installEventFilter(self)
        self._place(view)

    def show_with(self, colour: bool, grid: bool) -> None:
        """Shown with the look's colour part, hidden while the 2x2 view is on: there I Q U V have each their own map
        and levels, and each panel its own key (ui.scalekey); one Stokes' key over the four would describe none of
        them. Kept up to date while hidden (set), so it
        comes back for the Stokes in the image. The prototype's grid covered it the same way: the key is made on the
        image's widget first (app/look.py:327), the grid over it later (app/look_glass.py:928) and raised above it
        (935), the key seen again when the grid hides (945)."""
        self.setVisible(colour and not grid)

    def flash(self, text, ms: int | None = None):
        """Show text (the map's name, gamma after G) in place of the numbers for a moment (ms, else NOTE_MS); None
        puts the numbers back."""
        self.note = text
        if text:
            self._note_t.start(self.NOTE_MS if ms is None else ms)
        self.update()

    def eventFilter(self, obj, e):
        if e.type() == QtCore.QEvent.Type.Resize:
            self._place(obj)
        return False

    def _place(self, view):
        self.move(12, view.height() - self.height() - 12)

    def set(self, name, lim, lut, cmap=None, gamma: float = 1.0):
        """gamma: the image's (core.levels); written on the hot key only (ui.scalekey), never at rest."""
        st = (name, round(float(lim[0]), 12), round(float(lim[1]), 12), cmap if cmap is not None else lut is None)
        if st == self.state:
            return
        self.state, self.lut = st, lut
        self.update()

    def title(self, fm: QtGui.QFontMetrics, room: float, extra: str = "") -> str:
        """The top row: the name, the power of ten with the unit, as the spectra's axis titles write it, and extra
        (the hot key's rule). With fit_title, when that is wider than room (in fm, the key's own units), the unit is
        left out and the power of ten kept: the numbers under the bar carry none."""
        name, lo, hi, _ = self.state if self.state is not None else ("", 0.0, 0.0, None)
        power = _sci(max(abs(lo), abs(hi)))[1].replace(" ×", "")

        def row(unit: str) -> str:
            label = (f"[{power} {unit}]" if power else f"[{unit}]") if unit else (f"×{power}" if power else "")
            return "   ".join(t for t in (name, label, extra) if t)
        text = row(self.unit)
        if self.fit_title and self.unit and fm.horizontalAdvance(text) > room:
            text = row("")
        return text

    def paintEvent(self, e):
        if self.state is None:
            return
        name, lo, hi, _ = self.state
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        z = self.zoom
        p.scale(z, z)                                   # from here on in its own units (zoom)
        r = QtCore.QRectF(0, 0, self.width() / z, self.height() / z).adjusted(0.5, 0.5, -0.5, -0.5)
        lt = style.is_light()                           # over a white image in light: a light key, dark text
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        # alpha 185: at 150, over the brightest granules the white text stood at 4.3:1; now about 9:1
        p.setBrush(QtGui.QColor(255, 255, 255, 215) if lt else QtGui.QColor(0, 0, 0, 185))
        p.drawRoundedRect(r, 8, 8)
        W = self.width() / z                            # W, or the image's width when narrower (ui.scalekey)
        bar = QtCore.QRectF(12, 22, W - 24, 6)
        g = QtGui.QLinearGradient(bar.topLeft(), bar.topRight())
        lut = self.lut if self.lut is not None else np.repeat(np.arange(256, dtype=np.uint8)[:, None], 3, 1)
        for i in range(0, 256, 16):
            g.setColorAt(i / 255, QtGui.QColor(*[int(c) for c in lut[i]]))
        g.setColorAt(1.0, QtGui.QColor(*[int(c) for c in lut[255]]))
        p.setBrush(g)
        p.drawRoundedRect(bar, 3, 3)
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)       # a hairline round the bar: its dark end vanished into the key
        p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 70) if lt else QtGui.QColor(255, 255, 255, 70), 1))
        p.drawRoundedRect(bar.adjusted(-0.5, -0.5, 0.5, 0.5), 3.5, 3.5)
        f = QtGui.QFont(p.font())
        f.setPixelSize(self.TEXT_PX)
        p.setFont(f)
        k = _sci(max(abs(lo), abs(hi)))[0]
        A = QtCore.Qt.AlignmentFlag
        p.setPen(QtGui.QColor(0, 0, 0, 217) if lt else QtGui.QColor(255, 255, 255, 215))
        draw_text(p, QtCore.QRectF(12, 3, W - 24, 16), A.AlignLeft | A.AlignVCenter,
                  self.title(QtGui.QFontMetrics(f), W - 24))
        ink = QtGui.QColor(0, 0, 0, 150) if lt else QtGui.QColor(255, 255, 255, 170)
        p.setPen(QtGui.QPen(ink, 1))                    # a short tick under each number's place on the bar
        ticks = [bar.left() + 0.5, bar.right() - 0.5] + ([bar.left() + bar.width() * (-lo) / (hi - lo)]
                                                          if lo < 0 < hi else [])
        for tx in ticks:
            x = round(tx) + 0.5
            p.drawLine(QtCore.QPointF(x, bar.bottom() + 1), QtCore.QPointF(x, bar.bottom() + 3))
        p.setPen(ink)
        top = bar.bottom() + 3
        if self.note:
            draw_text(p, QtCore.QRectF(bar.left(), top, bar.width(), 16), A.AlignHCenter, self.note)
            p.end()
            return
        lo_t, hi_t = limits_text(lo / k, hi / k)
        p.drawText(QtCore.QRectF(bar.left(), top, 70, 16), A.AlignLeft, lo_t)
        if lo < 0 < hi:
            x0 = bar.left() + bar.width() * (-lo) / (hi - lo)
            p.drawText(QtCore.QRectF(x0 - 20, top, 40, 16), A.AlignHCenter, "0")
        p.drawText(QtCore.QRectF(bar.right() - 70, top, 70, 16), A.AlignRight, ("+" if lo < 0 else "") + hi_t)
        p.end()


class Reticle(pg.GraphicsObject):
    """Four short arms round the pixel, in screen pixels whatever the zoom: a dark halo under a light stroke, so it
    reads on sunspot and on granulation alike (as CRISPEX's '+' in black or white did), and the pixel under it stays
    visible. Yellow with a ring while the cursor is locked. It repaints its own 36 x 36 px, not two lines across the
    image."""
    GAP, ARM = 5.0, 14.0

    def __init__(self):
        super().__init__()
        self.setFlag(self.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setZValue(1000)
        self.locked = False
        self.colour = QtGui.QColor(255, 255, 255, 235)  # the glass look's: its accent

    def boundingRect(self):
        a = self.ARM + 3
        return QtCore.QRectF(-a, -a, 2 * a, 2 * a)

    def paint(self, p, *args):
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        g, a = self.GAP, self.ARM
        L = QtCore.QLineF
        arms = [L(-a, 0, -g, 0), L(g, 0, a, 0), L(0, -a, 0, -g), L(0, g, 0, a)]
        for pen in (QtGui.QPen(QtGui.QColor(0, 0, 0, 160), 3.6),
                    QtGui.QPen(LOCKED if self.locked else self.colour, 1.6)):
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLines(arms)
            if self.locked:
                p.drawEllipse(QtCore.QPointF(0, 0), g - 1.5, g - 1.5)

    def set_locked(self, on: bool) -> None:
        if on != self.locked:
            self.locked = on
            self.update()

    def set_colour(self, c) -> None:
        self.colour = QtGui.QColor(c)
        self.update()


class OverImage(QtCore.QObject):
    """The overlays of one image's view (an ImageView's QGraphicsView): see the module."""
    REPAINT = (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Move, QtCore.QEvent.Type.Show, QtCore.QEvent.Type.Hide)

    def __init__(self, view: QtWidgets.QGraphicsView):
        super().__init__(view)
        self.view = view
        self.items: list = []

    def add(self, overlay) -> None:
        """overlay over this image from now on: a QWidget child of the view, or a QGraphicsItem on its scene."""
        self.items.append(overlay)
        if isinstance(overlay, QtWidgets.QWidget):
            overlay.installEventFilter(self)

    def covers(self, at: QtCore.QPoint) -> bool:
        """Whether at, in the viewport's pixels, is on a shown overlay."""
        vp = self.view.viewport()
        for o in self.items:
            if isinstance(o, QtWidgets.QWidget):
                if o.isVisible() and o.geometry().contains(vp.mapTo(self.view, at)):
                    return True
            elif o.isVisible() and o.sceneBoundingRect().isValid() and \
                    self.view.mapFromScene(o.sceneBoundingRect()).boundingRect().contains(at):
                return True
        return False

    def eventFilter(self, obj, e) -> bool:
        if e.type() in self.REPAINT:
            self.view.viewport().update()
        return False


class Toast(QtWidgets.QLabel):
    """A short note in a widget that goes by itself: centred, its foot at `bottom` (the widget's foot when None),
    shown for ms and fading over its last fade_ms (0: gone at once); wrapped when the widget is narrower than its
    line. Clicks go through it."""
    MARGIN = 6                                          # px between its foot and bottom

    def __init__(self, host: QtWidgets.QWidget):
        super().__init__(host)
        self.setObjectName("toast")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("QLabel#toast { background: rgba(20, 20, 20, 210); color: #f0f0f0; border-radius: 6px; "
                           "padding: 4px 10px; }")
        self._fx = QtWidgets.QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._anim = QtCore.QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.finished.connect(self.hide)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade)
        self._fade_ms = 0
        self.hide()

    def say(self, text: str, ms: int, fade_ms: int, bottom: int | None = None) -> None:
        host = self.parentWidget()
        if host is None:
            return
        self.setText(text)
        self.setWordWrap(False)
        self.adjustSize()
        room = host.width() - 8
        if self.width() > room > 0:                     # wider than its widget: on two lines rather than cut
            self.setWordWrap(True)
            self.resize(room, self.heightForWidth(room))
        foot = host.height() if bottom is None else min(host.height(), bottom)
        self.move(max(4, (host.width() - self.width()) // 2), max(4, foot - self.height() - self.MARGIN))
        self._anim.stop()
        self._fx.setOpacity(1.0)
        self._fade_ms = fade_ms
        self.show()
        self.raise_()
        self._timer.start(max(0, ms - fade_ms))

    def _fade(self) -> None:
        if self._fade_ms <= 0:
            self.hide()
            return
        self._anim.setDuration(self._fade_ms)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()
