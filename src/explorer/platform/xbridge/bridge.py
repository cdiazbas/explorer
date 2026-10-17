"""The bridge: Qt renders offscreen and its top-level windows are shown on an X display through X windows of their
own (transport.py sends the pixels, windows.py talks to the window manager, qtinput.py brings the input back,
clipboard.py joins the clipboards).

Two stages:
- XLink.open(), before Qt exists: the X connection, and everything the bridge will need asked in one go (atoms,
  extensions, keyboard, the monitors, the pointer); only the monitors are waited for, as Qt's screens come from
  them. The sender thread connects and loads its kernels meanwhile.
- Bridge(link), once the QApplication exists: X events reach Qt from the reader thread through a queued signal,
  one at a time, so an event handler that starts a nested event loop (a menu's exec) does not stop the others
  (audit F45: the prototype's 4-ms timer did not fire inside such a loop and the viewer hung). Nothing polls: X
  events wake the interface, repaints schedule a grab, the sender says when it can take the next one.
"""
import atexit
import json
import os
import struct
import sys
import tempfile
import time
from collections.abc import Callable
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from ...obs import get_logger
from . import clipboard as clip_mod
from . import keys
from . import trace as trace_mod
from . import xproto as X
from .qtinput import QtInput
from .transport import Transport
from .windows import ATOMS, MOVERESIZE, MOVERESIZE_MOVE, Windows, XWin

log = get_logger("platform.xbridge")
Qt, E = QtCore.Qt, QtCore.QEvent
MAX_RECTS = 8                                           # pieces of a repaint grabbed apart; more: one bounding box
MAX_PIECES = 16                                         # widgets' repaints shown apart in one update; more: the rest
#                                                         together, after them
CHECK_S = 1.0                                           # every window grabbed whole this often: the tile comparison
#                                                         sends only what Qt changed without a Paint event
DRAWN, PAINTED = "drawn", "painted"                     # a frame of the viewer's panels before it is grabbed
FRAMES_AHEAD = 1                                        # frames of the viewer's panels on the link at a time
EXTENSIONS = ("XINERAMA", "SHAPE", "XFIXES", "RENDER", "Apple-WM")


class XLink:
    """The X connection before Qt: opened, asked, and the sender started."""

    def __init__(self, display: str | None = None):
        t0 = time.perf_counter()
        self.display = display or os.environ.get("DISPLAY", "")
        self.events = X.EventQueue(lambda: None)        # the bridge takes over the wake-up
        self.lost: BaseException | None = None
        self.ready_cb: Callable[[], None] | None = None
        self.trace = trace_mod.from_env()                # EXPLORER_BRIDGE_TRACE=1: what goes to X, per window
        self.c = X.Connection(self.display, name="xbridge-ctl", on_event=self.events.put,
                              on_error=self._error, on_lost=self._lost)
        self.connect_s = time.perf_counter() - t0
        self.transport = Transport(self.display, on_ready=self._ready, on_error=self._lost, trace=self.trace)
        c = self.c
        ext_cookies = {}
        for n in EXTENSIONS:                            # sent together; one round trip for all
            b = n.encode()
            ext_cookies[n] = c.request(98, 0, struct.pack("<HH", len(b), 0) + b, reply=True)
        names = ATOMS + clip_mod.NAMES
        self.atom_cookies = {n: c.intern_atom(n) for n in dict.fromkeys(names)}
        self.kbd = c.keyboard_mapping()
        self.modmap = c.modifier_mapping()
        self.pointer = c.query_pointer(c.screen.root)
        for n, ck in ext_cookies.items():
            r = ck.result()                             # type: ignore[union-attr]
            c._ext[n] = (r[9], r[10], r[11]) if r[8] else None
        self.heads = c.xinerama_screens() or [(0, 0, c.screen.width, c.screen.height)]
        self.open_s = time.perf_counter() - t0

    @classmethod
    def open(cls, display: str | None = None) -> "XLink":
        return cls(display)

    def _ready(self):
        cb = self.ready_cb
        if cb is not None:
            cb()

    def _error(self, err):
        log.debug("X error on the control connection: %s", err)
        if self.trace is not None:
            self.trace.error("ctl", err)

    def _lost(self, e):
        self.lost = e
        self.events.put(None)                           # wakes the interface, which closes

    def qpa(self) -> str:
        """QT_QPA_PLATFORM: offscreen, one Qt screen per X monitor, no fake frame margins; Qt's global coordinates
        are then X root coordinates."""
        scr = self.c.screen
        dpi = round(scr.width / (scr.width_mm / 25.4)) if scr.width_mm else 96
        cfg = dict(windowFrameMargins=False,
                   screens=[dict(name=f"X{i}", x=x, y=y, width=w, height=h, logicalDpi=96, logicalBaseDpi=96,
                                 physicalDpi=dpi, dpr=1) for i, (x, y, w, h) in enumerate(self.heads)])
        f = tempfile.NamedTemporaryFile("w", prefix="xbridge_", suffix=".json", delete=False)
        json.dump(cfg, f)
        f.close()

        def remove():
            if os.path.exists(f.name):
                os.remove(f.name)
        atexit.register(remove)
        return f"offscreen:configfile={f.name}"


class Bridge(QtCore.QObject):
    _wake = QtCore.Signal()
    _call = QtCore.Signal(object, object)
    _sender_ready = QtCore.Signal()
    _repainted = QtCore.Signal()

    def __init__(self, link: XLink, app: QtWidgets.QApplication):
        super().__init__()
        self.link, self.app, self.c = link, app, link.c
        self.dead = False
        self._wake.connect(self._drain, Qt.ConnectionType.QueuedConnection)
        self._call.connect(self._run_call, Qt.ConnectionType.QueuedConnection)
        self._sender_ready.connect(self._flush, Qt.ConnectionType.QueuedConnection)
        self._repainted.connect(self._flush, Qt.ConnectionType.QueuedConnection)
        link.events._wake = self._wake.emit
        link.ready_cb = self._sender_ready.emit
        self.transport = link.transport
        self.windows = Windows(self.c, on_destroyed=lambda rec: self.transport.forget(rec.xid))
        self.trace = link.trace
        self.windows.trace = self.trace
        self.windows.start({n: link.atom_cookies[n] for n in ATOMS})
        self.keymap: keys.Keymap | None = None
        try:
            self.keymap = keys.Keymap.from_replies(self.c.setup.min_keycode, link.kbd.result(), link.modmap.result())
        except (X.XError, TimeoutError) as e:
            log.warning("no keyboard map from the X server (%s): keys will not reach the viewer", e)
        self.input = QtInput(lambda: self.keymap, self._inside_qt_window)
        self.clip: clip_mod.Clipboard | None = None
        try:
            self.clip = clip_mod.Clipboard(self.c, {n: link.atom_cookies[n] for n in clip_mod.NAMES},
                                           lambda: self.windows.xtime, self.post)
            # a server time for what asks for one (activation, selection ownership) before any input came
            self.c.change_property(self.clip.win, self.windows.atoms["XBRIDGE_TIME"], X.ATOM_STRING, 8, b"",
                                   X.PropModeAppend)
            self.c.flush()
        except (X.XError, TimeoutError, RuntimeError) as e:
            log.warning("no X clipboard: %s", e)
        try:
            p = link.pointer.result()
            QtGui.QCursor.setPos(*struct.unpack_from("<hh", p, 16))     # windows open on the monitor under it
        except (X.XError, TimeoutError):
            pass
        self._flush_posted = False                      # a grab is queued (_schedule)
        # the viewer's panels as frames (screen()): the one being drawn (None, DRAWN, PAINTED), those on the link
        self._frame: str | None = None
        self._frames_out: set[int] = set()
        self._frame_n = 0
        self._frame_shown: list = []
        self._check = QtCore.QTimer(self)
        self._check.setInterval(int(CHECK_S * 1000))
        self._check.timeout.connect(self._check_all)
        self._repeat = None                             # keycode of an auto-repeat release whose press comes next
        self.main: QtWidgets.QWidget | None = None
        self.stats: dict[str, Any] = dict(grabs=0, grab_ms=[], x_events=0, flushes=0, applied=0)
        app.installEventFilter(self)
        app.aboutToQuit.connect(self.close)

    # ---------------------------------------------------------------- windows
    def attach(self, window: QtWidgets.QWidget) -> None:
        """Show window (already shown by Qt) and any other visible top-level on X, and give window the keyboard."""
        self.main = window
        for w in QtWidgets.QApplication.topLevelWidgets():
            if w.isVisible() and self.windows.get(w) is None and w.windowType() not in (
                    Qt.WindowType.Popup, Qt.WindowType.ToolTip, Qt.WindowType.Desktop):
                self._add(w)
        rec = self.windows.get(window)
        if rec is not None:
            rec.activate_on_map = True
        self._check.start()
        self._schedule()
        self._drain()                                   # anything that came before the bridge took over
        if self.trace is not None:
            for k, s in enumerate(self.trace.probes):
                QtCore.QTimer.singleShot(int(s * 1000), lambda k=k: self._probe(k))

    def _add(self, w: QtWidgets.QWidget) -> XWin:
        rec = self.windows.create(w)
        rec.dirty = QtGui.QRegion(w.rect())
        self._schedule()
        return rec

    def _remove(self, w: QtWidgets.QWidget) -> None:
        self.windows.destroy(w)

    def _inside_qt_window(self, x: int, y: int) -> bool:
        return any(r.w.isVisible() and r.w.geometry().contains(x, y) for r in self.windows)

    def activate(self, w: QtWidgets.QWidget) -> None:
        rec = self.windows.get(w)
        if rec is not None and not self.dead:
            self.windows.activate(rec)

    def minimize(self, w: QtWidgets.QWidget) -> None:
        rec = self.windows.get(w)
        if rec is not None and not self.dead:
            self.windows.minimize(rec)

    def moveresize(self, w: QtWidgets.QWidget, edges=None) -> bool:
        """Let the window manager move w (edges None) or resize it by these Qt edges, from the press now held
        (windows.moveresize); False when it cannot: the caller does it. Qt is then given the release the manager
        takes (qtinput.handed_to_manager)."""
        rec = self.windows.get(w)
        held = self.input.held()
        if rec is None or self.dead or held is None:
            return False
        if edges is None:
            direction: int | None = MOVERESIZE_MOVE
        else:
            ed = Qt.Edge
            direction = MOVERESIZE.get((bool(edges & ed.TopEdge), bool(edges & ed.LeftEdge),
                                        bool(edges & ed.RightEdge), bool(edges & ed.BottomEdge)))
        if direction is None:
            return False
        (x, y), button = held
        if not self.windows.moveresize(rec, x, y, direction, button):
            return False
        self.post(self.input.handed_to_manager, w)      # after the press that asked has returned
        return True

    # ---------------------------------------------------------------- Qt events
    def eventFilter(self, obj, e) -> bool:
        if self.dead:
            return False
        t = e.type()
        if t == E.Type.MouseMove and isinstance(obj, QtGui.QWindow) and self.input.is_own_synthetic_move(e):
            return True                                 # offscreen's answer to our setPos, not input (qtinput)
        if t == E.Type.Paint:
            if isinstance(obj, QtWidgets.QWidget):
                top = obj.window()
                rec = self.windows.get(top)
                if rec is not None:
                    # the region, not its bounding rect: a crosshair move repaints two thin strips whose bounding
                    # rect is the whole image (26x more pixels, measured in the prototype)
                    reg = e.region()
                    if obj is not top:
                        reg = reg.translated(obj.mapTo(top, QtCore.QPoint(0, 0)))
                    rec.dirty += reg
                    if len(rec.pieces) < MAX_PIECES:
                        rec.pieces.append(reg)
                    if self._frame == DRAWN:
                        self._frame = PAINTED
                    self._schedule()
            return False
        if t not in (E.Type.Show, E.Type.Hide, E.Type.Move, E.Type.Resize, E.Type.WindowStateChange,
                     E.Type.WindowTitleChange, E.Type.WindowIconChange, E.Type.PaletteChange) \
                or not isinstance(obj, QtWidgets.QWidget):
            return False
        if not obj.isWindow():
            if t in (E.Type.Move, E.Type.Resize, E.Type.Hide):
                self._child_moved(obj, e, t)
            return False
        rec = self.windows.get(obj)
        if t in (E.Type.Show, E.Type.Hide) and e.spontaneous():
            return False                                # minimised or restored, not shown or hidden by the program
        if t == E.Type.Show:
            if rec is None and self.main is not None and obj.windowType() != Qt.WindowType.Desktop:
                self._add(obj)
        elif t == E.Type.Hide:
            if rec is not None:
                self._remove(obj)
        elif rec is None:
            pass
        elif t in (E.Type.Resize, E.Type.Move):
            self.windows.qt_geometry(rec)
            if t == E.Type.Resize:
                rec.dirty = QtGui.QRegion(obj.rect())
                self._schedule()
        elif t == E.Type.WindowStateChange:
            self._state_changed(rec, e.oldState(), obj.windowState())
        elif t == E.Type.WindowTitleChange and not rec.popup:
            self.windows.set_title(rec)
            self.c.flush()
        elif t == E.Type.WindowIconChange and not rec.popup:
            # its own icon, or the application's set after the window was made (QApplication.setWindowIcon tells
            # every top-level so)
            self.windows.set_icon(rec)
            self.c.flush()
        elif t == E.Type.PaletteChange:
            # a change of theme reaches every top-level so (QApplication.setPalette), and the glass look's colour of
            # the window its own (setPalette)
            self.windows.set_background(rec)
            self.c.flush()
        return False

    def _child_moved(self, obj, e, t) -> None:
        """A child moved, resized or hid: Qt can move its pixels in the backing store without a Paint event (stale
        regions on screen, seen in the prototype): its old and new places are dirty."""
        rec = self.windows.get(obj.window())
        par = obj.parentWidget()
        if rec is None or par is None:
            return
        top = rec.w
        g = obj.geometry()
        if t == E.Type.Move:
            old = QtCore.QRect(e.oldPos(), g.size())
        elif t == E.Type.Resize:
            old = QtCore.QRect(g.topLeft(), e.oldSize())
        else:
            old = g
        for r in (g, old):
            rec.dirty += QtCore.QRect(par.mapTo(top, r.topLeft()), r.size()) if par is not top else r
        self._schedule()

    def _state_changed(self, rec: XWin, old, new) -> None:
        """Minimised, maximised or restored from Qt's side: asked of the window manager, as xcb does. Not when the
        change came from X."""
        if rec.popup or rec.state_from_x:
            return
        M, Z = Qt.WindowState.WindowMinimized, Qt.WindowState.WindowMaximized
        if new & M and not old & M and not rec.iconic:
            self.windows.minimize(rec)
        elif old & M and not new & M and rec.iconic:
            self.c.map_window(rec.xid)                  # ICCCM: a client de-iconifies by mapping again
            self.c.flush()
        if bool(new & Z) != bool(old & Z):
            self.windows.set_net_state(rec, bool(new & Z), "_NET_WM_STATE_MAXIMIZED_VERT",
                                       "_NET_WM_STATE_MAXIMIZED_HORZ")

    # ---------------------------------------------------------------- pixels
    def _schedule(self) -> None:
        """A grab queued behind the events posted before it. A 0-ms timer instead also waited for the events posted
        after the repaint: a panel repainting its slices three times per pointer move kept a line painted before
        them off the screen until they were done, and the line then went out in one update with them."""
        if not self._flush_posted:
            self._flush_posted = True
            self._repainted.emit()

    def _check_all(self) -> None:
        """Grab each window whole when nothing is pending for it: what the comparison then finds is what Qt changed
        without a Paint event (counted as check_hits)."""
        for rec in self.windows:
            if rec.dirty.isEmpty() and not rec.iconic:
                rec.dirty = QtGui.QRegion(rec.w.rect())
                rec.check = True
        self._schedule()

    def _flush(self) -> None:
        """Grab what Qt repainted and hand it to the sender, if it can take it; otherwise it asks again when free."""
        self._flush_posted = False
        if self.dead or not self.transport.ready.is_set():
            return
        t0 = time.perf_counter()
        items = []
        for rec in self.windows:
            w = rec.w
            self.windows.sync_shape(rec)
            if rec.iconic:                              # sent in full when mapped again
                continue
            d = rec.dirty.intersected(QtGui.QRegion(w.rect()))
            rec.dirty = QtGui.QRegion()
            painted, rec.pieces = rec.pieces, []
            check, rec.check = rec.check, False
            if d.isEmpty():
                continue
            W, H = w.width(), w.height()
            if self.trace is not None:
                b = d.boundingRect()
                self.trace.write("GRAB", rec.xid, f"{len(list(d))} rects in ({b.x()}, {b.y()}, {b.width()}, "
                                                  f"{b.height()}) of {W}x{H}, {len(painted)} pieces"
                                                  f"{', the periodic check' if check else ''}")
            for piece in _pieces(d, painted):
                rects = list(piece)
                if len(rects) > MAX_RECTS:
                    rects = [piece.boundingRect()]
                for i, r in enumerate(rects):
                    img = self._grab(w, r)
                    if img is None:
                        if w.isVisible():
                            rec.dirty += r              # no backing store yet (just shown)
                        if self.trace is not None:
                            self.trace.write("GRAB", rec.xid, "nothing: no backing store yet" if w.isVisible()
                                             else "nothing: hidden")
                        continue
                    a = _pixels(img)
                    items.append((rec.xid, W, H, r.x(), r.y(), a, img, False, check, i == len(rects) - 1))
        if items:
            then = None
            if self._frame == PAINTED:                  # the panels drawn go in this update
                self._frame_n += 1
                n, self._frame = self._frame_n, None
                self._frames_out.add(n)
                then = lambda n=n: self._call.emit(self._frame_confirmed, (n,))    # noqa: E731
            self.transport.submit(items, then)
            self.stats["flushes"] += 1
            self.stats["grab_ms"].append((time.perf_counter() - t0) * 1e3)
            if len(self.stats["grab_ms"]) > 1000:
                del self.stats["grab_ms"][:500]
        self._sync_cursors()

    def _grab(self, w: QtWidgets.QWidget, r: QtCore.QRect):
        scr = w.screen()
        if scr is None:
            return None
        img = scr.grabWindow(w.winId(), r.x(), r.y(), r.width(), r.height()).toImage()
        if img.isNull():
            return None
        if img.format() != QtGui.QImage.Format.Format_RGB32:
            img = img.convertToFormat(QtGui.QImage.Format.Format_RGB32)
        self.stats["grabs"] += 1
        return img

    def _sync_cursors(self) -> None:
        oc = QtGui.QGuiApplication.overrideCursor()
        for rec in self.windows:
            if oc is not None:
                shape = oc.shape()
            else:
                h = rec.w.windowHandle()
                shape = h.cursor().shape() if h is not None else Qt.CursorShape.ArrowCursor
            self.windows.sync_cursor(rec, shape)

    # ---------------------------------------------------------------- the viewer's pace (screen())
    def frame_behind(self) -> bool:
        """The panels drawn last are on their way to the server, not yet confirmed: what is drawn now would wait
        behind them on the link."""
        return len(self._frames_out) >= FRAMES_AHEAD

    def frame_drawn(self) -> None:
        if self._frame is None:
            self._frame = DRAWN

    def frame_when_shown(self, fn) -> None:
        self._frame_shown.append(fn)

    def _frame_confirmed(self, n: int) -> None:
        self._frames_out.discard(n)
        if self.frame_behind():
            return
        fns, self._frame_shown = self._frame_shown, []
        for fn in fns:
            fn()

    # ---------------------------------------------------------------- X events
    def post(self, fn, *args) -> None:
        """Run fn(*args) on the interface thread (from the reader thread)."""
        self._call.emit(fn, args)

    def _run_call(self, fn, args) -> None:
        if not self.dead:
            fn(*args)

    def _drain(self) -> None:
        """Handle the X events that came, one at a time. Before each one the queue wakes the interface again if more
        are left: a handler that runs a nested event loop (a menu, a dialog) leaves the rest to that loop, in order."""
        q = self.link.events
        while not self.dead:
            raw = q.take()
            if raw is None:
                if self.link.lost is not None:
                    self._lost(self.link.lost)
                break
            q.rewake()
            try:
                self._event(raw)
            except ConnectionError as e:
                self._lost(e)
                break
        if not self.dead:
            self._sync_cursors()

    def _event(self, raw: bytes) -> None:
        e = X.decode_event(raw)
        self.stats["x_events"] += 1
        code = e.code
        t = getattr(e, "time", 0)
        if t:
            self.windows.xtime = t
        if code == X.MappingNotify:
            if e.request in (0, 1):                     # modifiers or keyboard
                def got(r, err):
                    if err is None:
                        self.post(self._keymap, r)
                self.c.keyboard_mapping().then(got)
            return
        if self.clip is not None and self.clip.handles(e):
            return
        rec = self.windows.by_xid.get(getattr(e, "window", 0))
        if code == X.PropertyNotify:
            self._property(rec, e)
            return
        if rec is None:
            return
        w = rec.w
        if code == X.MotionNotify:
            nxt = self.link.events.peek()
            if nxt is not None and nxt[0] & 0x7F == X.MotionNotify and nxt[12:16] == raw[12:16]:
                return                                  # only the last of a run of moves matters
            self.input.motion(w, e)
        elif code in (X.ButtonPress, X.ButtonRelease):
            self.input.button(w, e)
        elif code in (X.KeyPress, X.KeyRelease):
            self._key(w, e)
        elif code in (X.EnterNotify, X.LeaveNotify):
            self.input.crossing(w, e)
        elif code == X.Expose:
            if self.trace is not None:
                self.trace.write("EXPOSE", rec.xid, f"({e.x}, {e.y}, {e.width}, {e.height}) count {e.count}")
                self.trace.count(rec.xid, exposes=1)
            self.transport.expose(rec.xid, e.x, e.y, e.width, e.height)
        elif code == X.ConfigureNotify:
            self.windows.configured(rec, e, self._apply_geometry)
        elif code == X.ReparentNotify:
            rec.reparented = e.parent != self.c.screen.root
            if self.trace is not None:
                root = "" if rec.reparented else " (the root)"
                self.trace.write("REPARENT", rec.xid, f"into {e.parent:#x}{root}")
        elif code == X.MapNotify:
            if self.trace is not None:
                self.trace.write("MAPPED", rec.xid, "")
            self._mapped(rec, True)
        elif code == X.UnmapNotify:
            if self.trace is not None:
                self.trace.write("UNMAPPED", rec.xid, "")
            self._mapped(rec, False)
        elif code == X.ClientMessage:
            self._client_message(rec, e)
        elif code in (X.FocusIn, X.FocusOut):
            self._focus(rec, e)

    def _key(self, w, e) -> None:
        # X auto-repeat sends release + press with one time: both are repeats, as xcb reports them
        rep = False
        if e.code == X.KeyRelease:
            nxt = self.link.events.peek()
            if nxt is not None and nxt[0] & 0x7F == X.KeyPress and nxt[1] == e.detail and \
                    struct.unpack_from("<I", nxt, 4)[0] == e.time:
                rep = True
                self._repeat = e.detail
        elif self._repeat == e.detail:
            rep = True
            self._repeat = None
        else:
            self._repeat = None
        self.input.key(w, e, rep)

    def _keymap(self, reply: bytes) -> None:
        mods = None
        try:
            mods = self.c.modifier_mapping().result(5.0)
        except (X.XError, TimeoutError):
            pass
        self.keymap = keys.Keymap.from_replies(self.c.setup.min_keycode, reply, mods)

    def _property(self, rec, e) -> None:
        A = self.windows.atoms
        if e.atom == A["XBRIDGE_TIME"]:
            for r in self.windows:                      # the launch time, for the manager's focus rules
                if not r.popup:
                    self.c.change_property(r.xid, A["_NET_WM_USER_TIME"], X.ATOM_CARDINAL, 32, [e.time])
            self.c.flush()
        elif rec is not None and e.atom == A["_NET_WM_STATE"] and not rec.popup:
            def got(r, err):
                if err is None:
                    self.post(self._net_state, rec, r)
            self.c.get_property(rec.xid, A["_NET_WM_STATE"], X.ATOM_ATOM).then(got)
        elif rec is not None and e.atom == A["WM_STATE"] and not rec.popup:
            def got_state(r, err):
                if err is None:
                    self.post(self._wm_state, rec, r)
            self.c.get_property(rec.xid, A["WM_STATE"], A["WM_STATE"]).then(got_state)

    def _net_state(self, rec: XWin, reply: bytes) -> None:
        """The manager maximised or restored the window (its own button, a double click on its frame): Qt's state
        follows, without asking back."""
        _t, fmt, val, _ = self.c.property_value(reply)
        st = set(struct.unpack(f"<{len(val) // 4}I", val)) if fmt == 32 else set()
        A = self.windows.atoms
        maxed = A["_NET_WM_STATE_MAXIMIZED_VERT"] in st and A["_NET_WM_STATE_MAXIMIZED_HORZ"] in st
        cur = rec.w.windowState()
        want = (cur | Qt.WindowState.WindowMaximized) if maxed else (cur & ~Qt.WindowState.WindowMaximized)
        if want != cur and rec.w in [r.w for r in self.windows]:
            self._set_state_from_x(rec, want)

    def _set_state_from_x(self, rec: XWin, state) -> None:
        rec.state_from_x = True
        try:
            g = rec.w.geometry()
            rec.w.setWindowState(state)
            if rec.xg is not None and rec.w.geometry() != rec.xg:
                rec.w.setGeometry(rec.xg)               # X decides the geometry; Qt's maximise would move it
            elif rec.xg is None and rec.w.geometry() != g:
                rec.w.setGeometry(g)
        finally:
            rec.state_from_x = False

    def _probe(self, k: int) -> None:
        """Trace: each window's pixels as Qt has them now, to be read back from X and compared (trace.Trace.probed),
        and where it does not show: outside its shape, and under another window of ours (X may hold that one's
        pixels there)."""
        import numpy as np

        if self.dead:
            return
        recs = [r for r in self.windows if not r.iconic and r.w.isVisible()]
        for rec in recs:
            img = self._grab(rec.w, rec.w.rect())
            if img is None:
                continue
            g = rec.w.geometry()
            hidden = np.zeros((g.height(), g.width()), bool)
            if rec.mask is not None and not rec.mask.isEmpty():
                hidden[:] = True
                for r in rec.mask:
                    hidden[r.y():r.y() + r.height(), r.x():r.x() + r.width()] = False
            for o in recs:
                if o is not rec:
                    i = o.w.geometry().intersected(g).translated(-g.x(), -g.y())
                    if not i.isEmpty():
                        hidden[i.y():i.y() + i.height(), i.x():i.x() + i.width()] = True
            self.transport.probe(k, rec.xid, _pixels(img).copy(), hidden)

    def _apply_geometry(self, rec: XWin, x: int, y: int, w: int, h: int, from_reader: bool = False) -> None:
        if from_reader:
            self.post(self._apply_geometry, rec, x, y, w, h)
            return
        if self.windows.get(rec.w) is not rec:
            return
        self.stats["applied"] += 1
        # what X has now: Qt taking it must not become a request of ours (late notices of a burst of requests set
        # Qt back, and Qt's resize asked X for that old size again: audit F23c)
        rec.xg = QtCore.QRect(x, y, w, h)
        g = rec.w.geometry()
        # Qt's resize and move, one after the other, ask X nothing: between the two Qt had X's new size at its old
        # place, which was asked of X as a new request (after an edge resize through XQuartz, the old size asked
        # again while the new one was on its way: the window went back and forth between the two, each size sent
        # whole). What Qt would not take (its minimum size, a popup's own place) is asked once, after
        rec.taking = True
        try:
            if (w, h) != (g.width(), g.height()):
                rec.w.resize(w, h)
            if (x, y) != (g.x(), g.y()) and not rec.popup:
                rec.w.move(x, y)
        finally:
            rec.taking = False
        self.windows.qt_geometry(rec)

    def _mapped(self, rec: XWin, mapped: bool) -> None:
        """Mapped: the window can take the focus, and the one shown first asks for it. Map and unmap do not say
        iconified: a manager that reparents the window into a new frame (metacity, when maximising) unmaps and maps
        it (the prototype read iconify from them and hid the viewer's window); WM_STATE says it (_wm_state)."""
        if mapped:
            rec.viewable = True
            if rec.activate_on_map:
                rec.activate_on_map = False
                self.windows.activate(rec)

    def _wm_state(self, rec: XWin, reply: bytes) -> None:
        """The manager iconified or restored a window of ours (ICCCM WM_STATE: 3 iconic, 1 normal): Qt is told, as
        xcb tells it, and nothing is sent to an iconified window."""
        _t, fmt, val, _ = self.c.property_value(reply)
        if fmt != 32 or len(val) < 4 or self.windows.get(rec.w) is not rec:
            return
        iconic = struct.unpack_from("<I", val)[0] == 3
        if iconic == rec.iconic:
            return
        rec.iconic = iconic
        st = rec.w.windowState()
        if not iconic:
            rec.dirty = QtGui.QRegion(rec.w.rect())
            self._schedule()
            if st & Qt.WindowState.WindowMinimized:
                self._set_state_from_x(rec, st & ~Qt.WindowState.WindowMinimized)
        elif not st & Qt.WindowState.WindowMinimized:
            self._set_state_from_x(rec, st | Qt.WindowState.WindowMinimized)

    def _client_message(self, rec: XWin, e) -> None:
        A = self.windows.atoms
        if e.type != A["WM_PROTOCOLS"] or e.format != 32:
            return
        what = e.data[0]
        if what == A["WM_DELETE_WINDOW"]:
            QtCore.QTimer.singleShot(0, rec.w.close)
        elif what == A["WM_TAKE_FOCUS"]:
            self.windows.xtime = e.data[1] or self.windows.xtime
            self.windows.take_focus(rec, e.data[1])
        elif what == A["_NET_WM_PING"]:
            self.windows.pong(e)

    def _focus(self, rec: XWin, e) -> None:
        if e.detail == X.NotifyPointer:
            return
        if e.code == X.FocusOut and e.mode == X.NotifyGrab:
            return                                      # a keyboard grab (the manager's): the window keeps the focus
        if e.code == X.FocusIn and e.mode == X.NotifyUngrab and self.input.xfocus is rec.w:
            return
        focus_in = e.code == X.FocusIn
        self.input.x_focus(rec.w, focus_in)
        if focus_in:
            self.windows.raise_owned(rec)
            if self.clip is not None:
                self.clip.focus_in()

    # ---------------------------------------------------------------- the end
    def _lost(self, e) -> None:
        """The X display went away (XQuartz quit, ssh cut): say so once, close the windows, exit 1 (the prototype
        kept running at 79 % CPU with a traceback per tick, audit F32)."""
        if self.dead:
            return
        self.dead = True
        print(f"[xbridge] the X display went away ({type(e).__name__}: {e}); closing", file=sys.stderr, flush=True)
        app = self.app
        app.setQuitOnLastWindowClosed(False)            # else closing the last window quits with 0 before exit(1)
        QtCore.QTimer.singleShot(0, lambda: (app.closeAllWindows(), app.exit(1)))

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self._check.stop()
        self.app.removeEventFilter(self)
        self.input.close()
        if self.clip is not None:
            self.clip.close()
        if not self.dead:
            try:
                for rec in list(self.windows):
                    self.windows.destroy(rec.w)
                self.c.flush()
            except ConnectionError:
                pass
        self.transport.stop()
        self.dead = True
        if self.trace is not None:
            self.trace.stop()

    # ---------------------------------------------------------------- report
    def summary(self) -> dict:
        import statistics as st

        s = self.stats
        out = dict(self.transport.summary())
        out.update(grab_ms=round(st.median(s["grab_ms"]), 2) if s["grab_ms"] else None, x_events=s["x_events"],
                   ctl_wire_MB=round(self.c.bytes_out / 1e6, 3), ctl_errors=self.c.errors,
                   connect_s=round(self.link.connect_s, 3), open_s=round(self.link.open_s, 3),
                   input=dict(self.input.stats), windows=dict(self.windows.stats))
        if self.clip is not None:
            out["clipboard"] = dict(self.clip.stats)
        return out

    def describe(self) -> str:
        d = self.summary()
        if not d["updates"]:
            return "X11 bridge: nothing sent yet"
        return (f"X11 bridge: {d['updates']} updates, {d['bytes_per_update'] / 1e3:.0f} kB of pixels each "
                f"({d['wire_per_update'] / 1e3:.0f} kB on the wire), send {d['send_ms']} ms, confirmed "
                f"{d['ack_ms']} ms median")


def _pieces(dirty: QtGui.QRegion, painted: list) -> list:
    """dirty split into what each repaint added, in the order Qt painted them (each piece without what an earlier
    one has), and the rest (dirty without a Paint event: a child moved, a resize, the periodic check) last."""
    out, covered = [], QtGui.QRegion()
    for reg in painted:
        p = reg.intersected(dirty).subtracted(covered)
        if not p.isEmpty():
            out.append(p)
            covered += p
    rest = dirty.subtracted(covered)
    if not rest.isEmpty():
        out.append(rest)
    return out


def _pixels(img: QtGui.QImage):
    """The pixels of a grabbed RGB32 image as a uint32 [h, w] view (no copy: the image travels with it)."""
    import numpy as np

    h, w = img.height(), img.width()
    bpl = img.bytesPerLine()
    a = np.frombuffer(img.constBits(), np.uint32, count=bpl // 4 * h).reshape(h, bpl // 4)
    return a[:, :w]
