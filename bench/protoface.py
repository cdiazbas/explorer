"""The prototype's viewer as its tests see it, on explorer's window: the names app/smoke.py and app/conformance.py
read and call (v.spec_dock, v.idx, v._yr, v.stats ...), each mapped to what explorer has for it, so those tests run
unchanged against explorer (ROADMAP E4.11, E4.12). A name explorer has no counterpart for yet raises
NotInExplorer, and the check that needs it is counted as not there yet, never as passed.

adopt(shell) mixes the names into the Shell's own class, so the viewer the tests hold is explorer's window itself.
Only reads and the same actions as the prototype's API; nothing here changes how explorer behaves. Where the
mapping is not one to one, the comment says what is compared.
"""
import os
import time
from types import SimpleNamespace

import numpy as np

HOVER_WAIT_S = 3.0          # smoke.py's own wait for the reader thread
HOVER_ASK_S = 0.2           # for the cursor's read to be asked: a few turns of the loop

# which later task brings what a missing name belongs to (ROADMAP)
LATER = {"slit": "slit (E7)", "title": "own title bar (E5)", "persist": "layout persistence (E5)",
         "look": "the modern look (E5)",
         "slit C": "the prototype's slit C: not ported, explorer has variant D alone (ROADMAP P5, its F74)"}


class NotInExplorer(AttributeError):
    """The prototype's name has no counterpart in explorer yet; the message names the task that brings it."""

    def __init__(self, name: str, what: str):
        super().__init__(f"not in explorer yet: {name} ({LATER.get(what, what)})")


_SLIT = {"slit_w", "slit_ts", "slit_sl", "slit_ts_img", "slit_sl_img", "slit_path",
         "slit_t", "slit_p", "slit_l"}
# the slit tool the prototype's tests may pin: D is explorer's (ROADMAP P5); A draws as D does, without the slices
# while drawing, and the checks pinned to it test the drawing. C is another tool, not ported
SLIT_TOOLS = ("A", "D")


class _Flag:
    """The prototype's hidden 'fixed contrast' check box (app/viewer.py:949): the image padlock's state, which the
    tests set and read as a check box. Explorer keeps that state in the padlock itself; it has no check box, in the
    toolbar or elsewhere (parentWidget None, never visible: what the prototype's hidden one also answers)."""

    def __init__(self, lock):
        self.lock = lock

    def isChecked(self):
        return self.lock.isChecked()

    def setChecked(self, on):
        if self.lock.isChecked() != bool(on):
            self.lock.click()

    def parentWidget(self):
        return None

    def isVisible(self):
        return False


class _Hint:
    """v._slit_hint: the slit's line inside the image (ui.slit.SlitHint), its text under the prototype's name."""

    def __init__(self, hint):
        self._hint = hint

    @property
    def _text(self):
        return self._hint.text

    def __getattr__(self, attr):
        return getattr(self._hint, attr)


class _RestTimer:
    """The prototype's _yfit_timer (400 ms after the last spectrum, app/viewer.py:846): active while explorer's
    YRange has a rest refit pending (YRange._rest_later .. _rest)."""

    def __init__(self, yr):
        self.pending = False
        rest_later, rest = yr._rest_later, yr._rest

        def later():
            self.pending = True
            rest_later()

        def at_rest(token):
            if token == yr._rest_token:
                self.pending = False
            rest(token)
        yr._rest_later, yr._rest = later, at_rest

    def isActive(self):
        return self.pending


class _Backend:
    """v.be: the prototype's image backend (app/viewer.py, pgr); explorer's ImageView is its port (vb, hl, vl, _lim,
    last_render), with the widget named widget instead of image_widget."""

    def __init__(self, view):
        self._view = view

    @property
    def image_widget(self):
        return self._view.widget

    def __getattr__(self, name):
        return getattr(self._view, name)


class _Stats(dict):
    """v.stats: the prototype's per-viewer counters, from explorer's counters (obs.spans.counter)."""
    MAP = {"pixel_reads": "core.cursor.reads", "skipped_hidden": "core.cursor.skipped_hidden",
           "skipped_padding": "core.cursor.skipped_padding", "cursor_updates": "core.cursor.updates",
           "limits_computed": "core.levels.computed", "limits_cached": "core.levels.cached"}

    def __getitem__(self, k):
        from explorer.obs import spans

        return spans.summary().get("counters", {}).get(self.MAP[k], 0)


class ProtoViewer:
    """The prototype's Viewer names on explorer's Shell, mixed into the Shell's own class by adopt(): the viewer the
    tests hold is the Shell itself, so what they compare by identity (the active window, the window a Close is for)
    is explorer's window."""
    _w = property(lambda self: self)

    def _pf_adopt(self):
        r = self.dataset.roles
        self._pf_roles = r
        self._pf_names = {r.t: "t", r.s: "s", r.l: "l"}
        self._pf_slit_ui = "D"                          # the slit tool: explorer's D (the tests pin A for some checks)
        self.be = _Backend(self.view)
        self.stats = _Stats()
        self.fix = _Flag(self.image_lock)
        self._yfit_timer = _RestTimer(self.scheduler.yrange)
        for pe in getattr(self, "_panel_edges", None) or ():   # each panel's resizer, where the tests look for it
            pe.d._crispex_resizer = pe.resizer

    # ------------------------------------------------------------------ the slit (ui.slit, ui.slitpanel, slitreads)
    # set_slit_mode, clear_slit and _slit_tab are the Shell's own, under the prototype's names already. A name of the
    # slit's not mapped here is NotInExplorer
    def __getattr__(self, name):
        if name in _SLIT or name.startswith("_slit"):
            raise NotInExplorer(name, "slit")
        raise AttributeError(name)

    @property
    def SLIT_UI(self):
        return self._pf_slit_ui

    @SLIT_UI.setter
    def SLIT_UI(self, value):
        if value not in SLIT_TOOLS:
            raise NotInExplorer(f"SLIT_UI = {value!r}", f"slit {value}")
        self._pf_slit_ui = value

    slit_btn = property(lambda self: self._w.nav.slit)
    _slit_mode = property(lambda self: self._w.slit_tool.mode)
    _slit_pts = property(lambda self: self._w.slit_tool.pts)          # the slit being drawn: the points clicked
    _slit_hint = property(lambda self: _Hint(self._w.slit_hint))

    @property
    def _slit_front(self):
        """Its tab in front: the core reads for it (a tab behind is moved off screen, not hidden)."""
        return "slit" in self._w.session.state.panels

    @property
    def slit(self):
        """The finished slit: its points (x, y) as an array, or None (ViewState.path)."""
        path = self._w.session.state.path
        return None if path is None else np.asarray(path, np.float64)

    @property
    def slit_path(self):
        """The finished slit sampled every pixel, (N, 2) x, y (data.slits.slit_path), or None."""
        from explorer.data.slits import slit_path

        pts = self.slit
        return None if pts is None else slit_path(pts)

    def _slit_add(self, p):
        """A point at view coordinates p (QPointF), as a click there in the mode."""
        self._w.slit_tool.add(p.x(), p.y())

    def _slit_finish(self):
        self._w.slit_tool.finish()

    def _slit_hover(self, scene_pos):
        """The pointer at a scene position of the image: the slit being drawn reaches to it (Shell._hover)."""
        q = self._w.view.vb.mapSceneToView(scene_pos)
        self._w._hover(q.y(), q.x())

    # what the panel shows: the pixels along the slit shown (the one being drawn, else the finished one) and the first
    # point on each pixel, as the prototype's _slit_pix and _slit_on
    _slit_pix = property(lambda self: self._w.slit_panel.pix)
    _slit_on = property(lambda self: self._w.slit_panel.on)
    slit_w = property(lambda self: self._w.slit_panel.w)
    slit_ts = property(lambda self: self._w.slit_panel.ts)
    slit_sl = property(lambda self: self._w.slit_panel.sl)
    slit_ts_img = property(lambda self: self._w.slit_panel.ts_img)
    slit_sl_img = property(lambda self: self._w.slit_panel.sl_img)
    slit_t = property(lambda self: self._w.slit_panel.t_line)
    slit_l = property(lambda self: self._w.slit_panel.l_line)
    slit_p = property(lambda self: self._w.slit_panel.cur_lines)

    # the reads (core.slitreads.SlitReads). The prototype painted the slices in the call that had read them; explorer
    # makes them on its slit thread and shows them a turn of the loop later, so what the tests wait for (the blocks
    # read, the bands read) counts only once the slices of the newest request are on screen
    @property
    def _slit_slab(self):
        """The prototype's A read one slab per slit with a per-pixel file, and the checks pinned to A wait for it:
        here the blocks of every pixel of the slit, once its newest slices are on screen. None until then, and
        without a per-pixel file (the bands, _slit_bands)."""
        r = self._w.scheduler.slit
        pix = r.pix
        if not r.per_pixel or pix is None or self._slitc_busy:
            return None
        with r._lock:
            whole = all(p in r.blocks for p in zip(pix[0].tolist(), pix[1].tolist(), strict=True))
        return r.blocks if whole else None

    def _pf_slit_pending(self, kind):
        """The newest request's slice of this kind ("ts" or "sl") not on screen yet."""
        r = self._w.scheduler.slit
        return r.shown._shown.get(f"slit_{kind}", 0) < r.gens.current("slit")

    @property
    def _slitc_busy(self):
        r = self._w.scheduler.slit
        return r._busy or self._pf_slit_pending("ts") or self._pf_slit_pending("sl")

    @property
    def _slitc_blocks(self):
        return self._w.scheduler.slit.blocks

    @property
    def _slit_bands(self):
        """(kind, s, lambda or t) of the slices read without a per-pixel file for the slit shown, once on screen."""
        r = self._w.scheduler.slit
        return {(k, s, u): v for (pid, k, s, u), v in list(r._bands.items())
                if pid == r.path_id and not self._pf_slit_pending(k)}

    # the title bar's zoom: the geometry before it while zoomed (the prototype kept it on the window)
    @property
    def _crispex_unzoomed(self):
        bar = self.menuWidget()
        if bar is None:
            raise NotInExplorer("_crispex_unzoomed", "title")
        return bar.m.unzoomed

    @_crispex_unzoomed.setter
    def _crispex_unzoomed(self, value):
        bar = self.menuWidget()
        if bar is not None:
            bar.m.unzoomed = value
        elif value is not None:
            raise NotInExplorer("_crispex_unzoomed", "title")

    # the saved layout (ui.layout.LayoutStore): the prototype's names for it
    GEOMETRY_KEY = "app/{kind}/geometry"
    kind = property(lambda self: self.layout_store.kind)

    def restore(self, app):
        if self.layout_store.restore(self, app):
            self._sized = True

    def forget_layout(self):
        self.layout_store.forget()

    @property
    def _crispex_panel_edges(self):
        edges = getattr(self, "_panel_edges", None)
        if edges is None:
            raise AttributeError("_crispex_panel_edges")
        return edges

    # ------------------------------------------------------------------ axes and indices
    ta = property(lambda self: self._pf_roles.t)
    sa = property(lambda self: self._pf_roles.s)
    la = property(lambda self: self._pf_roles.l)
    nt = property(lambda self: self._pf_roles.nt)
    ns = property(lambda self: self._pf_roles.ns)
    nl = property(lambda self: self._pf_roles.nl)
    cube = property(lambda self: self._w.dataset)
    sp = property(lambda self: getattr(self._w.dataset, "pixel", None))
    ax = property(lambda self: self._w.dataset.axes)

    @property
    def idx(self):
        """One index per leading axis, in the cube's order (the prototype's idx)."""
        st = self._w.session.state
        n = len(self._w.dataset.shape) - 2
        return [getattr(st, self._pf_names[a]) if a in self._pf_names else 0 for a in range(n)]

    def _t(self):
        return self._w.session.state.t

    def _s(self):
        return self._w.session.state.s

    def _l(self):
        return self._w.session.state.l

    def _axis(self, a):
        return self._pf_names[a]

    def set_index(self, a, v):
        if a is not None:
            self._w.session.set_index(self._axis(a), int(v))

    def _step(self, a, d, wrap=False):
        if a is not None:
            self._w.session.step(self._axis(a), d, wrap=wrap)

    def _frame_index(self, t, s, l):  # noqa: E741
        """The frame at (t, s, lambda): its leading-axes index, which the cube's frame_offset takes."""
        from explorer.data.axes import frame_index

        return frame_index(len(self._w.dataset.shape) - 2, self._pf_roles, t=t, s=s, l=l)

    # ------------------------------------------------------------------ cursor
    @property
    def hover(self):
        return tuple(self._w.session.state.cursor)

    @hover.setter
    def hover(self, yx):                                # the tests set the cursor this way, then _update_cursor
        self._w.session.hover(*yx)

    @property
    def locked(self):
        return self._w.session.state.locked

    def set_locked(self, on):
        self._w.session.lock(bool(on))

    def _on_hover(self, y, x):
        """With a per-pixel file the prototype read the cursor's block inside _on_hover: its spectrum and lambda-t
        were on screen when it returned, and smoke.py's hover() relies on it (it waits only for the reader thread,
        without one). Explorer reads it on its I/O pool, so this waits for that result to be shown: the checks that
        follow see the new pixel, and the cursor's timing (perf: cursor update) counts the read, as the
        prototype's did. Without the wait, a cold block (20-50 ms on StorNext) made 'spectrum follows' compare the
        first pixel's spectrum with itself, or pass comparing it with an empty plot."""
        req0 = self._req
        self._w.session.hover(int(y), int(x))
        if self.sp is not None:
            from PySide6 import QtWidgets

            app = QtWidgets.QApplication.instance()
            q = time.perf_counter()
            # the read is asked on the loop's next turn, and not at all on padding or the same pixel
            while self._req == req0 and time.perf_counter() - q < HOVER_ASK_S:
                app.processEvents()
            while self._shown_req < self._req and time.perf_counter() - q < HOVER_WAIT_S:
                app.processEvents()

    def _update_cursor(self, changed=None):
        """The prototype's redraw of the cursor's panels, from the cursor as it is. Explorer's scheduler follows the
        session by itself; this asks it once more for the same pixel, which matters after conformance's reset: it
        forgets the y ranges the cursor grew (_yr) and redraws, so they grow again from that pixel. Without it the
        next pixel's spectrum was fitted from nothing ([2, 4] against the prototype's [0, 4] in
        separator_central_docks)."""
        self._w.scheduler._evaluate(self._w.session.state, {"cursor"})

    @property
    def _img(self):
        """The image of the frame the session is at. The prototype read it inside set_index (show_frame), so after a
        slider moved its _img was the new frame's; explorer reads it on its I/O pool, so a read still on its way is
        waited for here. Without it, 'λ slider changes the image' (20 ms after the move) failed on a cold frame
        (50-100 ms on StorNext)."""
        s = self._w.scheduler
        want = tuple(self._w.session.index())
        if s.img_idx is not None and tuple(s.img_idx) != want:
            from PySide6 import QtWidgets

            app = QtWidgets.QApplication.instance()
            end = time.perf_counter() + HOVER_WAIT_S
            while tuple(s.img_idx) != want and time.perf_counter() < end:
                app.processEvents()
        return s.img

    @property
    def _req(self):
        return self._w.scheduler.gens.current("cursor")

    @property
    def _shown_req(self):
        """The newest cursor result on screen, over the panels that are shown (the prototype sends both in one)."""
        sh = self._w.scheduler.shown._shown
        kinds = [k for k, d in (("spectra", self._w.spec_dock), ("lambda_t", self._w.lt_dock)) if d.isVisible()]
        return min((sh.get(k, 0) for k in kinds), default=self._req)

    # ------------------------------------------------------------------ toolbar, status
    @property
    def sliders(self):
        nav = self._w.nav
        return {a: nav.sliders[n] for a, n in self._pf_names.items() if a is not None and n in nav.sliders}

    @property
    def slider_labels(self):
        return {a: (self._w.nav.labels[n], self._w.nav.n[n]) for a, n in self._pf_names.items()
                if a is not None and n in self._w.nav.labels}

    nav_tb = property(lambda self: self._w.nav.tb)
    stokes_box = property(lambda self: self._w.nav.stokes)
    play = property(lambda self: self._w.nav.play)
    fps_box = property(lambda self: self._w.nav.fps)
    _timer = property(lambda self: self._w._play)
    reset_btn = property(lambda self: self._w.nav.reset)
    panels_btn = property(lambda self: self._w.nav.panels)
    st_pix = property(lambda self: self._w.status)

    # ------------------------------------------------------------------ image levels
    @property
    def fixed(self):
        """The fixed image levels for the Stokes shown, None when automatic (the prototype's self.fixed)."""
        lv = self._w.scheduler.levels
        return lv._fixed.get(self._w.session.state.s > 0)

    def _fit_image(self):
        self._w.view.show_all()

    # ------------------------------------------------------------------ spectra and lambda-t
    spec_plots = property(lambda self: self._w.spectra.plots)
    spec_curves = property(lambda self: self._w.spectra.curves)
    spec_w = property(lambda self: self._w.spectra.w)
    lt_w = property(lambda self: self._w.lambda_t.w)
    lt_img = property(lambda self: self._w.lambda_t.img)
    _xl_phys = property(lambda self: self._w.spectra.physical)
    _spec_xr = property(lambda self: self._w.spectra.x_range)
    _iscale = property(lambda self: self._w.spectra.iscale)
    @property
    def _yr(self):
        return list(self._w.scheduler.yrange.r)

    @_yr.setter
    def _yr(self, value):                               # forget the ranges the cursor grew (conformance's reset)
        yr = self._w.scheduler.yrange
        yr.r = [None] * yr.ns
    _ylast = property(lambda self: list(self._w.scheduler.yrange.last))
    _yfixed = property(lambda self: self._w.scheduler.yrange.fixed)
    _ysample = property(lambda self: self._w.scheduler.yrange.sample)
    _yquv = property(lambda self: self._w.scheduler.yrange.quv)
    _quv_started = property(lambda self: self._w.scheduler.yrange.quv_started)
    _quv_pending = property(lambda self: self._w.scheduler.yrange.quv_pending)

    def _yfit(self):
        """The prototype's refit at rest (_yfit): each plot to its profile, unless fixed."""
        self._w.scheduler.yrange.fit(force=False)


class BridgeView:
    """S.bridge as the prototype's tests read it (its app/xbridge.py), on explorer's bridge (platform.xbridge.Bridge):
    - wins: widget -> {"x": its X window (.id), "dirty": what Qt drew and X has not been sent yet};
    - inflight: pixel updates handed to the sender and not taken yet (the prototype's requests in flight);
    - _tick_run: called on each tick. The prototype's bridge ticked every 4 ms and the tests count ticks to see its
      loop alive after a click; explorer's flushes only when something is dirty, so an idle, healthy bridge would
      count none. Here a 4 ms timer calls it while the Qt loop runs and the bridge is not dead: the same proof the
      tests use without a bridge (their heartbeat), plus the bridge's own dead flag;
    - tx.display.data_send (in a failure's message only): its length is inflight, a count, not bytes.
    Anything else is the bridge's own attribute."""

    def __init__(self, bridge):
        from PySide6 import QtCore

        self._b = bridge
        self._tick_run = lambda: None
        self._beat = QtCore.QTimer(interval=4)
        self._beat.timeout.connect(lambda: None if bridge.dead else self._tick_run())
        self._beat.start()

    @property
    def wins(self):
        return {w: {"x": SimpleNamespace(id=rec.xid), "dirty": rec.dirty}
                for w, rec in self._b.windows.by_widget.items()}

    @property
    def inflight(self):
        return int(self._b.transport._pending)

    @property
    def tx(self):
        return SimpleNamespace(display=SimpleNamespace(data_send=[0] * self.inflight))

    def __getattr__(self, name):
        return getattr(self._b, name)


def adopt(shell):
    """shell becomes a ProtoViewer: the same object, its class a subclass of its own with the prototype's names. None
    of those names may already be the Shell's: they would change how it works."""
    names = {n for c in (ProtoViewer,) for n in vars(c) if not n.startswith("__")}
    names |= {"be", "stats", "fix", "_pf_roles", "_pf_names", "_pf_slit_ui"}
    names -= {"restore"}                                # QMainWindow has none; QWidget's restoreGeometry is not it
    clash = sorted(n for n in names if hasattr(type(shell), n) or n in vars(shell))
    if clash:
        raise RuntimeError(f"the prototype's names already on the Shell: {clash}")
    shell.__class__ = type("ProtoViewer", (ProtoViewer, type(shell)), {})
    shell._pf_adopt()
    return shell


def monitor_rect(app, point=None):
    """The usable rectangle of the monitor at point (default: the pointer): explorer's (platform.screens)."""
    from explorer.platform.screens import monitor_rect as explorer_monitor_rect

    return explorer_monitor_rect(app, point)


class _ViewerModule(SimpleNamespace):
    """viewer.SETTINGS is the file the tests keep the layout in: explorer's layout goes there (EXPLORER_LAYOUT)."""

    @property
    def SETTINGS(self):
        from explorer.ui.layout import layout_path

        return layout_path()

    @SETTINGS.setter
    def SETTINGS(self, path):
        from explorer.ui.layout import ENV

        os.environ[ENV] = str(path)


def viewer_module():
    """A stand-in for the prototype's app/viewer.py: the constants and helpers smoke.py reads from it."""
    from explorer.data.stats import nice_range
    from explorer.ui import docks

    class _ViewerMeta(type):
        def __getattr__(cls, name):
            raise NotInExplorer(f"Viewer.{name}", "slit" if "SLIT" in name else name)

    Viewer = _ViewerMeta("Viewer", (), {"FILL": docks.FILL, "SLIT_UI": "D"})
    return _ViewerModule(Viewer=Viewer, monitor_rect=monitor_rect, nice_range=nice_range, np=np)
