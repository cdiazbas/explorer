"""The window: the image panel, the spectra and lambda-t panels in docks on the right (ROADMAP E4.2-E4.4), the
navigation toolbar (E4.5), a status line and the keys that move through the cube (E3.6). Playback comes in E4.9,
the look in E5, the slit in E7. Linked cubes (E8.1, ui.linked): their images beside the main one, their panels as
tabs beside its panels.

It draws what explorer.core decides and turns input into core actions: the mouse over the image moves the cursor, a
click locks it there and a right click releases it (the prototype's _image_click), a double click shows the whole
image again. The keys, from the prototype's _key_table, in one table (ui.actions: shortcuts, terminal, ? sheet):
- Left / Right: lambda, previous / next tuning; Down / Up: t, previous / next frame (each arrow moves its line the
  way it points: lambda is horizontal on the spectra and lambda-t, t vertical on lambda-t);
- 1..ns: that Stokes, whenever the cube has Stokes (the prototype registered them only when it also had t);
- L: lock or release the cursor; Esc: release it (while a slit is drawn: drop it);
- S: the slit mode on and off, ⌫ or Delete: the slit removed (ui.slit; a click in the mode adds a point to the slit
  instead of locking the cursor). The slit panel (ui.slitpanel) is a tab beside lambda-t from the first S on, in front
  while a slit is drawn and when one is finished, gone with the slit; A / D: the cursor to the previous / next point
  along the slit, locked;
- Ctrl+W close, Ctrl+M minimise, Ctrl+Q quit (Qt reads Ctrl as Cmd on a Mac, where Cmd+Q is the application menu's).
"""
import math
import os
import sys
import time
from typing import TYPE_CHECKING

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from .._name import APP_NAME
from ..core.scheduler import Scheduler
from ..core.session import Session
from ..core.state import ViewState
from ..data.axes import STOKES, unit_text
from ..data.names import cube_names
from ..look import LOOKS, get_look
from ..look.colormaps import ColormapRegistry
from . import docks, glass, icons, pens, style
from .actions import ActionRegistry, KeySheet, mod_key
from .cards import CARD, CARD_LIGHT, MacSeams, Rounder
from .gestures import Gestures
from .imageview import CURSOR_PEN, ImageView
from .lambda_t import LambdaTPanel
from .linked import ImageTitle, LinkedCube, PanelTabs, ViewSync
from .loop import QtLoop
from .overlays import ColourKey
from .padlock import PanelLock
from .slit import SlitHint, SlitTool
from .slitpanel import SlitPanel
from .spectra import AxisDrag, SpectraPanel
from .status import diagnostics_text, pixel_text
from .stokesgrid import StokesGrid
from .toolbar import NavBar

if TYPE_CHECKING:
    from ..platform.display import WindowOps
    from .layout import LayoutStore
    from .termkeys import TerminalKeys
    from .titlebar import TitleBar

MEMORY_S = 1.0                                          # the caches' budget follows the machine's memory (Dataset)
STATUS_INSET = 8            # px each side of the status line: half the rounded corners' 16, its text clear of the curve
GRID_LABEL = 30             # px from the top: the slit's hint below the 2x2 view's Stokes label (stokesgrid, at 6)
SLIT_FLOAT_H = 320          # px: the slit panel floating below lambda-t in glass (the prototype's look_glass.py:615)


class _Follow(QtCore.QObject):
    """The 2x2 view over the image panel keeps its size."""

    def __init__(self, panel: QtWidgets.QWidget, grid: QtWidgets.QWidget):
        super().__init__(grid)
        self.grid = grid
        panel.installEventFilter(self)

    def eventFilter(self, obj, e):
        if e.type() == QtCore.QEvent.Type.Resize:
            self.grid.setGeometry(obj.rect())
        return False


class _Sink:
    """The scheduler's results on screen: the image now; the other panels come in E4 and are kept until then."""

    def __init__(self, shell: "Shell"):
        self.shell = shell

    def image(self, idx, img, levels):
        self.shell.last["image"] = (idx, levels)
        self.shell.view.set_image(img, levels)
        if self.shell.glass is not None:
            self.shell.glass.image_changed()
        self.shell._paint_colour()
        self.shell.update_status()
        self.shell.first_image()

    def spectra(self, spec, pixel, t):
        self.shell.last["spectra"] = (spec, pixel, t)
        if self.shell.spectra is not None:
            self.shell.spectra.show(spec)
        self.shell.update_status()                      # I_c for Q U V in % comes with the spectrum

    def lambda_t(self, lt, pixel, s, levels):
        self.shell.last["lambda_t"] = (lt, pixel, s, levels)
        if self.shell.lambda_t is not None:
            self.shell.lambda_t.show(lt, levels)
            if self.shell.colours is not None and self.shell.look.has("colour"):
                self.shell.lambda_t.set_lut(self.shell.colours.lut(s))

    def cleared(self, pixel):
        self.shell.last.pop("spectra", None)
        self.shell.last.pop("lambda_t", None)
        if self.shell.spectra is not None:
            self.shell.spectra.clear()
        if self.shell.lambda_t is not None:
            self.shell.lambda_t.clear()

    def y_range(self, k, r):
        if self.shell.spectra is not None:
            self.shell.spectra.set_range(k, r)

    def units(self, iscale):
        if self.shell.spectra is not None:
            self.shell.spectra.set_units(iscale)

    def grid_image(self, s, idx, img, levels):
        if self.shell.grid is not None:
            self.shell.grid.set_image(s, img, levels)

    def slit_path(self, pix):
        self.shell.slit_panel.set_path(pix)

    def slit(self, ts, sl, s, ts_levels, sl_levels):
        self.shell.last["slit"] = s
        self.shell.slit_panel.show(ts, sl, ts_levels, sl_levels)
        if self.shell.colours is not None and self.shell.look.has("colour"):
            self.shell.slit_panel.set_lut(self.shell.colours.lut(s))


class Shell(QtWidgets.QMainWindow):
    def __init__(self, dataset, title: str | None = None, t0: float | None = None, look=None, linked=()):
        """t0: perf_counter() when opening started, for the time to the first image. linked: cubes linked to this
        one (data.link has checked them; opened with its executors), shown beside it."""
        super().__init__()
        self.dataset = dataset
        self.images = 1 + len(linked)                   # side by side (ui.docks: the first window's width)
        self.t0 = time.perf_counter() if t0 is None else t0
        self.first_image_s: float | None = None
        self.breakdown: tuple | None = None
        self._after_first: list = []
        self.loop = QtLoop(self)
        self.session = Session(self.loop, dataset)
        members = [self.session.add(ds) for ds in linked]
        ex = dataset.executors
        light = style.is_light()                        # the theme the application was given (ui.style)
        self.look = look if look is not None else get_look()
        self.view = ImageView(on_hover=self._hover, strips=ex.strips, parts=ex.n_strips, light=light)
        self.setCentralWidget(docks.gutter(self.view.widget))
        # the slit (S): drawn on the image, the finished one the session's path (ui.slit)
        self.slit_hint = SlitHint(self.view.widget, light=light)
        self.slit_tool = SlitTool(self.session, self.view, self.slit_hint, CURSOR_PEN.color())
        self.slit_tool.modeChanged.connect(self._slit_mode_changed)
        r = dataset.roles
        # a cube without lambda has no spectra: that dock stays empty and hidden
        self.spectra = SpectraPanel(max(1, r.ns if r.s is not None else 1), r.nl, dataset.axes, light=light) \
            if r.l is not None else None
        self.spec_panel = self.spectra.widget if self.spectra is not None else QtWidgets.QWidget()
        # lambda-t needs both t and lambda
        self.lambda_t = LambdaTPanel(r.nt, r.nl, dataset.axes) if r.t is not None and r.l is not None else None
        self.lt_panel = self.lambda_t.widget if self.lambda_t is not None else QtWidgets.QWidget()
        # linked cubes: their images beside this one, their panels a tab each in these (ui.linked)
        self._closing = False
        names = cube_names([dataset, *linked])
        self.linked = [LinkedCube(self, k, name) for k, name in zip(members, names[1:], strict=True)]
        self.spec_tabs = self._tabs(names[0], "spectra", self.spectra, self.spec_panel)
        self.lt_tabs = self._tabs(names[0], "lambda_t", self.lambda_t, self.lt_panel)
        self.spec_dock = docks.dock(self, "Spectrum", self.spec_tabs or self.spec_panel, "spectrum")
        self.lt_dock = docks.dock(self, "λ–t", self.lt_tabs or self.lt_panel, "lambda_t")
        # the slit's slices: lambda-t's tab, there from the first S on and only with a slit or one being drawn
        # (_slit_tab; the prototype's 1046-1052)
        self.slit_panel = SlitPanel(r.nt, r.nl, dataset.axes)
        slit_dock = docks.dock(self, "Slit", self.slit_panel.widget, "slit", cls=docks.GatedDock)
        assert isinstance(slit_dock, docks.GatedDock)
        self.slit_dock = slit_dock
        # lambda-t's tab from the start, as the prototype makes it (1047): its first show as a third panel resized
        # the spectra and back, and their ResizeFreezer's grab cost the first slit ~40 ms
        self.tabifyDockWidget(self.lt_dock, self.slit_dock)
        self.slit_dock.hide()
        self.slit_dock.allowed = lambda: self.session.state.path is not None or self.slit_tool.mode
        self.slit_dock.toggleViewAction().setEnabled(False)
        self.image_title: ImageTitle | None = None
        if self.linked:
            # the linked images as panels between this image and the spectra, in order; this one with the same title
            # above it (its own name), so that docked they are one size
            H, V = QtCore.Qt.Orientation.Horizontal, QtCore.Qt.Orientation.Vertical
            self.splitDockWidget(self.linked[0].dock, self.spec_dock, H)
            self.splitDockWidget(self.spec_dock, self.lt_dock, V)
            for a, b in zip(self.linked, self.linked[1:], strict=False):
                self.splitDockWidget(a.dock, b.dock, H)
            box = self.centralWidget()
            assert box is not None
            lay = box.layout()
            assert isinstance(lay, QtWidgets.QVBoxLayout)      # docks.gutter's
            self.image_title = ImageTitle(names[0], parent=box)
            self.image_title.setToolTip(os.path.basename(str(getattr(dataset, "path", ""))))
            lay.insertWidget(0, self.image_title)
            # as a panel's: the title at the top, then the gutter, then the image (inside the gutter the name sat
            # 5 px lower than the linked images' titles)
            g = docks.PANEL_GUTTER
            lay.setContentsMargins(g, 0, g, g)
            lay.setSpacing(g)
            self._view_sync = ViewSync([self.view] + [c.view for c in self.linked], self)
            for c in self.linked:                       # the slit on every image, drawn on any of them (as the
                self.slit_tool.attach(c.view)           # 2x2 view's panels)
        self.setAnimated(False)
        self.nav = NavBar(self)
        # playback: t forward at the toolbar's rate, round the end (the prototype's _toggle_play, _play_step)
        self._play = QtCore.QTimer(self)
        self._play.timeout.connect(self._play_step)
        self._fps: list[float] = []
        self.nav.play.toggled.connect(self.set_playing)
        self.nav.fps.valueChanged.connect(lambda v: self._play.setInterval(int(1000 / v)))
        self._play.setInterval(int(1000 / self.nav.fps.value()))
        self.scheduler: Scheduler                       # made below, once the panels are; the padlocks ask it
        # the padlocks, both open at start (the prototype's): closed = fixed, right click = fit to what is shown
        self.image_lock = PanelLock(self.view.widget, "Image contrast: closed = fixed, open = automatic per image. "
                                    "Click to switch; right click fixes it to this image", light=light)
        self.image_lock.toggled.connect(lambda on: self.scheduler.fix_levels(on))
        self.image_lock.refit.connect(self._image_refit)
        self.spec_lock = None
        if self.spectra is not None:
            self.spec_lock = PanelLock(self.spectra.w, "Spectra y range: open = automatic, closed = fixed (I from "
                                       "100 random profiles, Q U V from the whole image). Click to switch; right click "
                                       "(or F) fixes it to this pixel", light=light, backed=False)
            self.spec_lock.toggled.connect(lambda on: self.scheduler.set_y_fixed(on))
            self.spec_lock.refit.connect(self.fit_spectra)
        # set by whoever shows the window (ui.app): the saved layout (not `layout`: that is QWidget.layout(), which it
        # hid), its WindowOps (zoom state for the layout), our title bar, the keys read from the terminal
        self.layout_store: LayoutStore | None = None
        self.theme: str | None = None                   # the one applied (ui.app.start, set_theme): kept at the close
        self.window_ops: WindowOps | None = None
        self.title_bar: TitleBar | None = None
        self.terminal_keys: TerminalKeys | None = None
        # a tab behind is moved off screen, not hidden: isVisible() says True for both (Qt 6.11, offscreen), and
        # visibilityChanged follows the tab in front (the prototype's 1049-1052)
        for d, panel in ((self.spec_dock, "spectra"), (self.lt_dock, "lambda_t"), (self.slit_dock, "slit")):
            d.visibilityChanged.connect(lambda on, panel=panel: self._panel_shown(panel, on))
        self.status = QtWidgets.QLabel()
        self.status.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.statusBar().setContentsMargins(STATUS_INSET, 0, STATUS_INSET, 0)
        self.statusBar().addWidget(self.status, 1)
        self.sys_status = QtWidgets.QLabel()
        self.statusBar().addPermanentWidget(self.sys_status)
        self.diagnostics = False
        self.sys_status.hide()
        self.last: dict = {}
        self.setWindowTitle(title or str(getattr(dataset, "path", "")))
        self.view.widget.scene().sigMouseClicked.connect(self._click)
        self._keys()
        self._install_gestures()
        # what the sink reads, before the scheduler: an image already in the cache (a second window on the same
        # Dataset) is shown inside Scheduler()
        self.colours: ColormapRegistry | None = None    # made the first time the look has colour
        self.colour_key: ColourKey | None = None
        self.grid: StokesGrid | None = None             # the 2x2 view (ui.stokesgrid), made the first time it is asked
        self.glass: glass.GlassChrome | None = None     # the glass look's chrome (ui.glass), while worn
        self._seams: MacSeams | None = None
        self._shown_lut = object()
        self._off = self.session.store.subscribe(self._on_state)
        self.scheduler = Scheduler(self.session, _Sink(self))
        for c in self.linked:
            c.start()
        st = self.session.state
        self.view.set_crosshair(*st.cursor)
        if self.spectra is not None:
            self.spectra.set_lambda(st.l)
        elif self.spec_tabs is None:
            self.spec_dock.hide()
        if self.lambda_t is not None:
            self.lambda_t.set_markers(st.t, st.l)
        elif self.lt_tabs is None:
            self.lt_dock.hide()
        self.slit_panel.set_markers(st.t, st.l)
        self.slit_panel.set_cursor(*st.cursor)
        self._mem = QtCore.QTimer(self)
        self._mem.setInterval(int(MEMORY_S * 1000))
        self._mem.timeout.connect(self._memory)
        self._mem.start()
        self._initial_state = self.saveState()          # before the first show: reset_panels comes back to it
        self._sized = False
        self._ratio_followed = False
        style.separators(self)                          # 8 px to grab between the docked panels, with the theme
        panels = [self.view.widget] + [p for p in (self.spec_panel, self.lt_panel, self.slit_panel.w) if p is not None]
        self._rounders = [Rounder(w) for w in panels]   # 6-px corners on the panels, in both looks
        self.set_look(self.look)

    # ---------------------------------------------------------------- the look (look.Look; the prototype's app/look.py)
    def set_look(self, look) -> None:
        """Wear look (look.Look): every part put on or taken off, so the window can switch while it runs (M). The
        colour maps chosen with C stay for the next time the colour part is on."""
        if self.glass is not None and not look.has("glass"):   # out of glass first: it gives back what it took
            self.glass.remove()
            self.glass = None
            self._slit_dock_again()
            QtCore.QTimer.singleShot(0, self._slit_dock_again)    # after glass restores the panels once more
        self.look, L = look, look
        light = style.is_light()
        st = QtWidgets.QApplication.style()
        acc = glass.accent() if L.has("glass") else style.accent()
        if hasattr(st, "SLIDER"):                       # the sliders in the colour of the markers they move
            st.SLIDER = acc if L.has("glass") else None if L.has("marks") else CURSOR_PEN.color()
            for sl in self.nav.sliders.values():
                sl.update()
        self.view.set_reticle(L.has("reticle"))
        if self.grid is not None:
            self.grid.set_reticle(L.has("reticle"))
        self.nav.set_stokes_drop(L.has("stokes"))
        self._reticle_colours()
        if self.spectra is not None:
            self.spectra.set_marks(acc, light) if L.has("marks") else self.spectra.clear_marks()
        if self.lambda_t is not None:
            self.lambda_t.set_marks(acc) if L.has("marks") else self.lambda_t.clear_marks()
        self.slit_panel.set_marks(acc) if L.has("marks") else self.slit_panel.clear_marks()
        if L.has("colour") and self.colours is None:
            self.colours = ColormapRegistry(self.session.sizes["s"] if self.session.present["s"] else 1, light)
            self.colour_key = ColourKey(self.view.widget, unit_text(getattr(self.dataset.axes, "bunit", None) or ""))
        if self.colour_key is not None:
            self.colour_key.show_with(L.has("colour"), grid=self.grid is not None and not self.grid.isHidden())
        self._shown_lut = object()
        if L.has("colour"):
            self._paint_colour()
        else:
            self.view.set_lut(self.view.base_lut)
        self._grid_luts()
        if self.lambda_t is not None:
            lt = self.last.get("lambda_t")
            cols = self.colours if L.has("colour") else None
            self.lambda_t.set_lut(cols.lut(lt[2]) if cols is not None and lt is not None else None)
        cols = self.colours if L.has("colour") else None
        self.slit_panel.set_lut(cols.lut(self.last.get("slit", self.session.state.s)) if cols is not None else None)
        if st.name() == "macos" and self._seams is None:   # the native style's light lines under the panel titles
            self._seams = MacSeams()                    # and on the separators: in the window's colour, in both looks
            for w in (self, self.spec_dock, self.lt_dock, self.slit_dock):
                w.setStyle(self._seams)
        card = (CARD_LIGHT if light else CARD) if L.has("cards") else pg.getConfigOption("background")
        for pw in (getattr(self.spectra, "w", None), getattr(self.lambda_t, "w", None), self.slit_panel.w):
            if pw is not None and self.glass is None:   # worn, glass keeps them clear over its slabs
                pw.setBackground(card)
        if L.has("glass") and self.glass is None:       # its own parts last, over the modern look's (ui.glass); the
            self.glass = glass.GlassChrome(self)        # slit's panel, if shown, among the panels it floats
            self.glass.apply()
        # the slit in the markers' colour: the cursor's in the classic look (the prototype's _slit_style, 1733)
        self.slit_tool.set_colour(acc if L.has("marks") or L.has("glass") else CURSOR_PEN.color())
        self._place_slit_hint()
        for c in self.linked:
            c.set_look(L, acc, light)

    # ---------------------------------------------------------------- the theme (ui.style), while the window runs
    def set_theme(self, theme: str) -> None:
        """dark or light (style.apply_theme) while the window runs (T): the application's style and palette, and
        every part that took the theme when it was made, given the new one. The look stays as worn; glass in place,
        its panels where they are and the image's region kept."""
        app = QtWidgets.QApplication.instance()
        if self._seams is not None:                     # off a Mac's native style: its seams go with it
            for w in (self, self.spec_dock, self.lt_dock, self.slit_dock):
                w.setStyle(None)  # type: ignore[arg-type]  # None: the application's style again
            self._seams = None
        self.theme = style.apply_theme(app, theme)
        style.separators(self)
        light = style.is_light()
        self.view.set_light(light)
        self.slit_tool.set_light(light)
        if self.grid is not None:
            self.grid.set_light(light)
        for lock in (self.image_lock, self.spec_lock):
            if lock is not None:
                lock.set_light(light)
        if self.spectra is not None:
            self.spectra.set_light(light)
        if self.lambda_t is not None:
            self.lambda_t.set_light(light)
        self.slit_panel.set_light(light)
        for c in self.linked:
            c.set_light(light)
        if self.colours is not None:
            self.colours.set_light(light)
        self.nav.restyle()
        self.sheet.setText(self.action_registry.sheet_html(self.palette()))
        self.set_look(self.look)                        # marks, cards and colour maps in the new theme
        if self.glass is not None:
            self.glass.retheme()
        if self.colour_key is not None:
            self.colour_key.update()

    def toggle_theme(self) -> None:
        """T: dark and light in turn; from a Mac's native theme, the other of the two."""
        self.set_theme("dark" if style.is_light() else "light")
        self.statusBar().showMessage(f"{'light' if style.is_light() else 'dark'} theme (T switches)", 3000)

    def _reticle_colours(self) -> None:
        """The reticles white, in the glass look its accent; the 2x2 view's too, whenever it is made."""
        c = glass.accent() if self.look.has("glass") else QtGui.QColor(255, 255, 255, 235)
        for v in [self.view] + (self.grid.views if self.grid is not None else []):
            if v.reticle is not None:
                v.reticle.set_colour(c)

    # ---------------------------------------------------------------- the 2x2 view (ROADMAP E5.11)
    def set_grid(self, on: bool) -> None:
        """I Q U V side by side over the image (ui.stokesgrid), or the single view back: the region in view goes
        with it either way. Key 5, and All in the Stokes control; 1-4, or a Stokes picked there, leave it. Only with
        more than one Stokes. From the prototype's app/look_glass.py set_grid (600-614)."""
        ns = self.session.sizes["s"] if self.session.present["s"] else 1
        on = bool(on) and ns > 1
        if on == (self.grid is not None and self.grid.isVisible()):
            return
        if on:
            if self.grid is None:
                ex = self.dataset.executors
                self.grid = StokesGrid(self.view.widget, ns, self._hover, self._grid_click, light=style.is_light(),
                                       strips=ex.strips, parts=ex.n_strips)
                self.grid.set_reticle(self.look.has("reticle"))
                self._reticle_colours()
                self._grid_follow = _Follow(self.view.widget, self.grid)
                for v in self.grid.views:               # the slit on the four, drawn on any of them
                    self.slit_tool.attach(v)
            self.grid.setGeometry(self.view.widget.rect())
            self.grid.set_region(self.view.vb.viewRect())
            st = self.session.state
            self.grid.set_crosshair(*st.cursor)
            self.grid.set_locked(st.locked)
            self._grid_luts()
            self.grid.show()
            self.grid.raise_()
            for w in (self.image_lock, self.slit_hint):  # the padlock and the hint stay on top
                if w is not None:
                    w.raise_()
            self.scheduler.set_grid(True)
            self.view.set_paused(True)                  # under the 2x2 view: nothing of it is seen
        elif self.grid is not None:                     # shown: on == visible returned above
            self.view.vb.setRange(self.grid.region(), padding=0)
            self.grid.hide()
            self.scheduler.set_grid(False)
            self.view.set_paused(False)
        if self.colour_key is not None:                 # no single Stokes' key over the four panels
            self.colour_key.show_with(self.look.has("colour"), grid=on)
        self.nav.set_all(on)
        self._place_slit_hint()
        if self.glass is not None:
            self.glass.grid_changed(on)

    def toggle_grid(self) -> None:
        self.set_grid(not (self.grid is not None and self.grid.isVisible()))

    def pick_stokes(self, s: int) -> None:
        """One Stokes in the image (keys 1-4, the Stokes control): the 2x2 view, if on, gives way."""
        self.set_grid(False)
        self.session.set_index("s", s)

    def _grid_luts(self) -> None:
        if self.grid is None:
            return
        cols = self.colours if self.look.has("colour") else None
        for s in range(len(self.grid.views)):
            self.grid.set_lut(s, cols.image_lut(s) if cols is not None else None)

    def _grid_click(self, s: int, ev) -> None:
        """A click on panel s: the cursor locked there and that Stokes the session's, so lambda-t shows it; right
        click: released; double click: the whole image."""
        if self.grid is None or self.slit_tool.click(ev, self.grid.views[s].vb):
            return
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            self.session.lock(False)
            return
        p = self.grid.panel_point(s, ev)
        if ev.button() != QtCore.Qt.MouseButton.LeftButton or p is None:
            return
        if ev.double():
            self.grid.show_all()
            return
        self.session.lock(False)
        self.session.hover(math.floor(p[0]), math.floor(p[1]))
        self.session.set_index("s", s)
        self.session.lock(True)

    def toggle_look(self) -> None:
        """M: classic, modern and glass in turn."""
        nxt = LOOKS[(LOOKS.index(self.look.name) + 1) % len(LOOKS)]
        self.set_look(get_look(nxt))
        self.statusBar().showMessage(f"{self.look.name} look (M switches)", 3000)

    def toggle_panels(self) -> None:
        """I: every panel hidden, or shown again (the glass look's; its panels float beside the window)."""
        if self.glass is None:
            self.statusBar().showMessage("I: the glass look's (M)", 3000)
            return
        self.glass.toggle_panels()

    def _paint_colour(self) -> None:
        """The image's colour table and the key, for the Stokes shown (the modern look's colour part)."""
        if self.colours is None or not self.look.has("colour"):
            return
        for c in self.linked:                           # a linked cube with the main cube's Stokes
            c.paint_colour()
        s = self.session.state.s
        tab = self.colours.image_lut(s)
        if tab is not self._shown_lut:
            self.view.set_lut(tab)
            self._shown_lut = tab
        last = self.last.get("image")
        if self.colour_key is not None and last is not None:
            ns = self.session.sizes["s"] if self.session.present["s"] else 1
            self.colour_key.set(STOKES[s] if ns > 1 else "I", last[1], self.colours.lut(s), self.colours.maps[s])

    def cycle_colours(self, step: int) -> None:
        """C / Shift+C: the next or previous map for the Stokes shown; image, lambda-t and key follow, nothing is
        read again. Only in a look with the colour maps (the modern one)."""
        if self.colours is None or not self.look.has("cmap"):
            self.statusBar().showMessage("colour maps: the modern look (M)", 3000)
            return
        s = self.session.state.s
        name = self.colours.cycle(s, step)
        self._shown_lut = object()
        self._paint_colour()
        self._grid_luts()                               # the 2x2 view's panel of that Stokes too
        if self.lambda_t is not None:
            self.lambda_t.set_lut(self.colours.lut(s))
        self.slit_panel.set_lut(self.colours.lut(s))
        if self.colour_key is not None:
            self.colour_key.flash(name)

    # ---------------------------------------------------------------- panels
    def _panel_shown(self, panel: str, on: bool) -> None:
        """A dock shown, closed or hidden: the core reads nothing for a hidden panel, and fills a shown one; with
        linked cubes, only for the tab in front (PanelTabs)."""
        tabs = {"spectra": self.spec_tabs, "lambda_t": self.lt_tabs}.get(panel)
        if tabs is not None:
            tabs.set_shown(on)
        elif not self._closing:
            self.session.show(panel, on)

    def _tabs(self, name: str, key: str, own, widget) -> PanelTabs | None:
        """A panel's tabs, one per cube that has it (a map has no spectra), when a linked cube has it; else None."""
        others = [(c.name, getattr(c, key).widget, f"{key}:{c.k}") for c in self.linked if getattr(c, key) is not None]
        if not others:
            return None
        tabs = PanelTabs(self.session, ([(name, widget, key)] if own is not None else []) + others,
                         closing=lambda: self._closing)
        files = ([self.dataset] if own is not None else []) + [c.dataset for c in self.linked
                                                                 if getattr(c, key) is not None]
        for i, ds in enumerate(files):                 # the whole file name, under a short tab name
            tabs.setTabToolTip(i, os.path.basename(str(getattr(ds, "path", ""))))
        return tabs

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        if self.glass is None or not self.glass.on:     # the glass bar lays its sliders out itself
            self.nav.fit(self.width())

    def showEvent(self, ev) -> None:
        super().showEvent(ev)
        if not self._ratio_followed:                    # the plots' line widths at this screen's ratio (ui.pens)
            self._ratio_followed = True
            pens.follow(self)
        if not self._sized:                             # the fresh start's sizes, once the layout exists
            self._sized = True
            QtCore.QTimer.singleShot(0, self.reset_sizes)

    def reset_sizes(self) -> None:
        docks.reset_sizes(self, (self.spec_dock, self.lt_dock), self.images)
        self.same_image_widths()

    def same_image_widths(self) -> None:
        """The docked linked images and the main one one width: theirs and the main one's shared out (Qt keeps a
        panel's width when the window changes, and the main image took all the change: 80 px against 527 in glass)."""
        imgs = [c.dock for c in self.linked if c.dock.isVisible() and not c.dock.isFloating()]
        cw = self.centralWidget()
        lay = QtWidgets.QMainWindow.layout(self)
        if imgs and cw is not None and lay is not None:
            # the widths as Qt has them after the last resizeDocks (the spectra's, in reset_sizes): read before, the
            # main image came out 223 px against 362 for each linked one
            lay.activate()
            each = (cw.width() + sum(d.width() for d in imgs)) // (len(imgs) + 1)
            self.resizeDocks(imgs, [each] * len(imgs), QtCore.Qt.Orientation.Horizontal)

    def reset_panels(self) -> None:
        """Every panel docked where it started and shown, and the whole image in view again (the prototype's
        reset_panels: one button brings everything back). In the glass look its panels float, placed again."""
        if self.glass is not None:
            self.glass.reset()
            self.statusBar().showMessage("panels and zoom back to the start", 4000)
            return
        for d in (self.spec_dock, self.lt_dock, self.slit_dock, *(c.dock for c in self.linked)):
            d.setFloating(False)
        self.restoreState(self._initial_state)
        for d in (self.spec_dock, self.lt_dock, *(c.dock for c in self.linked)):
            if d.isHidden():
                d.show()
        if self.slit_dock.allowed():                    # the slit's tab only with a slit, or one being drawn (the
            self._slit_tab(True)                        # prototype's 2536); in front while drawn, its slices live
            if self.slit_tool.mode:
                self.slit_dock.raise_()
        self.reset_sizes()
        QtCore.QTimer.singleShot(0, self.reset_sizes)     # again once the layout has settled
        self.reset_view()
        self.statusBar().showMessage("panels and zoom back to the start", 4000)

    # ---------------------------------------------------------------- picks on the panels
    def _install_gestures(self) -> None:
        """Click or drag picks on the spectra (lambda) and on lambda-t (t and lambda); a right click on either
        releases the cursor; each panel's pointer names what it does."""
        C = QtCore.Qt.CursorShape
        self._wanted: dict = {}
        self._pick_timer = QtCore.QTimer(self, singleShot=True, interval=0)
        self._pick_timer.timeout.connect(self._pick_flush)
        picks = {}
        if self.spectra is not None:
            vp = self.spectra.w.viewport()
            vp.setCursor(C.SizeHorCursor)
            picks[vp] = self._spectrum_pick
            self.spectra.w.scene().sigMouseClicked.connect(self._panel_click)
        if self.lambda_t is not None:
            vp = self.lambda_t.w.viewport()
            vp.setCursor(C.SizeAllCursor)
            picks[vp] = self._lt_pick
            self.lambda_t.w.scene().sigMouseClicked.connect(self._panel_click)
        vp = self.slit_panel.w.viewport()               # picks two things, as lambda-t (the prototype's 1975)
        vp.setCursor(C.SizeAllCursor)
        picks[vp] = self._slit_pick
        self.slit_panel.w.scene().sigMouseClicked.connect(self._panel_click)
        # no context menus: a right click releases the cursor, nothing else. pyqtgraph's on the image, and
        # QMainWindow's (toolbar and docks on/off) over the toolbar, the dock titles and the sliders; an open one
        # also left the next keys unanswered (the prototype's app/viewer.py:1018-1028)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        self.view.vb.setMenuEnabled(False)
        image = self.view.widget.viewport()
        image.setCursor(C.CrossCursor)
        self._gestures = Gestures(self, picks, image)
        for vp in [*picks, image]:
            vp.installEventFilter(self._gestures)
        if self.spectra is not None:                    # after the gestures: the y axis strip first (E4.1)
            self._axis_drag = AxisDrag(self.spectra, self.scheduler_y_manual, self.scheduler_y_auto)

    def scheduler_y_manual(self, k: int, r) -> None:
        if r[1] > r[0]:
            self.scheduler.set_y_manual(k, r)

    def scheduler_y_auto(self, k: int) -> None:
        self.scheduler.y_auto(k)

    def _panel_click(self, ev) -> None:
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            self.session.lock(False)                    # the right click releases from any panel

    def _spectrum_pick(self, pos, now: bool = True) -> None:
        """lambda nearest to x on whichever spectrum plot is under pos."""
        if self.spectra is None:
            return
        for p in self.spectra.plots:
            if p.vb.sceneBoundingRect().contains(pos):
                xv = p.vb.mapSceneToView(pos).x()
                self._want_pick({"l": int(np.argmin(np.abs(self.spectra.xl - xv)))}, now)
                return

    def _lt_pick(self, pos, now: bool = True) -> None:
        """(t, lambda) of the cell under pos on lambda-t."""
        if self.lambda_t is None:
            return
        vb = self.lambda_t.w.getPlotItem().vb
        if not vb.sceneBoundingRect().contains(pos):
            return
        q = vb.mapSceneToView(pos)
        self._want_pick({"l": int(np.clip(int(q.x()), 0, self.lambda_t.nl - 1)),
                         "t": int(np.clip(int(q.y()), 0, self.lambda_t.nt - 1))}, now)

    def _slit_pick(self, pos, now: bool = True) -> None:
        """A click or drag on the slit panel: the cursor to that point of the slit, locked there as a click on the image
        does, and t (time slice) or lambda (spectral slice) from y (the prototype's _slit_pick, 1932)."""
        hit = self.slit_panel.point_at(pos)
        if hit is None or self.slit_panel.pix is None:
            return
        i, axis, v = hit
        iy, ix = self.slit_panel.pix
        self.session.lock(False)
        self.session.hover(int(iy[i]), int(ix[i]))
        self.session.lock(True)
        if self.session.present[axis]:
            self._want_pick({axis: v}, now)

    def _want_pick(self, want: dict, now: bool) -> None:
        """now: at once (a press); else the latest wins at the next pass of the event loop (a fast drag reads one
        image per pass, not one per mouse event)."""
        if now:
            for axis, v in want.items():
                self.session.set_index(axis, v)
            return
        self._wanted.update(want)
        self._pick_timer.start()

    def _pick_flush(self) -> None:
        want, self._wanted = self._wanted, {}
        for axis, v in want.items():
            self.session.set_index(axis, v)

    # ---------------------------------------------------------------- playback
    def set_playing(self, on: bool) -> None:
        self.session.set_playing(on)
        self._fps = []
        (self._play.start if on else self._play.stop)()
        self.nav.play.setIcon(icons.glyph_icon("pause" if on else "play", self.nav.play))
        if self.nav.play.isChecked() != on:
            self.nav.play.setChecked(on)

    def _play_step(self) -> None:
        self.session.step("t", 1, wrap=True)
        self._fps.append(time.perf_counter())
        self._fps = self._fps[-30:]

    def played_fps(self) -> float | None:
        """The rate actually shown over the last steps (30 at most); None before three."""
        f = self._fps
        return (len(f) - 1) / (f[-1] - f[0]) if len(f) > 2 and f[-1] > f[0] else None

    def start_link_probe(self, link) -> None:
        """Over a remote X display: the link measured in the background 1.5 s after start (so it does not compete
        with the start-up's traffic), and the default rate set to 60 % of it over one image, unless the rate was
        already changed; the prototype's start_link_probe. link: the Display's LinkInfo (bytes per image pixel,
        the rate not to go above)."""
        import threading

        from ..platform import linkprobe

        res, default = {}, self.nav.fps.value()

        def run():
            try:
                res.update(linkprobe.measure())
            except Exception as e:                      # the display refused a second connection...: keep it
                res["error"] = str(e)

        th = threading.Thread(target=run, daemon=True, name="linkprobe")

        def apply():
            if th.is_alive():
                QtCore.QTimer.singleShot(100, apply)
                return
            if "MBps" not in res:
                print(f"[{APP_NAME}] link probe skipped: {res.get('error')}", file=sys.stderr)
                return
            cw = self.centralWidget()
            if cw is None:
                return
            fps = linkprobe.suggest_fps(res["MBps"], link.bytes_per_px * cw.width() * cw.height(), hi=link.fps_cap)
            if self.nav.fps.value() == default:
                self.nav.fps.setValue(fps)
            msg = f"X11 link ~{res['MBps']:.0f} MB/s, round trip {res['rtt_ms']:.1f} ms: playback at {fps} fps"
            self.statusBar().showMessage(msg, 10000)
            print(f"[{APP_NAME}] {msg}", file=sys.stderr)

        def start():
            th.start()
            QtCore.QTimer.singleShot(100, apply)

        QtCore.QTimer.singleShot(1500, start)

    def _image_refit(self) -> None:
        """The image padlock's right click: the contrast fixed to the image shown now."""
        self.scheduler.fix_levels(True, refit=True)
        self.image_lock.set_closed(True)

    def fit_spectra(self) -> None:
        """F, or the spectra padlock's right click: each plot fitted to this pixel's profile, and kept (closed)."""
        self.scheduler.fit_y()
        if self.spec_lock is not None:
            self.spec_lock.set_closed(self.scheduler.yrange.fixed)

    def spectra_to_sample(self) -> None:
        """Shift+F: back to the sample's ranges, fixed (as closing the padlock)."""
        self.scheduler.y_to_sample()
        if self.spec_lock is not None:
            self.spec_lock.set_closed(self.scheduler.yrange.fixed)

    def reset_view(self) -> None:
        """The whole image, the spectra's whole lambda range, and their y ranges as the padlock says: the sample's
        when closed, this pixel's when open (the prototype's reset_view)."""
        self.view.show_all()
        if self.spectra is not None:
            self.spectra.reset_view()
            self.scheduler.yrange.reset()
        if self.lambda_t is not None:
            self.lambda_t.reset_view()
        for c in self.linked:
            c.reset_view()

    # ---------------------------------------------------------------- input
    def _hover(self, y: float, x: float) -> None:
        self.session.hover(math.floor(y), math.floor(x))
        self.slit_tool.hover(y, x)

    def _click(self, ev) -> None:
        if self.slit_tool.click(ev, self.view.vb):     # drawing a slit: the click adds or removes a point
            return
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            self.session.lock(False)
            return
        if ev.button() != QtCore.Qt.MouseButton.LeftButton or not self.view.vb.sceneBoundingRect().contains(
                ev.scenePos()):
            return
        if ev.double():
            self.view.show_all()
            return
        p = self.view.vb.mapSceneToView(ev.scenePos())
        self.session.lock(False)                        # move there, then lock
        self.session.hover(math.floor(p.y()), math.floor(p.x()))
        self.session.lock(True)

    def key_table(self):
        """(keys as shown, what they do, ((key sequence, action), ...)) for this cube: the shortcuts, the terminal's
        keys and the ? sheet all come from it (ui.actions)."""
        K, s = QtCore.Qt.Key, self.session
        mod = mod_key()
        rows: list[tuple[str, str, tuple]] = []
        if s.present["l"]:
            rows.append(("← →", "λ: previous, next tuning",
                         ((K.Key_Left, lambda: s.step("l", -1)), (K.Key_Right, lambda: s.step("l", 1)))))
        if s.present["t"]:
            rows.append(("↓ ↑", "t: previous, next frame",
                         ((K.Key_Down, lambda: s.step("t", -1)), (K.Key_Up, lambda: s.step("t", 1)))))
        if s.present["s"] and s.sizes["s"] > 1:
            n = s.sizes["s"]
            rows.append((f"1–{n}", "Stokes " + " ".join(STOKES[:n]),
                         tuple((str(k + 1), lambda k=k: self.pick_stokes(k)) for k in range(n))))
            rows.append((str(n + 1), " ".join(STOKES[:n]) + " side by side, zoom linked; again: one Stokes",
                         ((str(n + 1), self.toggle_grid),)))
        if s.present["t"] and s.sizes["t"] > 1:
            rows.append(("Space", "play, pause t", ((K.Key_Space, lambda: self.nav.play.toggle()),)))
        rows.append(("L", "lock, release the cursor", ((K.Key_L, lambda: s.lock(not s.state.locked)),)))
        # A and D walk along the slit: the left hand on them, the right on the mouse (the prototype's 1324-1327, F75)
        rows += [("S", "draw a slit on the image (again: cancel)", ((K.Key_S, self.toggle_slit_mode),)),
                 ("\u232b", "remove the slit", ((K.Key_Backspace, self.clear_slit), (K.Key_Delete, self.clear_slit))),
                 ("A  D", "along the slit: previous, next point (the cursor locked there)",
                  ((K.Key_A, lambda: self.slit_step(-1)), (K.Key_D, lambda: self.slit_step(1))))]
        if self.spectra is not None:
            rows += [("F", "spectra: fit y to this pixel, and keep it", ((K.Key_F, self.fit_spectra),)),
                     ("\u21e7F", "spectra: fixed range (I: 100 random profiles; Q U V: the whole image)",
                      (("Shift+F", self.spectra_to_sample),))]
        # always bound: the terminal's keys are read once, and the look can change while the window runs
        rows += [("M", "look: classic \u2192 modern \u2192 glass", ((K.Key_M, self.toggle_look),)),
                 ("T", "theme: dark \u21c4 light", ((K.Key_T, self.toggle_theme),)),
                 ("I", "panels: hide all, show again (glass look)", ((K.Key_I, self.toggle_panels),)),
                 ("C  \u21e7C", "colours: next, previous map for the Stokes shown (modern look)",
                  (("C", lambda: self.cycle_colours(1)), ("Shift+C", lambda: self.cycle_colours(-1))))]
        rows += [("Esc", "release the cursor; while a slit is drawn, cancel it (first closes this sheet)",
                  ((K.Key_Escape, self._escape),)),
                 (mod + "W", "close the window", (("Ctrl+W", self.close),)),
                 (mod + "M", "minimise", (("Ctrl+M", self.showMinimized),)),
                 # on a Mac the application menu's own, which closes through closeEvent and keeps the layout
                 (mod + "Q", "quit", () if sys.platform == "darwin" else (("Ctrl+Q", self.close),)),
                 ("F12", "the cube, storage and memory in the status bar",
                  ((K.Key_F12, lambda: self.set_diagnostics(not self.diagnostics)),)),
                 # "?" alone misses Shift+/ on the offscreen platform, so through the X11 bridge
                 ("?", "this sheet", (("?", self.toggle_sheet), ("Shift+?", self.toggle_sheet)))]
        return rows

    def mouse_table(self):
        """(gesture, what it does) for the ? sheet; the handlers are ui.gestures and _click."""
        rows = [("click on the image", "lock the cursor there"), ("right click on the image", "release it"),
                ("S, then click on the image", "slit: a point per click; double click ends it, right click removes "
                                               "the last point, Esc cancels")]
        if self.spectra is not None:
            rows += [("click on a spectrum", "pick λ"),
                     ("drag on a spectrum's y axis", "move its range; right drag or wheel: stretch it; "
                                                     "double click: automatic again")]
        if self.lambda_t is not None:
            rows.append(("click on λ–t", "pick t and λ"))
        rows.append(("click on the slit panel", "the cursor to that point of the slit; t or λ from the height"))
        ns = self.session.sizes["s"] if self.session.present["s"] else 1
        if ns > 1:
            rows.append(("click on a panel of the side-by-side view", "lock the cursor there; λ–t shows its Stokes"))
        rows.append(("padlock, top right of the image and of the spectra",
                     "fixed ⇄ automatic scale; right click: fit it to what is shown"))
        return rows

    def _keys(self) -> None:
        self.action_registry = ActionRegistry(self.key_table(), self.mouse_table())     # not `actions`: QWidget's
        self.action_registry.install(self)
        self.sheet = KeySheet(self, self.action_registry.sheet_html(self.palette()))

    def toggle_sheet(self) -> None:
        self.sheet.toggle()

    def _escape(self) -> None:
        """Esc closes the ? sheet if it is open, and only that; otherwise it leaves the slit mode, dropping the slit
        being drawn (a finished one stays), or else releases the cursor."""
        if self.sheet.isVisible():
            self.sheet.set_shown(False)
        elif self.slit_tool.mode:
            self.set_slit_mode(False)
        else:
            self.session.lock(False)

    # ---------------------------------------------------------------- the slit (ui.slit, ROADMAP E7)
    def set_slit_mode(self, on: bool) -> None:
        """S or the toolbar's slit button: the image's click adds points of a slit until a double click ends it; Esc
        (or S again) leaves without it. Drag still pans and the wheel still zooms."""
        self.slit_tool.set_mode(on)

    def toggle_slit_mode(self) -> None:
        self.set_slit_mode(not self.slit_tool.mode)

    def clear_slit(self) -> None:
        """⌫: the finished slit removed, from the image and from the session."""
        self.slit_tool.clear()

    def slit_step(self, d: int) -> None:
        """A (d = -1) and D (+1): the cursor to the previous or next pixel of the slit shown, locked there as a click on
        the slit panel does; held down, the key's auto-repeat walks the slit. From a cursor off the slit, its nearest
        point first. The slit is sampled every pixel and two samples can fall on one pixel: a step goes to the next
        different one. The slit shown is the slit panel's: the finished one, or the one being drawn. Without one the
        prototype did nothing; here the status line says what the keys are for. From the prototype's _slit_step
        (app/viewer.py:1901-1920)."""
        p = self.slit_panel
        if p.pix is None:
            self.statusBar().showMessage("A D: along a slit (S draws one)", 3000)
            return
        iy, ix = p.pix
        n = len(iy)
        y, x = self.session.state.cursor
        i = p.on.get((y, x))
        if i is None:
            i = int(np.argmin((iy - y) ** 2 + (ix - x) ** 2))
        else:
            j = i
            while 0 <= j + d < n and iy[j + d] == iy[i] and ix[j + d] == ix[i]:
                j += d
            i = int(np.clip(j + d, 0, n - 1))
        self.session.lock(False)
        self.session.hover(int(iy[i]), int(ix[i]))
        self.session.lock(True)

    def _slit_mode_changed(self, on: bool) -> None:
        """The button and the image's pointer at rest (ui.gestures puts it back after a pan) follow the mode, however
        it changed: a key, the button, a double click, a right click with no point left."""
        b = self.nav.slit
        if b.isChecked() != on:
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)
        self._gestures.rest = self.slit_tool.pointer()
        for c in self.linked:
            c._gestures.rest = self.slit_tool.pointer()
        self._slit_shown(on or self.session.state.path is not None)

    def _slit_shown(self, on: bool) -> None:
        """The slit's tab there and in front (S: its slices live while the slit is drawn; a slit finished), or gone
        (no slit, none being drawn). The prototype's set_slit_mode (1505-1515) and _slit_changed (1745)."""
        self._slit_tab(on)
        if on:
            self.slit_dock.raise_()

    def _slit_tab(self, on: bool) -> None:
        """The Slit tab beside lambda-t, lambda-t left in front; gone with the slit (the prototype's _slit_tab, 1772):
        as lambda-t's tab whenever it comes back, even from a layout that had it as a third panel (its F70b). In
        glass, whose panels float, a floating panel over lambda-t's place."""
        d, lt = self.slit_dock, self.lt_dock
        d.toggleViewAction().setEnabled(on)
        if on and d.isHidden():
            front = lt.isVisible()
            if self.glass is not None and (lt.isFloating() or self.spec_dock.isFloating()):
                self._slit_float()
                return
            d.show()
            if (d not in self.tabifiedDockWidgets(lt) and not lt.isHidden() and not lt.isFloating()
                    and not d.isFloating()):
                self.tabifyDockWidget(lt, d)
            if front:
                lt.raise_()
        elif not on and not d.isHidden():
            d.hide()

    def _slit_float(self) -> None:
        """In glass: the slit's panel floating below lambda-t (or the spectra, with lambda-t closed), SLIT_FLOAT_H
        high, when the monitor has room for it there; else the three stacked beside the window again, 40/30/30
        (glass's place_panels). The prototype's slit_tab_float, app/look_glass.py:607-618. Docked it would narrow the
        image."""
        from ..platform.screens import monitor_rect

        d = self.slit_dock
        ref = self.lt_dock if not self.lt_dock.isHidden() else self.spec_dock
        if self.glass is None or not ref.isFloating():
            return
        g = ref.frameGeometry()
        scr = monitor_rect(QtWidgets.QApplication.instance(), g.center())
        if g.bottom() + glass.GAP + SLIT_FLOAT_H <= scr.bottom():
            # its place given before it is shown, as place_panels does: its window made where it goes
            d.setFloating(True)
            d.setGeometry(g.x(), g.bottom() + glass.GAP, glass.FLOAT_W, SLIT_FLOAT_H)
            d.show()
        else:
            d.show()                                    # one panel more: place_panels floats it with the others
            self.glass.place_panels()
        d.raise_()

    def _slit_dock_again(self) -> None:
        """Out of glass: the slit's panel back as lambda-t's tab, in front, while there is a slit or one is drawn.
        Glass gives back the window's state from before it (hidden there if no slit had been drawn yet)."""
        d = self.slit_dock
        if d.isFloating():
            d.setFloating(False)
        if self.session.state.path is None and not self.slit_tool.mode:
            return
        if not d.isHidden() and d not in self.tabifiedDockWidgets(self.lt_dock):
            d.hide()                                    # _slit_tab places it again as lambda-t's tab
        self._slit_shown(True)

    def _place_slit_hint(self) -> None:
        """The slit's hint at the image's top left; in glass below the colour key, which glass moves there (the
        prototype's app/look_glass.py:1015-1021); in the 2x2 view below the panel's Stokes label."""
        x = y = SlitHint.MARGIN
        key = self.colour_key
        if self.glass is not None and key is not None and key.isVisibleTo(self.view.widget):
            x, y = glass.MARGIN, key.y() + key.height() + 8
        if self.grid is not None and self.grid.isVisibleTo(self.view.widget):
            y = max(y, GRID_LABEL)
        self.slit_hint.move(x, y)

    # ---------------------------------------------------------------- state
    def _on_state(self, st: ViewState, changed: frozenset) -> None:
        self.nav.sync(st, changed)
        if "cursor" in changed:
            self.view.set_crosshair(*st.cursor)
            if self.grid is not None:
                self.grid.set_crosshair(*st.cursor)
            self.slit_panel.set_cursor(*st.cursor)
        if "path" in changed:
            self.slit_tool.show_path(st.path)
            if st.path is not None or not self.slit_tool.mode:
                self._slit_shown(st.path is not None)
        if "locked" in changed:
            self.view.set_locked(st.locked)
            if self.grid is not None:
                self.grid.set_locked(st.locked)
        if "l" in changed and self.spectra is not None:
            self.spectra.set_lambda(st.l)
        if changed & {"t", "l"} and self.lambda_t is not None:
            self.lambda_t.set_markers(st.t, st.l)
        if changed & {"t", "l"}:
            self.slit_panel.set_markers(st.t, st.l)
        self.update_status()

    def update_status(self) -> None:
        """The cursor's pixel in physical units (status.pixel_text); I_c from the spectrum the core gave for this
        pixel and t, when the continuum tuning is known."""
        st = self.session.state
        y, x = st.cursor
        img = self.scheduler.img if hasattr(self, "scheduler") else None
        v = float(img[y, x]) if img is not None else float("nan")
        ic = None
        cont = getattr(self.dataset.axes, "cont", None)
        last = self.last.get("spectra")
        if cont is not None and last is not None and last[1] == (y, x) and last[2] == st.t and \
                self.spectra is not None and self.spectra.ns > 1:
            ic = float(last[0][0, cont]) * (self.spectra.iscale or 1.0)       # plot units back to physical
        present = tuple(a for a in ("t", "l") if self.session.present[a])
        ns = self.session.sizes["s"] if self.session.present["s"] else 1
        iscale = self.spectra.iscale if self.spectra is not None else None
        self.status.setText(pixel_text(self.dataset.axes, ns, y, x, st.t, st.l, st.s, v, ic, iscale, st.locked,
                                       present))
        if self.glass is not None:
            self.glass.readout()

    def set_diagnostics(self, on: bool) -> None:
        """F12: the cube, the storage probe, memory and the image cache, at the right of the status bar."""
        self.diagnostics = bool(on)
        self.sys_status.setVisible(self.diagnostics)
        if self.glass is not None:                      # the glass look's status line: only with the diagnostics
            self.statusBar().setVisible(self.diagnostics)
        if self.diagnostics:
            self.sys_status.setText(diagnostics_text(self.dataset))

    def first_image(self) -> None:
        if self.first_image_s is not None:
            return
        QtWidgets.QApplication.processEvents()          # on screen, not only handed to Qt
        self.first_image_s = time.perf_counter() - self.t0
        line = f"first image handed to the screen {self.first_image_s:.2f} s after opening started"
        if self.breakdown is not None:                  # set by ui.app.run: where the time went
            # what the user waits for is the time since the command started (Python, its imports, anything run
            # before the window, as the demo's doctor): that leads; the breakdown follows
            before, phases, platform, remote = self.breakdown
            rest = self.first_image_s - sum(phases.values())
            parts = ([f"start and imports {before:.2f} s"] if before is not None else []) + [
                f"{k} {v:.2f} s" for k, v in phases.items()] + [f"first image {rest:.2f} s"]
            where = f"{platform or 'default'}{' over ssh' if remote else ''}"
            if before is not None:
                line = f"first image handed to the screen {before + self.first_image_s:.2f} s after the command started"
            line += f" ({', '.join(parts)}; {where})"
            if remote:
                line += "; over X11 the pixels may still be on their way to the screen"
        print(line, file=sys.stderr, flush=True)
        for seconds, fn in self._after_first:
            QtCore.QTimer.singleShot(int(seconds * 1000), fn)

    def after_first_image(self, seconds: float, fn) -> None:
        """Run fn this many seconds after the first image is on screen (or after now, if it already is)."""
        if self.first_image_s is not None:
            QtCore.QTimer.singleShot(int(seconds * 1000), fn)
        else:
            self._after_first.append((seconds, fn))

    def _memory(self) -> None:
        for ds in [self.dataset, *(c.dataset for c in self.linked)]:     # linked: each its share (GuardShare)
            if hasattr(ds, "update_memory"):
                ds.update_memory()
        if self.diagnostics:
            self.sys_status.setText(diagnostics_text(self.dataset))

    # ---------------------------------------------------------------- closing
    def closeEvent(self, ev) -> None:
        if self.layout_store is not None and not self._closing:   # before the docks say hidden
            ops = self.window_ops
            store = self.layout_store.for_look(self.look.name)  # the glass look's own layout
            store.save(self, zoomed=ops is not None and ops.unzoomed is not None, look=self.look.name,
                       theme=self.theme)
        self._closing = True                            # the docks then say hidden: nothing to read any more
        self._play.stop()
        self._mem.stop()
        self._off()
        for c in self.linked:
            c.close()
        self.scheduler.close()
        super().closeEvent(ev)
