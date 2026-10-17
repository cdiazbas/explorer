"""A title bar of our own (ROADMAP E5.2), so the window looks the same on a Linux desktop, over ssh -Y and from a Mac:
the window manager's frame differs on each (GNOME, KDE, XQuartz's quartz-wm), so the window drops it and draws a
macOS-like bar (traffic lights at the left, the title centred). A local Mac keeps its native frame, which this
imitates. EXPLORER_TITLEBAR=wm keeps the window manager's frame.

Moving: the window manager is asked first (startSystemMove: GNOME and KDE then also snap); XQuartz's quartz-wm offers
no _NET_WM_MOVERESIZE, so otherwise the bar moves the window itself. The same for resizing from the edges. What the
bar and the edges ask of a window is its WindowOps (platform.display; the bridge's own through it).

From the prototype's app/titlebar.py (all of it) and install_titlebar (app/viewer.py:2545).

    chrome(app, window, ops, ops_for)   title bar, rounded corners, edges, dock titles; None where not wanted
"""
import os
import sys

from PySide6 import QtCore, QtGui, QtWidgets

from ..data import tsample
from . import icons

Qt = QtCore.Qt
E = QtCore.QEvent.Type
ENV = "EXPLORER_TITLEBAR"
RESIZE_ENV = "EXPLORER_RESIZE"                         # live: resize at every step of a drag, not on release


def wanted(bridge: bool) -> bool:
    """Our chrome everywhere but on a Mac showing its own windows (its native frame; through the bridge a Mac's
    screen is an X display like any other) and with EXPLORER_TITLEBAR=wm."""
    native_mac = sys.platform == "darwin" and not bridge
    return not native_mac and os.environ.get(ENV) != "wm"


def light(w) -> bool:
    """True when the widget's window colour is light (the light theme, or a light native palette)."""
    return w.palette().color(QtGui.QPalette.ColorRole.Window).lightness() > 128


# ---------------------------------------------------------------- the glass look's light (ui.glass), on its panels and
# on the window's title bar and edge: inside, light falling from above (dark) or a shade (light) that fades out; a rim
# brighter at the top; the accent's light along the top edge, fading at the sides. Keyed by light().
HUD_GLOW = {False: (255, ((0.0, 22), (0.35, 10), (0.7, 3), (1.0, 0))),
            True: (0, ((0.0, 10), (0.35, 5), (0.7, 1), (1.0, 0)))}
HUD_RIM = {False: (255, ((0.0, 70), (0.3, 26), (1.0, 16))), True: (0, ((0.0, 46), (0.3, 18), (1.0, 12)))}


def hud_glow(p: QtGui.QPainter, rect: QtCore.QRectF, height: float, lt: bool) -> None:
    """The light from above over the top `height` px of rect, to nothing at its end: over a 32-px title bar it has
    to end within it, or its last row stood grey against the image below."""
    grey, stops = HUD_GLOW[lt]
    g = QtGui.QLinearGradient(0, rect.top(), 0, rect.top() + height)
    for at, a in stops:
        g.setColorAt(at, QtGui.QColor(grey, grey, grey, a))
    p.fillRect(QtCore.QRectF(rect.left(), rect.top(), rect.width(), height), g)


def hud_rim(p: QtGui.QPainter, rect: QtCore.QRectF, r: float, lt: bool) -> None:
    """The rim 1.5 px inside rect's rounded edge, brighter (darker, in light) at the top."""
    grey, stops = HUD_RIM[lt]
    g = QtGui.QLinearGradient(0, rect.top(), 0, rect.bottom())
    for at, a in stops:
        g.setColorAt(min(at, 120 / max(1.0, rect.height())) if 0 < at < 1 else at, QtGui.QColor(grey, grey, grey, a))
    p.setPen(QtGui.QPen(QtGui.QBrush(g), 1.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(rect.adjusted(1.5, 1.5, -1.5, -1.5), r - 1.5, r - 1.5)


def hud_accent(p: QtGui.QPainter, rect: QtCore.QRectF, r: float, colour: QtGui.QColor) -> None:
    """The accent's light along rect's top edge between the corners, strongest at the middle."""
    g = QtGui.QLinearGradient(rect.left() + r, 0, rect.right() - r, 0)
    for at, a in ((0.0, 0), (0.5, 210), (1.0, 0)):
        c = QtGui.QColor(colour)
        c.setAlpha(a)
        g.setColorAt(at, c)
    p.setPen(QtGui.QPen(QtGui.QBrush(g), 1.5))
    y = rect.top() + 1.75
    p.drawLine(QtCore.QPointF(rect.left() + r, y), QtCore.QPointF(rect.right() - r, y))


class TitleBar(QtWidgets.QWidget):
    """macOS-style: traffic lights (close, minimise, zoom) at the left, the title centred; drag to move, double click
    to zoom. Geometry and colours of macOS 26 (Tahoe), a titlebar-only window; XQuartz shows 1 X pixel per point, so
    points are pixels."""
    H = 32                                             # Tahoe titled window (Sequoia: 28)
    corners: "Corners"                                 # set by install(): the rounded shape and the edges
    resizer: "EdgeResizer"
    hud: QtGui.QColor | None = None                    # the glass look's light (hud_*), in this accent
    D, PITCH, INSET = 14, 23, 9                        # light diameter, centre to centre, left edge (inset: estimate)
    FILL = ("#ED6A5F", "#F6BE50", "#61C555")           # close, minimise, zoom
    RIM = ("#E24B41", "#E1A73E", "#2DAC2F")
    PRESSED = ("#B15048", "#B8923B", "#4A9741")
    GLYPH = ("#460804", "#90591D", "#2A6218")
    INACTIVE = "#4A4A4A"                               # dark mode's inactive grey (estimate)
    INACTIVE_LIGHT = "#CFCFCF"                         # light mode's (estimate)

    def __init__(self, window, ops):
        super().__init__(window)
        self.w, self.m = window, ops
        self.setFixedHeight(self.H)
        self.setMouseTracking(True)                      # hover over the lights shows their symbols
        self._drag = self._press = self._monitor = None
        self._hover = False
        window.windowTitleChanged.connect(lambda _t: self.update())

    def _lights(self):
        return [QtCore.QRectF(self.INSET + self.PITCH * i, (self.H - self.D) / 2, self.D, self.D) for i in range(3)]

    def _active(self):
        return self.m.active

    def _light_at(self, pos):
        return next((i for i, r in enumerate(self._lights()) if r.adjusted(-4, -4, 4, 4).contains(pos)), None)

    def _over_lights(self, pos):                         # macOS shows all three symbols over the group
        L = self._lights()
        return L[0].united(L[-1]).adjusted(-4, -6, 4, 6).contains(pos)

    def _lights_rect(self):
        return QtCore.QRect(0, 0, self.INSET + 3 * self.PITCH, self.H)

    def _set_hover(self, on):
        if on != self._hover:
            self._hover = on
            self.update(self._lights_rect())

    def _glyph(self, p, i, r):
        """x close, - minimise, two diagonal arrows zoom (macOS 11+), in each light's dark tint."""
        c, col = r.center(), QtGui.QColor(self.GLYPH[i])
        k = self.D / 14.0
        P = QtCore.QPointF
        if i == 2:                                       # zoom: two filled triangles pointing to the corners
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            a, b = 0.7 * k, 3.8 * k
            p.drawPolygon(QtGui.QPolygonF([c + P(-b, -b), c + P(a, -b), c + P(-b, a)]))
            p.drawPolygon(QtGui.QPolygonF([c + P(b, b), c + P(-a, b), c + P(b, -a)]))
            return
        pen = QtGui.QPen(col, 1.3 * k)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        d = 3.1 * k
        if i == 0:
            p.drawLine(c + P(-d, -d), c + P(d, d))
            p.drawLine(c + P(-d, d), c + P(d, -d))
        else:
            p.drawLine(c + P(-d - 0.8, 0), c + P(d + 0.8, 0))

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self.palette().color(QtGui.QPalette.ColorRole.Window))   # Tahoe: bar = window
        if self.hud is not None:
            hud_glow(p, QtCore.QRectF(self.rect()), self.height(), light(self))
        active = self._active()
        for i, r in enumerate(self._lights()):
            if active or self._hover:
                fill = QtGui.QColor(self.PRESSED[i] if self._press == i else self.FILL[i])
                rim = QtGui.QColor(self.RIM[i])
            else:
                fill = rim = QtGui.QColor(self.INACTIVE_LIGHT if light(self) else self.INACTIVE)
            p.setBrush(fill)
            p.setPen(QtGui.QPen(rim, 0.8))
            p.drawEllipse(r.adjusted(0.4, 0.4, -0.4, -0.4))
            if self._hover:
                self._glyph(p, i, r)
        f = p.font()
        f.setWeight(QtGui.QFont.Weight.DemiBold)
        p.setFont(f)
        # the title in the window's text colour (a fixed white is unreadable on the light theme's bar): 85 % active,
        # 43 % inactive
        ink = QtGui.QColor(self.palette().color(QtGui.QPalette.ColorRole.WindowText))
        ink.setAlpha(217 if active else 110)
        p.setPen(ink)
        from .._name import APP_NAME

        text = p.fontMetrics().elidedText(self.w.windowTitle() or APP_NAME, Qt.TextElideMode.ElideMiddle,
                                          self.width() - 2 * 90)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)

    def changeEvent(self, e):
        if e.type() == E.ActivationChange:
            self.update()
        super().changeEvent(e)

    def mousePressEvent(self, e):
        self._press = self._light_at(e.position())
        if self._press is not None:
            self.update(self._lights_rect())
        self._drag = self._monitor = None
        if self._press is None and e.button() == Qt.MouseButton.LeftButton and not self.m.begin_drag():
            self._drag = (e.globalPosition().toPoint(), self.w.pos())   # the manager cannot: we move it

    def mouseMoveEvent(self, e):
        self._set_hover(self._over_lights(e.position()))
        if self._drag:
            g0, p0 = self._drag
            gp = e.globalPosition().toPoint()
            d = gp - g0
            self.m.move(p0.x() + d.x(), max(p0.y() + d.y(), self._top(gp)))

    def _top(self, gp) -> int:
        """The top of the monitor under the pointer: the window goes no higher, as a macOS window's bar stays below
        the menu bar (by the sides and the bottom it may leave). Over XQuartz the bar moves the window itself and
        nothing else held it: dragged up, it left the screen. Asked again only when the pointer leaves that
        monitor (on X11 its heads are an X request)."""
        if self._monitor is None or not self._monitor.contains(gp):
            from ..platform.screens import monitor_rect

            self._monitor = monitor_rect(QtWidgets.QApplication.instance(), gp)
        return self._monitor.top()

    def leaveEvent(self, e):
        self._set_hover(False)

    def mouseReleaseEvent(self, e):
        i, self._press, self._drag = self._press, None, None
        if i is not None:
            self.update(self._lights_rect())
        if i is not None and self._light_at(e.position()) == i:      # released on the light it was pressed on
            (self.w.close, self.m.minimize, self.m.zoom)[i]()

    def mouseDoubleClickEvent(self, e):
        if self._light_at(e.position()) is None:
            self.m.zoom()


# ---------------------------------------------------------------- rounded corners
# X11 can shape a window (SHAPE, 1 bit per pixel) but XQuartz has no 32-bit ARGB visual nor Composite, so the
# corners cannot blend with what lies behind the window, nor get macOS's shadow. The window's shape is a rounded
# rectangle, and a 1-px hairline is drawn antialiased just inside the curve: it hides most of the 1-bit staircase.
RADIUS = 16              # px = pt over XQuartz; macOS 26 titlebar-only window (14/15: 10)
HAIRLINE = QtGui.QColor(255, 255, 255, 31)    # inner light line, ~12 % (estimate)
OUTLINE = QtGui.QColor(0, 0, 0, 128)          # outer dark line, ~50 % (estimate)
HAIRLINE_LIGHT = QtGui.QColor(255, 255, 255, 0)   # light windows: no inner light line, a fainter outer one
OUTLINE_LIGHT = QtGui.QColor(0, 0, 0, 64)


def rounded_region(rect, r) -> QtGui.QRegion:
    path = QtGui.QPainterPath()
    path.addRoundedRect(QtCore.QRectF(rect), r, r)
    return QtGui.QRegion(path.toFillPolygon().toPolygon())


def round_window(w: QtWidgets.QWidget, radius: int) -> None:
    """w's shape: rounded while it is a window of its own (a floating panel), square docked. A mask on xcb, the X
    SHAPE through the bridge (which publishes the region it finds on the widget), nothing on a local Mac (the
    system rounds its windows, and a mask there cut them square)."""
    from ..platform.xbridge.windows import SHAPE_ATTR

    platform = QtGui.QGuiApplication.platformName()
    region = rounded_region(w.rect(), radius) if w.isWindow() and platform != "cocoa" else QtGui.QRegion()
    setattr(w, SHAPE_ATTR, region)
    if platform == "xcb":
        if region.isEmpty():
            w.clearMask()
        else:
            w.setMask(region)


EDGE = 3                    # px of the hairline overlay along each edge: its two lines are 1 px, at 0.5 and 1.5


class Corners(QtCore.QObject):
    """Keeps the window's shape rounded (WindowOps.set_shape: a mask on xcb, the X SHAPE through the bridge) and the
    hairline overlay above every child."""

    def __init__(self, window, ops, radius=RADIUS):
        super().__init__(window)
        self.w, self.ops, self.r = window, ops, radius
        self.region = QtGui.QRegion()
        self.line = Hairline(window, radius)
        window.installEventFilter(self)
        self.apply()

    def apply(self):
        self.region = QtGui.QRegion() if self.w.isFullScreen() else rounded_region(self.w.rect(), self.r)
        self.ops.set_shape(self.region)
        rect = self.w.rect()
        self.line.setGeometry(rect)
        # masked to what it draws, the edges and the corners' curves: unmasked, every repaint under it repainted it
        # too (8 rounded outlines a step of the 2x2 view, 2.4 ms on bellatrix)
        ring = QtGui.QRegion(rect).subtracted(QtGui.QRegion(rect.adjusted(EDGE, EDGE, -EDGE, -EDGE)))
        for x, y in ((0, 0), (rect.width() - self.r, 0), (0, rect.height() - self.r),
                     (rect.width() - self.r, rect.height() - self.r)):
            ring = ring.united(QtGui.QRegion(x, y, self.r, self.r))
        self.line.setMask(ring)
        self.line.raise_()

    def eventFilter(self, obj, e):
        if obj is self.w and e.type() in (E.Resize, E.WindowStateChange):
            self.apply()
        elif obj is self.w and e.type() == E.ChildAdded:
            QtCore.QTimer.singleShot(0, self.line, self.line.raise_)   # docks re-parented later stay below it
        return False


class Hairline(QtWidgets.QWidget):
    hud: QtGui.QColor | None = None                    # the glass look's rim and accent light (hud_*) instead

    def __init__(self, window, radius):
        super().__init__(window)
        self.r = radius
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # macOS draws a dark hairline outside and a light one inside; nothing can be drawn outside the window
        # (no alpha on XQuartz), so both go inside: the dark one on the edge also softens the 1-bit stairs
        lt = light(self)
        p.setPen(QtGui.QPen(OUTLINE_LIGHT if lt else OUTLINE, 1.0))
        p.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self.r - 0.5, self.r - 0.5)
        if self.hud is not None:
            rect = QtCore.QRectF(self.rect())
            hud_rim(p, rect, self.r, lt)
            hud_accent(p, rect, self.r, self.hud)
            return
        p.setPen(QtGui.QPen(HAIRLINE_LIGHT if lt else HAIRLINE, 1.0))
        p.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), self.r - 1.5, self.r - 1.5)


# ---------------------------------------------------------------- resizing from every edge, as on macOS
class Outline:
    """The size a window is being dragged to, drawn by Qt as four thin windows round it (ToolTip: override-redirect,
    never focused, on top; no pointer grab, unlike a popup): where there is no X server to draw it (the window's
    ops give no outline). Over X11 the server draws it (platform.xoutline): there these four strips cost XQuartz 57 ms
    a step, and queued."""
    T = 2                                               # px

    def __init__(self, owner: QtWidgets.QWidget):
        flags = Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus
        colour = owner.palette().color(QtGui.QPalette.ColorRole.Highlight)
        self.bars = []
        for _ in range(4):
            b = QtWidgets.QWidget(owner, flags)
            b.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            b.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            pal = b.palette()
            pal.setColor(QtGui.QPalette.ColorRole.Window, colour)
            b.setPalette(pal)
            b.setAutoFillBackground(True)
            self.bars.append(b)

    def show(self, r: QtCore.QRect) -> None:
        t = self.T
        for b, g in zip(self.bars, (QtCore.QRect(r.x(), r.y(), r.width(), t),
                                    QtCore.QRect(r.x(), r.bottom() - t + 1, r.width(), t),
                                    QtCore.QRect(r.x(), r.y(), t, r.height()),
                                    QtCore.QRect(r.right() - t + 1, r.y(), t, r.height())), strict=True):
            b.setGeometry(g)
            if not b.isVisible():
                b.show()
            b.raise_()

    def hide(self) -> None:
        for b in self.bars:
            b.hide()

    def close(self) -> None:
        self.hide()


def outline_colours(w) -> tuple[QtGui.QColor, QtGui.QColor, QtGui.QColor]:
    """The resize outline's border, inside and ink, in w's look: the accent round the darker of the window's and
    the content's colours (never white: a white flash was what the shaped ring showed on XQuartz); in glass its
    accent round its slab."""
    from . import glass, style

    main = w if isinstance(w, QtWidgets.QMainWindow) else w.parentWidget()
    g = getattr(main, "glass", None)
    if g is not None and getattr(g, "on", False):
        mode = "light" if light(w) else "dark"
        return glass.accent(), QtGui.QColor(glass.SLAB[mode][0]), QtGui.QColor(glass.INK[mode])
    pal = w.palette()
    inside = min(pal.color(QtGui.QPalette.ColorRole.Window), pal.color(QtGui.QPalette.ColorRole.Base),
                 key=lambda c: c.lightness())
    return style.accent(), inside, pal.color(QtGui.QPalette.ColorRole.Text)


class EdgeResizer(QtCore.QObject):
    """Without the window manager's frame there are no resize borders: a 7-px band inside every edge and 16-px corner
    zones (the corner radius) resize the window, with the matching pointer. The window manager does it when it can
    (startSystemResize: GNOME, KDE); XQuartz's cannot, so then this resizes it: an outline follows the pointer (the
    X server's, platform.xoutline, at the pace the server keeps; else Qt's, Outline, every 25 ms at most), and the
    window takes that size once, where the pointer is released. Resized at
    every step, over X11 the whole window was redrawn and sent each time, and it flickered: through an emulated ssh
    link (bench/xlink.py, 8 ms each way, 20 MB/s, the bridge) a 1-s drag of 200 px sent 17.7 MB while dragging, the
    link full, 24.9 MB in all; with the outline 0.7-0.9 MB, 3.3-3.5 MB in all. EXPLORER_RESIZE=live resizes at every
    step, as before.
    7 px: macOS grabs an edge 3 pt inside and 4 pt outside the window; an X window takes no input outside itself (no
    ARGB visual on XQuartz, a SHAPE only cuts), so the same 7 go inside. A button inside the band keeps its clicks:
    a floating panel's float button sits in the top-right corner zone, and a band taking it lost about half of the
    clicks on it."""
    BAND, CORNER = 7, 16
    MIN_W, MIN_H = 640, 400
    SHAPES = {Qt.Edge.LeftEdge: Qt.CursorShape.SizeHorCursor, Qt.Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
              Qt.Edge.TopEdge: Qt.CursorShape.SizeVerCursor, Qt.Edge.BottomEdge: Qt.CursorShape.SizeVerCursor}

    def __init__(self, window, ops, min_size=None):
        super().__init__(window)
        self.w, self.m = window, ops
        if min_size is not None:
            self.MIN_W, self.MIN_H = min_size
        self.top_band = self.BAND
        self._drag: tuple | None = None
        self._cursor = None
        self._pending = None
        self._timer = QtCore.QTimer(self, singleShot=True, interval=25)
        self._timer.timeout.connect(self._apply)
        self.live = os.environ.get(RESIZE_ENV) == "live"
        self.outline = None                             # the X server's (ready from here) or Qt's, made at a press
        if not self.live:
            self.outline = getattr(ops, "outline", lambda c: None)(
                window.palette().color(QtGui.QPalette.ColorRole.Highlight))
            if self.outline is not None:
                window.destroyed.connect(self.outline.close)

    def edges_at(self, p):
        w, h, x, y = self.w.width(), self.w.height(), p.x(), p.y()
        left, right, top, bottom = x < self.BAND, x >= w - self.BAND, y < self.top_band, y >= h - self.BAND
        e = Qt.Edge(0)
        if left or (x < self.CORNER and (top or bottom)):
            e |= Qt.Edge.LeftEdge
        if right or (x >= w - self.CORNER and (top or bottom)):
            e |= Qt.Edge.RightEdge
        if top or (y < self.CORNER and (left or right)):
            e |= Qt.Edge.TopEdge
        if bottom or (y >= h - self.CORNER and (left or right)):
            e |= Qt.Edge.BottomEdge
        if e and isinstance(self.w.childAt(p), QtWidgets.QAbstractButton):
            return Qt.Edge(0)
        return e

    def _shape(self, e):
        if not e:
            return None
        L, R, T, B = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge
        if e in (T | L, B | R):
            return Qt.CursorShape.SizeFDiagCursor
        if e in (T | R, B | L):
            return Qt.CursorShape.SizeBDiagCursor
        return next((c for k, c in self.SHAPES.items() if e == k), None)

    def _set_cursor(self, shape):
        if shape != self._cursor:
            self._cursor = shape
            self.m.set_cursor(shape)

    def mouse(self, kind, pos, gpos, buttons):
        """True when the event is the resize's, so nothing below gets it."""
        if kind == E.MouseMove:
            if self._drag:
                self._pending = self._rect(gpos)
                if not self._timer.isActive():
                    self._timer.start()
                return True
            if not (buttons & Qt.MouseButton.LeftButton):
                self._set_cursor(self._shape(self.edges_at(pos)))
            return False
        if kind == E.MouseButtonPress and buttons & Qt.MouseButton.LeftButton:
            edges = self.edges_at(pos)
            if not edges:
                return False
            if not self.m.begin_resize(edges):
                self._drag = (edges, QtCore.QPoint(gpos), self.w.geometry())
                paint = getattr(self.outline, "colours", None)
                if paint is not None:                       # the X server's: the look as it is now
                    paint(*outline_colours(self.w))
                if not self.live and self.outline is None:
                    self.outline = Outline(self.w)      # no X server to draw it: Qt's
            return True
        if kind == E.MouseButtonRelease and self._drag:
            self._pending = self._rect(gpos)            # where it is released: the moves before may not all have come
            self._drag = None
            self._timer.stop()
            self._apply(final=True)
            return True
        return False

    def _rect(self, gpos) -> QtCore.QRect:
        assert self._drag is not None                   # called while a drag is on
        edges, g0, geom = self._drag
        d = gpos - g0
        r = QtCore.QRect(geom)
        # QRect's right and bottom are its last pixel: MIN - 1 from the opposite edge is MIN wide
        if edges & Qt.Edge.LeftEdge:
            r.setLeft(min(geom.left() + d.x(), geom.right() - self.MIN_W + 1))
        if edges & Qt.Edge.RightEdge:
            r.setRight(max(geom.right() + d.x(), geom.left() + self.MIN_W - 1))
        if edges & Qt.Edge.TopEdge:
            r.setTop(min(geom.top() + d.y(), geom.bottom() - self.MIN_H + 1))
        if edges & Qt.Edge.BottomEdge:
            r.setBottom(max(geom.bottom() + d.y(), geom.top() + self.MIN_H - 1))
        return r

    def _apply(self, final: bool = False):
        if self._pending is None:
            return
        r, self._pending = self._pending, None
        if self.outline is not None and not final:
            self.outline.show(r)
            return
        if self.outline is not None:
            self.outline.hide()
        self.m.set_geometry(r)

    def eventFilter(self, obj, e):                   # on the window's QWindow: every mouse event passes it
        t = e.type()
        if t in (E.MouseMove, E.MouseButtonPress, E.MouseButtonRelease):
            b = e.buttons() | (e.button() if t == E.MouseButtonPress else Qt.MouseButton.NoButton)
            return self.mouse(t, e.position().toPoint(), e.globalPosition().toPoint(), b)
        if t == E.Leave:
            self._set_cursor(None)
        return False


# ---------------------------------------------------------------- dock titles
# Qt draws a floating dock's title bar itself only on xcb; elsewhere it asks for the system's frame. Through the
# bridge Qt runs offscreen, so a floating dock got the window manager's frame, whose clicks never reach Qt: it could
# not be dragged back nor docked again. A title bar widget of our own makes Qt draw and handle it as on xcb. It only
# paints (with the style's dock title) and holds the buttons; presses and double clicks are left to QDockWidget,
# which drags, floats and docks as usual (Qt's documented contract).
class TimeSteps(QtCore.QObject):
    """The number of t steps the temporal panels show at most (data.tsample), as their titles show it: set(v) asks
    for it (the session's), update(v) says what it is now (changed then repaints the numbers)."""
    changed = QtCore.Signal(object)

    def __init__(self, value, ask, parent=None):
        super().__init__(parent)
        self.value, self.ask = value, ask

    def set(self, v) -> None:
        self.ask(v)

    def update(self, v) -> None:
        if v != self.value:
            self.value = v
            self.changed.emit(v)

    def step(self, d: int) -> None:
        """The next choice up (d > 0) or down: 25 50 100 all."""
        ch = list(tsample.CHOICES)
        i = ch.index(self.value) if self.value in ch else ch.index(tsample.CAP)
        self.set(ch[min(len(ch) - 1, max(0, i + d))])


class TitleButton(QtWidgets.QAbstractButton):
    """A small button of a panel's title, drawn here: a glyph (ui.icons) as high as the title's digits, centred on
    them, a faint rounded back under the pointer. ink: the colour of what it draws (None: the palette's text); the
    glass title sets its own."""

    def __init__(self, parent, tip: str):
        super().__init__(parent)
        self.ink: QtGui.QColor | None = None
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tip)
        f = QtGui.QFont(self.font())
        f.setPointSizeF(max(6.0, f.pointSizeF() * 0.85))
        self.setFont(f)
        self.glyph = round(QtGui.QFontMetrics(f).capHeight()) + 1   # px: the glyph's square, the digits' height + 1

    def _start(self) -> tuple[QtGui.QPainter, QtGui.QColor, float, int]:
        """A painter on it with its back drawn, the ink, the digits' baseline and the glyph's top there."""
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        ink = (QtGui.QColor(self.ink) if self.ink is not None
               else self.palette().color(QtGui.QPalette.ColorRole.WindowText))
        if self.underMouse() or self.isDown():
            c = QtGui.QColor(ink)
            c.setAlpha(40)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)
        fm = QtGui.QFontMetrics(self.font())
        base = (self.height() - fm.height()) / 2 + fm.ascent()     # where AlignCenter puts the baseline
        return p, ink, base, round(base - fm.capHeight() / 2 - self.glyph / 2)     # the glyph centred on the digits

    def _glyph(self, p: QtGui.QPainter, name: str, x: int, y: int, ink: QtGui.QColor) -> None:
        g = self.glyph
        p.drawPixmap(x, y, icons.glyph_pixmap(name, QtCore.QSize(g, g), ink, self.devicePixelRatioF()))

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()


class StepsButton(TitleButton):
    """The t steps shown, a small number beside the close and float marks after a glyph that says what it counts
    (icons.STEPS, the digits' height): a click opens the choices, the wheel steps through them."""
    GAP = 3                                             # px between the glyph and the number

    def __init__(self, steps: TimeSteps, parent, size: QtCore.QSize):
        super().__init__(parent, "t steps shown at most, read evenly spread over t (click: choose; wheel: change).\n"
                                 "Fewer read faster; \"all\" reads every t.")
        self.steps = steps
        self.setObjectName("time_steps")
        fm = QtGui.QFontMetrics(self.font())
        w = self.glyph + self.GAP + max(fm.horizontalAdvance(t) for t in ("100", "all")) + 8
        self.setFixedSize(max(size.width(), w), size.height())
        self.clicked.connect(self.choose)
        # a method, not a lambda: Qt drops the connection with the button (a title replaced by another look's),
        # where a lambda stays connected and repaints a deleted button at every change
        steps.changed.connect(self._changed)

    def _changed(self, _v) -> None:
        self.update()

    def choose(self) -> None:
        m = QtWidgets.QMenu(self)
        for v in tsample.CHOICES:
            a = m.addAction(tsample.label(v))
            a.setCheckable(True)
            a.setChecked(v == self.steps.value)
            a.triggered.connect(lambda _on=False, v=v: self.steps.set(v))
        m.popup(self.mapToGlobal(QtCore.QPoint(0, self.height())))

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if d:
            self.steps.step(1 if d > 0 else -1)
        e.accept()

    def paintEvent(self, e):
        p, ink, base, y = self._start()
        text = tsample.label(self.steps.value)
        g = self.glyph
        x = round((self.width() - (g + self.GAP + QtGui.QFontMetrics(self.font()).horizontalAdvance(text))) / 2)
        self._glyph(p, icons.STEPS, x, y, ink)
        p.setPen(ink)
        p.setFont(self.font())
        p.drawText(QtCore.QPointF(x + g + self.GAP, base), text)


SAVE_TIP = "Save the slit's time slice to a FITS file (as shown: this Stokes, this λ, these t steps)"


class SaveButton(TitleButton):
    """After the number of t steps in the slit's title: its glyph (icons.SAVE) alone, the digits' height; a click
    calls save() (Shell.save_slit, which says on the status line what it wrote, or why nothing)."""
    PAD = 4                                             # px each side of the glyph

    def __init__(self, save, parent, size: QtCore.QSize):
        super().__init__(parent, SAVE_TIP)
        self.save = save
        self.setObjectName("save_slit")
        self.setFixedSize(self.glyph + 2 * self.PAD, size.height())
        self.clicked.connect(self._clicked)

    def _clicked(self) -> None:
        self.save()

    def paintEvent(self, e):
        p, ink, _base, y = self._start()
        self._glyph(p, icons.SAVE, round((self.width() - self.glyph) / 2), y, ink)


STEPS_GAP_QT = 4                                        # px from Qt's float mark to the number of t steps


class QtMark(QtWidgets.QAbstractButton):
    """Close or float as QDockWidget draws its own (QDockWidgetTitleButton, qdockwidget.cpp): the icon Qt gave its
    own button (own), painted as a tool button without a frame where the style's dock buttons have none (macOS: the
    grey discs). A title of ours standing in for Qt's (DockTitle, stand_in) shows the marks of the panels beside it,
    which keep Qt's."""

    def __init__(self, own: QtWidgets.QAbstractButton, parent):
        super().__init__(parent)
        self.own = own                                  # Qt keeps its icon in the style's (a change of style too)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setSizePolicy(own.sizePolicy())
        self.resize(own.sizeHint())                     # placed by the title where Qt places its own

    def sizeHint(self):
        return self.own.sizeHint()

    def _icon_size(self) -> QtCore.QSize:
        st, S = self.style(), QtWidgets.QStyle
        n = st.pixelMetric(S.PixelMetric.PM_SmallIconSize, None, self)
        if st.styleHint(S.StyleHint.SH_DockWidget_ButtonsHaveFrame, None, self):
            n = n * 5 // 8
        return QtCore.QSize(n, n)

    def paintEvent(self, e):
        S = QtWidgets.QStyle
        p = QtWidgets.QStylePainter(self)
        opt = QtWidgets.QStyleOptionToolButton()
        opt.initFrom(self)
        opt.state |= S.StateFlag.State_AutoRaise
        if self.style().styleHint(S.StyleHint.SH_DockWidget_ButtonsHaveFrame, None, self):
            if self.isEnabled() and self.underMouse() and not self.isDown():
                opt.state |= S.StateFlag.State_Raised
            if self.isDown():
                opt.state |= S.StateFlag.State_Sunken
            p.drawPrimitive(S.PrimitiveElement.PE_PanelButtonTool, opt)
        elif self.isDown():
            opt.state |= S.StateFlag.State_On | S.StateFlag.State_Sunken
        opt.icon = self.own.icon()
        opt.subControls = S.SubControl.SC_None
        opt.activeSubControls = S.SubControl.SC_None
        opt.features = QtWidgets.QStyleOptionToolButton.ToolButtonFeature.None_
        opt.arrowType = Qt.ArrowType.NoArrow
        opt.iconSize = self._icon_size()
        p.drawComplexControl(S.ComplexControl.CC_ToolButton, opt)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()


class DockTitle(QtWidgets.QWidget):
    """Close and float buttons at the left, the title centred: what macOS draws on a local Mac, so every path looks
    and works the same. A temporal panel's (dock.steps, a TimeSteps) has the number of its t steps after them.
    stand_in: the title stands in for Qt's own (Shell.give_steps: a local Mac, where the other panels keep Qt's);
    under the native macOS style, and under any style on a local Mac (explorer's dark and light themes), its close
    and float are then Qt's (QtMark), where Qt puts them, and the bar is drawn in the panel's style (MacSeams: no
    light line under it), so it reads as its neighbours' titles: the macOS style's marks at the left, the name centred
    after the number; the themes' marks at the right, the name at the left as the style draws Qt's, the number by the
    marks."""
    QT_MARKS = ("macos",)                               # the styles whose stand-in titles show Qt's marks
    QT_MARKS_PLATFORMS = ("cocoa",)                     # and the platforms, whatever the style

    def __init__(self, dock, stand_in: bool = False):
        super().__init__(dock)
        self.d = dock
        self.qt_marks = stand_in and (QtWidgets.QApplication.style().name() in self.QT_MARKS
                                      or QtGui.QGuiApplication.platformName() in self.QT_MARKS_PLATFORMS)
        st = dock.style()
        PM = QtWidgets.QStyle.PixelMetric
        m = st.pixelMetric(PM.PM_DockWidgetTitleMargin, None, dock)
        # the size of Qt's own dock buttons (QDockWidgetTitleButton): the small icon size, at most 10 px at 96 dpi
        icon = min(st.pixelMetric(PM.PM_SmallIconSize, None, dock), 10 * self.logicalDpiX() // 96)
        bm = st.pixelMetric(PM.PM_DockWidgetTitleBarButtonMargin, None, dock)
        size = QtCore.QSize(icon + 2 * bm, icon + 2 * bm)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(m + 4, 0, m + 4, 0)
        lay.setSpacing(2)
        self.buttons: list[QtWidgets.QAbstractButton] = []
        SP = QtWidgets.QStyle.StandardPixmap
        for name, sp, tip, fn in (("qt_dockwidget_closebutton", SP.SP_DockWidgetCloseButton,
                                   "Close (Panels in the toolbar opens it again)", dock.close),
                                  ("qt_dockwidget_floatbutton", SP.SP_TitleBarNormalButton,
                                   "Float / dock", lambda: dock.setFloating(not dock.isFloating()))):
            if self.qt_marks:
                b: QtWidgets.QAbstractButton = QtMark(
                    dock.findChild(QtWidgets.QAbstractButton, name, Qt.FindChildOption.FindDirectChildrenOnly), self)
            else:
                b = QtWidgets.QToolButton(self)
                b.setAutoRaise(True)
                b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                b.setIcon(st.standardIcon(sp, None, dock))
                b.setIconSize(QtCore.QSize(icon, icon))
                b.setFixedSize(size)
            b.setObjectName(name)                        # the names Qt gives its own (tests find them by name)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            if not self.qt_marks:                        # Qt's marks go where Qt puts its own: qt_places
                lay.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
            self.buttons.append(b)
        self.button = self.buttons[1]                    # the float button
        if self.qt_marks:                                # the number as high as Qt's marks (resizeEvent)
            size = self.button.sizeHint()
        steps, save = getattr(dock, "steps", None), getattr(dock, "save", None)
        self.steps_button = StepsButton(steps, self, size) if isinstance(steps, TimeSteps) else None
        # the slit's (dock.save, Shell.save_slit): its time slice to a file, right after the number
        self.save_button = SaveButton(save, self, size) if self.steps_button is not None and callable(save) else None
        if self.steps_button is not None and not self.qt_marks:
            lay.addSpacing(2)
            lay.addWidget(self.steps_button, 0, Qt.AlignmentFlag.AlignVCenter)
            if self.save_button is not None:
                lay.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addStretch(1)

    def _qt_rects(self, rect: QtCore.QRect) -> list[QtCore.QRect]:
        """Where Qt puts its own close, float and title text in a title of this rect: the style's
        (QDockWidgetLayout::setGeometry, from the panel's title option)."""
        opt = QtWidgets.QStyleOptionDockWidget()
        opt.initFrom(self.d)
        opt.rect = rect
        opt.movable, opt.floatable, opt.closable, opt.verticalTitleBar = True, True, True, False
        SE = QtWidgets.QStyle.SubElement
        st = self.d.style()
        return [st.subElementRect(se, opt, self.d)
                for se in (SE.SE_DockWidgetCloseButton, SE.SE_DockWidgetFloatButton, SE.SE_DockWidgetTitleBarText)]

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.qt_marks:
            self._place_qt_marks()

    def marks_at_right(self) -> bool:
        return self.qt_marks and self.button.geometry().center().x() > self.width() // 2

    def _place_qt_marks(self) -> None:
        rects = self._qt_rects(self.rect())
        for b, r in zip(self.buttons, rects[:2], strict=True):
            QtWidgets.QWidgetItem(b).setGeometry(r)     # as Qt lays out its own: within their size and policy
        if self.steps_button is None:
            return
        f = self.button.geometry()                      # as high as the float mark
        self.steps_button.setFixedHeight(f.height())
        if self.save_button is not None:
            self.save_button.setFixedHeight(f.height())
        if self.marks_at_right():                       # before the marks: number and save end STEPS_GAP_QT short
            end = min(b.geometry().left() for b in self.buttons) - STEPS_GAP_QT
            if self.save_button is not None:
                self.save_button.move(end - self.save_button.width(), f.top())
                end = self.save_button.x()
            self.steps_button.move(end - self.steps_button.width(), f.top())
        else:                                           # after the float mark
            self.steps_button.move(f.right() + 1 + STEPS_GAP_QT, f.top())
            if self.save_button is not None:
                self.save_button.move(self.steps_button.geometry().right() + 1, f.top())

    def left_end(self) -> int:
        """Where the marks at the left end, x: the title stays clear of them on both sides."""
        return (self.save_button or self.steps_button or self.buttons[-1]).geometry().right()

    def sizeHint(self):
        # Qt's rule (QDockWidgetLayout::titleHeight): the button plus 2, or the dock's font plus the margins
        m = self.d.style().pixelMetric(QtWidgets.QStyle.PixelMetric.PM_DockWidgetTitleMargin, None, self.d)
        # (Qt's own button's size where the marks are Qt's: the title as high as the panels' beside it)
        h = self.button.own.sizeHint().height() if isinstance(self.button, QtMark) else self.button.height()
        return QtCore.QSize(80, max(self.d.fontMetrics().height() + 2 * m, h + 2))

    minimumSizeHint = sizeHint

    def paintEvent(self, e):
        p = QtWidgets.QStylePainter(self)
        opt = QtWidgets.QStyleOptionDockWidget()
        opt.initFrom(self.d)
        opt.rect = self.rect()
        opt.title = ""                                   # the style paints the bar; the title goes centred below
        opt.movable, opt.floatable, opt.closable, opt.verticalTitleBar = True, True, True, False
        if self.qt_marks:
            self._paint_as_qt(p, opt)
            return
        p.drawControl(QtWidgets.QStyle.ControlElement.CE_DockWidgetTitle, opt)
        f = QtGui.QFont(self.d.font())
        f.setWeight(QtGui.QFont.Weight.DemiBold)
        p.setFont(f)
        side = self.left_end() + 6                       # clear of the buttons on both sides: centred
        r = self.rect().adjusted(side, 0, -side, 0)
        text = QtGui.QFontMetrics(f).elidedText(self.d.windowTitle(), Qt.TextElideMode.ElideRight, max(0, r.width()))
        R = QtGui.QPalette.ColorRole
        p.setPen(self.palette().color(R.WindowText if self.isEnabled() else R.PlaceholderText))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_as_qt(self, p: QtGui.QPainter, opt: QtWidgets.QStyleOptionDockWidget) -> None:
        """The bar and the title as QDockWidget paints its own: in the panel's style (MacSeams: no light line under
        it), the name in the panel's font centred where the style puts it (after the marks), moved clear of the
        number (and the slit's save) when it would run over it. With the marks at the right (explorer's themes) the
        style draws the name too, where it draws Qt's (at the left), cut short before the number."""
        st = self.d.style()
        if self.marks_at_right():
            r = self._qt_rects(self.rect())[2]
            f = QtGui.QFont(self.font())
            f.setWeight(QtGui.QFont.Weight.DemiBold)    # the widest a style draws it: elided early, never late
            room = (self.steps_button.x() - 6 if self.steps_button is not None else r.right()) - r.left()
            opt.title = QtGui.QFontMetrics(f).elidedText(self.d.windowTitle(), Qt.TextElideMode.ElideRight,
                                                         max(0, room))
            st.drawControl(QtWidgets.QStyle.ControlElement.CE_DockWidgetTitle, opt, p, self)
            return
        st.drawControl(QtWidgets.QStyle.ControlElement.CE_DockWidgetTitle, opt, p, self)
        r = self._qt_rects(self.rect())[2]
        fm = QtGui.QFontMetrics(self.d.font())
        if self.steps_button is not None:
            clear = self.left_end() + 6
            if r.center().x() - fm.horizontalAdvance(self.d.windowTitle()) / 2 < clear:
                r.setLeft(clear)                        # it would run over it: centred after it, elided if need be
        text = fm.elidedText(self.d.windowTitle(), Qt.TextElideMode.ElideRight, max(0, r.width()))
        p.setFont(self.d.font())
        st.drawItemText(p, r, int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextHideMnemonic), self.palette(),
                        self.isEnabled(), text, QtGui.QPalette.ColorRole.WindowText)


def dock_titles(window) -> None:
    """Our title bars on every dock of the window, but one with its own (a linked image's: ui.linked.ImageTitle);
    the window remembers it, for the docks made later (dress)."""
    window.dock_titles = True
    for d in window.findChildren(QtWidgets.QDockWidget):
        if not getattr(d.titleBarWidget(), "own", False):
            d.setTitleBarWidget(DockTitle(d))


def dress(window, dock) -> None:
    """A dock made after chrome (a cube's spectra and lambda-t in its window, ui.linked) dressed as the window's own:
    our title and the main window's edges when floating, where chrome put them on."""
    if getattr(window, "dock_titles", False) and not getattr(dock.titleBarWidget(), "own", False):
        dock.setTitleBarWidget(DockTitle(dock))
    ops_for = getattr(window, "panel_ops", None)
    if ops_for is not None:
        window._panel_edges.append(PanelEdges(dock, ops_for(dock)))


# ---------------------------------------------------------------- floating panels: the main window's edges
# A floating panel is resized by Qt's QWidgetResizeHandler, which only sees the mouse where no child covers the panel:
# its 1-px frame, plus the top 5 px inside Qt's own title on xcb, so a resize pointer 1 px wide on most edges. The
# panels get the main window's EdgeResizer, on the QWindow each one gets when it floats.
PANEL_MIN = (200, 150)          # a floating panel's smallest size by its edges (Qt's own allowed 60 x 76)


class PanelEdges(QtCore.QObject):
    def __init__(self, dock, ops):
        super().__init__(dock)
        self.d = dock
        self.resizer = EdgeResizer(dock, ops, PANEL_MIN)
        # a panel's title is 17 px: a 7-px band resized where a drag should move it, and the close and float buttons
        # sit near the top. 3 px, what macOS keeps inside the top edge (the rest of its 7 pt are outside the window)
        self.resizer.top_band = 3
        self._h = None
        dock.installEventFilter(self)

    def eventFilter(self, obj, e):
        # isinstance: a panel being destroyed can reach here as a plain QWidget
        if e.type() in (E.Show, E.WinIdChange) and isinstance(obj, QtWidgets.QDockWidget) and obj.isFloating():
            h = obj.windowHandle()                   # a new QWindow each time the panel floats
            if h is not None and h is not self._h:
                h.installEventFilter(self.resizer)
                self._h = h
        return False


def install(window, ops) -> TitleBar:
    """The bar on window (frameless from here), its rounded shape and its edges."""
    window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    bar = TitleBar(window, ops)
    window.setMenuWidget(bar)
    bar.corners = Corners(window, ops)
    bar.resizer = resizer = EdgeResizer(window, ops)
    if ops.qwindow_events:
        window.winId()                                   # creates the QWindow, whose mouse events the edges watch
        window.windowHandle().installEventFilter(resizer)
    return bar


def chrome(app, window, ops, ops_for, bridge: bool = False) -> TitleBar | None:
    """Before window.show(): our title bar, corners and edges, and our dock titles with the main window's edges on
    the floating panels (ops_for(dock) -> that panel's WindowOps). Where not wanted (a local Mac,
    EXPLORER_TITLEBAR=wm), nothing, except through the bridge: a floating panel there still needs a title Qt draws
    and handles (offscreen gives none), so it gets ours, and the window manager adds its frame above it."""
    if not wanted(bridge):
        if bridge:
            dock_titles(window)
        return None
    # our dock titles on every path with our chrome: the same float button in the same place, so the panel's resize
    # corner behaves the same (Qt's own float button reached into that corner on xcb)
    dock_titles(window)
    window.panel_ops = ops_for
    window._panel_edges = [PanelEdges(d, ops_for(d)) for d in window.findChildren(QtWidgets.QDockWidget)]
    return install(window, ops)
