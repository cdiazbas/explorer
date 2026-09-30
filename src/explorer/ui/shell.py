"""The window: the image panel, the spectra and lambda-t panels in docks on the right (ROADMAP E4.2-E4.4), the
navigation toolbar (E4.5), a status line and the keys that move through the cube (E3.6). Playback comes in E4.9,
the look in E5, the slit in E7.

It draws what explorer.core decides and turns input into core actions: the mouse over the image moves the cursor, a
click locks it there and a right click releases it (the prototype's _image_click), a double click shows the whole
image again. The keys, from the prototype's _key_table, in one table (the ? sheet and the ActionRegistry come in E5):
- Left / Right: lambda, previous / next tuning; Down / Up: t, previous / next frame (each arrow moves its line the
  way it points: lambda is horizontal on the spectra and lambda-t, t vertical on lambda-t);
- 1..ns: that Stokes, whenever the cube has Stokes (the prototype registered them only when it also had t);
- L: lock or release the cursor; Esc: release it;
- Ctrl+W close, Ctrl+M minimise, Ctrl+Q quit (Qt reads Ctrl as Cmd on a Mac, where Cmd+Q is the application menu's).
"""
import math
import sys
import time

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ..core.scheduler import Scheduler
from ..core.session import Session
from ..core.state import ViewState
from ..data.axes import STOKES
from . import docks
from .gestures import Gestures
from .imageview import ImageView
from .lambda_t import LambdaTPanel
from .loop import QtLoop
from .padlock import PanelLock
from .spectra import SpectraPanel
from .status import diagnostics_text, pixel_text
from .toolbar import NavBar

MEMORY_S = 1.0                                          # the caches' budget follows the machine's memory (Dataset)


class _Sink:
    """The scheduler's results on screen: the image now; the other panels come in E4 and are kept until then."""

    def __init__(self, shell: "Shell"):
        self.shell = shell

    def image(self, idx, img, levels):
        self.shell.last["image"] = (idx, levels)
        self.shell.view.set_image(img, levels)
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


class Shell(QtWidgets.QMainWindow):
    def __init__(self, dataset, title: str | None = None, t0: float | None = None):
        """t0: perf_counter() when opening started, for the time to the first image."""
        super().__init__()
        self.dataset = dataset
        self.t0 = time.perf_counter() if t0 is None else t0
        self.first_image_s: float | None = None
        self.breakdown: tuple | None = None
        self._after_first: list = []
        self.loop = QtLoop(self)
        self.session = Session(self.loop, dataset)
        ex = dataset.executors
        self.view = ImageView(on_hover=self._hover, strips=ex.strips, parts=ex.n_strips)
        self.setCentralWidget(docks.gutter(self.view.widget))
        r = dataset.roles
        # a cube without lambda has no spectra: that dock stays empty and hidden
        self.spectra = SpectraPanel(max(1, r.ns if r.s is not None else 1), r.nl, dataset.axes) \
            if r.l is not None else None
        self.spec_panel = self.spectra.widget if self.spectra is not None else QtWidgets.QWidget()
        # lambda-t needs both t and lambda
        self.lambda_t = LambdaTPanel(r.nt, r.nl, dataset.axes) if r.t is not None and r.l is not None else None
        self.lt_panel = self.lambda_t.widget if self.lambda_t is not None else QtWidgets.QWidget()
        self.spec_dock = docks.dock(self, "Spectrum", self.spec_panel, "spectrum")
        self.lt_dock = docks.dock(self, "λ–t", self.lt_panel, "lambda_t")
        self.setAnimated(False)
        self.nav = NavBar(self)
        # the padlocks, both open at start (the prototype's): closed = fixed, right click = fit to what is shown
        self.image_lock = PanelLock(self.view.widget, "Image contrast: closed = fixed, open = automatic per image. "
                                    "Click to switch; right click fixes it to this image")
        self.image_lock.toggled.connect(lambda on: self.scheduler.fix_levels(on))
        self.image_lock.refit.connect(self._image_refit)
        self.spec_lock = None
        if self.spectra is not None:
            self.spec_lock = PanelLock(self.spectra.w, "Spectra y range: open = automatic, closed = fixed (I from "
                                       "100 random profiles, Q U V from the whole image). Click to switch; right click "
                                       "(or F) fixes it to this pixel")
            self.spec_lock.toggled.connect(lambda on: self.scheduler.set_y_fixed(on))
            self.spec_lock.refit.connect(self.fit_spectra)
        self._closing = False
        for d, panel in ((self.spec_dock, "spectra"), (self.lt_dock, "lambda_t")):
            d.visibilityChanged.connect(lambda on, panel=panel: self._panel_shown(panel, on))
        self.status = QtWidgets.QLabel()
        self.status.setTextFormat(QtCore.Qt.TextFormat.PlainText)
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
        self._off = self.session.store.subscribe(self._on_state)
        self.scheduler = Scheduler(self.session, _Sink(self))
        st = self.session.state
        self.view.set_crosshair(*st.cursor)
        if self.spectra is not None:
            self.spectra.set_lambda(st.l)
        else:
            self.spec_dock.hide()
        if self.lambda_t is not None:
            self.lambda_t.set_markers(st.t, st.l)
        else:
            self.lt_dock.hide()
        self._mem = QtCore.QTimer(self)
        self._mem.setInterval(int(MEMORY_S * 1000))
        self._mem.timeout.connect(self._memory)
        self._mem.start()
        self._initial_state = self.saveState()          # before the first show: reset_panels comes back to it
        self._sized = False

    # ---------------------------------------------------------------- panels
    def _panel_shown(self, panel: str, on: bool) -> None:
        """A dock shown, closed or hidden: the core reads nothing for a hidden panel, and fills a shown one."""
        if not self._closing:
            self.session.show(panel, on)

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self.nav.fit(self.width())

    def showEvent(self, ev) -> None:
        super().showEvent(ev)
        if not self._sized:                             # the fresh start's sizes, once the layout exists
            self._sized = True
            QtCore.QTimer.singleShot(0, self.reset_sizes)

    def reset_sizes(self) -> None:
        docks.reset_sizes(self, (self.spec_dock, self.lt_dock))

    def reset_panels(self) -> None:
        """Every panel docked where it started and shown, and the whole image in view again (the prototype's
        reset_panels: one button brings everything back)."""
        for d in (self.spec_dock, self.lt_dock):
            d.setFloating(False)
        self.restoreState(self._initial_state)
        for d in (self.spec_dock, self.lt_dock):
            if d.isHidden():
                d.show()
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
        image = self.view.widget.viewport()
        image.setCursor(C.CrossCursor)
        self._gestures = Gestures(self, picks, image)
        for vp in [*picks, image]:
            vp.installEventFilter(self._gestures)

    def _panel_click(self, ev) -> None:
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            self.session.lock(False)                    # the right click releases from any panel

    def _spectrum_pick(self, pos, now: bool = True) -> None:
        """lambda nearest to x on whichever spectrum plot is under pos."""
        for p in self.spectra.plots:
            if p.vb.sceneBoundingRect().contains(pos):
                xv = p.vb.mapSceneToView(pos).x()
                self._want_pick({"l": int(np.argmin(np.abs(self.spectra.xl - xv)))}, now)
                return

    def _lt_pick(self, pos, now: bool = True) -> None:
        """(t, lambda) of the cell under pos on lambda-t."""
        vb = self.lambda_t.w.getPlotItem().vb
        if not vb.sceneBoundingRect().contains(pos):
            return
        q = vb.mapSceneToView(pos)
        self._want_pick({"l": int(np.clip(int(q.x()), 0, self.lambda_t.nl - 1)),
                         "t": int(np.clip(int(q.y()), 0, self.lambda_t.nt - 1))}, now)

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

    # ---------------------------------------------------------------- input
    def _hover(self, y: float, x: float) -> None:
        self.session.hover(math.floor(y), math.floor(x))

    def _click(self, ev) -> None:
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
        """(keys as shown, what they do, ((key sequence, action), ...)) for this cube."""
        K, s = QtCore.Qt.Key, self.session
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
                         tuple((str(k + 1), lambda k=k: s.set_index("s", k)) for k in range(n))))
        if self.spectra is not None:
            rows += [("F", "spectra: fit y to this pixel, and keep it", ((K.Key_F, self.fit_spectra),)),
                     ("\u21e7F", "spectra: fixed range (I: 100 random profiles; Q U V: the whole image)",
                      (("Shift+F", self.spectra_to_sample),))]
        rows += [("L", "lock, release the cursor", ((K.Key_L, lambda: s.lock(not s.state.locked)),)),
                 ("Esc", "release the cursor", ((K.Key_Escape, lambda: s.lock(False)),)),
                 ("F12", "the cube, storage and memory in the status bar",
                  ((K.Key_F12, lambda: self.set_diagnostics(not self.diagnostics)),)),
                 ("Ctrl+W", "close the window", (("Ctrl+W", self.close),)),
                 ("Ctrl+M", "minimise", (("Ctrl+M", self.showMinimized),)),
                 ("Ctrl+Q", "quit", () if sys.platform == "darwin" else (("Ctrl+Q", self.close),))]
        return rows

    def _keys(self) -> None:
        for _keys, _what, binds in self.key_table():
            for seq, fn in binds:
                sc = QtGui.QShortcut(QtGui.QKeySequence(seq), self)
                sc.activated.connect(fn)

    # ---------------------------------------------------------------- state
    def _on_state(self, st: ViewState, changed: frozenset) -> None:
        self.nav.sync(st, changed)
        if "cursor" in changed:
            self.view.set_crosshair(*st.cursor)
        if "l" in changed and self.spectra is not None:
            self.spectra.set_lambda(st.l)
        if changed & {"t", "l"} and self.lambda_t is not None:
            self.lambda_t.set_markers(st.t, st.l)
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

    def set_diagnostics(self, on: bool) -> None:
        """F12: the cube, the storage probe, memory and the image cache, at the right of the status bar."""
        self.diagnostics = bool(on)
        self.sys_status.setVisible(self.diagnostics)
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
        if hasattr(self.dataset, "update_memory"):
            self.dataset.update_memory()
        if self.diagnostics:
            self.sys_status.setText(diagnostics_text(self.dataset))

    # ---------------------------------------------------------------- closing
    def closeEvent(self, ev) -> None:
        self._closing = True                            # the docks then say hidden: nothing to read any more
        self._mem.stop()
        self._off()
        self.scheduler.close()
        super().closeEvent(ev)
