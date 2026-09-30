"""The bridge itself: the X connection of the interface thread, the tick that reads X events and hands repaints to
the sender, and what Qt tells about its windows (eventFilter). From the prototype's app/xbridge.py (XBridge); the
window half is in wm.py, the input half in qtinput.py, the pixels in transport.py, the clipboard in clipboard.py.

    b = Bridge()                    connect to $DISPLAY, before QApplication exists
    os.environ["QT_QPA_PLATFORM"] = b.qpa()     offscreen, with the X monitors as Qt screens, so window placement
                                    and popups follow the real monitors
    b.attach(app, window)           start mirroring, after window.show()
"""
import atexit
import json
import os
import sys
import tempfile
import time

from PySide6 import QtCore, QtGui, QtWidgets

from ..._name import APP_NAME
from . import xconn
from .clipboard import Clipboard
from .qtinput import Platform, QtInput, x_gone
from .transport import Knobs, Sender
from .wm import WindowManager

Qt = QtCore.Qt
MINIMIZED = Qt.WindowState.WindowMinimized


class Bridge(QtCore.QObject, WindowManager, QtInput):
    FULL_CHECK_S = 1.0          # every window is compared whole this often: anything Qt changed without telling us

    def __init__(self, knobs: Knobs | None = None):
        super().__init__()
        from Xlib import X, Xutil

        self.k = knobs or Knobs.from_env()
        self.X, self.Xutil = X, Xutil
        self.app = None
        self.ev = xconn.connect()                           # interface thread: windows, input events
        self.scr = self.ev.screen()
        self.depth = self.scr.root_depth
        self.WM_DELETE = self.ev.intern_atom("WM_DELETE_WINDOW")
        self.wins: dict = {}                                # Qt top-level widget -> its record (wm.py)
        self.by_xid: dict = {}
        self.own_frame: set = set()                         # windows with a title bar of ours: no manager's frame
        self.grab_target = None                             # widget holding the implicit mouse grab (legacy input)
        self.buttons = Qt.MouseButton.NoButton
        self._last_press = None                             # (button, X time, root x, y): double clicks (legacy)
        self.plat = Platform.load(self.k.legacy_input)      # Qt's platform input entry (None: the legacy path)
        self.clip: Clipboard | None = None
        self.xfocus, self._focus_known, self._focus_out_at, self._activate_t = None, False, None, 0.0
        self._repeat = self._mode_switch = None
        self._repeat_rd = None                              # the same, as _events reads the keys
        self.xtime = 0                                      # last X server time seen (selection ownership)
        self.dead = False                                   # the X display went away (_lost), or close()
        self._net_supported: set | None = None
        self._xcursors: dict = {}
        self._last_full = 0.0
        self.timer: QtCore.QTimer | None = None
        self.transport = Sender(xconn.connect(), self.depth, self.k)   # sender thread, its own connection: images only

    # ------------------------------------------------------------------ geometry
    def heads(self) -> list[tuple[int, int, int, int]]:
        """X monitors as (x, y, w, h) (xconn, cached); the whole screen when Xinerama says nothing."""
        return xconn.heads(self.ev) or [(0, 0, self.scr.width_in_pixels, self.scr.height_in_pixels)]

    def qpa(self) -> str:
        """QT_QPA_PLATFORM value: offscreen with one Qt screen per X monitor and no fake frame margins."""
        f = tempfile.NamedTemporaryFile("w", prefix=f"{APP_NAME}_xbridge_", suffix=".json", delete=False)
        json.dump(qpa_config(self.heads()), f)
        f.close()
        atexit.register(_remove_file, f.name)
        return f"offscreen:configfile={f.name}"

    def sync_cursor(self) -> None:
        """Tell Qt where the X pointer is (window placement uses the monitor under it)."""
        p = self.scr.root.query_pointer()
        QtGui.QCursor.setPos(p.root_x, p.root_y)

    # ------------------------------------------------------------------ windows
    def attach(self, app, window, own_frame: bool = False) -> None:
        """Start mirroring app's windows, window first. own_frame: window draws its own title bar, and asks the window
        manager for no frame (quartz-wm honours it)."""
        self.app = app
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(self.k.tick_ms)
        self.timer.timeout.connect(self._tick)
        self.own_frame = {window} if own_frame else set()
        # every Paint event of every widget, application-wide. Watching only each top-level's UpdateRequest and
        # grabbing the whole window measured no gain on Xvfb (29.1/29.9 against 30.0/28.0 fps), so this stays
        app.installEventFilter(self)
        self._add(window)
        # the keyboard to the new window, as a desktop gives it: launched from a terminal, the window opened without
        # focus and the first key press (Space to play) went to the terminal. Once the manager has taken the window in
        # (its MapRequest), else it may ignore the request
        QtCore.QTimer.singleShot(500, lambda: self.activate(window))
        # windows Qt already shows (floating docks of a saved layout appear before the bridge is attached, so their
        # Show event came too early and they never got an X window: visible to Qt, absent from the screen)
        for w in QtWidgets.QApplication.topLevelWidgets():
            if (w is not window and w.isVisible() and w not in self.wins
                    and w.windowType() not in (Qt.WindowType.Popup, Qt.WindowType.ToolTip)):
                self._add(w)
        try:
            self.clip = Clipboard(self)
        except Exception as e:                              # no clipboard across X: the rest still works
            print(f"[{APP_NAME}] no X clipboard: {e}", file=sys.stderr)
        self.timer.start()

    def eventFilter(self, obj, e):
        if self.dead:                                       # no X any more: windows close without talking to it
            return False
        t = e.type()
        E = QtCore.QEvent.Type
        if t == E.Paint:
            if isinstance(obj, QtWidgets.QWidget):
                top = obj.window()
                rec = self.wins.get(top)
                if rec is not None:
                    # the region, not its bounding rect: a crosshair move repaints two thin strips whose bounding rect
                    # is the whole image (26x more pixels)
                    reg = e.region()
                    if obj is not top:
                        reg = reg.translated(obj.mapTo(top, QtCore.QPoint(0, 0)))
                    rec["dirty"] += reg
        elif t in (E.Move, E.Resize, E.Hide) and isinstance(obj, QtWidgets.QWidget) and not obj.isWindow():
            # a child moved, resized or hidden: Qt can move its pixels inside the backing store without any paint
            # event (seen as stale regions on screen): its old and new places are dirty
            top = obj.window()
            rec = self.wins.get(top)
            par = obj.parentWidget()
            if rec is not None and par is not None:
                g = obj.geometry()
                if t == E.Move:
                    old_g = QtCore.QRect(e.oldPos(), g.size())
                elif t == E.Resize:
                    old_g = QtCore.QRect(g.topLeft(), e.oldSize())
                else:
                    old_g = g
                for rr in (g, old_g):
                    rec["dirty"] += QtCore.QRect(par.mapTo(top, rr.topLeft()), rr.size()) if par is not top else rr
        elif t == E.WindowStateChange and obj in self.wins and not self.wins[obj]["popup"]:
            # minimised or restored from Qt's side (a title bar, showNormal): ask the window manager, as xcb does
            rec, new, old = self.wins[obj], obj.windowState(), e.oldState()
            if new & MINIMIZED and not old & MINIMIZED and not rec.get("unmapped"):
                self.minimize(obj)
            elif old & MINIMIZED and not new & MINIMIZED and rec.get("unmapped"):
                rec["x"].map()                              # ICCCM: a client de-iconifies by mapping again
                self.ev.flush()
        elif t in (E.Show, E.Hide, E.Resize, E.Move) and isinstance(obj, QtWidgets.QWidget) and obj.isWindow():
            if t == E.Show and obj not in self.wins and self.wins:
                self._add(obj)
            elif t == E.Hide and obj in self.wins and len(self.wins) > 1:
                self._remove(obj)
            elif obj in self.wins and t in (E.Resize, E.Move):
                g = obj.geometry()
                rec = self.wins[obj]
                if g == rec.get("xg"):
                    pass                                    # X told us this geometry (_configured): no request back
                elif rec["popup"] or rec["qt_moves"]:       # override-redirect, or dragged by Qt: we place it
                    self._configure(rec, x=g.x(), y=g.y(), width=max(1, g.width()), height=max(1, g.height()))
                elif t == E.Resize:                         # managed: size only, the window manager owns the position
                    self._configure(rec, width=max(1, g.width()), height=max(1, g.height()))
                if t == E.Resize:
                    rec["dirty"] = QtGui.QRegion(obj.rect())
                self.ev.flush()
        return False

    # ------------------------------------------------------------------ the loop
    def _tick(self):
        """One pass of the bridge, and the way out when the X display goes away (XQuartz quit, ssh cut): the connection
        error was raised on every 4-ms tick, the process stayed alive at 79 % CPU and printed 324 000 tracebacks (24 MB)
        in 30 s, where xcb says "X11 connection broke" and exits in 1 s."""
        if self.dead:
            return
        try:
            if self.transport.error is not None:
                raise self.transport.error
            self._tick_run()
        except Exception as e:
            if not x_gone(e):
                raise
            self._lost(e)

    def _lost(self, e):
        self.dead = True
        if self.timer is not None:
            self.timer.stop()
        print(f"[{APP_NAME}] the X display went away ({type(e).__name__}: {e}); closing", file=sys.stderr, flush=True)
        # closing the windows runs their closeEvent (saving what they save); nothing more is sent to X
        app = QtWidgets.QApplication.instance()
        assert isinstance(app, QtWidgets.QApplication)
        app.setQuitOnLastWindowClosed(False)                # else closing the last window quits with 0 before exit(1)
        QtCore.QTimer.singleShot(0, lambda: (app.closeAllWindows(), app.exit(1)))

    def _tick_run(self):
        self._events()
        self._sync_cursors()
        if self.plat is not None:
            self._sync_activation()
        now = time.perf_counter()
        if self.k.diff and now - self._last_full > self.FULL_CHECK_S:
            self._last_full = now                           # anything Qt changed without telling us gets resent
            for w, rec in self.wins.items():
                rec["dirty"] += QtGui.QRegion(w.rect())
        if self.transport.inflight < self.k.inflight:
            for w, rec in self.wins.items():
                if not rec.get("unmapped"):
                    self._shape(w, rec)
            self.transport.grab(self.wins)

    def _events(self):
        X, motion = self.X, None
        evs = []
        while self.ev.pending_events():
            evs.append(self.ev.next_event())
        for i, e in enumerate(evs):
            t = e.type
            if t == X.MappingNotify:                        # keyboard layout changed: python-xlib caches the keymap
                self.ev.refresh_keyboard_mapping(e)
                self._mode_switch = None
                continue
            if self.clip is not None and self.clip.handles(e):
                continue
            w = self.by_xid.get(getattr(e, "window", None) and e.window.id)
            if w is None:
                continue
            born = self.wins[w].get("born")
            if born is not None and 0 < ((born - e.sequence_number) & 0xffff) < 0x8000:
                # generated before this window existed: python-xlib reuses the id of a window destroyed a moment ago,
                # and the old window's UnmapNotify minimised and hid the new one (a panel re-created when a drag ends
                # lost its X window in 2 of 3 runs)
                continue
            if hasattr(e, "time"):
                self.xtime = e.time
            # input reaches Qt through _later, never from inside this tick
            if t == X.MotionNotify:
                motion = (w, e)                             # only the last one of this pass matters
            elif t in (X.ButtonPress, X.ButtonRelease):
                if motion:
                    self._later(self._motion, *motion)
                    motion = None
                self._later(self._button, w, e)
            elif t in (X.KeyPress, X.KeyRelease):
                if motion:
                    self._later(self._motion, *motion)
                    motion = None
                nxt = evs[i + 1] if i + 1 < len(evs) else None
                # X auto-repeat sends release + press with one timestamp: xcb flags both as repeats. Worked out here,
                # in reading order, and handed to _key with its event (the keys are delivered later)
                r = e.detail if (t == X.KeyRelease and nxt is not None and nxt.type == X.KeyPress
                                 and nxt.detail == e.detail and nxt.time == e.time) else \
                    (self._repeat_rd if t == X.KeyPress else None)
                self._repeat_rd = None if t == X.KeyPress else r          # _key clears it after a press
                self._later(self._key_repeat, w, e, r)
            elif t in (X.EnterNotify, X.LeaveNotify):
                if motion:
                    self._later(self._motion, *motion)
                    motion = None
                self._later(self._crossing, w, e)
            elif t == X.Expose:                             # the X server lost those pixels: resend them whole
                r = QtCore.QRect(e.x, e.y, e.width, e.height)
                self.wins[w]["dirty"] += r
                self.wins[w]["force"] = (self.wins[w].get("force") or QtGui.QRegion()) + r
            elif t == X.ConfigureNotify:
                self._configured(w, e)
            elif t in (X.UnmapNotify, X.MapNotify) and not self.wins[w]["popup"]:
                self._mapped(w, t == X.MapNotify)
            elif t == X.ClientMessage and e.data[1][0] == self.WM_DELETE:
                self._later(w.close)
            elif t in (X.FocusIn, X.FocusOut) and e.detail != X.NotifyPointer:
                self._later(self._x_focus, w, t == X.FocusIn)   # in order with the clicks (focus by click)
        if motion:
            self._later(self._motion, *motion)

    # ------------------------------------------------------------------ report
    @property
    def stats(self) -> dict:
        return self.transport.stats

    @property
    def inflight(self) -> int:
        return self.transport.inflight

    @property
    def busy(self) -> bool:
        return self.transport.busy

    @property
    def grey_on(self) -> bool:
        return self.transport.grey_on

    def summary(self) -> dict:
        return self.transport.summary()

    def describe(self) -> str:
        d = self.summary()
        return (f"X11 bridge: {d['frames']} updates, send {d['send_ms_median']} ms median, {d['MBps']} MB/s"
                if d["frames"] else "X11 bridge: nothing sent yet")

    def close(self) -> None:
        """Stop mirroring and close both X connections (the windows go with them)."""
        if self.timer is not None:
            self.timer.stop()
        self.dead = True
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        if self.clip is not None:
            self.clip.close()
        self.transport.close()
        for d in (self.ev, self.transport.tx):
            try:
                d.close()
            except Exception:
                pass


def _remove_file(name) -> None:
    if os.path.exists(name):
        os.remove(name)


def qpa_config(heads) -> dict:
    """Qt's offscreen configuration: one screen per X monitor, 96 dpi, dpr 1, no fake frame margins."""
    return dict(windowFrameMargins=False,
                screens=[dict(name=f"X{i}", x=x, y=y, width=w, height=h, logicalDpi=96, logicalBaseDpi=96, dpr=1)
                         for i, (x, y, w, h) in enumerate(heads)])
