"""A cube linked to the main one (ROADMAP E8.1), in the main cube's window: its image beside the main image, the
same size and showing the same region (zoom and pan are the main image's), and its spectra and lambda-t as tabs in
the main cube's panels (PanelTabs: a tab per cube, named as the cube, in every look; as docks of their own, glass
floated four panels in one column, 120 px each, or two columns that left no room for the images). It follows the
main cube's cursor, lock and t; its lambda (and its Stokes, when the two cubes do not have the same number) are its
own (core.session.Member), picked on its own panels and kept in the state, so that its panels' markers and reads
follow as the main cube's do. Its reads are a scheduler of its own (core.scheduler, member=k) on the main cube's
threads (data.dataset: one thread runs parallel numba for all). The slit and the 2x2 view are the main cube's.

A name over each image says which cube it is (the line, else the file); the panels' tabs carry it.
"""
import math
import os

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from ..core.scheduler import Scheduler
from . import glass, style
from .cards import CARD, CARD_LIGHT, Rounder
from .gestures import Gestures
from .imageview import ImageView
from .lambda_t import LambdaTPanel
from .padlock import PanelLock
from .slit import SlitHint
from .spectra import AxisDrag, SpectraPanel

SUFFIXES = (".fits", ".icube", ".fcube")
TAG_TOP = 8                 # px from the image's top: the name, centred (the padlock top right, the hints top left)


def stem(path) -> str:
    """The file's name without its cube suffix: Blos.6173_map for Blos.6173_map.fcube."""
    name = os.path.basename(str(path))
    for suf in SUFFIXES:
        if name.endswith(suf):
            return name[:-len(suf)]
    return name


def cube_names(datasets) -> list[str]:
    """A short name for each cube, as the tags and the panels' titles show it: its line (WAVEBAND, data.axes), or
    its file when it has none or another cube has the same line (a field map of the same line, a second
    observation of it)."""
    lines = [getattr(getattr(ds, "axes", None), "line", None) for ds in datasets]
    return [ln if ln and lines.count(ln) == 1 else stem(ds.path) for ds, ln in zip(datasets, lines, strict=True)]


class NameTag(SlitHint):
    """Which cube an image shows, at its top centre, below what it would cover (avoid: in glass the colour key goes
    top left, and over a narrow image it hid the name); no mouse, light or dark with the theme (the slit's hint)."""

    def __init__(self, view: QtWidgets.QWidget, text: str, light: bool = False):
        super().__init__(view, light=light)
        self.set_text(text)
        self._avoid: list[QtWidgets.QWidget] = []
        view.installEventFilter(self)
        self.place()
        self.show()

    def avoid(self, *widgets) -> None:
        """Keep clear of these overlays of the same image, wherever they move."""
        for w in widgets:
            if w is not None and w not in self._avoid:
                self._avoid.append(w)
                w.installEventFilter(self)
        self.place()

    def eventFilter(self, obj, e):
        E = QtCore.QEvent.Type
        if e.type() in (E.Resize, E.Move, E.Show, E.Hide):
            self.place()
        return False

    def place(self) -> None:
        view = self.parentWidget()
        assert view is not None
        r = QtCore.QRect(max(0, (view.width() - self.width()) // 2), TAG_TOP, self.width(), self.height())
        for w in self._avoid:
            if w.isVisibleTo(view) and w.geometry().intersects(r):
                r.moveTop(w.geometry().bottom() + 6)
        self.move(r.topLeft())


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
        self.tag = NameTag(self.view.widget, name, light=light)
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
        self.tag.set_light(light)
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

    # ---------------------------------------------------------------- input
    def _hover(self, y: float, x: float) -> None:
        self.session.hover(math.floor(y), math.floor(x))

    def _click(self, ev) -> None:
        """As on the main image: a click locks the cursor there, a right click releases it, a double click shows the
        whole image (in both)."""
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
