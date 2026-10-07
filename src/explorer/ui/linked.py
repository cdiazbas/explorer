"""A cube linked to the main one (ROADMAP E8.1), in the main cube's window: its image beside the main image, the
same size and showing the same region (zoom and pan are the main image's), and its spectra and lambda-t as tabs in
the main cube's panels (PanelTabs: a tab per cube, named as the cube, in every look; as docks of their own, glass
floated four panels in one column, 120 px each, or two columns that left no room for the images). It follows the
main cube's cursor, lock and t; its lambda (and its Stokes, when the two cubes do not have the same number) are its
own (core.session.Member), picked on its own panels and kept in the state, so that its panels' markers and reads
follow as the main cube's do. Its reads are a scheduler of its own (core.scheduler, member=k) on the main cube's
threads (data.dataset: one thread runs parallel numba for all). The slit and the 2x2 view are the main cube's; the
slit is drawn on every image, and can be drawn on any of them (ui.slit attaches each).

Each image carries its cube's name above it (data.names: the line, and the quantity of a map; ImageTitle; the file
in its tooltip): a linked image is a panel of its own, between the main image and the spectra, that floats and docks
as the others do; closed, it reads nothing. The panels' tabs carry the names too.
"""
import math
import os

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from ..core.scheduler import Scheduler
from . import docks, glass, style
from .cards import CARD, CARD_LIGHT, Rounder
from .gestures import Gestures
from .imageview import ImageView
from .lambda_t import LambdaTPanel
from .padlock import PanelLock
from .spectra import AxisDrag, SpectraPanel

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
    title its float and close marks show at the right. A drag on the title floats the panel and a double click
    docks it again (QDockWidget's own, for any title bar widget). One height for all (height()), so the images
    beside each other are one size."""
    own = True                                          # titlebar.dock_titles leaves it in place

    def __init__(self, text: str, dock: QtWidgets.QDockWidget | None = None, parent=None):
        super().__init__(parent if parent is not None else dock)
        self.text, self.dock = text, dock
        self.back: QtGui.QColor | None = None           # its background (glass: the image's colour); None: the window's
        self.buttons: list[_TitleButton] = []
        self.setFixedHeight(self.height_for(self))
        if dock is None:
            return
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(0)
        lay.addStretch(1)
        for kind, tip, fn in (("float", "Detach (or drag the title); double click the title: back in place",
                               lambda: dock.setFloating(not dock.isFloating())),
                              ("close", "Close (Panels in the toolbar opens it again)", dock.close)):
            b = _TitleButton(kind, self, tip)
            b.clicked.connect(fn)
            b.hide()
            lay.addWidget(b)
            self.buttons.append(b)

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
        self.keys = []
        for name, widget, key in tabs:
            self.addTab(widget, name)
            self.keys.append(key)
        self.shown = True
        self.currentChanged.connect(lambda _i: self._tell())
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
    """The images side by side show one region: a zoom or a pan in one, the same region in the others (the 2x2
    view's _follow, ui.stokesgrid). Not pyqtgraph's setXLink/setYLink: with the aspect locked, views of different
    sizes drifted apart (after glass and back, its margins taken from the main image only: Blos 57-1974 in x against
    0-2031, the cursor 18 rows lower)."""

    def __init__(self, views, parent):
        super().__init__(parent)
        self.views = list(views)
        self._following = False
        for v in self.views:
            v.vb.sigRangeChanged.connect(lambda *_a, v=v: self._follow(v))

    def _follow(self, src) -> None:
        if self._following:
            return
        self._following = True
        try:
            r = src.vb.viewRect()
            for v in self.views:
                if v is not src:
                    v.vb.setRange(r, padding=0)
        finally:
            self._following = False


class _Sink:
    """The linked cube's scheduler's results, on its panels."""

    def __init__(self, cube: "LinkedCube"):
        self.cube = cube

    def image(self, idx, img, levels):
        self.cube.view.set_image(img, levels)
        self.cube.paint_colour()

    def spectra(self, spec, pixel, t):
        if self.cube.spectra is not None:
            self.cube.spectra.show(spec)

    def lambda_t(self, lt, pixel, s, levels):
        self.cube.last_s = s
        if self.cube.lambda_t is not None:
            self.cube.lambda_t.show(lt, levels)
            self.cube.paint_colour()

    def cleared(self, pixel):
        for p in (self.cube.spectra, self.cube.lambda_t):
            if p is not None:
                p.clear()

    def y_range(self, k, r):
        if self.cube.spectra is not None:
            self.cube.spectra.set_range(k, r)

    def units(self, iscale):
        if self.cube.spectra is not None:
            self.cube.spectra.set_units(iscale)

    def grid_image(self, s, idx, img, levels):          # the 2x2 view is the main cube's
        pass

    def slit_path(self, pix):                           # and so is the slit
        pass

    def slit(self, ts, sl, s, ts_levels, sl_levels):
        pass


class LinkedCube:
    def __init__(self, shell, k: int, name: str):
        """Member k of the shell's session, named name: its image and its panels (the shell puts them beside the
        main one's and in its panels' tabs), and its scheduler (start(), once the window has its own)."""
        self.shell, self.k, self.name = shell, k, name
        self.session = session = shell.session
        self.dataset = ds = session.members[k].dataset
        ex = shell.dataset.executors
        light = style.is_light()
        self.view = ImageView(on_hover=self._hover, strips=ex.strips, parts=ex.n_strips, light=light)
        self.view.vb.setMenuEnabled(False)              # its region the main image's: ViewSync
        self.view.widget.viewport().setCursor(QtCore.Qt.CursorShape.CrossCursor)
        self.view.widget.scene().sigMouseClicked.connect(self._click)
        # its image a panel of its own (the shell places it beside the main image), titled with its name
        self.dock = docks.dock(shell, name, self.view.widget, f"image:{k}")
        self.title = ImageTitle(name, self.dock)
        self.title.setToolTip(os.path.basename(str(ds.path)))
        self.dock.setTitleBarWidget(self.title)
        self.dock.visibilityChanged.connect(self._image_shown)
        r = ds.roles
        self.spectra = SpectraPanel(max(1, r.ns if r.s is not None else 1), r.nl, ds.axes, light=light) \
            if r.l is not None else None
        self.lambda_t = LambdaTPanel(r.nt, r.nl, ds.axes) if r.t is not None and r.l is not None else None
        self.last_s = 0
        self.image_lock = PanelLock(self.view.widget, "Image contrast: closed = fixed, open = automatic per image. "
                                    "Click to switch; right click fixes it to this image", light=light)
        self.image_lock.toggled.connect(lambda on: self.scheduler.fix_levels(on))
        self.image_lock.refit.connect(self._image_refit)
        self.spec_lock = None
        if self.spectra is not None:
            self.spec_lock = PanelLock(self.spectra.w, "Spectra y range: open = automatic, closed = fixed (I from "
                                       "100 random profiles, Q U V from the whole image). Click to switch; right "
                                       "click fixes it to this pixel", light=light, backed=False)
            self.spec_lock.toggled.connect(lambda on: self.scheduler.set_y_fixed(on))
            self.spec_lock.refit.connect(self.fit_spectra)
        self.scheduler: Scheduler                       # made in start(), once the window has its own; the padlocks
        self._install_gestures()                        # and picks ask it
        self._rounders = [Rounder(w) for w in [self.view.widget] + [p.widget for p in (self.spectra, self.lambda_t)
                                                                    if p is not None]]
        self._off = None

    def start(self) -> None:
        """Its scheduler, and the state followed from now on."""
        self.scheduler = Scheduler(self.session, _Sink(self), member=self.k)
        self._off = self.session.store.subscribe(self._on_state)
        self._follow(self.session.member_state(self.k), None)

    def close(self) -> None:
        if self._off is not None:
            self._off()
            self._off = None
        if hasattr(self, "scheduler"):
            self.scheduler.close()

    # ---------------------------------------------------------------- the state
    def _on_state(self, st, changed) -> None:
        self._follow(self.session.member_state(self.k, st), changed)

    def _follow(self, st, changed) -> None:
        """The crosshair, the lock and its markers, from its own state (changed None: all of them)."""
        def has(*f):
            return changed is None or bool(changed & set(f))
        if has("cursor"):
            self.view.set_crosshair(*st.cursor)
        if has("locked"):
            self.view.set_locked(st.locked)
        if has("l", "own") and self.spectra is not None:
            self.spectra.set_lambda(st.l)
        if has("t", "l", "own") and self.lambda_t is not None:
            self.lambda_t.set_markers(st.t, st.l)

    # ---------------------------------------------------------------- the look and the theme
    def set_look(self, look, acc, light: bool) -> None:
        """What the main cube's panels wear (Shell.set_look): the reticle, the marks, the cards, the colour maps."""
        self.view.set_reticle(look.has("reticle"))
        if self.view.reticle is not None:
            self.view.reticle.set_colour(glass.accent() if look.has("glass") else pg.mkColor(255, 255, 255, 235))
        if self.spectra is not None:
            self.spectra.set_marks(acc, light) if look.has("marks") else self.spectra.clear_marks()
        if self.lambda_t is not None:
            self.lambda_t.set_marks(acc) if look.has("marks") else self.lambda_t.clear_marks()
        card = (CARD_LIGHT if light else CARD) if look.has("cards") else pg.getConfigOption("background")
        for pw in (getattr(self.spectra, "w", None), getattr(self.lambda_t, "w", None)):
            if pw is not None and self.shell.glass is None:
                pw.setBackground(card)
        self.paint_colour()

    def set_light(self, light: bool) -> None:
        self.view.set_light(light)
        for lock in (self.image_lock, self.spec_lock):
            if lock is not None:
                lock.set_light(light)
        if self.spectra is not None:
            self.spectra.set_light(light)
        if self.lambda_t is not None:
            self.lambda_t.set_light(light)

    def paint_colour(self) -> None:
        """Its image and lambda-t in the main cube's colour maps, by its own Stokes (the modern look's colour)."""
        cols = self.shell.colours if self.shell.look.has("colour") else None
        s = self.session.member_state(self.k).s
        self.view.set_lut(cols.image_lut(s) if cols is not None else self.view.base_lut)
        if self.lambda_t is not None:
            self.lambda_t.set_lut(cols.lut(self.last_s) if cols is not None else None)

    def _image_shown(self, on: bool) -> None:
        """Its panel closed (or behind another): nothing read for its image; shown again, the image of now."""
        if not self.shell._closing:
            self.session.show(f"image:{self.k}", on)

    # ---------------------------------------------------------------- input
    def _hover(self, y: float, x: float) -> None:
        self.session.hover(math.floor(y), math.floor(x))
        self.shell.slit_tool.hover(y, x)                # the slit being drawn follows the pointer here too

    def _click(self, ev) -> None:
        """As on the main image: a click locks the cursor there, a right click releases it, a double click shows the
        whole image (in both); while a slit is drawn, the click is the slit's."""
        if self.shell.slit_tool.click(ev, self.view.vb):
            return
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            self.session.lock(False)
            return
        if ev.button() != QtCore.Qt.MouseButton.LeftButton or not self.view.vb.sceneBoundingRect().contains(
                ev.scenePos()):
            return
        if ev.double():
            self.shell.view.show_all()
            return
        p = self.view.vb.mapSceneToView(ev.scenePos())
        self.session.lock(False)
        self.session.hover(math.floor(p.y()), math.floor(p.x()))
        self.session.lock(True)

    def _install_gestures(self) -> None:
        """Its panels pick its own lambda (and t on lambda-t, everyone's), as the main cube's do (ui.gestures)."""
        C = QtCore.Qt.CursorShape
        self._wanted: dict = {}
        self._pick_timer = QtCore.QTimer(self.view.widget, singleShot=True, interval=0)
        self._pick_timer.timeout.connect(self._pick_flush)
        picks = {}
        for panel, pick, cursor in ((self.spectra, self._spectrum_pick, C.SizeHorCursor),
                                    (self.lambda_t, self._lt_pick, C.SizeAllCursor)):
            if panel is None:
                continue
            vp = panel.w.viewport()
            vp.setCursor(cursor)
            picks[vp] = pick
            panel.w.scene().sigMouseClicked.connect(self._panel_click)
        image = self.view.widget.viewport()
        self._gestures = Gestures(self.view.widget, picks, image)
        for vp in [*picks, image]:
            vp.installEventFilter(self._gestures)
        if self.spectra is not None:
            self._axis_drag = AxisDrag(self.spectra, self._y_manual, lambda k: self.scheduler.y_auto(k))

    def _y_manual(self, k: int, r) -> None:
        if r[1] > r[0]:
            self.scheduler.set_y_manual(k, r)

    def _panel_click(self, ev) -> None:
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            self.session.lock(False)

    def _spectrum_pick(self, pos, now: bool = True) -> None:
        if self.spectra is None:
            return
        for p in self.spectra.plots:
            if p.vb.sceneBoundingRect().contains(pos):
                xv = p.vb.mapSceneToView(pos).x()
                self._want({"l": int(np.argmin(np.abs(self.spectra.xl - xv)))}, now)
                return

    def _lt_pick(self, pos, now: bool = True) -> None:
        if self.lambda_t is None:
            return
        vb = self.lambda_t.w.getPlotItem().vb
        if not vb.sceneBoundingRect().contains(pos):
            return
        q = vb.mapSceneToView(pos)
        self._want({"l": int(np.clip(int(q.x()), 0, self.lambda_t.nl - 1)),
                    "t": int(np.clip(int(q.y()), 0, self.lambda_t.nt - 1))}, now)

    def _want(self, want: dict, now: bool) -> None:
        """now: at once (a press); else the latest at the next pass of the event loop (Shell._want_pick)."""
        if now:
            self._set(want)
            return
        self._wanted.update(want)
        self._pick_timer.start()

    def _pick_flush(self) -> None:
        want, self._wanted = self._wanted, {}
        self._set(want)

    def _set(self, want: dict) -> None:
        for axis, v in want.items():
            self.session.set_member_index(self.k, axis, v)

    # ---------------------------------------------------------------- its padlocks
    def _image_refit(self) -> None:
        self.scheduler.fix_levels(True, refit=True)
        self.image_lock.set_closed(True)

    def fit_spectra(self) -> None:
        self.scheduler.fit_y()
        if self.spec_lock is not None:
            self.spec_lock.set_closed(self.scheduler.yrange.fixed)

    def reset_view(self) -> None:
        if self.spectra is not None:
            self.spectra.reset_view()
            if hasattr(self, "scheduler"):
                self.scheduler.yrange.reset()
        if self.lambda_t is not None:
            self.lambda_t.reset_view()
