"""The glass look (ROADMAP E5.12): the image fills the window and the rest floats over it on glass. From the
prototype's app/look_glass.py, its floating panels (its default; the column of cards is not ported).

- The image has the main window to itself, to its edges; the window as wide as the image at its height. A zoomed
  window (maximised, full screen, or by our title bar's zoom) leaves its zoom: it keeps the monitor's height, left of
  the panels' column; out of glass it is zoomed again.
- The panels (spectra, lambda-t, and the slit's while there is a slit) float beside the main window as rounded slabs
  in the image's own colour (near-black; near-white in the light theme), lit from above, with a rim and the accent's
  light along their top edge, and a title of their own (PanelSkin, PanelTitle). The window's title bar and edge take
  the same while glass is worn: the windows read as one set, on the image's black (a smoked grey parted the panels
  from it). They move, resize, close and dock back as any floating panel; I hides and shows them all, Panels one by
  one, the reset button places them again. Stacked beside the window: 52/48, or 40/30/30 with the slit's
  (look_glass.py:572); S puts the slit's below lambda-t when the monitor has room there, else the three are stacked
  again (look_glass.py:604-618).
- The toolbar's controls float in one compact glass bar at the bottom of the image, two rows. It hides after HIDE_MS
  without a mouse move, wheel or key, and comes back on the next one; it stays while in use (AutoHide).
- The cursor's readout is the window's title while the pointer is on the image or the cursor is locked; the status
  line only with the diagnostics (F12).
- Glass: what the image shows under the bar, blurred, under a veil and a grey grain; all grey, since the X11 bridge
  sends a grey tile at 1 B/px and a tinted one at 4. While the image changes the bar keeps its backdrop; it is
  redrawn once the image has been still for REST_MS, and when the view moves.
- The markers and what is on in one accent, Apple's orange (ACCENT): white is lost on bright granulation, green
  nearly vanished against a colour map's red for deuteranopes. The rest is the modern look's parts but its cards.

Every change is undone by remove(), so M can go in and out of it while the window runs.

    g = GlassChrome(shell); g.apply() ... g.remove()
"""
import os

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from ..platform.screens import monitor_rect
from . import docks, style, titlebar
from .status import SEP

FLOAT_W = 560                                      # px: a floating panel's width
# px: the least height its plots read at; the slit's two slices have lambda-t's axes, side by side
FLOAT_MIN_H = {"spectrum": 380, "lambda_t": 240, "slit": 240}
SLIDER_MIN, SLIDER_LEAST = 140, 48                 # px: a slider in the bar, and the least it gives way to
ROW_GAP, ROW_GAP_LEAST = 8, 4                      # px between the bar's controls, and in a bar too narrow for it
HIDE_MS = 2500
BAR_BOTTOM = 6                                     # px between the bar and the image's bottom edge
REST_MS = 250                                      # still this long: the glass takes the new image as its backdrop
MARGIN = 16
GAP = 12
RADIUS_BAR = 16
RADIUS_PANEL = 12
VEIL = {"dark": QtGui.QColor(30, 30, 32, 200), "light": QtGui.QColor(246, 246, 246, 190)}
HAIRLINE = {"dark": QtGui.QColor(255, 255, 255, 26), "light": QtGui.QColor(0, 0, 0, 18)}
INK = {"dark": QtGui.QColor(235, 235, 240), "light": QtGui.QColor(30, 30, 34)}
# what is pointed at or selected: Apple's system orange (light: its accessible variant). From look_glass.py:56-61,
# where it was measured against the alternatives: on a grey image 2.23:1 at worst (yellow 1.41, green 2.02, white
# 1.31); from the colour maps C steps through dE76 33-38, 17-33 for deuteranopes (green 5-18); dE 44 from the locked
# yellow. EXPLORER_GLASS_ACCENT=#rrggbb tries another (the prototype's CRISPEX_GLASS_ACCENT)
ACCENT = {"dark": QtGui.QColor(255, 146, 48), "light": QtGui.QColor(197, 83, 0)}
ACCENT_ENV = "EXPLORER_GLASS_ACCENT"
MIN_VIEW_W = 480                                   # px: the image's least width when the window is fitted to it
# a floating panel, opaque on every path (XQuartz has no alpha to blend with): a slab in the image's colour, a touch
# lighter (dark) or darker (light) at the top, its outer edge against what is behind; the light, rim and accent line
# are titlebar's hud_*; pure greys, for the bridge
SLAB = {"dark": (QtGui.QColor(16, 16, 19), QtGui.QColor(4, 4, 6)),
        "light": (QtGui.QColor(244, 244, 246), QtGui.QColor(255, 255, 255))}
EDGE = {"dark": QtGui.QColor(0, 0, 0, 200), "light": QtGui.QColor(0, 0, 0, 70)}
TITLE = {"dark": QtGui.QColor(0, 0, 0), "light": QtGui.QColor(255, 255, 255)}      # the title bar: the image's colour
GLOW_H = 56                                        # px of a panel's light from above: its title and a little below
AXIS = {"dark": (QtGui.QColor(255, 255, 255, 60), QtGui.QColor(160, 160, 160)),
        "light": (QtGui.QColor(0, 0, 0, 60), QtGui.QColor(90, 90, 90))}
GRAIN = 0.03
ZOOMED = QtCore.Qt.WindowState.WindowMaximized | QtCore.Qt.WindowState.WindowFullScreen


def _app() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    assert isinstance(app, QtWidgets.QApplication)
    return app


def _mode() -> str:
    return "light" if style.is_light() else "dark"


def accent() -> QtGui.QColor:
    c = QtGui.QColor(os.environ.get(ACCENT_ENV) or ACCENT[_mode()].name())
    return c if c.isValid() else QtGui.QColor(ACCENT[_mode()])


def _luminance(c: QtGui.QColor) -> float:
    def f(u):
        return u / 12.92 if u <= 0.03928 else ((u + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c.redF()) + 0.7152 * f(c.greenF()) + 0.0722 * f(c.blueF())


def contrast_white(c: QtGui.QColor) -> float:
    """White text's contrast on c (WCAG)."""
    return 1.05 / (_luminance(c) + 0.05)


def for_white_text(c: QtGui.QColor) -> QtGui.QColor:
    """The accent darkened, hue kept, until white text on it reads at 4.5:1 (WCAG AA), as style.SELECTED is the blue
    darkened: what is on and carries a label (a Stokes segment, a toggled button, a menu row). From
    look_glass.py:87-96."""
    q = QtGui.QColor(c)
    while contrast_white(q) < 4.5 and q.value() > 30:
        q = q.darker(104)
    return q


_grain = None


def _grain_tile() -> QtGui.QPixmap:
    global _grain
    if _grain is None:
        a = np.random.default_rng(0).integers(0, 256, (64, 64), dtype=np.uint8)
        _grain = QtGui.QPixmap.fromImage(QtGui.QImage(a.data, 64, 64, 64, QtGui.QImage.Format.Format_Grayscale8).copy())
    return _grain


def scene_blur(view: QtWidgets.QGraphicsView, widget: QtWidgets.QWidget, rect: QtCore.QRect) -> QtGui.QPixmap:
    """What the image view's scene shows under `rect` of `widget`, blurred: a 1/8 smooth downscale and back up.
    QGraphicsView.render draws the scene only, no child widget (so not the glass itself). From look_glass.py:87-96."""
    pm = QtGui.QPixmap(rect.size())
    pm.fill(QtCore.Qt.GlobalColor.black)
    at = widget.mapTo(widget.window(), rect.topLeft()) - view.viewport().mapTo(view.window(), QtCore.QPoint(0, 0))
    q = QtGui.QPainter(pm)
    view.render(q, QtCore.QRectF(pm.rect()), QtCore.QRect(at, rect.size()))
    q.end()
    S, any_ = QtCore.Qt.TransformationMode.SmoothTransformation, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio
    small = pm.scaled(max(1, rect.width() // 8), max(1, rect.height() // 8), any_, S)
    return small.scaled(rect.size(), any_, S)


class Bar(QtWidgets.QWidget):
    """The controls' bar over the image, painted as frosted glass from what the view shows under it. From
    look_glass.py Glass (99-147) and Bar (245-246)."""
    radius = RADIUS_BAR

    def __init__(self, parent: QtWidgets.QWidget, view: QtWidgets.QGraphicsView, changing):
        super().__init__(parent)
        self.view, self.changing = view, changing   # changing(): the image is moving; the backdrop is kept
        self._backdrop: QtGui.QPixmap | None = None
        self._composed_pm = QtGui.QPixmap()
        self._composed_of: QtGui.QPixmap | None = None

    def invalidate(self) -> None:
        self._backdrop = None
        self.update()

    def _blurred(self) -> QtGui.QPixmap:
        if self._backdrop is not None and self.changing() and self._backdrop.size() == self.size():
            return self._backdrop
        self._backdrop = b = scene_blur(self.view, self, self.rect())
        return b

    def _composed(self) -> QtGui.QPixmap:
        b = self._blurred()
        if self._composed_of is not b:
            pm = QtGui.QPixmap(b)
            q = QtGui.QPainter(pm)
            q.fillRect(pm.rect(), VEIL[_mode()])
            q.setOpacity(GRAIN)
            q.drawTiledPixmap(pm.rect(), _grain_tile())
            q.end()
            self._composed_pm, self._composed_of = pm, b
        return self._composed_pm

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        r = QtCore.QRectF(self.rect())
        path = QtGui.QPainterPath()
        path.addRoundedRect(r, self.radius, self.radius)
        p.setClipPath(path)
        p.drawPixmap(0, 0, self._composed())
        p.setClipping(False)
        p.setPen(QtGui.QPen(HAIRLINE[_mode()], 1))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), self.radius, self.radius)
        p.end()


class AutoHide(QtCore.QObject):
    """Shows the bar on any mouse move, wheel or key in the window; hides it HIDE_MS later unless in use (the pointer
    on it, a button held, a popup open, one of its fields focused). From look_glass.py:344-373."""

    def __init__(self, window: QtWidgets.QWidget, widgets):
        super().__init__(window)
        self.window, self.widgets = window, widgets
        self.timer = QtCore.QTimer(self, singleShot=True, interval=HIDE_MS)
        self.timer.timeout.connect(self.idle)
        _app().installEventFilter(self)
        self.timer.start()

    def stop(self) -> None:
        _app().removeEventFilter(self)
        self.timer.stop()

    def eventFilter(self, obj, e):
        if e.type() in (QtCore.QEvent.Type.MouseMove, QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.Wheel):
            if isinstance(obj, QtWidgets.QWidget) and obj.window() is self.window:
                for w in self.widgets:
                    if not w.isVisible():
                        w.show()
                        w.raise_()
                self.timer.start()
        return False

    def idle(self) -> None:
        fw = QtWidgets.QApplication.focusWidget()
        busy = (any(w.underMouse() for w in self.widgets)
                or QtWidgets.QApplication.mouseButtons() != QtCore.Qt.MouseButton.NoButton
                or QtWidgets.QApplication.activePopupWidget() is not None
                or (fw is not None and any(w.isAncestorOf(fw) for w in self.widgets)
                    and isinstance(fw, (QtWidgets.QAbstractSpinBox, QtWidgets.QLineEdit))))
        if busy:
            self.timer.start()
            return
        for w in self.widgets:
            w.hide()


class _Glyph(QtCore.QObject):
    """A title button drawn in the glass's ink, whatever the platform's style: a local Mac's native style drew the
    standard dock icons as grey squares on the smoked glass. A small x (close) or two offset squares (float), faint
    until the pointer is on it, then brighter on a soft disc. From look_glass.py CloseButton (203-222)."""

    def __init__(self, button: QtWidgets.QToolButton, kind: str):
        super().__init__(button)
        self.b, self.kind = button, kind
        button.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover)
        button.installEventFilter(self)

    def eventFilter(self, obj, e):
        if e.type() != QtCore.QEvent.Type.Paint:
            return False
        b = self.b
        p = QtGui.QPainter(b)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        ink = QtGui.QColor(INK[_mode()])
        hover = b.underMouse()
        if hover:
            bg = QtGui.QColor(ink)
            bg.setAlphaF(0.12)
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawEllipse(QtCore.QRectF(b.rect()).adjusted(1, 1, -1, -1))
        ink.setAlphaF(0.9 if hover else 0.45)
        pen = QtGui.QPen(ink, 1.4)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        c = QtCore.QPointF(b.width() / 2, b.height() / 2)
        d = min(b.width(), b.height()) * 0.2
        P = QtCore.QPointF
        if self.kind == "close":
            p.drawLine(c + P(-d, -d), c + P(d, d))
            p.drawLine(c + P(-d, d), c + P(d, -d))
        else:                                       # float / dock: a square, another behind it up and to the right
            a, o = 1.7 * d, 0.7 * d
            x, y = c.x() - (a + o) / 2, c.y() - (a - o) / 2
            p.drawRect(QtCore.QRectF(x, y, a, a))
            p.drawPolyline(QtGui.QPolygonF([P(x + o, y), P(x + o, y - o), P(x + o + a, y - o), P(x + o + a, y - o + a),
                                            P(x + a, y - o + a)]))
        p.end()
        return True


class PanelTitle(titlebar.DockTitle):
    """The panel's title on the panel's own glass: its name and a faint line below, its buttons in the glass's ink
    (_Glyph). From look_glass.py:386-398."""

    def __init__(self, dock):
        super().__init__(dock)
        self._glyphs = [_Glyph(b, k) for b, k in zip(self.buttons, ("close", "float"), strict=True)]

    def paintEvent(self, e):
        mode = _mode()
        p = QtGui.QPainter(self)
        f = QtGui.QFont(self.d.font())
        f.setWeight(QtGui.QFont.Weight.DemiBold)
        p.setFont(f)
        side = self.buttons[-1].geometry().right() + 6
        r = self.rect().adjusted(side, 0, -side, 0)
        p.setPen(INK[mode])
        text = QtGui.QFontMetrics(f).elidedText(self.d.windowTitle(), QtCore.Qt.TextElideMode.ElideRight,
                                                max(0, r.width()))
        p.drawText(r, QtCore.Qt.AlignmentFlag.AlignCenter, text)
        p.setPen(HAIRLINE[mode])
        p.drawLine(RADIUS_PANEL, self.height() - 1, self.width() - RADIUS_PANEL, self.height() - 1)


class PanelSkin(QtCore.QObject):
    """A floating panel as a rounded slab of smoked glass: the panel paints it, its title and plots are transparent
    over it. The rounded shape: a mask on X11 (xcb: Qt's X SHAPE; the bridge: the published shape), a transparent
    window on a local Mac. From look_glass.py:401-471; remove() puts the panel back as it was."""

    def __init__(self, dock: QtWidgets.QDockWidget):
        super().__init__(dock)
        from ..platform.xbridge.windows import SHAPE_ATTR

        self.d, self.shape_attr = dock, SHAPE_ATTR
        self.platform = QtGui.QGuiApplication.platformName()
        self._title = dock.titleBarWidget()
        self._translucent = dock.testAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self._autofill = dock.widget().autoFillBackground()
        self._views = []
        if self.platform == "cocoa":
            dock.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        dock.setTitleBarWidget(PanelTitle(dock))
        dock.widget().setAutoFillBackground(False)
        edge, label = AXIS[_mode()]
        for gv in dock.widget().findChildren(pg.GraphicsView):
            axes = [(it, it.pen(), it.textPen()) for it in gv.scene().items() if isinstance(it, pg.AxisItem)]
            self._views.append((gv, gv.backgroundBrush(), gv.viewport().autoFillBackground(), gv.styleSheet(), axes))
            gv.setBackground(None)
            gv.viewport().setAutoFillBackground(False)
            gv.setStyleSheet("background: transparent; border: none")
            for it, _p, _t in axes:
                it.setPen(edge)
                it.setTextPen(label)
        dock.installEventFilter(self)
        dock.topLevelChanged.connect(self._floated)
        self.shape()

    def retheme(self) -> None:
        """Another theme while worn: its plots' axes went back to the default pens (Shell.set_theme), which remove()
        gives back now; the glass's go on again, and the plots stay clear over the slab."""
        edge, label = AXIS[_mode()]
        views = []
        for gv, bg, fill, css, axes in self._views:
            axes = [(it, it.pen(), it.textPen()) for it, _p, _t in axes]
            gv.setBackground(None)
            for it, _p, _t in axes:
                it.setPen(edge)
                it.setTextPen(label)
            views.append((gv, bg, fill, css, axes))
        self._views = views
        self.d.update()

    def titles_changed(self) -> None:
        """Someone put another title on the panel (the chrome's, after the look): that one is the panel's own, to
        give back on remove(); the glass title goes on again."""
        t = self.d.titleBarWidget()
        if isinstance(t, PanelTitle):
            return
        self._title = t
        self.d.setTitleBarWidget(PanelTitle(self.d))

    def _floated(self, _floating) -> None:
        self.shape()

    def remove(self) -> None:
        d = self.d
        d.removeEventFilter(self)
        d.topLevelChanged.disconnect(self._floated)
        skin_title = d.titleBarWidget()
        d.setTitleBarWidget(self._title)
        if skin_title is not None and skin_title is not self._title:
            skin_title.deleteLater()
        d.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, self._translucent)
        d.widget().setAutoFillBackground(self._autofill)
        for gv, bg, fill, css, axes in self._views:
            gv.setBackgroundBrush(bg)
            gv.viewport().setAutoFillBackground(fill)
            gv.setStyleSheet(css)
            for it, p, t in axes:
                it.setPen(p)
                it.setTextPen(t)
        setattr(d, self.shape_attr, QtGui.QRegion())
        if self.platform == "xcb":
            d.clearMask()
        d.update()

    def shape(self) -> None:
        titlebar.round_window(self.d, RADIUS_PANEL)  # rounded floating, square docked (the bridge's X SHAPE too)

    def eventFilter(self, obj, e):
        if obj is not self.d:
            return False
        if e.type() == QtCore.QEvent.Type.Resize:
            self.shape()
        elif e.type() == QtCore.QEvent.Type.Paint:
            self.paint()
            return True
        return False

    def paint(self) -> None:
        mode, d = _mode(), self.d
        p = QtGui.QPainter(d)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(d.rect())
        top, bottom = SLAB[mode]
        g = QtGui.QLinearGradient(0, 0, 0, rect.height())
        g.setColorAt(0, top)
        g.setColorAt(1, bottom)
        if not d.isFloating():                      # docked: the same slab, square, in the main window
            p.fillRect(rect, g)
            return
        r = RADIUS_PANEL
        if self.platform == "cocoa":
            p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Source)
            p.fillRect(rect, QtCore.Qt.GlobalColor.transparent)
            p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, r, r)
        p.setClipPath(path)
        p.fillRect(rect, g)
        titlebar.hud_glow(p, rect, GLOW_H, mode == "light")
        p.setClipping(False)
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.setPen(QtGui.QPen(EDGE[mode], 1.0))
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), r - 0.5, r - 0.5)
        titlebar.hud_rim(p, rect, r, mode == "light")
        titlebar.hud_accent(p, rect, r, accent())


class _Watch(QtCore.QObject):
    """Calls on(event) for the events of one object it watches."""

    def __init__(self, obj: QtCore.QObject, types, on):
        super().__init__(obj)
        self.obj, self.types, self.on = obj, types, on
        obj.installEventFilter(self)

    def stop(self) -> None:
        self.obj.removeEventFilter(self)

    def eventFilter(self, obj, e):
        if e.type() in self.types:
            self.on(e)
        return False


class GlassChrome:
    """The glass look on a Shell, and back. apply() before or after the window is shown; remove() undoes it."""

    def __init__(self, shell):
        self.w = shell
        self.on = False
        self.changing = False
        self.over_image = False
        self.bar: Bar                               # made by apply()
        self.autohide: AutoHide | None = None
        self.skins: list[PanelSkin] = []
        self._watches: list[_Watch] = []
        self._was: dict = {}
        self._hidden: list = []
        self._tinted = self._sheet = None
        self._sheets: dict = {}

    # ---------------------------------------------------------------- in
    def apply(self) -> None:
        w, nav, view = self.w, self.w.nav, self.w.view
        self.on = True
        # worn before the window was first shown (the last session closed in glass): there is no "before" to give
        # back, only a window not yet sized; out of glass, the other looks start then as at a fresh start
        self._fresh = not w.isVisible()
        self._was = dict(state=w.saveState(), geometry=w.geometry(), title=w.windowTitle(),
                         statusbar=w.statusBar().isVisibleTo(w), floating={d: d.isFloating() for d in self.docks()},
                         margins=w.centralWidget().layout().contentsMargins(),
                         # the layout's (9 px), not the layout item's own (0): given back as 0, the image came out
                         # of glass 18 px larger
                         ci=view.widget.ci.layout.getContentsMargins() if hasattr(view.widget, "ci") else None,
                         sliders={a: (s.minimumWidth(), s.maximumWidth()) for a, s in nav.sliders.items()},
                         # the zoom to give back: Qt's (a Mac's green button, a window manager's maximise) with the
                         # size under it, and our title bar's
                         zoom=w.windowState() & ZOOMED, normal=w.normalGeometry(),
                         unzoomed=w.window_ops.unzoomed if w.window_ops is not None else None)
        # the image to the window's edges (look_glass.py:651-658)
        w.centralWidget().layout().setContentsMargins(0, 0, 0, 0)
        self._was["spacing"] = w.centralWidget().layout().spacing()     # under a linked image's header (ui.linked)
        w.centralWidget().layout().setSpacing(0)
        for v in self._images():                    # linked cubes' too: images of one size show one region
            if hasattr(v.widget, "ci"):
                v.widget.ci.setContentsMargins(0, 0, 0, 0)
        for c in getattr(w, "linked", ()):          # their panels' margins, as the main image's (docked)
            c.set_docked_margin(0)
        self._bar(nav, view)
        # the readout as the title (look_glass.py:693-724)
        self._watches.append(_Watch(view.widget.viewport(), (QtCore.QEvent.Type.Enter, QtCore.QEvent.Type.Leave),
                                    self._enter_leave))
        w.statusBar().setVisible(w.diagnostics)
        # the backdrop, kept while the image moves (look_glass.py:848-865)
        self._rest = QtCore.QTimer(w, singleShot=True, interval=REST_MS)
        self._rest.timeout.connect(self._rested)
        view.vb.sigRangeChanged.connect(self._view_moved)
        nav.play.toggled.connect(self._play_toggled)
        # the panels, floating beside the window (look_glass.py:474-608)
        self.skins = [PanelSkin(d) for d in self.docks()]
        if w.isVisible():
            QtCore.QTimer.singleShot(0, self.first_place)
        else:
            self._watches.append(_Watch(w, (QtCore.QEvent.Type.Show,), self._first_show))
        self._tint(accent())
        self.place_bar()
        self.bar.show()
        self.bar.raise_()
        self.autohide = AutoHide(w, (self.bar,))
        self._hud_title()
        self._tabs(True)
        key = w.colour_key                          # at the top left: the bar is at the bottom (look_glass.py:937-943)
        if key is not None:
            key._place = lambda view_: key.move(MARGIN, MARGIN)
            key._place(view.widget)
        self.readout()

    def titles_changed(self) -> None:
        """The chrome put its dock titles on after glass (app.chrome): glass's own over them again, and its title bar
        (made after the look when the window starts in glass) takes the look's."""
        for s in self.skins:
            s.titles_changed()
        self._hud_title()

    def _image_titles(self, colour) -> None:
        """The images' titles (linked cubes, ui.linked.ImageTitle) on the image's colour, as the window's title bar,
        and the window's own colour too: the separators between the images are drawn in it, by any style, and were
        the theme's grey between black images. Only that colour is the window's own (the rest it inherits, so a
        change of theme reaches it); None: the titles' and the window's own again. The linked images' panels too: a
        cube's window floats, and a window does not take its parent's colour (its spectra and lambda-t, clear over
        it in glass, showed the theme's grey: lightness 45 against 7-16 of the floating panels)."""
        titles = [getattr(self.w, "image_title", None)] + [c.title for c in getattr(self.w, "linked", ())]
        for t in titles:
            if t is not None:
                t.set_back(colour)
        if not getattr(self.w, "linked", None):     # one image: no separator beside it
            return
        pal = QtGui.QPalette()
        if colour is not None:
            pal.setColor(QtGui.QPalette.ColorRole.Window, colour)
        self.w.setPalette(pal)
        for c in self.w.linked:
            c.dock.setPalette(pal)
            c.dock.plain_separators = colour is not None    # floating, its window's separators (ui.style)
        self.w.plain_separators = colour is not None    # ui.style: no hairline in them either
        self.w.update()

    def _hud_title(self) -> None:
        """The window's title bar in the image's colour with the panels' light, and its edge with their rim and accent
        line; given back by remove(). None where the window manager draws the title (a local Mac). Only its window
        colour is its own: the rest it takes from the application, so it follows a change of theme (T); a whole
        palette copied here kept the old theme's text and, given back, the old theme's colours."""
        self._image_titles(TITLE[_mode()])
        tb = getattr(self.w, "title_bar", None)
        if tb is None:
            return
        self._was["title_bar"] = tb
        pal = QtGui.QPalette()                      # nothing set but the window colour: the rest inherited
        pal.setColor(QtGui.QPalette.ColorRole.Window, TITLE[_mode()])
        tb.setPalette(pal)
        tb.hud = accent()
        tb.corners.line.hud = accent()
        tb.corners.line.update()
        tb.update()

    def _images(self) -> list:
        """The image views: the main one, and the linked cubes' beside it (ui.linked)."""
        return [self.w.view] + [c.view for c in getattr(self.w, "linked", ())]

    def docks(self) -> list:
        """The panels glass floats: the slit's too, shown only with a slit (docks.GatedDock; look_glass.py:518-519).
        Linked cubes' panels are tabs inside these (ui.linked)."""
        return [d for d in (self.w.spec_dock, self.w.lt_dock, self.w.slit_dock) if d is not None]

    def _bar(self, nav, view) -> None:
        """The toolbar's controls in the bar, two rows (look_glass.py:660-691): every action leaves the toolbar,
        kept in order to come back."""
        tb = nav.tb
        self._actions = [(a, a.isVisible()) for a in tb.actions()]
        for a, _v in self._actions:
            tb.removeAction(a)                      # a widget action hides its widget and lets it go
        self.bar = Bar(view.widget, view.widget, lambda: self.changing or nav.play.isChecked())
        lay = QtWidgets.QVBoxLayout(self.bar)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(1)
        self._rows = rows = [QtWidgets.QHBoxLayout(), QtWidgets.QHBoxLayout()]
        for r in rows:
            r.setSpacing(ROW_GAP)
            lay.addLayout(r)
        ink = INK[_mode()]
        self._made: list[QtWidgets.QWidget] = []
        for row, axis, name in ((0, "t", "t"), (1, "l", "λ")):
            s = nav.sliders.get(axis)
            if s is None:
                continue
            s.setMinimumWidth(SLIDER_MIN)
            s.setMaximumWidth(16777215)
            if row == 0:
                rows[0].addWidget(nav.play)
            else:
                stokes = nav.drop if nav.drop is not None else nav.stokes
                if stokes is not None:
                    rows[1].addWidget(stokes)
                nl = QtWidgets.QLabel(name)
                nl.setStyleSheet(f"color: {ink.name()};")
                rows[1].addWidget(nl)
                self._made.append(nl)
            rows[row].addWidget(s, 1)
            rows[row].addWidget(nav.labels[axis])
        for b in (nav.slit, nav.panels, nav.reset, nav.help):     # the slit's first (look_glass.py:729-731)
            rows[0].addWidget(b)
        # I Q U V side by side: All in the Stokes control and key 5, as in the other looks; the prototype's own 2x2
        # button (look_glass.py:685-687) would be a second name and a second control for it
        rows[1].addWidget(nav.fps)
        self._flatten([nav.play, nav.slit, nav.panels, nav.reset, nav.help, nav.drop])
        for x in [nav.play, nav.fps, nav.slit, nav.panels, nav.reset, nav.help, *nav.sliders.values(),
                  *nav.labels.values()]:
            x.show()
        if nav.drop is not None:
            nav.drop.show()
        elif nav.stokes is not None:
            nav.stokes.show()
        tb.hide()

    TINT = ("ACC", "SEL", "SEL_HOVER", "SEL_DOWN")

    def _tint(self, mark: QtGui.QColor) -> None:
        """What is on in the accent (look_glass.py:929-940): our style's fills, toggles, menu rows and focus (its
        attributes, on the instance: remove() lets the class's show again), and the Stokes segments' sheet, which
        holds the colour it was made with. Not under a Mac's native style, whose controls take the system's."""
        st = _app().style()
        old = style.selected().name()
        sel = for_white_text(mark)
        self._tinted = st if all(hasattr(st, a) for a in self.TINT) else None
        if self._tinted is not None:
            for a, c in zip(self.TINT, (mark, sel, sel.lighter(110), sel.darker(115)), strict=True):
                setattr(st, a, c)
        drop = self.w.nav.drop
        self._sheet = None
        if drop is not None:
            seg = drop.segments
            self._sheet = seg.styleSheet()
            seg.setStyleSheet(self._sheet.replace(f"background: {old};", f"background: {sel.name()};"))

    def _untint(self) -> None:
        st = self._tinted
        if st is not None:
            for a in self.TINT:
                if a in vars(st):
                    delattr(st, a)
        if self._sheet is not None and self.w.nav.drop is not None:
            self.w.nav.drop.segments.setStyleSheet(self._sheet)

    def _flatten(self, buttons) -> None:
        """The bar's buttons flat on the glass: out of a toolbar a Mac's native style drew each in a grey box. A sheet
        of their own (the Stokes segments, a child of the drop-down, keep theirs); the one they had comes back."""
        self._sheets = {b: b.styleSheet() for b in buttons if b is not None}
        sheet = self._flat_sheet()
        for b in self._sheets:
            b.setStyleSheet(sheet)

    @staticmethod
    def _flat_sheet() -> str:
        ink = INK[_mode()]
        H = QtGui.QColor.NameFormat.HexArgb
        hover, down = QtGui.QColor(ink), QtGui.QColor(ink)
        hover.setAlphaF(0.10)
        down.setAlphaF(0.18)
        return (f"QToolButton {{ border: none; border-radius: 6px; padding: 3px 7px; background: transparent;"
                f" color: {ink.name()}; }}"
                f"QToolButton:hover {{ background: {hover.name(H)}; }}"
                f"QToolButton:pressed {{ background: {down.name(H)}; }}"
                f"QToolButton:checked {{ background: {for_white_text(accent()).name()}; color: white; }}")

    @staticmethod
    def _tabs_sheet() -> str:
        """The linked cubes' tabs in the panels (ui.linked.PanelTabs) flat on the slab, as the bar's buttons: the
        style's were grey buttons on the near-black panel (lightness 67-74 against 5-18)."""
        ink = INK[_mode()]
        H = QtGui.QColor.NameFormat.HexArgb
        dim, hover, front = QtGui.QColor(ink), QtGui.QColor(ink), QtGui.QColor(ink)
        dim.setAlphaF(0.62)
        hover.setAlphaF(0.08)
        front.setAlphaF(0.12)                       # the tab in front: a shade, its name brighter
        return ("QTabWidget::pane { border: none; background: transparent; }"
                "QTabBar { background: transparent; }"
                f"QTabBar::tab {{ background: transparent; color: {dim.name(H)}; border: none; border-radius: 5px;"
                " padding: 2px 10px; margin: 2px 2px 3px 2px; }"
                f"QTabBar::tab:hover {{ background: {hover.name(H)}; }}"
                f"QTabBar::tab:selected {{ background: {front.name(H)}; color: {ink.name()}; }}")

    def _tabs(self, on: bool) -> None:
        sheet = self._tabs_sheet() if on else ""
        for t in (getattr(self.w, "spec_tabs", None), getattr(self.w, "lt_tabs", None)):
            if t is not None:
                t.setStyleSheet(sheet)

    def retheme(self) -> None:
        """Another theme while worn (Shell.set_theme), in place: the panels where they are, the image's region kept,
        which taking glass off and on again would not. What took the old theme's colours when glass went on takes
        the new ones; the rest (bar, slabs, titles, glyphs) reads the theme when it paints."""
        self._tint(accent())                        # the new style has no tint; the segments' sheet is made anew
        sheet = self._flat_sheet()
        for b in self._sheets:
            b.setStyleSheet(sheet)
        for x in self._made:
            if isinstance(x, QtWidgets.QLabel):
                x.setStyleSheet(f"color: {INK[_mode()].name()};")
        for sk in self.skins:
            sk.retheme()
        if "title_bar" in self._was:                # the title bar in the new theme's image colour and accent
            self._hud_title()
        else:
            self._image_titles(TITLE[_mode()])
        self._tabs(True)
        self.bar.invalidate()

    def _fit_sliders(self, room: int) -> None:
        """The sliders give way first, as in the toolbar: in a 480-px window the bar needed 505 px for 448 (its t
        row: play, the slider at 140, its label, Panels, reset, ?), and Qt squeezed the rest below their size. Then
        the gaps between the controls: with the slit's button the t row needed 454 px for 448 with its slider at its
        least."""
        sl = list(self.w.nav.sliders.values())
        lay = self.bar.layout()
        if lay is None:
            return
        for s in sl:
            s.setMinimumWidth(SLIDER_MIN)
        for r in self._rows:
            r.setSpacing(ROW_GAP)
        lay.activate()
        excess = self.bar.minimumSizeHint().width() - room
        if excess > 0:
            for s in sl:
                s.setMinimumWidth(max(SLIDER_LEAST, SLIDER_MIN - excess))
            lay.activate()
            if self.bar.minimumSizeHint().width() > room:
                for r in self._rows:
                    r.setSpacing(ROW_GAP_LEAST)
                lay.activate()

    def place_bar(self) -> None:
        view = self.w.view.widget
        W, H = view.width(), view.height()
        self._fit_sliders(max(320, W - 2 * MARGIN))
        bw = min(self.bar.sizeHint().width() + 8, max(320, W - 2 * MARGIN))
        self.bar.resize(bw, self.bar.sizeHint().height())
        self.bar.move((W - bw) // 2, H - self.bar.height() - BAR_BOTTOM)
        self.bar.invalidate()

    # ---------------------------------------------------------------- the panels
    def _first_show(self, _e) -> None:
        for wt in [x for x in self._watches if x.obj is self.w and QtCore.QEvent.Type.Show in x.types]:
            wt.stop()
            self._watches.remove(wt)
        QtCore.QTimer.singleShot(0, self.first_place)

    def first_place(self) -> None:
        """At start: the window fitted to the image; the panels where the last glass session left them, unless the
        fitted window now covers them or they were docked (look_glass.py:539-551)."""
        if not self.on:
            return
        shown = [d for d in self.docks() if not d.isHidden()]
        if not all(d.isFloating() for d in shown):
            self.place_panels()
            return
        fg = self.fit_window(monitor_rect(QtWidgets.QApplication.instance(), self.w.frameGeometry().center()), 0)
        if any(d.frameGeometry().intersects(fg) for d in shown):
            self.place_panels()
        else:
            QtCore.QTimer.singleShot(0, self.w.view.show_all)

    def fit_window(self, scr: QtCore.QRect, room: int) -> QtCore.QRect:
        """The main window as wide as the image at its height; room: px kept free on its right for the panels.
        Returns its frame as it will be (look_glass.py:496-516).

        A zoomed window leaves its zoom and takes the monitor's height at its left edge, the panels' column on its
        right. Left maximised (as the prototype did, look_glass.py:543), a window zoomed by a Mac's green button
        (Qt's maximised state) kept the screen's width and the panels landed on it. The zoom is left before the
        window is sized, so the size asked is not the zoom's to undo. Our title bar's zoom is a geometry
        only: the window has the monitor's height already, and the button's next press zooms rather than going back
        to the size before glass. remove() zooms it again."""
        w, vb = self.w, self.w.view.vb
        dx, dy = vb.viewPixelSize()
        img = w.scheduler.img
        if img is None or not (dx > 0 and dy > 0) or vb.height() < 50:
            return w.frameGeometry()
        ny, nx = img.shape
        # read before the zoom is left: the view follows a resize only once its layout has run. Linked cubes' images
        # (ui.linked) are as wide as the main one: n images, the rest of the width the window's own
        vbs = [vb] + [c.view.vb for c in getattr(w, "linked", ()) if c.dock.isVisible() and not c.dock.isFloating()]
        n = len(vbs)
        dw, dh = w.width() - sum(int(v.width()) for v in vbs), w.height() - int(vb.height())
        zoomed = w.windowState() & ZOOMED
        if zoomed:
            w.setWindowState(w.windowState() & ~ZOOMED)
        if w.window_ops is not None:
            w.window_ops.unzoomed = None
        fg = w.frameGeometry()
        if zoomed and w.windowHandle() is not None:     # out of full screen its frame is back, which the platform
            fg = w.geometry().marginsAdded(w.windowHandle().frameMargins())     # knows before the widget does
        frame_w, frame_h = fg.width() - w.width(), fg.height() - w.height()
        aspect = nx / ny * dy / dx                  # the image's width / height on screen
        if zoomed:
            h, top, at = scr.height() - frame_h - dh, scr.top(), scr.left()
        else:
            h, top, at = int(vb.height()), fg.top(), fg.left()
        wd = int(round(h * aspect))
        most = (scr.width() - room - frame_w - dw) // n
        if wd > most:
            wd = max(MIN_VIEW_W // n, most)         # side by side, the least width is theirs together
            h = int(round(wd / aspect))
        W, H = n * wd + dw, h + dh
        left = max(scr.left(), min(at, scr.right() + 1 - (W + frame_w + room)))
        w.setGeometry(left + (w.geometry().x() - fg.x()), top + (w.geometry().y() - fg.y()), W, H)
        if getattr(w, "linked", None):              # the images one width again, once the window has its size
            QtCore.QTimer.singleShot(0, w.same_image_widths)
        return QtCore.QRect(left, top, W + frame_w, H + frame_h)

    def place_panels(self) -> None:
        """The panels shown stacked beside the fitted window, 52/48 or, with the slit's, 40/30/30 (look_glass.py:
        559-579)."""
        w = self.w
        if not self.on or not w.isVisible():
            return
        shown = [d for d in self.docks() if not d.isHidden()]
        # out of the layout first: docked, they hold the window wider than the image. A panel not floating yet is
        # hidden, floated, given its place, and shown: floated while shown, its X window was made where Qt first put
        # it, and through XQuartz the manager's late notice of that place (with the size asked after it) moved it
        # back there after it was placed (a geometry trace through ssh -Y; the second time Qt had its place already)
        fresh = [d for d in shown if not d.isFloating()]
        for d in fresh:
            d.hide()
            d.setFloating(True)
        lay = QtWidgets.QMainWindow.layout(w)
        if lay is not None:
            lay.activate()
        scr = monitor_rect(QtWidgets.QApplication.instance(), w.frameGeometry().center())
        fg = self.fit_window(scr, GAP + FLOAT_W if shown else 0)
        QtCore.QTimer.singleShot(0, w.view.show_all)
        if not shown:
            if hasattr(w, "place_detached"):
                w.place_detached()
            return
        x = min(fg.right() + GAP, scr.right() - FLOAT_W)
        share = {1: [1.0], 2: [0.52, 0.48], 3: [0.40, 0.30, 0.30]}[len(shown)]
        avail = fg.height() - GAP * (len(shown) - 1)
        y = fg.top()
        for d, f in zip(shown, share, strict=True):
            # never shorter than its plots need: at 245 px the 2x2 spectra's axis titles ran into each other; below a
            # short window they go on past its bottom edge
            h = max(int(avail * f), FLOAT_MIN_H.get(d.objectName(), 0))
            if d in fresh:                          # its window made where it goes
                d.setGeometry(x, y, FLOAT_W, h)
                d.show()
            else:
                d.setFloating(True)
                d.show()
                d.setGeometry(x, y, FLOAT_W, h)
            y += h + GAP
        if hasattr(w, "place_detached"):             # linked images in windows of their own: beside the column
            w.place_detached()

    def toggle_panels(self) -> None:
        """I: every panel hidden, or those shown before back (look_glass.py:622-632); the slit's never without a slit
        (docks.GatedDock), as the prototype's default of spectra and lambda-t."""
        shown = [d for d in self.docks() if not d.isHidden()]
        if shown:
            self._hidden = shown
            for d in shown:
                d.hide()
        else:
            for d in self._hidden or self.docks():
                d.show()

    def reset(self) -> None:
        """The reset button: the whole image, and the panels shown and placed again; the slit's only with a slit
        (look_glass.py:634-642)."""
        self.w.reset_view()
        for d in self.docks():
            d.show()
        for c in getattr(self.w, "linked", ()):     # the linked images back in the window, shown
            c.dock.show()
            c.dock.setFloating(False)
        if getattr(self.w, "linked", None):
            self.refit_after_redock()
        else:
            self.place_panels()

    def refit_after_redock(self) -> None:
        """Linked images docked again: the window fitted and the panels placed once Qt has laid them out, on the
        loop's next pass. Read at once, a re-docked image still had its floating size or margin: the window came out
        845 px high for 1092, then a few px narrower or lower at each re-dock (934 x 348 -> 900 x 348)."""
        def fit():
            if not self.on:
                return
            self.w.same_image_widths()
            QtCore.QTimer.singleShot(0, self.place_panels)
        QtCore.QTimer.singleShot(0, fit)

    # ---------------------------------------------------------------- the image moving, the readout
    def image_changed(self) -> None:
        self.changing = True
        self._rest.start()

    def _rested(self) -> None:
        self.changing = False
        self.bar.invalidate()

    def _view_moved(self, *a) -> None:
        self.bar.invalidate()
        self.place_bar()

    def _play_toggled(self, on: bool) -> None:
        if not on:
            self.bar.invalidate()

    def _enter_leave(self, e) -> None:
        self.over_image = e.type() == QtCore.QEvent.Type.Enter
        self.readout()

    def readout(self) -> None:
        """The window's title: the cursor's readout while the pointer is on the image or the cursor is locked."""
        w = self.w
        text = w.status.text()
        if not ((self.over_image or w.session.state.locked) and text):
            w.setWindowTitle(self._was["title"])
            return
        # as many whole fields as the title has room for: elided in its middle at 480 px it read
        # "x -701.5" y +248.1" · 0...W m-2 Hz-1 sr-1", the values gone
        fm, room = QtGui.QFontMetrics(w.font()), max(120, w.width() - 2 * 90)
        fields, out = text.split(SEP), list[str]()
        for f in fields:
            if fm.horizontalAdvance(SEP.join([*out, f])) > room:
                break
            out.append(f)
        w.setWindowTitle(SEP.join(out) or fields[0])

    def grid_changed(self, on: bool) -> None:
        """The four Stokes shown or gone: the bar over them (look_glass.py:887)."""
        if on:
            self.bar.raise_()

    # ---------------------------------------------------------------- out
    def _start_afresh(self) -> None:
        """The other looks' own saved layout, as the prototype starts each look from its own; without one, the first
        start's window and panels."""

        w = self.w
        app = _app()
        store = w.layout_store.for_look("classic") if w.layout_store is not None else None
        if store is not None and store.restore(w, app):
            return
        if store is None:                           # (restore() sets the first geometry itself)
            w.setGeometry(docks.first_geometry(app, getattr(w, "images", 1)))
        w.restoreState(w._initial_state)
        for d in self.docks():
            if d.isHidden():
                d.show()
        w.reset_sizes()
        QtCore.QTimer.singleShot(0, w.reset_sizes)  # again once the layout has settled, as reset_panels

    def _restore_panels(self) -> None:
        w = self.w
        if self.on:                                 # in glass again
            return
        lay = QtWidgets.QMainWindow.layout(w)
        if lay is not None:
            lay.activate()
        w.restoreState(self._was["state"])
        for d in self.docks():
            if d.isHidden():
                d.show()

    def remove(self) -> None:
        w, nav, view = self.w, self.w.nav, self.w.view
        self.on = False
        if self.autohide is not None:
            self.autohide.stop()
        for wt in self._watches:
            wt.stop()
        self._watches = []
        self._rest.stop()
        self._untint()
        view.vb.sigRangeChanged.disconnect(self._view_moved)
        nav.play.toggled.disconnect(self._play_toggled)
        # the controls back in the toolbar, in their order
        for row in self._rows:
            while row.count():
                row.takeAt(0)
        for x in self._made:
            x.deleteLater()
        for btn, css in self._sheets.items():
            if btn not in self._made:
                btn.setStyleSheet(css)
        tb = nav.tb
        for a, visible in self._actions:
            tb.addAction(a)
            a.setVisible(visible)
        for a, (lo, hi) in self._was["sliders"].items():
            nav.sliders[a].setMinimumWidth(lo)
            nav.sliders[a].setMaximumWidth(hi)
        tb.show()
        self.bar.hide()
        self.bar.deleteLater()
        for s in self.skins:
            s.remove()
        self.skins = []
        for d, floating in self._was["floating"].items():
            d.setFloating(floating)
        # a zoom taken in glass is left first: the geometry given back below is the window's, not the zoom's
        if w.windowState() & ZOOMED:
            w.setWindowState(w.windowState() & ~ZOOMED)
        if w.window_ops is not None:
            w.window_ops.unzoomed = self._was["unzoomed"]
        # the window's size before the panels': restored into glass's narrowed window, Qt shared that width out and
        # kept the shares (spectra 414x245 where 520x343 had been). Once more when the window manager has applied
        # the size, which it may do later
        if self._fresh:
            self._start_afresh()
        else:
            if self._was["zoom"]:                   # zoomed as it came: its size under the zoom first, which the
                w.setGeometry(self._was["normal"])  # zoom's undo then gives back (a Mac's green button, measured)
                w.setWindowState(w.windowState() | self._was["zoom"])
            else:
                w.setGeometry(self._was["geometry"])
            self._restore_panels()
            QtCore.QTimer.singleShot(0, self._restore_panels)
        w.centralWidget().layout().setContentsMargins(self._was["margins"])
        w.centralWidget().layout().setSpacing(self._was["spacing"])
        if self._was["ci"] is not None:
            for v in self._images():
                v.widget.ci.setContentsMargins(*self._was["ci"])
        for c in getattr(w, "linked", ()):
            c.set_docked_margin(docks.PANEL_GUTTER)
        w.statusBar().setVisible(self._was["statusbar"])
        w.setWindowTitle(self._was["title"])
        self._image_titles(None)
        self._tabs(False)
        if "title_bar" in self._was:
            tb = self._was["title_bar"]
            tb.setPalette(QtGui.QPalette())         # nothing of its own: the application's, in the theme of now
            tb.hud = tb.corners.line.hud = None
            tb.corners.line.update()
            tb.update()
        key = w.colour_key
        if key is not None and "_place" in vars(key):   # its own corner again
            del key._place
            key._place(view.widget)
        nav.fit(w.width())                              # at the window's own width again; and once the toolbar is
        QtCore.QTimer.singleShot(0, lambda: nav.fit(w.width()))     # laid out (fit reads the sliders' own width)
        QtCore.QTimer.singleShot(0, view.show_all)
