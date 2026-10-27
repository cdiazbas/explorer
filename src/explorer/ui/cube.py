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
import os
import sys

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore

from .._name import APP_NAME
from ..core.scheduler import Scheduler
from ..data.axes import unit_text
from ..data.names import card, plane_text, slice_names, unit, value_name
from . import glass
from .cards import CARD, CARD_LIGHT
from .gestures import Gestures
from .imageview import ImageView
from .lambda_t import LambdaTPanel, TimeCurve
from .padlock import PanelLock
from .scalekey import ScaleKey
from .slitpanel import SlitPanel
from .spectra import AxisDrag, SpectraPanel

TAU1 = "τ₅₀₀=1"             # the profile's reference line at ZTAU51, the height of tau(500 nm) = 1
IMAGE_TIP = ("Image contrast: closed = fixed, open = automatic per image. Click to switch; right click fixes it to "
             "this image")
SPEC_TIP = ("Spectra y range: open = automatic, closed = fixed (I from 100 random profiles, Q U V from the whole "
            "image). Click to switch; right click {keys}fixes it to this pixel")


def reticle_colour(look):
    """The reticles': white, in the glass look its accent."""
    return glass.accent() if look.has("glass") else pg.mkColor(255, 255, 255, 235)


def card_colour(look, light: bool):
    """The plots' background: a card in the looks that have them, else pyqtgraph's own."""
    return (CARD_LIGHT if light else CARD) if look.has("cards") else pg.getConfigOption("background")


class CubeSink:
    """The scheduler's results on a cube's own panels (the main cube's adds the window's parts: ui.shell)."""

    def __init__(self, cube: "CubeView"):
        self.cube = cube

    def image(self, idx, img, levels):
        c = self.cube
        s = c.session.member_state(c.k).s
        c.view.set_image(img, levels, gamma=c.gamma_now(), centred=c.session.centred(c.k, s))
        self.cube.paint_colour()

    def spectra(self, spec, pixel, t):
        if self.cube.spectra is not None:
            self.cube.spectra.show(spec)

    def lambda_t(self, lt, pixel, s, levels):
        self.cube.last_s = s
        if self.cube.lambda_t is not None:
            self.cube.lambda_t.show(lt, levels, gamma=self.cube.session.gamma(self.cube.k, s),
                                    centred=self.cube.session.centred(self.cube.k, s))
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

    def noise(self, sigma, t):
        if self.cube.spectra is not None:
            self.cube.spectra.set_noise(sigma)

    def continuum(self, k, text):
        """A linked cube's continuum chosen from its sample: said on the terminal, with its name."""
        print(f"[{APP_NAME}] {self.cube.name}: {text}", file=sys.stderr)

    def grid_image(self, s, idx, img, levels):          # the 2x2 view is the main cube's
        pass

    def slit_path(self, pix):                           # its slit tab's, with a tab per cube (ViewState.slit_tabs)
        if self.cube.slit_panel is not None:
            self.cube.slit_panel.set_path(pix)

    def slit(self, ts, sl, s, ts_levels, sl_levels):
        p = self.cube.slit_panel
        if p is None:
            return
        self.cube.slit_s = s
        p.show(ts, sl, ts_levels, sl_levels, gamma=self.cube.session.gamma(self.cube.k, s),
               centred=self.cube.session.centred(self.cube.k, s))
        cols = self.cube.shell.maps_for(s)
        p.set_lut(cols.lut(s) if cols is not None else None)


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
        # its axis other than t named as data.names says (not lambda unless known to be), the main cube's as a linked
        # one's; the main cube's lambda of several tunings as it always was (None)
        names = slice_names(r, ds.axes, getattr(ds, "path", ""))
        # what one plane shows, for its key: "I" along a lambda, else the quantity ("Blos", "log₁₀(tg)")
        self.value = "I" if names.spectral else value_name(getattr(ds, "path", ""), ds.axes)
        self.slices = names if k or names.mapped or not names.spectral else None
        # a cube without lambda has no spectra; one whose axis is not known to be lambda has them named as its
        # lambda-t and slit are, and its values by what they are when it has no Stokes
        other = self.slices if self.slices is not None and not self.slices.spectral else None
        # that axis's own coordinates when the header gives them (data.axes.header_coords: Bifrost's z in Mm): the
        # profile's x axis, the slider and the status line in them; τ500 = 1 marked on a z in Mm (ZTAU51)
        lead = getattr(ds.axes, "lead_coord", None)
        self.l_coords = lead(r.l) if other is not None and r.l is not None and lead is not None else None
        coords = ref = None
        if self.l_coords is not None and other is not None:
            vals, u = self.l_coords
            coords = (vals, f"{other.axis} [{u}]" if u else other.axis)
            try:
                tau = float(card(ds.axes, "ZTAU51"))
            except ValueError:
                tau = None
            if tau is not None and other.axis == "z" and u == "Mm":
                ref = (tau, TAU1)
        self.spectra = SpectraPanel(max(1, r.ns if r.s is not None else 1), r.nl, ds.axes, light=light,
                                    label=other.label if other else None, planes=r.planes,
                                    value=value_name(getattr(ds, "path", ""), ds.axes) if other else None,
                                    coords=coords, ref=ref) \
            if r.l is not None else None
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
        self.slit_panel: SlitPanel | None = None        # its slit tab's panel (ui.slitpanel), made by the shell
        self.slit_s = 0                                 # the Stokes of the slices it shows
        self.ns, self.planes = r.ns, r.planes           # Stokes, or an inversion's parameters (data.axes.Roles)
        # its Stokes named in the image's top left by something else: the main cube's colour key, which glass puts there
        self.named = False
        self.scheduler: Scheduler                       # made in start(); the padlocks and picks ask it
        # the padlocks, both open at start (the prototype's): closed = fixed, right click = fit to what is shown
        self.image_lock = PanelLock(self.view.widget, IMAGE_TIP, light=light)
        self.image_lock.toggled.connect(lambda on: self.scheduler.fix_levels(on))
        self.image_lock.refit.connect(self.image_refit)
        self.view.over.add(self.image_lock)             # over the image (ui.overlays)
        # its colour key, interactive (ui.scalekey): the main cube's is the window's colour_key, which glass moves
        self.key = ScaleKey(shell, self.view, k, unit_text(unit(ds.axes)))      # BUNIT, else PIXLUNIT
        self.spec_lock: PanelLock | None = None
        if self.spectra is not None:
            self.spec_lock = PanelLock(self.spectra.w, SPEC_TIP.format(keys=keys), light=light, backed=False)
            self.spec_lock.toggled.connect(lambda on: self.scheduler.set_y_fixed(on))
            self.spec_lock.refit.connect(self.fit_spectra)
        self._install_gestures()
        self._off = lambda: None                        # nothing to unsubscribe before start()

    def start(self, sink=None) -> None:
        """Its scheduler (sink: where its results go; its own panels by default), and the state followed from now
        on. Q U V's noise levels are read for its spectra (core.noise: in a cube of 4 Stokes with a continuum)."""
        self.scheduler = Scheduler(self.session, sink if sink is not None else CubeSink(self), member=self.k,
                                   noise=self.spectra is not None)
        self._off = self.session.store.subscribe(self._on_state)
        self.follow(self.session.member_state(self.k), None)

    def close(self) -> None:
        self._off()
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
        if changed is not None and "gamma" in changed:  # an image or lambda-t of another Stokes brings its own
            self.view.set_gamma(self.gamma_now())
            if self.lambda_t is not None:
                self.lambda_t.set_gamma(self.session.gamma(self.k, self.last_s))
        if has("scale", "s", "own"):                    # the padlock says whether its Stokes now is fixed
            self.image_lock.set_closed(self.session.scale(self.k, st.s)[0] == "fixed")
        if changed is not None and changed & {"gamma", "scale", "zero"}:
            self.paint_colour()
            self.key.update()

    def scale_name(self) -> str:
        """The cube as the saved layout names its scale (ui.layout.LayoutStore.save_scale): its file's base name."""
        return os.path.basename(str(getattr(self.dataset, "path", "") or self.name).rstrip("/")) or self.name

    def gamma_now(self) -> float:
        """Its gamma at the Stokes its image shows (Session.gamma)."""
        return self.session.gamma(self.k, self.session.member_state(self.k).s)

    def show_stokes(self, s: int) -> None:
        """The label of Stokes s ("Stokes Q") on its image and its lambda-t (ui.stokeslabel), when it has the four
        Stokes; on the image, not while something else names it there (named). Planes of units of their own (a
        snapshot's variables): its key in plane s's."""
        units = getattr(self.dataset.axes, "plane_units", None)
        if units:
            self.key.unit = unit_text(units[min(s, len(units) - 1)])
            self.key.update()
        self.view.set_stokes(None if self.named else s, self.ns, self.planes)
        if self.lambda_t is not None:
            self.lambda_t.set_stokes(s, self.ns, self.planes)

    # ---------------------------------------------------------------- the look and the theme
    def set_look(self, look, acc, light: bool) -> None:
        """What a look puts on the cube's views (Shell.set_look): the reticle, the marks, the cards; a linked cube's
        colour maps too (the main cube's are the window's, with its colour key)."""
        self.view.set_reticle(look.has("reticle"))
        if self.view.reticle is not None:
            self.view.reticle.set_colour(reticle_colour(look))
        if self.spectra is not None:
            self.spectra.set_marks(acc, light) if look.has("marks") else self.spectra.clear_marks()
            self.spectra.set_noise_style("band" if look.has("band") else "lines")
        if self.lambda_t is not None:
            self.lambda_t.set_marks(acc) if look.has("marks") else self.lambda_t.clear_marks()
        card = card_colour(look, light)
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
        """A linked cube's image and lambda-t in the window's colour maps, by its own Stokes (Shell.maps_for); the
        main cube's are the window's own (Shell._paint_colour, with the colour key)."""
        if not self.k:
            return
        s = self.session.member_state(self.k).s
        cols = self.shell.maps_for(s)
        self.view.set_lut(cols.image_lut(s) if cols is not None else self.view.base_lut)
        if self.lambda_t is not None:
            lt = self.shell.maps_for(self.last_s)
            self.lambda_t.set_lut(lt.lut(self.last_s) if lt is not None else None)
        if self.view._full is not None:                 # its key: its name, its plane, its levels and gamma
            what = plane_text(s, self.ns, self.planes) or (self.value if self.value not in self.name else "")
            name = "   ".join(t for t in (self.name, what) if t)
            self.key.set(name, self.view._lim, cols.lut(s) if cols is not None else self.view.base_lut,
                         cols.maps[s] if cols is not None else None, gamma=self.session.gamma(self.k, s))

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
        self.shell.pointer = self.k                     # the image the gamma keys act on (Shell.step_gamma)
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
        self.session.lock_at(math.floor(p.y()), math.floor(p.x()))

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
