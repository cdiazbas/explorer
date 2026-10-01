"""What the modern look draws over the views (ROADMAP E5.5), from the prototype's app/look.py: ColourKey (217) and
Reticle (390)."""
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


class ColourKey(QtWidgets.QWidget):
    """The colour scale in the image's bottom-left corner: the bar, its two ends and, for Q U V, the zero. Painted
    only when the limits, the Stokes or the map change, never with the cursor. After C the map's name takes the
    numbers' row for NOTE_MS, so the key keeps its size. The power of ten goes with the unit on the top row, as the
    spectra's axis titles write it; the numbers under the bar carry none (after the last one only it reads as that
    number's)."""
    W, H = 230, 50
    NOTE_MS = 1500

    def __init__(self, view: QtWidgets.QWidget, unit: str = ""):
        super().__init__(view)
        self.unit = unit
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(self.W, self.H)
        self.state = None
        self.lut = None
        self.note = None
        self._note_t = QtCore.QTimer(self, singleShot=True, interval=self.NOTE_MS)
        self._note_t.timeout.connect(lambda: self.flash(None))
        view.installEventFilter(self)
        self._place(view)

    def flash(self, text):
        """Show text (the map's name) in place of the numbers for a moment; None puts the numbers back."""
        self.note = text
        if text:
            self._note_t.start()
        self.update()

    def eventFilter(self, obj, e):
        if e.type() == QtCore.QEvent.Type.Resize:
            self._place(obj)
        return False

    def _place(self, view):
        self.move(12, view.height() - self.H - 12)

    def set(self, name, lim, lut, cmap=None):
        st = (name, round(float(lim[0]), 12), round(float(lim[1]), 12), cmap if cmap is not None else lut is None)
        if st == self.state:
            return
        self.state, self.lut = st, lut
        self.update()

    def paintEvent(self, e):
        if self.state is None:
            return
        name, lo, hi, _ = self.state
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        lt = style.is_light()                           # over a white image in light: a light key, dark text
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(255, 255, 255, 215) if lt else QtGui.QColor(0, 0, 0, 150))
        p.drawRoundedRect(r, 8, 8)
        bar = QtCore.QRectF(12, 22, self.W - 24, 6)
        g = QtGui.QLinearGradient(bar.topLeft(), bar.topRight())
        lut = self.lut if self.lut is not None else np.repeat(np.arange(256, dtype=np.uint8)[:, None], 3, 1)
        for i in range(0, 256, 16):
            g.setColorAt(i / 255, QtGui.QColor(*[int(c) for c in lut[i]]))
        g.setColorAt(1.0, QtGui.QColor(*[int(c) for c in lut[255]]))
        p.setBrush(g)
        p.drawRoundedRect(bar, 3, 3)
        f = p.font()
        f.setPointSizeF(max(7.0, f.pointSizeF() - 2))
        p.setFont(f)
        k, pw = _sci(max(abs(lo), abs(hi)))
        power = pw.replace(" ×", "")
        if self.unit:
            label = f"[{power} {self.unit}]" if power else f"[{self.unit}]"
        else:
            label = f"×{power}" if power else ""
        A = QtCore.Qt.AlignmentFlag
        p.setPen(QtGui.QColor(0, 0, 0, 217) if lt else QtGui.QColor(255, 255, 255, 215))
        p.drawText(QtCore.QRectF(12, 3, self.W - 24, 16), A.AlignLeft | A.AlignVCenter, f"{name}   {label}".rstrip())
        p.setPen(QtGui.QColor(0, 0, 0, 150) if lt else QtGui.QColor(255, 255, 255, 170))
        top = bar.bottom() + 2
        if self.note:
            p.drawText(QtCore.QRectF(bar.left(), top, bar.width(), 16), A.AlignHCenter, self.note)
            p.end()
            return
        p.drawText(QtCore.QRectF(bar.left(), top, 70, 16), A.AlignLeft, _num(lo / k))
        if lo < 0 < hi:
            x0 = bar.left() + bar.width() * (-lo) / (hi - lo)
            p.drawText(QtCore.QRectF(x0 - 20, top, 40, 16), A.AlignHCenter, "0")
        p.drawText(QtCore.QRectF(bar.right() - 70, top, 70, 16), A.AlignRight, ("+" if lo < 0 else "") + _num(hi / k))
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

    def boundingRect(self):
        a = self.ARM + 3
        return QtCore.QRectF(-a, -a, 2 * a, 2 * a)

    def paint(self, p, *args):
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        g, a = self.GAP, self.ARM
        L = QtCore.QLineF
        arms = [L(-a, 0, -g, 0), L(g, 0, a, 0), L(0, -a, 0, -g), L(0, g, 0, a)]
        for pen in (QtGui.QPen(QtGui.QColor(0, 0, 0, 160), 3.6),
                    QtGui.QPen(LOCKED if self.locked else QtGui.QColor(255, 255, 255, 235), 1.6)):
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLines(arms)
            if self.locked:
                p.drawEllipse(QtCore.QPointF(0, 0), g - 1.5, g - 1.5)

    def set_locked(self, on: bool) -> None:
        if on != self.locked:
            self.locked = on
            self.update()
