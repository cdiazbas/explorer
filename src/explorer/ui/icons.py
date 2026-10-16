"""Toolbar glyphs drawn as vectors at the size and device pixel ratio each paint asks for (ROADMAP E4.5).

    button.setIcon(icons.reset_panels(button))     the colours follow button.palette()
    toolbar.setIconSize(icons.size(icons.RESET))   a button in a toolbar is asked for the TOOLBAR's size

Why not pixmaps: a QToolButton in a QToolBar is asked for the toolbar's icon size, not its own; on a local Mac that
is 32 x 32 at dpr 2, and fixed pixmaps came back upscaled 1.9x and made the toolbar 44 px high instead of 34. Here
nothing is scaled: each request paints its own pixmap, strokes a whole number of device pixels wide and straight
edges on pixel boundaries. The colour is the palette's text colour at paint time, so a change of system appearance
repaints it right. SF-Symbols-like: rounded caps and joins, one stroke weight, no fills.

From the prototype's app/icons.py (the glyph compared and chosen there: the counterclockwise arrow alone; the slit's,
_slit 111).
"""
import math

from PySide6 import QtCore, QtGui, QtWidgets

QP = QtGui.QPalette


def _snap(v, w):
    """Device coordinate of a stroke centre near v whose edges fall on pixel boundaries (w whole pixels)."""
    return round(v - w / 2) + w / 2


class Pen:
    """Device-pixel drawing on a grid of glyph units (u device px each), strokes w px wide."""

    def __init__(self, p, u, w):
        self.p, self.u, self.w = p, u, w

    def x(self, v):
        return _snap(v * self.u, self.w)

    def arrow(self, cx, cy, r, tail=160.0, head=100.0, arm=0.42):
        """arrow.counterclockwise: an arc from `tail` round to `head` (degrees, counterclockwise from 3 o'clock), an
        open chevron at the head. Centre on the pixel grid, radius whole pixels."""
        u = self.u
        c = QtCore.QPointF(self.x(cx), self.x(cy))
        rr = max(2.0, round(r * u))
        box = QtCore.QRectF(c.x() - rr, c.y() - rr, 2 * rr, 2 * rr)
        path = QtGui.QPainterPath()
        path.arcMoveTo(box, tail)
        path.arcTo(box, tail, (head - tail) % 360)
        a = math.radians(head)
        tip = c + QtCore.QPointF(rr * math.cos(a), -rr * math.sin(a))
        back = math.atan2(math.cos(a), math.sin(a))      # against the direction of travel
        k = max(2.0, arm * r * u)
        for s in (-1, 1):
            b = back + s * math.radians(48)
            path.moveTo(tip + QtCore.QPointF(k * math.cos(b), k * math.sin(b)))
            path.lineTo(tip)
        self.p.drawPath(path)

    def line(self, x0, y0, x1, y1):
        self.p.drawLine(QtCore.QPointF(self.x(x0), self.x(y0)), QtCore.QPointF(self.x(x1), self.x(y1)))

    def poly(self, pts):
        """A closed outline through grid points, its corners rounded by the pen's round join."""
        self.p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(self.x(x), self.x(y)) for x, y in pts]))

    def path(self, pts):
        """An open line through grid points."""
        self.p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(self.x(x), self.x(y)) for x, y in pts]))

    def ring(self, cx, cy, r):
        """A small open circle (a point of a slit)."""
        self.p.drawEllipse(QtCore.QPointF(self.x(cx), self.x(cy)), r * self.u, r * self.u)


def _arrow(g):
    g.arrow(9, 10, 6.8)


def _play(g):                                           # an outlined triangle, optically centred: its area's centre
    g.poly(((6, 3.5), (6, 14.5), (14.5, 9)))            # sits right of its box's, so the box 0.5 unit to the right


def _pause(g):                                          # two bars
    g.line(6.5, 4, 6.5, 14)
    g.line(11.5, 4, 11.5, 14)


def _slit(g):                                           # the slit tool: two points and the line between them
    g.ring(4, 14, 1.9)
    g.ring(14, 4, 1.9)
    g.line(5.4, 12.6, 12.6, 5.4)


# the t steps beside the number in the titles of the temporal panels (ui.titlebar.StepsButton), on a 12-unit grid:
# at the height of the title's digits that is 1 px strokes at 1x, 2 at 2x, as the digits' own stems
def _rows(g):                                           # the rows a lambda-t shows, one per t step read
    for y in (2, 6, 10):
        g.line(1.5, y, 10.5, y)


def _comb(g):                                           # a sampling comb along t: a spine, a tooth per step
    g.line(2, 1, 2, 11)
    for y in (1, 4.33, 7.67, 11):
        g.line(2, y, 10, y)


def _dots(g):                                           # the steps as points along t
    for y in (1.5, 4.5, 7.5, 10.5):
        g.ring(6, y, 0.6)


def _grid(g):                                           # a lambda-t image cut in rows
    g.poly(((1, 1.5), (11, 1.5), (11, 10.5), (1, 10.5)))
    g.line(1, 4.5, 11, 4.5)
    g.line(1, 7.5, 11, 7.5)


# saving the slit's time slice, after the number in the slit's title (ui.titlebar.SaveButton), on the same grid: at
# 8 px the shutter and the label are on different columns, so they do not join into an H
def _disk(g):                                           # a floppy disk: its shutter at the top right, its label below
    g.poly(((1, 1), (9, 1), (11, 3), (11, 11), (1, 11)))
    g.path(((5, 1), (5, 4), (8, 4), (8, 1)))
    g.path(((3, 11), (3, 7.5), (9, 7.5), (9, 11)))


# name: (grid width, grid height, draw(Pen)). Play and pause drawn as the others: the font's ▶ and ⏸ were another
# style beside them, and over X11 another font's
GLYPHS = {"arrow": (18, 18, _arrow), "play": (18, 18, _play), "pause": (18, 18, _pause), "slit": (18, 18, _slit),
          "rows": (12, 12, _rows), "comb": (12, 12, _comb), "dots": (12, 12, _dots), "grid": (12, 12, _grid),
          "disk": (12, 12, _disk)}
RESET = "arrow"                                         # the usual sign for "back to how it was"
STEPS = "grid"                                          # t steps shown at most: a lambda-t cut in rows
SAVE = "disk"                                           # the slit's time slice to a file


class GlyphEngine(QtGui.QIconEngine):
    """Paints a glyph at the requested size and scale in the palette colours of `widget`."""

    def __init__(self, glyph, widget=None):
        super().__init__()
        self.glyph, self.widget = glyph, widget

    def clone(self):
        return GlyphEngine(self.glyph, self.widget)

    def key(self):
        return "explorer-glyph"

    def isNull(self):
        return False

    def actualSize(self, size, mode, state):
        gw, gh, _ = GLYPHS[self.glyph]
        return QtCore.QSize(size.width(), min(size.height(), int(round(size.width() * gh / gw))))

    def _color(self, mode):
        try:
            pal = self.widget.palette() if self.widget is not None else QtWidgets.QApplication.palette()
        except RuntimeError:                            # the widget is gone (icon copied elsewhere)
            pal = QtWidgets.QApplication.palette()
        if mode == QtGui.QIcon.Mode.Disabled:
            return pal.color(QP.ColorGroup.Disabled, QP.ColorRole.WindowText)
        if mode == QtGui.QIcon.Mode.Selected:
            return pal.color(QP.ColorGroup.Active, QP.ColorRole.HighlightedText)
        c = QtGui.QColor(pal.color(QP.ColorGroup.Active, QP.ColorRole.WindowText))
        if mode == QtGui.QIcon.Mode.Active:             # hover over an auto-raise button: full strength
            c.setAlphaF(1.0)
        elif c.alphaF() > 0.85:                         # an opaque text colour (Fusion): 85 %, as macOS's labelColor
            c.setAlphaF(0.85)
        return c

    def scaledPixmap(self, size, mode, state, scale):
        return glyph_pixmap(self.glyph, size, self._color(mode), scale)

    def pixmap(self, size, mode, state):
        return self.scaledPixmap(size, mode, state, 1.0)

    def paint(self, p, rect, mode, state):
        dpr = p.device().devicePixelRatioF() if p.device() is not None else 1.0
        p.drawPixmap(rect.topLeft(), self.scaledPixmap(rect.size(), mode, state, dpr))


def glyph_pixmap(glyph, size, colour, scale) -> QtGui.QPixmap:
    """The glyph in colour at size (logical px) and device pixel ratio scale, centred on whole device pixels."""
    gw, gh, draw = GLYPHS[glyph]
    W, H = max(1, math.ceil(size.width() * scale - 1e-6)), max(1, math.ceil(size.height() * scale - 1e-6))
    pm = QtGui.QPixmap(W, H)
    pm.fill(QtCore.Qt.GlobalColor.transparent)
    u = min(W / gw, H / gh)
    w = max(1, int(1.35 * u + 0.5))                     # 1 px at 1x, 2 at 1.5x, 3 at 2x, 4 at 3x (18-unit glyph)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.translate(round((W - gw * u) / 2), round((H - gh * u) / 2))           # whole pixels: the snap holds
    col = QtGui.QColor(colour)
    alpha = col.alphaF()
    col.setAlphaF(1.0)
    pen = QtGui.QPen(col, w)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    draw(Pen(p, u, w))
    # opaque strokes, then one alpha for all: translucent strokes showed brighter dots where two met
    p.resetTransform()
    p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_DestinationIn)
    p.fillRect(pm.rect(), QtGui.QColor(0, 0, 0, round(alpha * 255)))
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


def glyph_icon(glyph, widget=None) -> QtGui.QIcon:
    return QtGui.QIcon(GlyphEngine(glyph, widget))


def size(glyph) -> QtCore.QSize:
    gw, gh, _ = GLYPHS[glyph]
    return QtCore.QSize(gw, gh)


def reset_panels(widget) -> QtGui.QIcon:
    return glyph_icon(RESET, widget)
