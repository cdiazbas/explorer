"""A cube linked to the main one (ROADMAP E8.1), in the main cube's window: its image beside the main image, the
same size and showing the same region (zoom and pan are the main image's), and its spectra and lambda-t as tabs in
the main cube's panels (PanelTabs: a tab per cube, named as the cube, in every look; as docks of their own, glass
floated four panels in one column, 120 px each, or two columns that left no room for the images). It follows the
main cube's cursor, lock and t; its lambda (and its Stokes, when the two cubes do not have the same number) are its
own (core.session.Member), picked on its own panels and kept in the state, so that its panels' markers and reads
follow as the main cube's do. Its reads are a scheduler of its own (core.scheduler, member=k) on the main cube's
threads (data.dataset: one thread runs parallel numba for all). The 2x2 view and the slit panel are the main
window's; the slit is drawn on every image, can be drawn on any of them (ui.slit attaches each), and its panel shows
the slices of the cube whose image took it (core.slitreads).

Each image carries its cube's name above it (data.names: the line, and the quantity of a map; ImageTitle; the file
in its tooltip): a linked image is a panel of its own, between the main image and the spectra, that floats and docks
as the others do; closed, it reads nothing. The panels' tabs carry the names too.
"""
import os

from PySide6 import QtCore, QtGui, QtWidgets

from . import docks, glass, style, titlebar
from .cards import Rounder
from .cube import CubeView

TITLE_PAD = 1               # px above and below an image's name: thin, it takes little of the image's height
TITLE_SMALLER = 1.5         # pt below the window's font (4 px and the full font took 28 px of a zoomed image's 844)


class _TitleButton(QtWidgets.QAbstractButton):
    """A mark drawn in the title's ink: "float" (two squares) or "close" (a cross); the style's own icons differ
    from one platform and theme to the next."""

    def __init__(self, kind: str, parent, tip: str):
        super().__init__(parent)
        self.kind = kind
        self.back: QtGui.QColor | None = None           # the title's background, under the float mark's front square
        self.setToolTip(tip)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)

    def sizeHint(self):
        s = self.fontMetrics().height()
        return QtCore.QSize(s, s)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        c = self.palette().color(QtGui.QPalette.ColorRole.WindowText)
        c.setAlphaF(1.0 if self.underMouse() else 0.55)
        p.setPen(QtGui.QPen(c, 1.2))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        side = round(min(self.width(), self.height()) * 0.5)
        r = QtCore.QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        if self.kind == "close":
            p.drawLine(r.topLeft(), r.bottomRight())
            p.drawLine(r.topRight(), r.bottomLeft())
        else:                                           # a window over another: one behind, one in front
            k = side * 0.7
            p.drawRect(QtCore.QRectF(r.right() - k, r.top(), k, k))
            p.setBrush(self.back if self.back is not None else self.palette().color(QtGui.QPalette.ColorRole.Window))
            p.drawRect(QtCore.QRectF(r.left(), r.bottom() - k, k, k))


class ImageTitle(QtWidgets.QWidget):
    """An image's name above it, the same for every image: the main one's in its place (a header), a linked one's as
    its panel's title bar. The name centred on the window's colour and nothing else at rest; over a linked image's
    title its close and float marks show at the left, as on every panel's title. A drag on the title floats the
    panel and a double click docks it again (QDockWidget's own, for any title bar widget). One height for all
    (height()), so the images beside each other are one size."""
    own = True                                          # titlebar.dock_titles leaves it in place

    def __init__(self, text: str, dock: QtWidgets.QDockWidget | None = None, parent=None):
        super().__init__(parent if parent is not None else dock)
        self.text, self.dock = text, dock
        self.back: QtGui.QColor | None = None           # its background (glass: the image's colour); None: the window's
        self.buttons: list[_TitleButton] = []
        self.setFixedHeight(self.height_for(self))
        if dock is None:
            return
        # close, then float, at the left: where every panel's title has them (titlebar.DockTitle, glass's PanelTitle;
        # at the right they were the one title with its marks on the other side)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 0, 0)
        lay.setSpacing(0)
        for kind, tip, fn in (("close", "Close (Panels in the toolbar opens it again)", dock.close),
                              ("float", "Detach (or drag the title); double click the title: back in place",
                               lambda: dock.setFloating(not dock.isFloating()))):
            b = _TitleButton(kind, self, tip)
            b.clicked.connect(fn)
            b.hide()
            lay.addWidget(b)
            self.buttons.append(b)
        lay.addStretch(1)

    @staticmethod
    def font_of(w: QtWidgets.QWidget) -> QtGui.QFont:
        f = QtGui.QFont(w.font())
        f.setWeight(QtGui.QFont.Weight.DemiBold)
        if f.pointSizeF() > 0:
            f.setPointSizeF(max(7.0, f.pointSizeF() - TITLE_SMALLER))
        else:                                           # a font set in pixels
            f.setPixelSize(max(9, f.pixelSize() - 2))
        return f

    def set_back(self, colour: QtGui.QColor | None) -> None:
        self.back = colour
        for b in self.buttons:
            b.back = colour
            b.update()
        self.update()

    @classmethod
    def height_for(cls, w: QtWidgets.QWidget) -> int:
        return QtGui.QFontMetrics(cls.font_of(w)).height() + 2 * TITLE_PAD

    def sizeHint(self):
        return QtCore.QSize(80, self.height_for(self))

    minimumSizeHint = sizeHint

    def enterEvent(self, e):
        for b in self.buttons:
            b.show()

    def leaveEvent(self, e):
        for b in self.buttons:
            b.hide()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        R = QtGui.QPalette.ColorRole
        p.fillRect(self.rect(), self.back if self.back is not None else self.palette().color(R.Window))
        p.setFont(self.font_of(self))
        p.setPen(self.palette().color(R.WindowText))
        # room for the marks on both sides, shown or not: the name stays put (a never-shown button's width is Qt's
        # default, ~100 px, and elided the name away)
        side = sum(b.sizeHint().width() for b in self.buttons) + 8 if self.buttons else 8
        r = self.rect().adjusted(side, 0, -side, 0)
        text = QtGui.QFontMetrics(self.font_of(self)).elidedText(self.text, QtCore.Qt.TextElideMode.ElideRight,
                                                                  max(0, r.width()))
        p.drawText(r, QtCore.Qt.AlignmentFlag.AlignCenter, text)


class PanelTabs(QtWidgets.QTabWidget):
    """One panel's cubes (the spectra, or lambda-t): a tab each, named as its cube, below. Only the tab in front is
    read (Session.show), as a dock behind another's tab is not; set_shown follows the panel's own dock."""

    def __init__(self, session, tabs, closing=lambda: False):
        """tabs: (name, widget, panel key: "spectra", "spectra:1"...), the main cube's first; closing(): the window
        closing, when nothing is told any more."""
        super().__init__()
        self.session, self.closing = session, closing
        self.setTabPosition(QtWidgets.QTabWidget.TabPosition.South)
        self.setDocumentMode(True)
        # never the keyboard's: the keys are the window's, and in glass its focus ring showed in the accent
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.tabBar().setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setTabBarAutoHide(True)                    # one cube left in it (the others in windows of their own)
        self.keys = []
        for name, widget, key in tabs:
            self.addTab(widget, name)
            self.keys.append(key)
        self.order = list(self.keys)                    # where each comes back to
        self._lent: dict = {}                           # key -> (name, tooltip) of a tab taken out
        self.shown = True
        self.currentChanged.connect(lambda _i: self._tell())
        self._tell()

    def take(self, key: str):
        """The tab of key taken out (its cube in a window of its own): its widget, no longer told about."""
        i = self.keys.index(key)
        w = self.widget(i)
        self._lent[key] = (self.tabText(i), self.tabToolTip(i))
        self.removeTab(i)
        self.keys.pop(i)
        self._tell()
        return w

    def give(self, key: str, widget) -> None:
        """The tab of key back, where it was among the others."""
        name, tip = self._lent.pop(key)
        i = sum(1 for k in self.keys if self.order.index(k) < self.order.index(key))
        self.insertTab(i, widget, name)
        self.setTabToolTip(i, tip)
        self.keys.insert(i, key)
        self._tell()

    def set_shown(self, on: bool) -> None:
        self.shown = bool(on)
        self._tell()

    def _tell(self) -> None:
        if self.closing():
            return
        for i, key in enumerate(self.keys):
            self.session.show(key, self.shown and i == self.currentIndex())


class ViewSync(QtCore.QObject):
    """The images side by side at one centre and one magnification (screen px per data pixel), as ds9's locked frames:
    a smaller image (squeezed, or floating) shows less, at the same zoom. Who leads:
    - the main image, whatever moved it (a zoom, a pan, its double click, a resize, glass): the others follow;
    - a linked image moved by the mouse (wheel, drag; pyqtgraph's sigRangeChangedManually): the main one follows it,
      and with it the others;
    - a linked image that changed for any other reason (its own resize): it takes the main image's centre and
      magnification again, and moves nothing else. On the loop's next pass: pyqtgraph tells a wheel's change
      (sigRangeChanged) before saying it was the mouse's (sigRangeChangedManually), and taken back at once the
      wheel zoomed nothing on a linked image.
    A linked image zooms out as far as the main one and no further (its guard's floor: the main image's fit), below
    its own fit when its panel is the larger: held at its own fit, a cube's window larger than the main image showed
    another magnification (7.95 px per pixel against 3.24).
    Sharing the region instead (the 2x2 view's _follow, whose panels are one size) showed a squeezed image at half
    the zoom (9.4 px per pixel against 18.4). Not pyqtgraph's setXLink/setYLink: with the aspect locked, views of
    different sizes drifted apart (after glass and back, Blos 57-1974 in x against 0-2031)."""

    def __init__(self, views, parent):
        super().__init__(parent)
        self.main, self.others = views[0], list(views[1:])
        self._following = False
        self._realigning: list = []                     # linked images to put back on the main one's scale
        self._timer = QtCore.QTimer(self, singleShot=True, interval=0)
        self._timer.timeout.connect(self._realign_now)
        self.main.vb.sigRangeChanged.connect(lambda *_a: self._lead(self.main))
        for v in self.others:
            v.zoom_floor = self._lowest
            v.vb.sigRangeChangedManually.connect(lambda *_a, v=v: self._lead(v))
            v.vb.sigRangeChanged.connect(lambda *_a, v=v: self._realign(v))

    def _lowest(self) -> float | None:
        """The main image's lowest magnification, every linked image's floor; None before its first image."""
        g = self.main.guard
        return None if g is None else g.lowest()

    @staticmethod
    def _place(dst, centre: QtCore.QPointF, sx: float, sy: float) -> None:
        """dst's view at this centre, sx and sy data pixels per screen px, over its own size."""
        w, h = dst.vb.width() * sx, dst.vb.height() * sy
        if w > 0 and h > 0:
            dst.vb.setRange(QtCore.QRectF(centre.x() - w / 2, centre.y() - h / 2, w, h), padding=0)

    @staticmethod
    def _scale(v) -> tuple[QtCore.QPointF, float, float] | None:
        r = v.vb.viewRect()
        if v.vb.width() < 2 or v.vb.height() < 2 or r.width() <= 0:
            return None
        return r.center(), r.width() / v.vb.width(), r.height() / v.vb.height()

    def _lead(self, src) -> None:
        if self._following:
            return
        if src in self._realigning:                     # the mouse's after all: it leads
            self._realigning.remove(src)
        got = self._scale(src)
        if got is None:
            return
        self._following = True
        try:
            for v in [self.main, *self.others]:
                if v is not src:
                    self._place(v, *got)
        finally:
            self._following = False

    def _realign(self, v) -> None:
        if self._following or v in self._realigning:
            return
        self._realigning.append(v)
        self._timer.start()

    def _realign_now(self) -> None:
        views, self._realigning = self._realigning, []
        got = self._scale(self.main)
        if got is None:
            return
        self._following = True
        try:
            for v in views:
                self._place(v, *got)
        finally:
            self._following = False


class _Rounded(QtCore.QObject):
    """A panel's shape rounded again at each resize while it floats (titlebar.round_window)."""

    def __init__(self, dock: QtWidgets.QDockWidget):
        super().__init__(dock)
        self.d = dock
        dock.installEventFilter(self)

    def eventFilter(self, obj, e):
        if obj is self.d and e.type() == QtCore.QEvent.Type.Resize:
            titlebar.round_window(self.d, glass.RADIUS_PANEL)
        return False


class LinkedCube(CubeView):
    """A linked cube (member k): a CubeView whose image is a panel of its own, titled with its name, between the main
    image and the spectra; closed (or behind another), nothing is read for it. As a window of its own (the mock the
    user chose for a cube apart: its image, its spectra and its lambda-t), the same panel floats, and inside it, a
    main window of its own (frame), the image is the centre and its spectra and lambda-t are panels docked beside it:
    docks as the main window's, with their titles, close and float, each shown again from Panels where it was. They
    are made the first time the cube is a window of its own, and their plots go back to the main window's tabs
    whenever its image panel docks, however it is docked."""

    def __init__(self, shell, k: int, name: str):
        super().__init__(shell, k, name, style.is_light())
        self.frame = docks.frame(self.view.widget)
        self.panes: dict[str, QtWidgets.QDockWidget] = {}    # panel key ("spectra:k") -> its dock in the frame
        self.windowed = False                           # its spectra and lambda-t in the frame, not in the tabs
        self.dock = docks.dock(shell, name, self.frame, f"image:{k}")
        self.title = ImageTitle(name, self.dock)
        self.title.setToolTip(os.path.basename(str(self.dataset.path)))
        self.dock.setTitleBarWidget(self.title)
        self.dock.visibilityChanged.connect(self._image_shown)
        self.dock.topLevelChanged.connect(lambda floating: None if floating else self.as_window(False))
        # floating, a window of its own: rounded as glass's panels are, with a margin the round corners do not cut
        # (in glass, docked, it had none, and floating it went on without one)
        self.docked_margin = docks.PANEL_GUTTER
        self.dock.topLevelChanged.connect(lambda _floating: self._frame())
        self._rounded = _Rounded(self.dock)
        self._rounders = [Rounder(w) for w in [self.view.widget] + [p.widget for p in (self.spectra, self.lambda_t)
                                                                    if p is not None]]

    def set_docked_margin(self, m: int) -> None:
        """Its margin while docked (glass: none, as the main image's); floating it keeps PANEL_GUTTER."""
        self.docked_margin = m
        self._frame()

    def _frame(self) -> None:
        g = docks.PANEL_GUTTER if self.dock.isFloating() else self.docked_margin
        lay = self.dock.widget().layout()
        if lay is not None and lay.contentsMargins().left() != g:
            lay.setContentsMargins(g, g, g, g)
            # at once, not at the next layout pass: glass fits the window right after a re-dock, and with the
            # floating margin still in place it read 10 px less of image and cut the window lower each time
            lay.activate()
        titlebar.round_window(self.dock, glass.RADIUS_PANEL)

    def panels(self) -> list:
        """(key, panel widget, the main window's tabs, title) of its spectra and lambda-t, those it has."""
        out = []
        for key, panel, tabs, title in (("spectra", self.spectra, self.shell.spec_tabs, "Spectrum"),
                                        ("lambda_t", self.lambda_t, self.shell.lt_tabs,
                                         self.slices.panel if self.slices else "λ–t")):
            if panel is not None and tabs is not None:
                out.append((f"{key}:{self.k}", panel.widget, tabs, title))
        return out

    def as_window(self, on: bool) -> None:
        """Its spectra and lambda-t docked beside its image in its frame (on: the panel about to float as the cube's
        window), or back in the main window's tabs. Each panel shown again as it comes in, docked."""
        if bool(on) == self.windowed:
            return
        self.windowed = bool(on)
        for key, widget, tabs, title in self.panels():
            if on:
                tabs.take(key)
                pane = self.panes.get(key) or self._pane(key, title)
                lay = pane.widget().layout()            # its gutter (docks.dock)
                assert lay is not None
                lay.addWidget(widget)
                widget.show()                           # a tab behind was hidden
                pane.setFloating(False)
                pane.show()
            else:
                self.panes[key].hide()
                tabs.give(key, widget)
        self._image_shown(None)

    def _pane(self, key: str, title: str) -> QtWidgets.QDockWidget:
        """The dock of one of its panels in its frame, made the first time: below the one before it (lambda-t below
        the spectra), right of the image; dressed as the main window's panels (Shell.dress)."""
        d = docks.dock(self.frame, title, None, key)
        before = list(self.panes.values())
        if before:
            self.frame.splitDockWidget(before[-1], d, QtCore.Qt.Orientation.Vertical)
        d.toggleViewAction().setText(f"{self.name} · {title}")
        d.visibilityChanged.connect(lambda _on: self._image_shown(None))
        d.topLevelChanged.connect(lambda floating: self.shell.pane_floated(d, floating))
        self.panes[key] = d
        if key.startswith("lambda_t"):                  # its number of t steps, as the main window's lambda-t
            self.shell.give_steps(d)
        self.shell.dress(d)
        return d

    def panels_width(self, w: int) -> None:
        """Its panels w px wide in its window, the image the rest. Its window laid out at its size first: before,
        the frame had its old width, and Qt shared out that one."""
        shown = [p for p in self.panes.values() if not p.isHidden()]
        if not shown:
            return
        for lay in (self.dock.layout(), self.dock.widget().layout(), self.frame.layout()):
            if lay is not None:
                lay.activate()
        self.frame.resizeDocks(shown[:1], [w], QtCore.Qt.Orientation.Horizontal)

    def _image_shown(self, on: bool | None) -> None:
        """Its panel closed (or behind another): nothing read for its image (nor, as its window, for its spectra and
        lambda-t); shown again, the image of now. As its window, each of its panels read while shown in it. None:
        one of those panels shown or closed, the image as it is."""
        if self.shell._closing:
            return
        if on is None:
            on = self.dock.isVisible()
        self.session.show(f"image:{self.k}", on)
        if self.windowed:
            for key, pane in self.panes.items():
                self.session.show(key, on and not pane.isHidden())
