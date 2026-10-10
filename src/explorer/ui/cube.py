"""One cube's views in the window: its image, its spectra and lambda-t, their padlocks, the gestures that pick on them,
its crosshair, markers and Stokes label, and its scheduler (ROADMAP E8.1). The main cube's and each linked cube's
are this one class, member k of the session: a pick sets the cube's own lambda (Session.set_member_index, the main
cube's index for k = 0), a click on its image locks the cursor for all. What differs is where the views sit and what
the main cube alone has: its image in the window's centre and the slit, the 2x2 view, the colour key and the status
line (ui.shell); a linked image in a panel of its own (ui.linked.LinkedCube).

The behaviour is the main cube's as it was in ui.shell (from the prototype's app/viewer.py: _install_gestures 1790,
_spectrum_click to _pick_flush 1270-1317, _image_click 1419), now one code for every cube.
"""
import math

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore

from ..core.scheduler import Scheduler
from ..data.names import slice_names
from . import glass
from .cards import CARD, CARD_LIGHT
from .gestures import Gestures
from .imageview import ImageView
from .lambda_t import LambdaTPanel, TimeCurve
from .padlock import PanelLock
from .spectra import AxisDrag, SpectraPanel

IMAGE_TIP = ("Image contrast: closed = fixed, open = automatic per image. Click to switch; right click fixes it to "
             "this image")
SPEC_TIP = ("Spectra y range: open = automatic, closed = fixed (I from 100 random profiles, Q U V from the whole "
            "image). Click to switch; right click {keys}fixes it to this pixel")


class CubeSink:
    """The scheduler's results on a cube's own panels (the main cube's adds the window's parts: ui.shell)."""

    def __init__(self, cube: "CubeView"):
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

    def slit_path(self, pix):                           # and so is the slit panel, whichever cube it reads
        pass

    def slit(self, ts, sl, s, ts_levels, sl_levels):
        pass


class CubeView:
    def __init__(self, shell, k: int, name: str, light: bool, keys: str = ""):
        """Member k of shell's session, named name. light: the theme it is made in; keys: what the spectra padlock's
        tip adds about the keyboard (the main cube's F)."""
        self.shell, self.k, self.name = shell, k, name
        self.session = session = shell.session
        self.dataset = ds = session.members[k].dataset
        ex = shell.dataset.executors                    # the main cube's: one thread runs parallel numba for all
        self.view = ImageView(on_hover=self._hover, strips=ex.strips, parts=ex.n_strips, light=light)
        self.view.widget.scene().sigMouseClicked.connect(self._click)
        r = ds.roles
        # a cube without lambda has no spectra
        self.spectra = SpectraPanel(max(1, r.ns if r.s is not None else 1), r.nl, ds.axes, light=light) \
            if r.l is not None else None
        # its axis other than t named as data.names says (not lambda unless known to be): a linked cube's, and the
        # main cube's with one plane along it or none; the main cube's with lambda as it always was
        self.slices = slice_names(r, ds.axes, getattr(ds, "path", "")) if k or r.l is None or r.nl <= 1 else None
        # lambda-t needs t; with one plane along the other axis it is one cell wide, a curve against t
        self.lambda_t: LambdaTPanel | TimeCurve | None = None
        if r.t is not None and self.slices is not None and self.slices.mapped:
            # a linked map without times of its own whose frames are the main cube's t (data.link: Blos and Vlos of
            # 6173): its t in the main cube's times, as its slit panel (Shell.slit_cube)
            times = ds.axes
            if k and getattr(ds.axes, "t_sec", None) is None and session.members[k].t == tuple(range(r.nt)):
                times = shell.dataset.axes
            self.lambda_t = TimeCurve(r.nt, times, self.slices.value, light=light)
        elif r.t is not None and r.l is not None:
            self.lambda_t = LambdaTPanel(r.nt, r.nl, ds.axes, *([self.slices.label] if self.slices else []))
        self.last_s = 0                                 # the Stokes of the lambda-t shown (its colour map)
        self.ns = r.ns
        # its Stokes named in the image's top left by something else: the main cube's colour key, which glass puts there
        self.named = False
        self.scheduler: Scheduler                       # made in start(); the padlocks and picks ask it
        # the padlocks, both open at start (the prototype's): closed = fixed, right click = fit to what is shown
        self.image_lock = PanelLock(self.view.widget, IMAGE_TIP, light=light)
        self.image_lock.toggled.connect(lambda on: self.scheduler.fix_levels(on))
        self.image_lock.refit.connect(self.image_refit)
        self.spec_lock: PanelLock | None = None
        if self.spectra is not None:
            self.spec_lock = PanelLock(self.spectra.w, SPEC_TIP.format(keys=keys), light=light, backed=False)
            self.spec_lock.toggled.connect(lambda on: self.scheduler.set_y_fixed(on))
            self.spec_lock.refit.connect(self.fit_spectra)
        self._install_gestures()
        self._off = None

    def start(self, sink=None) -> None:
        """Its scheduler (sink: where its results go; its own panels by default), and the state followed from now
        on."""
        self.scheduler = Scheduler(self.session, sink if sink is not None else CubeSink(self), member=self.k)
        self._off = self.session.store.subscribe(self._on_state)
        self.follow(self.session.member_state(self.k), None)

    def close(self) -> None:
        if self._off is not None:
            self._off()
            self._off = None
        if hasattr(self, "scheduler"):
            self.scheduler.close()

    # ---------------------------------------------------------------- the state
    def _on_state(self, st, changed) -> None:
        self.follow(self.session.member_state(self.k, st), changed)

    def follow(self, st, changed) -> None:
        """The crosshair, the lock, its markers and its Stokes label, from its own state (changed None: all of
        them)."""
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
        if has("s", "own"):
            self.show_stokes(st.s)

    def show_stokes(self, s: int) -> None:
        """The label of Stokes s ("Stokes Q") on its image and its lambda-t (ui.stokeslabel), when it has the four
        Stokes; on the image, not while something else names it there (named)."""
        self.view.set_stokes(None if self.named else s, self.ns)
        if self.lambda_t is not None:
            self.lambda_t.set_stokes(s, self.ns)

    # ---------------------------------------------------------------- the look and the theme
    def set_look(self, look, acc, light: bool) -> None:
        """What a look puts on the cube's views (Shell.set_look): the reticle, the marks, the cards; a linked cube's
        colour maps too (the main cube's are the window's, with its colour key)."""
        self.view.set_reticle(look.has("reticle"))
        if self.view.reticle is not None:
            self.view.reticle.set_colour(glass.accent() if look.has("glass") else pg.mkColor(255, 255, 255, 235))
        if self.spectra is not None:
            self.spectra.set_marks(acc, light) if look.has("marks") else self.spectra.clear_marks()
        if self.lambda_t is not None:
            self.lambda_t.set_marks(acc) if look.has("marks") else self.lambda_t.clear_marks()
        card = (CARD_LIGHT if light else CARD) if look.has("cards") else pg.getConfigOption("background")
        for pw in (getattr(self.spectra, "w", None), getattr(self.lambda_t, "w", None)):
            if pw is not None and self.shell.glass is None:     # worn, glass keeps them clear over its slabs
                pw.setBackground(card)
        if self.k:
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
        """A linked cube's image and lambda-t in the window's colour maps, by its own Stokes (the modern look's
        colour); the main cube's are the window's own (Shell._paint_colour, with the colour key)."""
        if not self.k:
            return
        cols = self.shell.colours if self.shell.look.has("colour") else None
        s = self.session.member_state(self.k).s
        self.view.set_lut(cols.image_lut(s) if cols is not None else self.view.base_lut)
        if self.lambda_t is not None:
            self.lambda_t.set_lut(cols.lut(self.last_s) if cols is not None else None)

    def reset_view(self) -> None:
        """Its spectra's whole lambda range and their y ranges as the padlock says, and its lambda-t's whole range."""
        if self.spectra is not None:
            self.spectra.reset_view()
            if hasattr(self, "scheduler"):
                self.scheduler.yrange.reset()
        if self.lambda_t is not None:
            self.lambda_t.reset_view()

    # ---------------------------------------------------------------- input
    def _hover(self, y: float, x: float) -> None:
        self.session.hover(math.floor(y), math.floor(x))
        self.shell.slit_tool.hover(y, x)                # the slit being drawn follows the pointer, on any image

    def _click(self, ev) -> None:
        """A click locks the cursor there, a right click releases it, a double click shows the whole image (in all of
        them); while a slit is drawn, the click is the slit's (the prototype's _image_click)."""
        if self.shell.slit_tool.click(ev, self.view.vb, self.k):
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
        self.session.lock(False)                        # move there, then lock
        self.session.hover(math.floor(p.y()), math.floor(p.x()))
        self.session.lock(True)

    def _install_gestures(self) -> None:
        """Click or drag picks on its spectra (lambda) and lambda-t (t and lambda); a right click on either releases
        the cursor; each panel's pointer names what it does (ui.gestures). No context menus: a right click releases
        the cursor, nothing else (pyqtgraph's on the image left the next keys unanswered, the prototype's
        app/viewer.py:1018-1028)."""
        C = QtCore.Qt.CursorShape
        self._wanted: dict = {}
        self._pick_timer = QtCore.QTimer(self.view.widget, singleShot=True, interval=0)
        self._pick_timer.timeout.connect(self._pick_flush)
        picks = {}
        for panel, pick, cursor in ((self.spectra, self.spectrum_pick, C.SizeHorCursor),
                                    (self.lambda_t, self.lt_pick,
                                     C.SizeHorCursor if isinstance(self.lambda_t, TimeCurve) else C.SizeAllCursor)):
            if panel is None:
                continue
            vp = panel.w.viewport()
            vp.setCursor(cursor)
            picks[vp] = pick
            panel.w.scene().sigMouseClicked.connect(self.panel_click)
        self.view.vb.setMenuEnabled(False)
        image = self.view.widget.viewport()
        image.setCursor(C.CrossCursor)
        self._gestures = Gestures(self.view.widget, picks, image)
        for vp in [*picks, image]:
            vp.installEventFilter(self._gestures)
        if self.spectra is not None:                    # after the gestures: the y axis strip first (E4.1)
            self._axis_drag = AxisDrag(self.spectra, self.y_manual, lambda k: self.scheduler.y_auto(k))

    def y_manual(self, k: int, r) -> None:
        if r[1] > r[0]:
            self.scheduler.set_y_manual(k, r)

    def panel_click(self, ev) -> None:
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            self.session.lock(False)                    # the right click releases from any panel

    def spectrum_pick(self, pos, now: bool = True) -> None:
        """lambda nearest to x on whichever spectrum plot is under pos."""
        if self.spectra is None:
            return
        for p in self.spectra.plots:
            if p.vb.sceneBoundingRect().contains(pos):
                xv = p.vb.mapSceneToView(pos).x()
                self.want({"l": int(np.argmin(np.abs(self.spectra.xl - xv)))}, now)
                return

    def lt_pick(self, pos, now: bool = True) -> None:
        """(t, lambda) of the cell under pos on lambda-t; t alone on its curve (TimeCurve)."""
        if self.lambda_t is None:
            return
        vb = self.lambda_t.w.getPlotItem().vb
        if not vb.sceneBoundingRect().contains(pos):
            return
        self.want(self.lambda_t.pick(vb.mapSceneToView(pos)), now)

    def want(self, want: dict, now: bool) -> None:
        """now: at once (a press); else the latest wins at the next pass of the event loop (a fast drag reads one
        image per pass, not one per mouse event)."""
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
    def image_refit(self) -> None:
        """The image padlock's right click: the contrast fixed to the image shown now."""
        self.scheduler.fix_levels(True, refit=True)
        self.image_lock.set_closed(True)

    def fit_spectra(self) -> None:
        """Each spectrum plot fitted to this pixel's profile, and kept (the padlock closed)."""
        self.scheduler.fit_y()
        if self.spec_lock is not None:
            self.spec_lock.set_closed(self.scheduler.yrange.fixed)
