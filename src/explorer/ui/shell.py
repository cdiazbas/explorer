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
  while a slit is drawn and when one is finished, gone with the slit; with linked cubes, a tab per cube in it, each
  its own cube's slices along the slit, the drawn-on cube's in front (Shift+S or Panels: one tab, the drawn-on
  cube's); A / D: the cursor to the previous / next point along the slit, locked;
- Ctrl+W close, Ctrl+M minimise, Ctrl+Q quit (Qt reads Ctrl as Cmd on a Mac, where Cmd+Q is the application menu's).
"""
import math
import os
import sys
import time
from typing import TYPE_CHECKING

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from .._name import APP_NAME
from ..core.levels import gamma_step
from ..core.scheduler import Scheduler
from ..core.session import Session
from ..core.state import ViewState
from ..data import slitfits
from ..data.axes import STOKES
from ..data.names import cube_names, slice_names, value_name
from ..look import ENV_OFF, LOOKS, get_look
from ..look.colormaps import ColormapRegistry
from ..obs import get_logger
from . import docks, glass, icons, overlays, pens, style, titlebar
from .actions import ActionRegistry, KeySheet, mod_key, per_pixel_sheet_html
from .cards import MacSeams, Rounder
from .cube import CubeView, card_colour, reticle_colour
from .gestures import Gestures
from .imageview import CURSOR_PEN
from .linked import ImageTitle, LinkedCube, PanelTabs, ViewSync
from .loop import QtLoop
from .mask import MaskOutlines, mask_colour
from .overlays import ColourKey, gamma_text
from .scalekey import ScaleCard, scale_menu
from .slit import SlitHint, SlitTool
from .slitpanel import SlitPanel
from .status import diagnostics_text, pixel_text
from .stokesgrid import StokesGrid
from .toolbar import NavBar

log = get_logger("ui")

if TYPE_CHECKING:
    from ..platform.display import WindowOps
    from .layout import LayoutStore
    from .termkeys import TerminalKeys
    from .titlebar import TitleBar

MEMORY_S = 1.0                                          # the caches' budget follows the machine's memory (Dataset)
STATUS_INSET = 8            # px each side of the status line: half the rounded corners' 16, its text clear of the curve
FRAME_ALLOWANCE = 24       # px a floating window's frame may add to the size asked
CUBE_MIN_H = 560           # px: a cube's window at least this high, for its spectra and lambda-t
CUBE_PANELS_MIN_W = 320    # px: its spectra and lambda-t no narrower, when the screen has no room for wider ones
DETACHED_MIN_W = 160       # px: a detached image no narrower than this to fit a row; else they cascade
CASCADE = 28               # px each detached image is moved down and left when there is no room for a row
WIDTHS_MS = 150            # the images share the window's width this long after its size last changed
SLIT_FLOAT_H = 320          # px: the slit panel floating below lambda-t in glass (the prototype's look_glass.py:615)
SP_SHEET_WIDTH = 560        # px: the sheet over a per-pixel file alone, its paragraphs wrapped to this
TOAST_MS, FADE_MS = 2000, 500  # a save's note over the slit panel: shown, of which fading
GAMMA_NOTE_MS = 1000        # gamma on the image's colour key after G, Shift+G, Ctrl+G
CONTINUUM_NOTE_MS = 10000   # the continuum chosen from the sample, on the status line (core.scheduler _choose_cont)
UPDATE_AFTER_S = 2.0        # the update check, this long after the first image (start_update_check)
UPDATE_NOTE_MS, UPDATE_FADE_MS = 6000, 1000     # the note that a newer version exists: shown, of which fading
UPDATE_NOTE = f"A newer {APP_NAME} is available: run <b>{APP_NAME} update</b> in a terminal"
UPDATE_NOTE_AGED = (f"Your {APP_NAME} is from {{since}}; a newer one is available: run <b>{APP_NAME} update</b> in a "
                    "terminal")         # since: HEAD's commit date, update_check.day_text


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
        self.shell.view.set_image(img, levels, gamma=self.shell.main.gamma_now())
        if self.shell.glass is not None:
            self.shell.glass.image_changed()
        self.shell._paint_colour()
        self.shell.update_status()
        self.shell.first_image()
        if self.shell.session.state.playing:
            self.shell._shown = (self.shell._shown + [time.perf_counter()])[-30:]

    def spectra(self, spec, pixel, t):
        self.shell.last["spectra"] = (spec, pixel, t)
        if self.shell.spectra is not None:
            self.shell.spectra.show(spec)
        self.shell.update_status()                      # I_c for Q U V in % comes with the spectrum

    def lambda_t(self, lt, pixel, s, levels):
        self.shell.last["lambda_t"] = (lt, pixel, s, levels)
        self.shell.main.last_s = s
        if self.shell.lambda_t is not None:
            self.shell.lambda_t.show(lt, levels, gamma=self.shell.session.gamma(0, s))
            cols = self.shell.maps_for(s)
            self.shell.lambda_t.set_lut(cols.lut(s) if cols is not None else None)

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

    def noise(self, sigma, t):
        if self.shell.spectra is not None:
            self.shell.spectra.set_noise(sigma)

    def continuum(self, k, text):
        """The continuum chosen from the sample: said once on the terminal and the status line; the lambda slider's
        label marks it from now on, and the status line's I_c comes with the next pixel."""
        sh = self.shell
        print(f"[{APP_NAME}] {text}", file=sys.stderr)
        sh.nav.sync(sh.session.state, frozenset({"l"}))
        sh.update_status()
        sh.statusBar().showMessage(text, CONTINUUM_NOTE_MS)

    def grid_image(self, s, idx, img, levels):
        if self.shell.grid is not None:
            self.shell.grid.set_image(s, img, levels, gamma=self.shell.session.gamma(0, s))

    def slit_path(self, pix):
        reads = self.shell.scheduler.slit               # the main cube's scheduler has them
        self.shell.slit_cube(reads.cube if reads is not None else 0)   # the cube it was drawn on
        self.shell.slit_panel.set_path(pix)

    def slit(self, ts, sl, s, ts_levels, sl_levels):
        self.shell.last["slit"] = s
        self.shell.slit_panel.show(ts, sl, ts_levels, sl_levels, gamma=self.shell.session.gamma(self.shell._slit_on, s))
        cols = self.shell.maps_for(s)
        self.shell.slit_panel.set_lut(cols.lut(s) if cols is not None else None)


class Shell(QtWidgets.QMainWindow):
    # (version line, update_check.Found or None), emitted by the update check's thread: Qt queues it to
    # the window's thread, where show_about runs
    _about_found = QtCore.Signal(object)

    def __init__(self, dataset, title: str | None = None, t0: float | None = None, look=None, linked=(), mask=None):
        """t0: perf_counter() when opening started, for the time to the first image. linked: cubes linked to this
        one (data.link has checked them; opened with its executors), shown beside it. mask: a data.mask.Mask on its
        grid, outlined on every image (ui.mask); None: nothing of it is made."""
        super().__init__()
        self.dataset = dataset
        self._value_name: str | None = None             # value_name, once
        self.images = 1 + len(linked)                   # side by side (ui.docks: the first window's width)
        self.t0 = time.perf_counter() if t0 is None else t0
        self.first_image_s: float | None = None
        self.breakdown: tuple | None = None
        self._after_first: list = []
        self.loop = QtLoop(self)
        self.session = Session(self.loop, dataset)
        members = [self.session.add(ds) for ds in linked]
        light = style.is_light()                        # the theme the application was given (ui.style)
        self.look = look if look is not None else get_look()
        self._closing = False
        names = cube_names([dataset, *linked])
        # the main cube's views (ui.cube, member 0: as a linked cube's), and the names the window has always used
        self.main = CubeView(self, 0, names[0], light, keys="(or F) ")
        self.view, self.spectra, self.lambda_t = self.main.view, self.main.spectra, self.main.lambda_t
        self.image_lock, self.spec_lock = self.main.image_lock, self.main.spec_lock
        self.setCentralWidget(docks.gutter(self.view.widget))
        # the slit (S): drawn on the image, the finished one the session's path (ui.slit)
        self.slit_hint = SlitHint(self.view.widget, light=light)
        self.view.over.add(self.slit_hint)              # over the image (ui.overlays)
        self.slit_tool = SlitTool(self.session, self.view, self.slit_hint, CURSOR_PEN.color())
        self.slit_tool.modeChanged.connect(self._slit_mode_changed)
        r = dataset.roles
        # a cube without lambda has no spectra (and without t no lambda-t): that dock stays empty and absent
        self.spec_panel = self.spectra.widget if self.spectra is not None else QtWidgets.QWidget()
        self.lt_panel = self.lambda_t.widget if self.lambda_t is not None else QtWidgets.QWidget()
        # linked cubes: their images beside this one, their panels a tab each in these (ui.linked)
        self.linked = [LinkedCube(self, k, name) for k, name in zip(members, names[1:], strict=True)]
        self.spec_tabs = self._tabs(names[0], "spectra", self.spectra, self.spec_panel)
        self.lt_tabs = self._tabs(names[0], "lambda_t", self.lambda_t, self.lt_panel)
        # a panel no cube has (the spectra without lambda, lambda-t without t) is absent: never shown, by a saved
        # layout, reset_panels or glass either (docks.GatedDock), and not in the Panels menu
        lt_title = self.main.slices.panel if self.main.slices is not None and self.lt_tabs is None else "λ–t"
        self.spec_dock = docks.dock(self, "Spectrum", self.spec_tabs or self.spec_panel, "spectrum",
                                    cls=docks.GatedDock)
        self.lt_dock = docks.dock(self, lt_title, self.lt_tabs or self.lt_panel, "lambda_t", cls=docks.GatedDock)
        for d, has in ((self.spec_dock, self.spectra is not None or self.spec_tabs is not None),
                       (self.lt_dock, self.lambda_t is not None or self.lt_tabs is not None)):
            assert isinstance(d, docks.GatedDock)
            d.allowed = (lambda: True) if has else (lambda: False)
            d.toggleViewAction().setVisible(has)
        # every cube with spectra at a single lambda point: its Spectrum (one point per Stokes) only on request from
        # Panels, as a 4-Stokes point still compares I, Q, U and V; one cube with more points, shown as ever
        nls = [c.dataset.roles.nl for c in (self.main, *self.linked) if c.spectra is not None]
        if nls and max(nls) <= 1:
            assert isinstance(self.spec_dock, docks.GatedDock)
            self.spec_dock.on_request()
        # the slit's slices: lambda-t's tab, there from the first S on and only with a slit or one being drawn
        # (_slit_tab; the prototype's 1046-1052)
        self.slit_panel = SlitPanel(r.nt, r.nl, dataset.axes)
        if self.main.slices is not None:                # one plane along lambda, or none: the time slice alone
            n = self.main.slices
            self.slit_panel.set_cube(r.nt, r.nl, dataset.axes, None, n.label, n.mapped, n.value)
        self.main.slit_panel = self.slit_panel
        # with linked cubes, a slit tab per cube (ViewState.slit_tabs, on at start; the Panels menu and Shift+S switch
        # it): each its own cube's slices along the slit, a tab each as the spectra's and lambda-t's; off, the main
        # cube's tab alone, showing the cube the slit was drawn on (slit_cube)
        for c in self.linked:
            m = self.session.members[c.k].dataset
            c.slit_panel = SlitPanel(m.roles.nt, m.roles.nl, getattr(m, "axes", None))
            self._slit_axes(c.slit_panel, c.k)
        self.slit_tabs = PanelTabs(self.session, [(c.name, c.slit_panel.widget, f"slit:{c.k}" if c.k else "slit")
                                                  for c in self.cubes if c.slit_panel is not None],
                                   closing=lambda: self._closing) if self.linked else None
        if self.slit_tabs is not None:
            self.slit_tabs.set_shown(False)             # behind lambda-t until a slit is drawn
            for i, c in enumerate(self.cubes):
                self.slit_tabs.setTabToolTip(i, os.path.basename(str(getattr(c.dataset, "path", ""))))
            self.slit_tabs.currentChanged.connect(lambda _i: self._slit_title())
        slit_dock = docks.dock(self, "Slit", self.slit_tabs or self.slit_panel.widget, "slit", cls=docks.GatedDock)
        assert isinstance(slit_dock, docks.GatedDock)
        self.slit_dock = slit_dock
        self._slit_on = 0                               # the cube whose slices the slit panel shows (slit_cube)
        self.slit_tabs_action: QtGui.QAction | None = None
        if linked:
            self.slit_dock.setWindowTitle(f"Slit: {names[0]}")
            act = QtGui.QAction("A slit tab per cube", self)
            act.setCheckable(True)
            act.setToolTip("Each cube's slices along the same slit, a tab each (Shift+S). Unticked, one tab: the "
                           "cube the slit is drawn on")
            act.setChecked(True)
            act.toggled.connect(self.set_slit_tabs)
            self.slit_tabs_action = act
            self.session.set_slit_tabs(True)
        # lambda-t's tab from the start, as the prototype makes it (1047): its first show as a third panel resized
        # the spectra and back, and their ResizeFreezer's grab cost the first slit ~40 ms
        self.tabifyDockWidget(self.lt_dock, self.slit_dock)
        self.slit_dock.hide()
        self.slit_dock.allowed = lambda: self.session.state.path is not None or self.slit_tool.mode
        self.slit_dock.toggleViewAction().setEnabled(False)
        # the t steps the temporal panels show at most (data.tsample), one number for every cube: a number in the
        # titles of lambda-t and the slit, there in every look (a title of our own where Qt's would be)
        self.t_steps = titlebar.TimeSteps(self.session.state.t_cap, self.session.set_t_cap, self)
        self.slit_dock.save = self.save_slit  # type: ignore[attr-defined]   # the slit's: a save button after the number
        for d in (self.lt_dock, self.slit_dock):
            self.give_steps(d)
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
        # the mask's outline on every image (ui.mask), the 2x2 view's when it is made (set_grid)
        self.mask_outlines: MaskOutlines | None = None
        if mask is not None:                            # its outlines computed on the main cube's io thread
            ex = getattr(dataset, "executors", None)
            self.mask_outlines = MaskOutlines(self.session, mask, ex.io if ex is not None else None)
        if self.mask_outlines is not None:
            for v in [self.view, *(c.view for c in self.linked)]:
                self.mask_outlines.attach(v)
        self.setAnimated(False)
        # each linked cube in a window of its own beside this one, or back in it (Panels; detach_cubes)
        self.detach_action: QtGui.QAction | None = None
        self._detached_width = 0                        # what the window gave up for them (detach_cubes), and the
        self._detached_spec_w = 0                       # spectra's width then
        if self.linked:
            act = QtGui.QAction("Each cube in a window of its own", self)
            act.setCheckable(True)
            act.setToolTip("Every linked cube in a window of its own beside this one: its image, its spectra and its "
                           "λ–t. Unticked, or a double click on a window's title, back in this window")
            act.toggled.connect(self.detach_cubes)
            self.detach_action = act
            for c in self.linked:
                c.dock.topLevelChanged.connect(self._cube_moved)
        self.nav = NavBar(self)
        # playback: t forward at the toolbar's rate, round the end (the prototype's _toggle_play, _play_step)
        self._play = QtCore.QTimer(self)
        self._play.timeout.connect(self._play_step)
        self._fps: list[float] = []
        self._shown: list[float] = []                   # when images reached the view while playing
        self._fps_default = self.nav.fps.value()
        self._fps_auto: dict[str, int] = {}             # rates set by what was measured: the link, the frames
        self.nav.play.toggled.connect(self.set_playing)
        self.nav.fps.valueChanged.connect(lambda v: self._play.setInterval(int(1000 / v)))
        self._play.setInterval(int(1000 / self.nav.fps.value()))
        self.scheduler: Scheduler                       # the main cube's, made below once the panels are
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
        self.version_line = ""                          # the ? sheet's last line, once the update check says it
        self.newer = None                               # update_check.Found, when the check asked
        self._update_note: overlays.Toast | None = None
        self._about_found.connect(self.show_about)
        self._keys()
        self._install_gestures()
        # what the sink reads, before the scheduler: an image already in the cache (a second window on the same
        # Dataset) is shown inside Scheduler()
        self.colours: ColormapRegistry | None = None    # made the first time the look has colour or cmap (maps_for)
        self.colour_key: ColourKey | None = self.main.key     # in every look (ui.scalekey), hidden in the 2x2 view
        self.scale_card: ScaleCard | None = None
        self.grid: StokesGrid | None = None             # the 2x2 view (ui.stokesgrid), made the first time it is asked
        self.pointer = 0                                # the cube whose image the mouse last moved over (CubeView)
        self.glass: glass.GlassChrome | None = None     # the glass look's chrome (ui.glass), while worn
        # (zoom state, geometry): the size glass put under a zoom it gave back on leaving (GlassChrome.remove)
        self.under_zoom: tuple[QtCore.Qt.WindowState, QtCore.QRect] | None = None
        self._seams: MacSeams | None = None
        self._shown_lut = object()
        self._off = self.session.store.subscribe(self._on_state)
        self.main.start(_Sink(self))                    # its crosshair and markers from here on (CubeView.follow)
        self.scheduler = self.main.scheduler
        for c in self.linked:
            c.start()
        st = self.session.state
        if self.spectra is None and self.spec_tabs is None:
            self.spec_dock.hide()
        if self.lambda_t is None and self.lt_tabs is None:
            self.lt_dock.hide()
        self._slit_markers()
        for p in self.slit_panels:
            p.set_cursor(*st.cursor)
        self._mem = QtCore.QTimer(self)
        self._mem.setInterval(int(MEMORY_S * 1000))
        self._mem.timeout.connect(self._memory)
        self._mem.start()
        self._initial_state = self.saveState()          # before the first show: reset_panels comes back to it
        self._sized = False
        self._ratio_followed = False
        self._separators()
        panels = [self.view.widget] + [p for p in (self.spec_panel, self.lt_panel, *(q.w for q in self.slit_panels))
                                       if p is not None]
        self._rounders = [Rounder(w) for w in panels]   # 6-px corners on the panels, in both looks
        self.set_look(self.look)

    # ---------------------------------------------------------------- the look (look.Look; the prototype's app/look.py)
    def set_look(self, look) -> None:
        """Wear look (look.Look): every part put on or taken off, so the window can switch while it runs (M). The
        colour maps chosen with C stay, in every look that has them (maps_for)."""
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
        self.main.set_look(L, acc, light)               # its reticle, marks and cards (ui.cube)
        if self.grid is not None:
            self.grid.set_reticle(L.has("reticle"))
        self.nav.set_stokes_drop(L.has("stokes"))
        self._reticle_colours()
        for p in self.slit_panels:
            p.set_marks(acc) if L.has("marks") else p.clear_marks()
        if (L.has("colour") or L.has("cmap")) and self.colours is None:
            self.colours = ColormapRegistry(self.session.ns, light, colour=L.has("colour"))
        elif self.colours is not None:
            self.colours.set_start(L.has("colour"))
        if self.colour_key is not None:
            self.colour_key.show_with(True, grid=self.grid is not None and not self.grid.isHidden())
        self._shown_lut = object()
        self._paint_colour()
        self._grid_luts()
        if self.lambda_t is not None:
            lt = self.last.get("lambda_t")
            cols = self.maps_for(lt[2]) if lt is not None else None
            self.lambda_t.set_lut(cols.lut(lt[2]) if cols is not None and lt is not None else None)
        s = self.last.get("slit", self.session.state.s)
        cols = self.maps_for(s)
        self.slit_panel.set_lut(cols.lut(s) if cols is not None else None)
        for c in self.linked:
            if c.slit_panel is not None:
                cols = self.maps_for(c.slit_s)
                c.slit_panel.set_lut(cols.lut(c.slit_s) if cols is not None else None)
        if st.name() == "macos" and self._seams is None:   # the native style's light lines under the panel titles
            self._seams = MacSeams()                    # and on the separators: in the window's colour, in both looks
            for w in self._seamed():
                w.setStyle(self._seams)
        card = card_colour(L, light)
        if self.glass is None:                          # worn, glass keeps it clear over its slab
            for p in self.slit_panels:
                p.w.setBackground(card)
        if L.has("glass") and self.glass is None:       # its own parts last, over the modern look's (ui.glass); the
            self.glass = glass.GlassChrome(self)        # slit's panel, if shown, among the panels it floats
            self.glass.apply()
        # the slit in the markers' colour: the cursor's in the classic look (the prototype's _slit_style, 1733)
        self.slit_tool.set_colour(acc if L.has("marks") or L.has("glass") else CURSOR_PEN.color())
        for c in self.cubes:                            # a hot key in the look's accent (ui.scalekey.accent)
            c.key.update()
        self._place_slit_hint()
        if self.mask_outlines is not None:
            self.mask_outlines.set_colour(mask_colour(L))
        for c in self.linked:
            c.set_look(L, acc, light)

    # ---------------------------------------------------------------- the theme (ui.style), while the window runs
    def set_theme(self, theme: str) -> None:
        """dark or light (style.apply_theme) while the window runs (T): the application's style and palette, and
        every part that took the theme when it was made, given the new one. The look stays as worn; glass in place,
        its panels where they are and the image's region kept."""
        app = QtWidgets.QApplication.instance()
        if self._seams is not None:                     # off a Mac's native style: its seams go with it
            for w in self._seamed():
                w.setStyle(None)                        # None: the application's style again
            self._seams = None
        self.theme = style.apply_theme(app, theme)
        self._separators()
        light = style.is_light()
        for c in self.cubes:                            # images, panels and padlocks (ui.cube)
            c.set_light(light)
        self.slit_tool.set_light(light)
        if self.grid is not None:
            self.grid.set_light(light)
        for p in self.slit_panels:
            p.set_light(light)
        if self.colours is not None:
            self.colours.set_light(light)
        self.nav.restyle()
        self.sheet.setText(self.sheet_html())
        if self.sp_sheet is not None:
            self.sp_sheet.setText(self.per_pixel_sheet_html())
        self.set_look(self.look)                        # marks, cards and colour maps in the new theme
        if self.glass is not None:
            self.glass.retheme()
        if self.colour_key is not None:
            self.colour_key.update()

    def _separators(self) -> None:
        """8 px to grab between the docked panels, with the theme: the window's, and in each cube's own window."""
        for w in (self, *(c.frame for c in self.linked)):
            style.separators(w)

    def _seamed(self) -> list:
        """What MacSeams is set on: the window, its panels, and each cube's window's frame and panels."""
        return [self, self.spec_dock, self.lt_dock, self.slit_dock,
                *(w for c in self.linked for w in (c.frame, *c.panes.values()))]

    def give_steps(self, dock: QtWidgets.QDockWidget) -> None:
        """The number of t steps (titlebar.StepsButton) in a temporal panel's title, with our title where it has
        Qt's (a local Mac's native frame): the number is then there too."""
        dock.steps = self.t_steps  # type: ignore[attr-defined]
        if dock.titleBarWidget() is None:
            dock.setTitleBarWidget(titlebar.DockTitle(dock, stand_in=True))

    def dress(self, dock: QtWidgets.QDockWidget) -> None:
        """A panel made after the window (a cube's spectra and lambda-t in its window, ui.linked) dressed as the
        window's own: our title and edges where the chrome put them on (titlebar.dress), the Mac's seams."""
        titlebar.dress(self, dock)
        if self._seams is not None:
            dock.setStyle(self._seams)

    def pane_floated(self, dock: QtWidgets.QDockWidget, floating: bool) -> None:
        """A panel of a cube's window floated out of it or docked in it again: in glass, it wears glass's skin while
        it floats, as a panel floated from this window does."""
        if self.glass is not None:
            self.glass.pane_floated(dock, floating)

    def toggle_theme(self) -> None:
        """T: dark and light in turn; from a Mac's native theme, the other of the two."""
        self.set_theme("dark" if style.is_light() else "light")
        self.statusBar().showMessage(f"{'light' if style.is_light() else 'dark'} theme (T switches)", 3000)

    def _reticle_colours(self) -> None:
        """The 2x2 view's reticles as the images' (CubeView.set_look), whenever it is made."""
        for v in self.grid.views if self.grid is not None else []:
            if v.reticle is not None:
                v.reticle.set_colour(reticle_colour(self.look))

    # ---------------------------------------------------------------- the 2x2 view (ROADMAP E5.11)
    def set_grid(self, on: bool) -> None:
        """I Q U V side by side over the image (ui.stokesgrid), or the single view back: the region in view goes
        with it either way. Key 5, and All in the Stokes control; 1-4, or a Stokes picked there, leave it. Only with
        more than one Stokes. From the prototype's app/look_glass.py set_grid (600-614)."""
        ns = self.session.ns
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
                    if self.mask_outlines is not None:
                        self.mask_outlines.attach(v)
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
            self.colour_key.show_with(True, grid=on)
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
        for s in range(len(self.grid.views)):
            cols = self.maps_for(s)
            self.grid.set_lut(s, cols.image_lut(s) if cols is not None else None)

    def _grid_click(self, s: int, ev) -> None:
        """A click on panel s: the cursor locked there and that Stokes the session's, so lambda-t shows it; right
        click: released; double click: the whole image."""
        if self.grid is None or self.slit_tool.click(ev, self.grid.views[s].vb):
            return
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            label = self.grid.views[s].stokes
            if label.isVisible() and label.sceneBoundingRect().contains(ev.scenePos()):
                # its scale's menu (ui.scalekey): the 2x2 view's panels have no key of their own
                scale_menu(self, 0, s).popup(QtGui.QCursor.pos())
                return
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

    def maps_for(self, s: int) -> ColormapRegistry | None:
        """The colour maps Stokes s is drawn through, or None: the image's plain grey (base_lut). A look with the
        colour part draws every Stokes through its map; one with cmap alone (classic) only a Stokes off grey, so it
        starts exactly as it did before it had maps."""
        cols = self.colours
        if cols is None or self.look.has("colour"):
            return cols
        return cols if self.look.has("cmap") and s < len(cols.maps) and cols.maps[s] != "gray" else None

    def _paint_colour(self) -> None:
        """The image's colour table, for the Stokes shown (maps_for), and the key in every look (in the image's plain
        grey without a map)."""
        s = self.session.state.s
        cols = self.maps_for(s)
        if self.colours is not None:
            for c in self.linked:                       # a linked cube with the main cube's Stokes
                c.paint_colour()
        tab = cols.image_lut(s) if cols is not None else self.view.base_lut
        if tab is not self._shown_lut:
            self.view.set_lut(tab)
            self._shown_lut = tab
        last = self.last.get("image")
        if self.colour_key is not None and last is not None:
            # named as the image's label is (ui.stokeslabel): "Stokes Q" with the four, nothing for one plane
            self.colour_key.set(f"Stokes {STOKES[s]}" if self.session.ns == len(STOKES) else "", last[1],
                                cols.lut(s) if cols is not None else self.view.base_lut,
                                cols.maps[s] if cols is not None else None, gamma=self.session.gamma(0, s))

    # ---------------------------------------------------------------- gamma (core.levels; keys G, Shift+G, Ctrl+G)
    def gamma_target(self) -> tuple[int, int]:
        """(cube, Stokes) of the image under the pointer, or the one it last moved over: a panel of the 2x2 view is
        its Stokes, any other image its cube's Stokes now."""
        k = self.pointer if 0 <= self.pointer < len(self.cubes) else 0
        if k == 0 and self.grid is not None and self.grid.isVisible() and self.grid.under is not None:
            return 0, self.grid.under
        return k, self.session.member_state(k).s

    def step_gamma(self, d: int) -> None:
        """G / Shift+G: gamma of the image under the pointer down or up one step (levels.gamma_step)."""
        k, s = self.gamma_target()
        self.set_gamma(k, s, gamma_step(self.session.gamma(k, s), d))

    def reset_gamma(self) -> None:
        """Ctrl+G: gamma of the image under the pointer back to 1."""
        self.set_gamma(*self.gamma_target(), 1.0)

    def set_gamma(self, k: int, s: int, g: float) -> None:
        self.session.set_gamma(k, s, g)
        g = self.session.gamma(k, s)
        ns = self.cubes[k].ns
        what = " ".join(t for t in (self.cubes[k].name if self.linked else "",
                                    f"Stokes {STOKES[s]}" if ns == len(STOKES) else "") if t)
        # the colour key at rest says gamma only for a moment after a key, in every look; its hot view always does
        self.statusBar().showMessage(f"{gamma_text(g)}{': ' + what if what else ''}  (G \u21e7G {mod_key()}G)", 3000)
        self.cubes[k].key.flash(gamma_text(g), GAMMA_NOTE_MS)

    # ---------------------------------------------------------------- the scale's menu and card (ui.scalekey)
    def scale_levels(self, k: int, s: int) -> tuple[float, float]:
        """The levels cube k's image at Stokes s is drawn with now: a panel of the 2x2 view's for the main cube when
        that view is on, else the cube's image."""
        if k == 0 and self.grid is not None and self.grid.isVisible():
            v = self.grid.views[s]
        else:
            v = self.cubes[k].view
        return float(v._lim[0]), float(v._lim[1])

    def open_scale_card(self, k: int, s: int) -> ScaleCard:
        """The card with the numbers of cube k at Stokes s, by its key (or, for the 2x2 view, at the image's top
        left); one at a time."""
        if self.scale_card is not None:
            self.scale_card.close()
        card = self.scale_card = ScaleCard(self, k, s)
        key = self.cubes[k].key
        w = key.parentWidget() if key.isVisible() else self.cubes[k].view.widget
        at = w.mapTo(self, key.geometry().topLeft() if key.isVisible() else QtCore.QPoint(12, 12))
        y = at.y() - card.height() - 8 if at.y() > self.height() // 2 else at.y() + key.height() + 8
        card.move(max(0, min(at.x(), self.width() - card.width())), max(0, min(y, self.height() - card.height())))
        card.show()
        card.raise_()
        card.setFocus()
        return card

    def scale_settings(self) -> dict:
        """What the layout keeps of each cube's scale (ui.layout.LayoutStore.save_scale): by the cube's file name and
        Stokes, (rule, lo, hi, gamma) where not as at start."""
        st, out = self.session.state, {}
        for k, s, rule, lo, hi in st.scale:
            out[(self.cubes[k].scale_name(), s)] = [rule, lo, hi, 1.0]
        for k, s, g in st.gamma:
            out.setdefault((self.cubes[k].scale_name(), s), ["p1", 0.0, 0.0, 1.0])[3] = g
        return {key: tuple(v) for key, v in out.items()}

    def restore_scale(self, kept: dict) -> None:
        """Each cube's scale as scale_settings() kept it, for the cubes of this session (by file name)."""
        for c in self.cubes:
            for s in range(c.ns if c.dataset.roles.s is not None else 1):
                v = kept.get((c.scale_name(), s))
                if v is None:
                    continue
                rule, lo, hi, g = v
                try:
                    self.session.set_scale(c.k, s, rule, lo, hi)
                    self.session.set_gamma(c.k, s, g)
                except ValueError as e:                 # a file edited by hand: that entry left out
                    log.warning("scale of %s Stokes %d not restored: %r", c.name, s, e)

    def _gamma_changed(self) -> None:
        """The parts with a gamma that are the window's: the 2x2 view's panels, the slit's slices, the colour key."""
        if self.grid is not None:
            for s, v in enumerate(self.grid.views):
                v.set_gamma(self.session.gamma(0, s))
        slit_s = self.last.get("slit")
        if slit_s is not None:
            self.slit_panel.show(None, None, gamma=self.session.gamma(self._slit_on, slit_s))
        for c in self.linked:
            if c.slit_panel is not None:
                c.slit_panel.show(None, None, gamma=self.session.gamma(c.k, c.slit_s))
        self._paint_colour()

    def cycle_colours(self, step: int) -> None:
        """C / Shift+C: the next or previous map for the Stokes shown; image, lambda-t, the slit's slices, linked
        images of that Stokes and the key follow, nothing is read again. In every look but one that leaves cmap out
        (EXPLORER_LOOK_OFF)."""
        if self.colours is None or not self.look.has("cmap"):
            self.statusBar().showMessage(f"colour maps: left out of this look ({ENV_OFF})", 3000)
            return
        s = self.session.state.s
        name = self.colours.cycle(s, step)
        cols = self.maps_for(s)
        lut = cols.lut(s) if cols is not None else None
        self._shown_lut = object()
        self._paint_colour()
        self._grid_luts()                               # the 2x2 view's panel of that Stokes too
        if self.lambda_t is not None:
            self.lambda_t.set_lut(lut)
        self.slit_panel.set_lut(lut)
        for c in self.linked:                           # a linked cube's slit tab of that Stokes
            if c.slit_panel is not None and c.slit_s == s:
                c.slit_panel.set_lut(lut)
        if self.colour_key is not None:
            self.colour_key.flash(name)

    # ---------------------------------------------------------------- panels
    def _panel_shown(self, panel: str, on: bool) -> None:
        """A dock shown, closed or hidden: the core reads nothing for a hidden panel, and fills a shown one; with
        linked cubes, only for the tab in front (PanelTabs)."""
        tabs = {"spectra": self.spec_tabs, "lambda_t": self.lt_tabs, "slit": self.slit_tabs}.get(panel)
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
        # Qt gave the whole change to the main image: shared out once the window stops changing size. At every step
        # it laid the window out twice (activate, then resizeDocks): a resize cost 62 ms against 43 (bellatrix)
        t = getattr(self, "_widths_timer", None)
        if t is None:
            t = self._widths_timer = QtCore.QTimer(self, singleShot=True, interval=WIDTHS_MS)
            t.timeout.connect(self.same_image_widths)
        t.start()

    def showEvent(self, ev) -> None:
        super().showEvent(ev)
        if not self._ratio_followed:                    # the plots' line widths at this screen's ratio (ui.pens)
            self._ratio_followed = True
            pens.follow(self)
        if not self._sized:                             # the fresh start's sizes, once the layout exists
            self._sized = True
            QtCore.QTimer.singleShot(0, self.reset_sizes)

    def reset_sizes(self) -> None:
        """The panels' sizes of a fresh start (docks.reset_sizes), the images one width."""
        self._size_panels(lambda: docks.reset_sizes(self, (self.spec_dock, self.lt_dock), self.images))

    def _size_panels(self, size) -> None:
        """The panels beside the images sized by size(), their room taken from the linked images narrowed to nothing
        first, and then the images one width: what the spectra got depended on what the images had (335 against
        338 px from a layout where the main image was at its least width; 517 against 527 after cubes apart and
        back, the images shared out as each one docked). Every dock's own layout settled first (Qt posts it), as at
        the end (settle_widths): read before, a closed lambda-t shown again counted its old height."""
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.LayoutRequest)
        imgs = [c.dock for c in self.linked if c.dock.isVisible() and not c.dock.isFloating()]
        lay = QtWidgets.QMainWindow.layout(self)
        if imgs and lay is not None:
            self.resizeDocks(imgs, [1] * len(imgs), QtCore.Qt.Orientation.Horizontal)
            lay.activate()
        size()
        self.settle_widths()

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

    def detach_cubes(self, on: bool) -> None:
        """Every linked cube in a window of its own (on): its image panel floating with its spectra and lambda-t beside
        the image (LinkedCube.as_window; the user's mock of a cube apart), the image at the main image's size, in a
        row beside the window; or back in it (off), one width with the main image, its panels in their tabs again. In
        classic and modern the window gives up the width the images took and the row goes in that room, the window's
        place on the screen kept (left as it was, they overlapped it and each other: 254 and 410 px on a 2560-px
        screen); back in it, the window takes that width again. In glass the window is fitted to the images left in
        it, and the row goes beside its panels' column."""
        imgs = [c.dock for c in self.linked if not c.dock.isHidden()]
        lay = QtWidgets.QMainWindow.layout(self)
        cw = self.centralWidget()
        assert cw is not None and lay is not None
        if on:
            todo = [d for d in imgs if not d.isFloating()]
            if not todo:
                return
            # the room they take docked, each with its separator (read from the layout once applied, it came out 0)
            room = sum(d.width() + docks.separator(self) for d in todo)
            spec_w = self.spec_dock.width()
            for c in self.linked:                       # out first, hidden: each window made where it goes
                if c.dock in todo:
                    c.dock.hide()
                    c.as_window(True)
                    c.dock.setFloating(True)
            if self.glass is not None:
                self.glass.place_panels()               # the window fitted to the images left in it
            else:
                # their room went to the spectra beside them (one dock area): the spectra as wide as before, the room
                # the main image's, and then the window's to give up (else the main image shrank to 80 px)
                lay.activate()
                if self.spec_dock.isVisible() and not self.spec_dock.isFloating():
                    self.resizeDocks([self.spec_dock], [spec_w], QtCore.Qt.Orientation.Horizontal)
                    lay.activate()
                self._detached_width, self._detached_spec_w = room, spec_w
                self.resize(max(self.minimumSizeHint().width(), self.width() - room), self.height())
                lay.activate()
            self.place_detached(todo)
        else:
            # the room they took, given back first: docked into the narrow window, Qt widened it itself
            if self.glass is None and self._detached_width > 0:
                from ..platform.screens import monitor_rect

                scr = monitor_rect(QtWidgets.QApplication.instance(), self.frameGeometry().center())
                frame = self.frameGeometry().width() - self.width()
                self.resize(min(self.width() + self._detached_width, scr.width() - frame), self.height())
                self._detached_width = 0
                lay.activate()
                restore_spec = True
            else:
                restore_spec = False
            # every cube, its window closed too (left floating, it came back as a window with the entry unticked):
            # its panels back in their tabs first (docked with them, it came back as wide as its window and the
            # window grew)
            for c in self.linked:
                c.as_window(False)
                c.dock.setFloating(False)
            if self.glass is not None:
                self.glass.refit_after_redock()
            elif restore_spec and self.spec_dock.isVisible() and not self.spec_dock.isFloating():
                # the spectra as wide as when the images left (the room came back to them: 647-px images for 428)
                self._size_panels(lambda: self.resizeDocks([self.spec_dock], [self._detached_spec_w],
                                                           QtCore.Qt.Orientation.Horizontal))
        self._detached_changed()

    def detached_size(self) -> QtCore.QSize:
        """A detached image's window: what the main image shows at its zoom (the data in view, with the title and the
        gutter; as large as the main image's box when zoomed in: the whole image left most of a tall, narrow box
        empty, 226 x 759 px for 214 x 252 of data). A cube's window adds its panels (place_detached)."""
        cw = self.centralWidget()
        assert cw is not None
        g = docks.PANEL_GUTTER
        w, h = cw.width(), cw.height()
        vb, img = self.view.vb, self.view._full
        r = vb.viewRect()
        if img is not None and r.width() > 0 and r.height() > 0:
            ny, nx = img.shape
            vis = r.intersected(QtCore.QRectF(0, 0, nx, ny))
            title = self.image_title.height() if self.image_title is not None else 0
            w = min(w, int(vis.width() * vb.width() / r.width()) + 2 * g)
            h = min(h, int(vis.height() * vb.height() / r.height()) + title + 2 * g)
        return QtCore.QSize(w, h)

    def place_detached(self, todo=None) -> None:
        """The floating linked images and cubes (todo: those; by default every one) beside the window, or beside
        glass's panels' column: in a row; without room for one (each image at least DETACHED_MIN_W wide), in a column
        in the strip beside it; without room for that either, cascaded over the monitor's right side. Each window
        placed before it is shown, as glass places its panels (made where it goes, no late notice moves it back
        through XQuartz); a frame is wider than the size asked (22 px measured: rows that fitted overlapped), so
        FRAME_ALLOWANCE is counted, and each next window goes from the last one's frame. Sizes: detached_size."""
        from ..platform.screens import monitor_rect

        if todo is None:
            todo = [c.dock for c in self.linked if c.dock.isFloating() and not c.dock.isHidden()]
        if not todo or self.centralWidget() is None:
            return
        cubes = {c.dock: c for c in self.linked}
        windowed = [cubes[d].windowed and bool(cubes[d].panels()) for d in todo]
        fg = self.frameGeometry()
        right = fg.right()
        if self.glass is not None:                      # beside the panels' column
            for d in self.glass.docks():
                if d.isVisible() and d.isFloating():
                    right = max(right, d.frameGeometry().right())
        scr = monitor_rect(QtWidgets.QApplication.instance(), fg.center())
        x0, y0, gap = right + 1 + glass.GAP, fg.top(), glass.GAP + FRAME_ALLOWANCE
        strip_w, strip_h = scr.right() + 1 - x0 - FRAME_ALLOWANCE, scr.bottom() + 1 - y0

        image = self.detached_size()                    # an image's window at the main image's zoom
        sep = docks.separator(self.linked[0].frame)     # between a cube's image and its panels

        def sizes_for(k: float, pw: int) -> list[QtCore.QSize]:
            """The windows with their images shrunk by k: a cube's panels keep pw (shrunk with the rest, a cube's
            spectra were 236 px wide), its window at least CUBE_MIN_H high for them."""
            iw, ih = round(image.width() * k), round(image.height() * k)
            return [QtCore.QSize(iw + sep + pw, max(ih, CUBE_MIN_H)) if wd else QtCore.QSize(iw, ih)
                    for wd in windowed]

        def fits(plan_: str, ss: list[QtCore.QSize]) -> bool:
            if plan_ == "row":
                return (sum(q.width() + gap for q in ss) <= scr.right() + 1 - x0
                        and max(q.height() for q in ss) <= strip_h)
            return max(q.width() for q in ss) <= strip_w and sum(q.height() + gap for q in ss) <= strip_h

        # a row or a column, with the main window's panels' width or narrower ones (CUBE_PANELS_MIN_W): the one
        # whose images shrink least, found by bisection (the first that fitted shrank a cube's window to 743 x 325
        # px where a column fitted unshrunk); none with images DETACHED_MIN_W wide or more: a cascade
        best: tuple[float, str, int] | None = None
        for pw in (self.spec_dock.width(), CUBE_PANELS_MIN_W):
            for plan_ in ("row", "column"):
                if fits(plan_, sizes_for(1.0, pw)):
                    k = 1.0
                else:
                    lo, hi = 0.0, 1.0
                    for _ in range(20):
                        mid = (lo + hi) / 2
                        lo, hi = (mid, hi) if fits(plan_, sizes_for(mid, pw)) else (lo, mid)
                    k = lo
                if best is None or k > best[0] + 1e-6:
                    best = (k, plan_, pw)
        assert best is not None
        k, plan, panels_w = best
        if k < 1.0 and image.width() * k < DETACHED_MIN_W:
            plan, k, panels_w = "cascade", 1.0, self.spec_dock.width()
        sizes = sizes_for(k, panels_w)
        x, y = x0, y0
        for i, (d, s, wd) in enumerate(zip(todo, sizes, windowed, strict=True)):
            if plan == "row":
                at = QtCore.QPoint(x, y0)
            elif plan == "column":
                at = QtCore.QPoint(x0, y)
            else:                                       # each no wider than half the monitor
                if s.width() > scr.width() // 2:
                    f = (scr.width() // 2) / s.width()
                    s = QtCore.QSize(int(s.width() * f), int(s.height() * f))
                at = QtCore.QPoint(max(scr.left(), scr.right() + 1 - s.width() - CASCADE * i), y0 + CASCADE * i)
            d.setGeometry(QtCore.QRect(at, s))
            d.show()
            if wd:                                      # the panels their width, the image the rest
                cubes[d].panels_width(panels_w)
            x = d.frameGeometry().right() + 1 + glass.GAP
            y = d.frameGeometry().bottom() + 1 + glass.GAP

    def cube_windows(self) -> dict:
        """What the saved layout keeps of the cubes' windows (ui.layout), beyond the main window's state (which has
        each cube's image panel, floating or not, with its place and size): which cubes are windows of their own, the
        arrangement of the panels inside each one, and the width the window gave up for them."""
        out: dict = {"room": self._detached_width, "spec_w": self._detached_spec_w}
        for c in self.linked:
            out[f"{c.k}/windowed"] = c.windowed
            if c.panes:
                out[f"{c.k}/state"] = c.frame.saveState()
        return out

    def restore_cube_windows(self, kept: dict) -> None:
        """The cubes' windows as cube_windows() kept them, once the main window's state has floated their image
        panels: each one a window again, its panels made in its frame before the frame's state is restored (a dock
        restored before it exists is left out of it), then shown (places and sizes, never absences)."""
        def flag(v) -> bool:                            # an INI file gives "true" back
            return v is True or str(v).lower() == "true"

        for c in self.linked:
            if not (flag(kept.get(f"{c.k}/windowed")) and c.dock.isFloating()):
                continue
            c.as_window(True)
            state = kept.get(f"{c.k}/state")
            if state:
                c.frame.restoreState(state)
            for p in c.panes.values():
                if p.isHidden():
                    p.show()
        if any(c.windowed for c in self.linked):
            self._detached_width = int(kept.get("room") or 0)
            self._detached_spec_w = int(kept.get("spec_w") or 0)
        self._detached_changed()

    def _cube_moved(self, floating: bool) -> None:
        """A linked image floated or docked, however: docked, the images one width again (it came back as wide as
        it was, into a window that may have given up its room); the Panels entry as it now is."""
        if not floating:
            self.settle_widths()
        self._detached_changed()

    def settle_widths(self) -> None:
        """same_image_widths once the docks' own layouts have settled (their size hints come back as posted
        requests): shared out before, from a dock's floating size, a 780-px window's images came out 143, 192 and
        127 px wide."""
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.LayoutRequest)
        self.same_image_widths()

    def _detached_changed(self) -> None:
        """The Panels entry ticked while any linked cube is in a window of its own (an image alone, dragged out by
        its title, too: the entry then docks it)."""
        a = self.detach_action
        if a is None:
            return
        on = any(c.dock.isFloating() and not c.dock.isHidden() for c in self.linked)
        if a.isChecked() != on:
            a.blockSignals(True)
            a.setChecked(on)
            a.blockSignals(False)

    def reset_panels(self) -> None:
        """Every panel docked where it started and shown, and the whole image in view again (the prototype's
        reset_panels: one button brings everything back). In the glass look its panels float, placed again. A panel
        shown only on request (docks.GatedDock.on_request) is hidden again, here and in the cubes' windows."""
        for d in (self.spec_dock, *(p for c in self.linked for p in c.panes.values())):
            if isinstance(d, docks.GatedDock):
                d.forget()
        if self.glass is not None:
            self.glass.reset()
            self.statusBar().showMessage("panels and zoom back to the start", 4000)
            return
        if self.linked:                                 # the cubes back first, with the width the window gave up
            self.detach_cubes(False)
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
        self.reset_view()
        self.statusBar().showMessage("panels and zoom back to the start", 4000)

    # ---------------------------------------------------------------- picks on the panels
    def _install_gestures(self) -> None:
        """The slit panel's picks (each cube's image and panels have their own: ui.cube); a right click on it releases
        the cursor. No context menus: QMainWindow's (toolbar and docks on/off) over the toolbar, the dock titles and
        the sliders; an open one also left the next keys unanswered (the prototype's app/viewer.py:1018-1028)."""
        picks = {}
        for c in self.cubes:                            # each slit tab's panel, of its cube (slit_tabs)
            if c.slit_panel is None:
                continue
            vp = c.slit_panel.w.viewport()              # picks two things, as lambda-t (the prototype's 1975)
            vp.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
            c.slit_panel.w.scene().sigMouseClicked.connect(self.main.panel_click)
            picks[vp] = (lambda pos, now=True, k=c.k: self._slit_pick(pos, now, k)) if c.k else self._slit_pick
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        self._gestures = Gestures(self, picks)
        for vp in picks:
            vp.installEventFilter(self._gestures)

    @property
    def cubes(self) -> list:
        """Every cube's views (ui.cube): the main cube's first."""
        return [self.main, *self.linked]

    def _slit_pick(self, pos, now: bool = True, tab: int = 0) -> None:
        """A click or drag on a slit panel: the cursor to that point of the slit, locked there as a click on the image
        does, and t (time slice) or lambda (spectral slice) from y (the prototype's _slit_pick, 1932): of the cube the
        slices are of. tab: the cube of a linked cube's slit tab; 0: the main cube's tab."""
        panel = self.cubes[tab].slit_panel
        assert panel is not None
        k = tab or self._slit_on
        hit = panel.point_at(pos)
        if hit is None or panel.pix is None:
            return
        i, axis, v = hit
        iy, ix = panel.pix
        self.session.lock_at(int(iy[i]), int(ix[i]))
        if k and axis == "t":                           # its t nearest the main cube's (Member.t)
            mt = self.session.members[k].t
            v = min(range(len(mt)), key=lambda i: abs(mt[i] - v))
        if self.session.present[axis] or (axis == "l" and k):
            self.cubes[k].want({axis: v}, now)

    # ---------------------------------------------------------------- playback
    def set_playing(self, on: bool) -> None:
        shown, played = self.shown_fps(), self.played_fps()
        if not on and shown is not None and played is not None and shown < 0.8 * played:
            self.statusBar().showMessage(f"played at {played:.1f} fps; images shown {shown:.1f} a second", 10000)
        if on:
            self.cap_fps_by_frames()
        self.session.set_playing(on)
        self._fps, self._shown = [], []
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

    def shown_fps(self) -> float | None:
        """The rate images reached the view over the last ones shown while playing (30 at most); None before
        three."""
        f = self._shown
        return (len(f) - 1) / (f[-1] - f[0]) if len(f) > 2 and f[-1] > f[0] else None

    def auto_fps(self, why: str, fps: int) -> int | None:
        """The playback rate from what was measured (why: "link", "frames"): the lowest of them, never above the
        default (toolbar.FPS: a measure only lowers it), set while the rate box holds the default or the last rate
        set this way (one the user chose stays). The rate set, or None."""
        held = self.nav.fps.value()
        if held != self._fps_default and held != min(self._fps_auto.values(), default=held + 1):
            return None
        self._fps_auto[why] = int(fps)
        rate = min(min(self._fps_auto.values()), self._fps_default)
        self.nav.fps.setValue(rate)
        return rate

    def cap_fps_by_frames(self) -> None:
        """The playback rate no higher than the main cube's frames can be read (a compressed series decompresses
        one frame at a time): steps faster than that move the slider, not the image."""
        cap = self.dataset.frames.playback_cap() if hasattr(self.dataset, "frames") else None
        if cap is None:
            return
        fps, before = max(1, int(cap)), self.nav.fps.value()
        if self.auto_fps("frames", fps) == fps and fps != before:
            what = getattr(self.dataset.frames, "cap_reason", "frames read in")
            msg = f"{what} ~{1000 / cap:.0f} ms each, one at a time: playback at {fps} fps"
            self.statusBar().showMessage(msg, 10000)
            print(f"[{APP_NAME}] {msg}", file=sys.stderr)

    def start_link_probe(self, link) -> None:
        """Over a remote X display: the link measured in the background 1.5 s after start (so it does not compete
        with the start-up's traffic), and the default rate set to 60 % of it over one image, unless the rate was
        already changed; the prototype's start_link_probe. link: the Display's LinkInfo (bytes per image pixel,
        the rate not to go above)."""
        import threading

        from ..platform import linkprobe

        res: dict = {}

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
            fps = self.auto_fps("link", fps) or fps
            msg = f"X11 link ~{res['MBps']:.0f} MB/s, round trip {res['rtt_ms']:.1f} ms: playback at {fps} fps"
            if self.session.pace.link(res["MBps"]):     # a slow link: the panels at the pace it shows them
                msg += "; panels at the link's pace"
            self.statusBar().showMessage(msg, 10000)
            print(f"[{APP_NAME}] {msg}", file=sys.stderr)

        def start():
            th.start()
            QtCore.QTimer.singleShot(100, apply)

        QtCore.QTimer.singleShot(1500, start)

    def start_update_check(self, about=None) -> None:
        """The version for the ? sheet and whether origin has a newer one (update_check.about: git takes ~70 ms, the
        remote up to its timeout), in a thread UPDATE_AFTER_S after the first image, so that it does not compete with
        the start; its answer reaches show_about through a queued signal. about: update_check.about's stand-in."""
        import threading

        from .. import update_check

        ask = about or update_check.about

        def run():
            try:
                found = ask()
            except Exception:                           # the check is silent: the log has it
                log.exception("update check failed")
                return
            try:
                self._about_found.emit(found)
            except RuntimeError:                        # the window was deleted meanwhile
                pass

        def start():
            if not self._closing:
                threading.Thread(target=run, daemon=True, name="updatecheck").start()

        self.after_first_image(UPDATE_AFTER_S, start)

    def show_about(self, about) -> None:
        """(version line, update_check.Found or None): the ? sheet's last line, and the note over the image when the
        check says to say it (a new head, or a reminder: update_check.REMIND_DAYS)."""
        self.version_line, self.newer = about
        self.sheet.setText(self.sheet_html())
        if self.sheet.isVisible():
            self.sheet.set_shown(True)                  # its size and place for the new line
        if self.newer is not None and self.newer.announce:
            self.show_update_note()

    def show_update_note(self) -> None:
        """The note that a newer version exists, with this copy's date when known (UPDATE_NOTE_AGED, else
        UPDATE_NOTE), over the foot of the image (overlays.Toast), above the colour key when the key is at the foot
        (glass moves it to the top): UPDATE_NOTE_MS, fading over its last UPDATE_FADE_MS; through the X11 bridge (pace
        offered a screen) gone at once, as each step of a fade is a repaint on the link. How to stop the reminders is
        on the ? sheet: in the note it made a line wider than most images."""
        from ..update_check import day_text

        since = self.newer.since if self.newer is not None else ""
        text = UPDATE_NOTE_AGED.format(since=day_text(since)) if since else UPDATE_NOTE
        host = self.view.widget
        if self._update_note is None:
            self._update_note = overlays.Toast(host)
            self.view.over.add(self._update_note)       # the whole image repainted when it goes (ui.overlays)
        key = self.colour_key
        bottom = None
        if key is not None and key.isVisible() and key.geometry().top() > host.height() // 2:
            bottom = key.geometry().top()
        self._update_note.say(text, UPDATE_NOTE_MS,
                              0 if self.session.pace.offer is not None else UPDATE_FADE_MS, bottom)

    def fit_spectra(self) -> None:
        """F: the main cube's spectra fitted to this pixel's profile, and kept (closed); its padlock's right click."""
        self.main.fit_spectra()

    def spectra_to_sample(self) -> None:
        """Shift+F: back to the sample's ranges, fixed (as closing the padlock)."""
        self.scheduler.y_to_sample()
        if self.spec_lock is not None:
            self.spec_lock.set_closed(self.scheduler.yrange.fixed)

    def reset_view(self) -> None:
        """The whole image, the spectra's whole lambda range, and their y ranges as the padlock says: the sample's
        when closed, this pixel's when open (the prototype's reset_view)."""
        self.view.show_all()
        for c in self.cubes:
            c.reset_view()

    # ---------------------------------------------------------------- input
    def _hover(self, y: float, x: float) -> None:
        """The mouse over the main image (the 2x2 view's panels too): ui.cube."""
        self.main._hover(y, x)

    def key_table(self):
        """(keys as shown, what they do, ((key sequence, action), ...)) for this cube: the shortcuts, the terminal's
        keys and the ? sheet all come from it (ui.actions). A row is a line of the sheet: related keys share one, " · "
        between them as between what each does."""
        K, s = QtCore.Qt.Key, self.session
        mod = mod_key()
        rows: list[tuple[str, str, tuple]] = []
        arrows = [(keys, name, binds) for ax, keys, name, binds in (
            ("l", "← →", "λ", ((K.Key_Left, lambda: s.step("l", -1)), (K.Key_Right, lambda: s.step("l", 1)))),
            ("t", "↓ ↑", "t", ((K.Key_Down, lambda: s.step("t", -1)), (K.Key_Up, lambda: s.step("t", 1)))))
            if s.present[ax]]
        if arrows:
            rows.append((" · ".join(a[0] for a in arrows), " · ".join(a[1] for a in arrows) + ": previous, next",
                         tuple(b for a in arrows for b in a[2])))
        if s.present["s"] and s.sizes["s"] > 1:
            n = s.sizes["s"]
            rows.append((f"1–{n} · {n + 1}", "one Stokes · all side by side",
                         (*((str(k + 1), lambda k=k: self.pick_stokes(k)) for k in range(n)),
                          (str(n + 1), self.toggle_grid))))
        if s.present["t"] and s.sizes["t"] > 1:
            rows.append(("Space", "play, pause", ((K.Key_Space, lambda: self.nav.play.toggle()),)))
        rows += [("L", "lock, release the cursor", ((K.Key_L, lambda: s.lock(not s.state.locked)),)),
                 ("Esc", "close sheet, cancel slit, release", ((K.Key_Escape, self._escape),)),
                 ("S · \u232b", "slit: draw · remove",
                  ((K.Key_S, self.toggle_slit_mode), (K.Key_Backspace, self.clear_slit),
                   (K.Key_Delete, self.clear_slit))),
                 # A and D walk along the slit: the left hand on them, the right on the mouse (the prototype's
                 # 1324-1327, F75)
                 ("A D", "previous, next slit point",
                  ((K.Key_A, lambda: self.slit_step(-1)), (K.Key_D, lambda: self.slit_step(1))))]
        if self.linked:
            rows.append(("\u21e7S", "slit tabs: per cube \u21c4 one",
                         (("Shift+S", lambda: self.set_slit_tabs(not self.session.state.slit_tabs)),)))
        if self.spectra is not None:
            rows.append(("F · \u21e7F", "spectra y: this pixel · fixed",
                         ((K.Key_F, self.fit_spectra), ("Shift+F", self.spectra_to_sample))))
        # always bound: the terminal's keys are read once, and the look can change while the window runs
        rows += [(f"G \u21e7G · {mod}G", "\u03b3: lower, higher · back to 1",
                  (("G", lambda: self.step_gamma(-1)), ("Shift+G", lambda: self.step_gamma(1)),
                   ("Ctrl+G", self.reset_gamma))),
                 ("C \u21e7C", "colour map: next, previous",
                  (("C", lambda: self.cycle_colours(1)), ("Shift+C", lambda: self.cycle_colours(-1)))),
                 ("M · T", "look · dark \u21c4 light", ((K.Key_M, self.toggle_look), (K.Key_T, self.toggle_theme))),
                 ("F12", "status: cube, storage, memory",
                  ((K.Key_F12, lambda: self.set_diagnostics(not self.diagnostics)),)),
                 # Q: on a Mac the application menu's own, which closes through closeEvent and keeps the layout
                 (f"{mod}W {mod}M {mod}Q", "close · minimise · quit",
                  (("Ctrl+W", self.close), ("Ctrl+M", self.showMinimized),
                   *(() if sys.platform == "darwin" else (("Ctrl+Q", self.close),)))),
                 # "?" alone misses Shift+/ on the offscreen platform, so through the X11 bridge
                 ("?", "this sheet", (("?", self.toggle_sheet), ("Shift+?", self.toggle_sheet)))]
        return rows

    def mouse_table(self):
        """(gesture, what it does) for the ? sheet, a line each as the keys' rows; the handlers are ui.gestures and
        _click."""
        rows = [("image: click · right click", "lock · release the cursor"),
                ("S, then: click · double · right", "slit: point · finish · undo")]
        picks = [(where, what) for where, what, has in (("spectrum", "λ", self.spectra is not None),
                                                        ("λ–t", "t and λ", self.lambda_t is not None)) if has]
        if picks:
            rows.append(("click: " + " · ".join(p[0] for p in picks), "pick " + " · ".join(p[1] for p in picks)))
        if self.spectra is not None:
            rows.append(("spectrum's y axis: drag · wheel · double", "move · stretch (or right drag) · automatic"))
        rows.append(("slit panel: click", "cursor, t or λ there"))
        if self.session.present["t"]:
            rows.append(("number in λ–t, Slit titles: click · wheel", "t steps: 25, 50, 100, all"))
        if self.session.present["s"] and self.session.sizes["s"] > 1:
            rows.append(("side by side: click · right click label", "lock there · limits, γ, Scale…"))
        rows += [("padlock: click · right click", "fixed \u21c4 automatic · fit to view"),
                 ("colour key: drag ▲ · wheel · double", "min, max · γ · automatic")]
        return rows

    def _keys(self) -> None:
        self.action_registry = ActionRegistry(self.key_table(), self.mouse_table())     # not `actions`: QWidget's
        self.action_registry.install(self)
        self.sheet = KeySheet(self, self.sheet_html())
        self.sp_sheet: KeySheet | None = None
        if getattr(self.dataset, "images_from_sp", False):     # shown at once: the first image takes seconds
            self.sp_sheet = KeySheet(self, self.per_pixel_sheet_html())
            self.sp_sheet.setWordWrap(True)             # paragraphs, not the ? sheet's table: a column to read
            self.sp_sheet.setFixedWidth(SP_SHEET_WIDTH)
            self.sp_sheet.set_shown(True)
            self.after_first_image(0, self._refresh_sp_sheet)

    def sheet_html(self) -> str:
        """The ? sheet (ui.actions), its last line the version and, when origin has a newer one, the command."""
        return self.action_registry.sheet_html(self.palette(), self.version_line,
                                               newer=self.newer is not None and self.newer.newer)

    def per_pixel_sheet_html(self) -> str:
        """The sheet over the window when the images come from a per-pixel file alone (data.transpose.estimate)."""
        from ..data.transpose import estimate

        if getattr(self, "_sp_estimate", None) is None or self.dataset.frames.passes:
            self._sp_estimate = estimate(self.dataset.frames)
        return per_pixel_sheet_html(self._sp_estimate, os.path.basename(self.dataset.path), self.palette())

    def _refresh_sp_sheet(self) -> None:
        """The first image's pass measured: the sheet says that instead of the estimate it opened with."""
        if self.sp_sheet is not None:
            self.sp_sheet.setText(self.per_pixel_sheet_html())
            if self.sp_sheet.isVisible():
                self.sp_sheet.set_shown(True)          # its size and place for the new text

    def toggle_sheet(self) -> None:
        self.sheet.toggle()

    def _escape(self) -> None:
        """Esc closes the ? sheet if it is open, and only that; otherwise it leaves the slit mode, dropping the slit
        being drawn (a finished one stays), or else releases the cursor."""
        if self.sheet.isVisible():
            self.sheet.set_shown(False)
        elif self.sp_sheet is not None and self.sp_sheet.isVisible():
            self.sp_sheet.set_shown(False)
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

    def slit_cube(self, k: int) -> None:
        """The slit panel on cube k's slices, the one the slit was drawn on: its axes, its markers and, with linked
        cubes, its name in the panel's title. A cube without times of its own whose frames are the main cube's t
        (data.link: Blos and Vlos of 6173) has its t labelled with the main cube's times."""
        if k == self._slit_on:
            return
        self._slit_on = k
        self._slit_axes(self.slit_panel, k)
        self._slit_title()
        self._slit_markers()

    def _slit_axes(self, panel: SlitPanel, k: int) -> None:
        """panel on cube k's slices: its t and lambda axes, its names."""
        m = self.session.members[k]
        axes, r = getattr(m.dataset, "axes", None), m.dataset.roles
        times = None
        if getattr(axes, "t_sec", None) is None and m.t == tuple(range(r.nt)):
            times = self.dataset.axes
        # a linked cube's names (data.names), and a main cube's with one plane along lambda or none; the main
        # cube's with lambda as always
        names = self.cubes[k].slices
        panel.set_cube(r.nt, r.nl, axes, times, *((names.label, names.mapped, names.value) if names else ()))

    def _slit_title(self) -> None:
        """With linked cubes, the slit panel titled with the cube it shows: the tab in front's, with a tab per cube."""
        if not self.linked:
            return
        k = self._slit_front_tab()
        self.slit_dock.setWindowTitle(f"Slit: {self.cubes[self._slit_on if k is None else k].name}")

    def _slit_front_tab(self) -> int | None:
        """The cube whose slit tab is in front, with a tab per cube; None with one tab (the main cube's, which shows
        the cube the slit was drawn on)."""
        if self.slit_tabs is not None and self.session.state.slit_tabs and self.slit_tabs.count():
            key = self.slit_tabs.keys[self.slit_tabs.currentIndex()]
            return int(key.split(":")[1]) if ":" in key else 0
        return None

    def _slit_markers(self) -> None:
        st = self.session.member_state(self._slit_on)
        self.slit_panel.set_markers(st.t, st.l)
        for c in self.linked:
            if c.slit_panel is not None:
                mine = self.session.member_state(c.k)
                c.slit_panel.set_markers(mine.t, mine.l)

    @property
    def slit_panels(self) -> list:
        """Every slit tab's panel: the main cube's first."""
        return [c.slit_panel for c in self.cubes if c.slit_panel is not None]

    def set_slit_tabs(self, on: bool) -> None:
        """Shift+S or the Panels menu: with linked cubes, a slit tab per cube (on), each its cube's slices along the
        same slit, or one tab, of the cube the slit is drawn on."""
        if self.linked:
            self.session.set_slit_tabs(on)

    def _slit_tabs_changed(self, on: bool) -> None:
        """The tabs after ViewState.slit_tabs: the linked cubes' in (on) or out; a cube in a window of its own has
        its slit panel there, shown while there is a slit (LinkedCube.show_slit)."""
        a = self.slit_tabs_action
        if a is not None and a.isChecked() != on:
            a.blockSignals(True)
            a.setChecked(on)
            a.blockSignals(False)
        tabs = self.slit_tabs
        if tabs is None:
            return
        for c in self.linked:
            key = f"slit:{c.k}"
            if c.windowed:
                c.show_slit(on and self.slit_dock.allowed())
            elif on and key not in tabs.keys:
                assert c.slit_panel is not None
                tabs.give(key, c.slit_panel.widget)
            elif not on and key in tabs.keys:
                tabs.take(key).hide()
        self._slit_front(self.session.state)
        self._slit_title()

    def _slit_front(self, st: ViewState) -> None:
        """With a tab per cube, the tab of the cube the slit is drawn on in front."""
        if self.slit_tabs is None or not st.slit_tabs:
            return
        k = st.draft_cube if st.draft is not None else st.path_cube
        key = f"slit:{k}" if k else "slit"
        if key in self.slit_tabs.keys:
            self.slit_tabs.setCurrentIndex(self.slit_tabs.keys.index(key))

    def clear_slit(self) -> None:
        """⌫: the finished slit removed, from the image and from the session."""
        self.slit_tool.clear()

    def save_slit(self, folder: str | None = None) -> str | None:
        """The slit title's save button (titlebar.SaveButton): the time slice of the slit tab in front, as it shows it
        (its t steps, Stokes and lambda: nothing read again), to a new FITS file in folder (the working directory by
        default), named after the cube whose slice it is (data.slitfits); its path on the status line and the
        terminal, its name in a note over the panel (_save_toast). Returns it, None when nothing is written: no
        slit, S on with no point placed, one being drawn, or its slice not come yet; the status line and the note
        say which."""
        st, tab = self.session.state, self._slit_front_tab() or 0
        reads = self.cubes[tab].scheduler.slit
        rec = reads.time_slice
        why = ("no slit (S draws one)" if st.path is None and st.draft is None
               else "no slit yet: click points, double click to finish" if st.path is None and not st.draft
               else "the slit is being drawn: finish it first (double click)" if st.draft is not None
               else "its time slice is not shown yet"
               if rec is None or rec.path_id != reads.path_id or reads.pix is None else None)
        if why is not None:
            self.statusBar().showMessage(f"slit not saved: {why}", 4000)
            self._save_toast(f"not saved: {why}", tab)
            return None
        assert rec is not None and reads.pix is not None and reads.pts is not None
        c, panel = self.cubes[rec.cube], self.cubes[tab].slit_panel
        ds, r = c.dataset, c.dataset.roles
        try:
            path = slitfits.write_time_slice(
                folder or os.getcwd(), rec.values, t=rec.t, pix=reads.pix, pts=reads.pts,
                source=getattr(ds, "path", "") or c.name, axes=getattr(ds, "axes", None),
                times=panel.tax if panel is not None else None, s=rec.s if r.s is not None else None, ns=r.ns,
                l=rec.l if r.l is not None else None, nt=r.nt)
        except OSError as e:                            # a folder that cannot be written: said, nothing else
            msg = f"slit not saved: {e}"
            self.statusBar().showMessage(msg, 10000)
            print(f"[{APP_NAME}] {msg}", file=sys.stderr)
            return None
        # with a per-pixel file, the points whose blocks have not come are NaN in it (the cube's padding is NaN too)
        gaps = (len(reads.blocks.missing(zip(reads.pix[0].tolist(), reads.pix[1].tolist(), strict=True)))
                if reads.per_pixel else 0)
        msg = f"slit saved: {path}" + (f" ({gaps} pixels along it not read yet: NaN)" if gaps else "")
        self.statusBar().showMessage(msg, 10000)
        print(f"[{APP_NAME}] {msg}", file=sys.stderr)
        self._save_toast(f"saved {os.path.basename(path)}", tab)
        return path

    def _save_toast(self, text: str, tab: int) -> None:
        """A save's note over the slit panel, just above the time slice's x axis (overlays.Toast): TOAST_MS, fading
        over its last FADE_MS; through the X11 bridge (pace offered a screen) gone at once, as each step of a fade
        is a repaint on the link."""
        host = self.slit_dock.widget()
        if host is None:
            return
        t = getattr(self, "_toast", None)
        if t is None or t.parentWidget() is not host:
            t = self._toast = overlays.Toast(host)
        bottom = None
        panel = self.cubes[tab].slit_panel
        if panel is not None and panel.w.isVisible() and host.isAncestorOf(panel.w):
            vb = panel.ts.vb                            # the time slice's plot area: its foot is the x axis
            foot = panel.w.mapFromScene(vb.mapRectToScene(vb.boundingRect()).bottomLeft())
            bottom = panel.w.mapTo(host, foot).y()
        t.say(text, TOAST_MS, 0 if self.session.pace.offer is not None else FADE_MS, bottom)

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
        self.session.lock_at(int(iy[i]), int(ix[i]))

    def _slit_mode_changed(self, on: bool) -> None:
        """The button and the image's pointer at rest (ui.gestures puts it back after a pan) follow the mode, however
        it changed: a key, the button, a double click, a right click with no point left."""
        b = self.nav.slit
        if b.isChecked() != on:
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)
        for c in self.cubes:
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
        for c in self.linked:                           # a cube in a window of its own: its slit panel there
            c.show_slit(on and self.session.state.slit_tabs)
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
        """What sits at the image's top left: the Stokes label (ui.stokeslabel), but not under glass's colour key,
        which glass moves there and whose top row names the Stokes; the slit's hint below the label, below the key
        (the prototype's app/look_glass.py:1015-1021) or below the 2x2 view's panel's label."""
        x = y = SlitHint.MARGIN
        key = self.colour_key
        keyed = self.glass is not None and key is not None and key.isVisibleTo(self.view.widget)
        self.main.named = keyed
        self.main.show_stokes(self.session.state.s)
        if keyed and key is not None:
            x, y = glass.MARGIN, key.y() + key.height() + 8
        labelled = self.grid.views[0] if self.grid is not None and self.grid.isVisibleTo(self.view.widget) else \
            self.view if self.view.stokes.isVisible() else None
        if labelled is not None:
            y = max(y, labelled.below_stokes())
        self.slit_hint.move(x, y)

    # ---------------------------------------------------------------- state
    def _on_state(self, st: ViewState, changed: frozenset) -> None:
        """The window's parts; each cube's crosshair and markers are its own (CubeView.follow)."""
        self.nav.sync(st, changed)
        if "cursor" in changed:
            if self.grid is not None:
                self.grid.set_crosshair(*st.cursor)
            for p in self.slit_panels:
                p.set_cursor(*st.cursor)
        if "slit_tabs" in changed:
            self._slit_tabs_changed(st.slit_tabs)
        # the drawn-on cube's tab in front: as a slit is started on an image, and when it is finished
        started = "draft" in changed and st.draft is not None and len(st.draft) <= 1
        if changed & {"draft_cube", "path_cube"} or started or ("path" in changed and st.path is not None):
            self._slit_front(st)
        if "path" in changed:
            self.slit_tool.show_path(st.path)
            if st.path is not None or not self.slit_tool.mode:
                self._slit_shown(st.path is not None)
        if "locked" in changed and self.grid is not None:
            self.grid.set_locked(st.locked)
        if changed & {"t", "l", "own"}:
            self._slit_markers()
        if "gamma" in changed:                          # each cube's image and lambda-t: CubeView.follow
            self._gamma_changed()
        if "t_cap" in changed:
            self.t_steps.update(st.t_cap)
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
        iscale = self.spectra.iscale if self.spectra is not None else None
        self.status.setText(pixel_text(self.dataset.axes, self.session.ns, y, x, st.t, st.l, st.s, v, ic, iscale,
                                       st.locked, present, self.value_name()))
        if self.glass is not None:
            self.glass.readout()

    def value_name(self) -> str:
        """What the main cube's values are called in the status bar without Stokes: I along an axis known to be
        lambda, else what the cube shows (data.names.value_name: "Blos", "value"), as its curve's axis says."""
        if self._value_name is None:
            ds = self.dataset
            path = getattr(ds, "path", "")
            spectral = slice_names(ds.roles, ds.axes, path).spectral
            self._value_name = "I" if spectral else value_name(path, ds.axes)
        return self._value_name

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
        QtCore.QTimer.singleShot(1000, self.cap_fps_by_frames)     # the frames read ahead by then counted too

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
            store.save_scale(self.scale_settings())
        self._closing = True                            # the docks then say hidden: nothing to read any more
        if self.scale_card is not None:                 # its filter on the application goes with it
            self.scale_card.close()
        self._play.stop()
        self._mem.stop()
        self._off()
        if self.mask_outlines is not None:
            self.mask_outlines.close()
        for c in [*self.linked, self.main]:             # the linked ones first: they read on the main one's threads
            c.close()
        super().closeEvent(ev)
