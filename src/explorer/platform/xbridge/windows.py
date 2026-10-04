"""One X window per Qt top-level window, and what the window manager needs to know about it (ICCCM, EWMH).

- Popups and tool tips are override-redirect (placed here, never by the manager), as xcb makes them; a popup holds
  the pointer, so a press anywhere (on another application too) reaches it and closes it.
- The others are managed: WM_NAME and _NET_WM_NAME, WM_CLASS, WM_HINTS (input), WM_NORMAL_HINTS with static
  gravity (a frame of the manager never shifts the window: quartz-wm moved a framed utility window down 16 px per
  round trip, audit F23c), WM_PROTOCOLS (delete, take focus, ping), _NET_WM_PID, a window type, the Motif hints of a
  frameless window, WM_TRANSIENT_FOR of a window owned by another (a panel or a dialog stays above its owner).
- Geometry: Qt's global coordinates are X root coordinates. A move or resize from Qt is asked of X; the notices of
  X are taken by Qt, except echoes of a request of ours older than the last one (unzooming through ssh met the late
  notice of the zoom and X and Qt ended with swapped sizes, audit F20i) and notices of older requests.
- The keyboard: with a manager, activation is asked through _NET_ACTIVE_WINDOW with a server time; without one
  (Xvfb), the X focus is set directly once the window is viewable. WM_TAKE_FOCUS is answered.
"""
import collections
import os
import socket
import struct

from PySide6 import QtCore, QtGui, QtWidgets

from ..._name import APP_NAME
from ...obs import get_logger
from . import xproto as X
from .trace import Trace, rect

log = get_logger("platform.xbridge")
Qt, E = QtCore.Qt, QtCore.QEvent
TITLEBAR_ENV = "EXPLORER_TITLEBAR"                     # =wm: the window manager's frames, not our own (ui.titlebar)
SHAPE_ATTR = "x11_shape"                                # a QRegion a top-level publishes as its shape (sync_shape)

ATOMS = ("WM_PROTOCOLS", "WM_DELETE_WINDOW", "WM_TAKE_FOCUS", "_NET_WM_PING", "WM_STATE", "WM_CHANGE_STATE",
         "WM_CLIENT_MACHINE", "_NET_WM_PID", "_NET_WM_NAME", "UTF8_STRING", "_NET_WM_WINDOW_TYPE",
         "_NET_WM_WINDOW_TYPE_NORMAL", "_NET_WM_WINDOW_TYPE_DIALOG", "_NET_WM_WINDOW_TYPE_UTILITY",
         "_NET_WM_WINDOW_TYPE_TOOLTIP", "_NET_WM_WINDOW_TYPE_POPUP_MENU", "_MOTIF_WM_HINTS", "_NET_ACTIVE_WINDOW",
         "_NET_SUPPORTED", "_NET_WM_USER_TIME", "_NET_WM_STATE", "_NET_WM_STATE_MAXIMIZED_VERT",
         "_NET_WM_STATE_MAXIMIZED_HORZ", "_NET_WM_STATE_FULLSCREEN", "_NET_WM_STATE_HIDDEN", "_NET_WM_MOVERESIZE",
         "XBRIDGE_TIME")
EVENTS = (X.ExposureMask | X.PointerMotionMask | X.ButtonPressMask | X.ButtonReleaseMask | X.KeyPressMask
          | X.KeyReleaseMask | X.StructureNotifyMask | X.FocusChangeMask | X.EnterWindowMask | X.LeaveWindowMask
          | X.PropertyChangeMask)
POPUP_GRAB = X.ButtonPressMask | X.ButtonReleaseMask | X.PointerMotionMask | X.EnterWindowMask | X.LeaveWindowMask
ROOT_MSG = X.SubstructureRedirectMask | X.SubstructureNotifyMask
STATIC_GRAVITY, NORTHWEST_GRAVITY = 10, 1
# X cursor-font glyphs for Qt's shapes (XQuartz draws them as bitmaps)
CURSORS = {Qt.CursorShape.ArrowCursor: 68, Qt.CursorShape.UpArrowCursor: 22, Qt.CursorShape.CrossCursor: 34,
           Qt.CursorShape.WaitCursor: 150, Qt.CursorShape.IBeamCursor: 152, Qt.CursorShape.SizeVerCursor: 116,
           Qt.CursorShape.SizeHorCursor: 108, Qt.CursorShape.SizeBDiagCursor: 12, Qt.CursorShape.SizeFDiagCursor: 14,
           Qt.CursorShape.SizeAllCursor: 52, Qt.CursorShape.SplitVCursor: 116, Qt.CursorShape.SplitHCursor: 108,
           Qt.CursorShape.PointingHandCursor: 60, Qt.CursorShape.ForbiddenCursor: 24,
           Qt.CursorShape.WhatsThisCursor: 92, Qt.CursorShape.BusyCursor: 150, Qt.CursorShape.OpenHandCursor: 58,
           Qt.CursorShape.ClosedHandCursor: 52, Qt.CursorShape.BitmapCursor: 86}
WIDGET_SIZE_MAX = (1 << 24) - 1


def who(w: QtWidgets.QWidget) -> str:
    """A window's name in the bridge's trace, as in the geometry trace: main, a panel's name, else its title."""
    if isinstance(w, QtWidgets.QMainWindow):
        return "main"
    return (w.objectName() or w.windowTitle() or type(w).__name__).replace(" ", "_")


def _rect(r: QtCore.QRect) -> str:
    return rect(r.x(), r.y(), r.width(), r.height())


class XWin:
    """What the bridge keeps for one top-level: its X window and the state between Qt and X."""

    def __init__(self, w: QtWidgets.QWidget, xid: int, popup: bool, owner: "XWin | None"):
        self.w, self.xid, self.popup, self.owner = w, xid, popup, owner
        self.dirty = QtGui.QRegion(w.rect())
        self.check = False                              # the next grab is the periodic whole-window check
        self.cfg_seq: int | None = None                 # our last ConfigureWindow
        self.want = QtCore.QRect(w.geometry())          # the whole geometry last asked for
        self.asked: collections.deque = collections.deque(maxlen=64)
        self.xg: QtCore.QRect | None = None             # the geometry X last told us (Qt taking it asks nothing)
        self.reparented = False
        self.viewable = False                           # mapped at least once (focus can be set)
        self.iconic = False
        self.mask: QtGui.QRegion | None = None
        self.cursor = None
        self.grab = False
        self.activate_on_map = False
        self.state_from_x = False


class Windows:
    def __init__(self, c: X.Connection, on_destroyed=None):
        self.c = c
        self.scr = c.screen
        self.by_widget: dict[QtWidgets.QWidget, XWin] = {}
        self.by_xid: dict[int, XWin] = {}
        self.atoms: dict[str, int] = {}
        self.supported: set[int] = set()
        self._supported_ck: X.Cookie | None = None
        self.xtime = 0                                  # the last X server time seen
        self._font = 0
        self._cursors: dict[int, int] = {}
        self.on_destroyed = on_destroyed
        self.host = socket.gethostname()
        self.stats: dict[str, int] = dict(created=0, configures=0, notices=0, echoes=0, activations=0, focus_set=0)
        self.trace: Trace | None = None                 # EXPLORER_BRIDGE_TRACE

    # ---- start
    def start(self, atom_cookies) -> None:
        """atom_cookies: name -> cookie of the InternAtom requests sent before Qt started."""
        for n, ck in atom_cookies.items():
            self.atoms[n] = struct.unpack_from("<I", ck.result(), 8)[0]
        self._supported_ck = self.c.get_property(self.scr.root, self.atoms["_NET_SUPPORTED"], X.ATOM_ATOM)

    def wm_supports(self, name: str) -> bool:
        if self._supported_ck is not None:
            try:
                _t, fmt, val, _ = self.c.property_value(self._supported_ck.result(5.0))
                self.supported = set(struct.unpack(f"<{len(val) // 4}I", val)) if fmt == 32 else set()
            except (X.XError, TimeoutError, ConnectionError):
                self.supported = set()
            self._supported_ck = None
        return self.atoms.get(name, -1) in self.supported

    def __iter__(self):
        return iter(list(self.by_widget.values()))

    def get(self, w) -> XWin | None:
        return self.by_widget.get(w)

    # ---- create and destroy
    @staticmethod
    def is_popup(w: QtWidgets.QWidget) -> bool:
        """Override-redirect: popups, tool tips, and a window that bypasses the manager (the type, not the flags:
        every window type has the Window bit, and flags & (Popup | ToolTip) made every panel override-redirect,
        audit F23b)."""
        return (w.windowType() in (Qt.WindowType.Popup, Qt.WindowType.ToolTip)
                or bool(w.windowFlags() & Qt.WindowType.X11BypassWindowManagerHint)) \
            and not isinstance(w, QtWidgets.QMainWindow)

    def create(self, w: QtWidgets.QWidget) -> XWin:
        c = self.c
        popup = self.is_popup(w)
        g = w.geometry()
        xid = c.new_id()
        attrs = {X.CW_BIT_GRAVITY: NORTHWEST_GRAVITY, X.CW_EVENT_MASK: EVENTS, X.CW_COLORMAP: self.scr.colormap}
        if popup:
            attrs[X.CW_OVERRIDE_REDIRECT] = 1
        vis = self.scr.root_visual
        c.create_window(xid, self.scr.root, g.x(), g.y(), g.width(), g.height(), depth=self.scr.root_depth,
                        visual=vis, attrs=attrs)
        pw = w.parentWidget()
        owner = self.by_widget.get(pw.window()) if pw is not None else None
        rec = XWin(w, xid, popup, owner)
        # the geometry it is created with is asked for too: a manager's late notice of it (quartz-wm through ssh -Y,
        # 230 ms after the glass look had placed a panel elsewhere) is an echo once newer geometry is asked
        rec.asked.append((g.x(), g.y(), g.width(), g.height()))
        tr = self.trace
        if tr is not None:
            tr.name(xid, f"{who(w)} window")
            tr.write("CREATE", xid, f"{_rect(g)} {'override-redirect' if popup else 'managed'}, owner "
                                    f"{tr.who(owner.xid) + f' {owner.xid:#x}' if owner is not None else '-'}")
        if not popup:
            self._properties(rec)
        c.map_window(xid)
        if tr is not None:
            tr.write("MAP", xid, "asked")
        if w.windowType() == Qt.WindowType.Popup:
            c.grab_pointer(xid, POPUP_GRAB, owner_events=True)       # reply not awaited
            rec.grab = True
        c.flush()
        self.by_widget[w] = rec
        self.by_xid[xid] = rec
        self.stats["created"] += 1
        return rec

    def _properties(self, rec: XWin) -> None:
        c, A, w = self.c, self.atoms, rec.w
        self.set_title(rec)
        cls = APP_NAME.encode()
        c.change_property(rec.xid, X.ATOM_WM_CLASS, X.ATOM_STRING, 8, cls + b"\0" + cls.capitalize() + b"\0")
        c.change_property(rec.xid, A["WM_PROTOCOLS"], X.ATOM_ATOM, 32,
                          [A["WM_DELETE_WINDOW"], A["WM_TAKE_FOCUS"], A["_NET_WM_PING"]])
        c.change_property(rec.xid, X.ATOM_WM_HINTS, X.ATOM_WM_HINTS, 32, [1 | 2, 1, 1, 0, 0, 0, 0, 0, 0])
        self.normal_hints(rec)
        c.change_property(rec.xid, A["_NET_WM_PID"], X.ATOM_CARDINAL, 32, [os.getpid()])
        c.change_property(rec.xid, A["WM_CLIENT_MACHINE"], X.ATOM_STRING, 8, self.host.encode("latin-1", "replace"))
        if self.xtime:
            c.change_property(rec.xid, A["_NET_WM_USER_TIME"], X.ATOM_CARDINAL, 32, [self.xtime])
        wt = w.windowType()
        # a window of another one (a floating panel, a tool window) is a normal one, transient for its owner: quartz-wm
        # puts its own 16-px title strip on a utility window even without decorations, and keeps a transient window
        # of any type above its owner. A panel under the manager's frames (EXPLORER_TITLEBAR=wm) is a utility window,
        # as xcb makes it: the manager's thin strip is its title. Through XQuartz a utility panel showed two titles
        # and crept down 16 px at each round trip. The prototype's xbridge.py:660-690 (audit F23c)
        wm_panel = os.environ.get(TITLEBAR_ENV) == "wm" and isinstance(w, QtWidgets.QDockWidget)
        kind = ("_NET_WM_WINDOW_TYPE_DIALOG" if wt in (Qt.WindowType.Dialog, Qt.WindowType.Sheet)
                else "_NET_WM_WINDOW_TYPE_UTILITY" if wm_panel
                else "_NET_WM_WINDOW_TYPE_NORMAL")
        c.change_property(rec.xid, A["_NET_WM_WINDOW_TYPE"], X.ATOM_ATOM, 32, [A[kind]])
        if w.windowFlags() & Qt.WindowType.FramelessWindowHint and not wm_panel:
            c.change_property(rec.xid, A["_MOTIF_WM_HINTS"], A["_MOTIF_WM_HINTS"], 32, [2, 0, 0, 0, 0])
        if rec.owner is not None:
            c.change_property(rec.xid, X.ATOM_WM_TRANSIENT_FOR, X.ATOM_WINDOW, 32, [rec.owner.xid])
        # windows of this one made before it (a saved glass layout floats the panels before the main window is shown):
        # transient for it now, so the manager keeps them above it
        for r in self.by_widget.values():
            pw = r.w.parentWidget()
            if r.owner is None and not r.popup and pw is not None and pw.window() is w:
                r.owner = rec
                c.change_property(r.xid, X.ATOM_WM_TRANSIENT_FOR, X.ATOM_WINDOW, 32, [rec.xid])
                if self.trace is not None:
                    self.trace.write("OWNER", r.xid, f"transient for {who(w)} {rec.xid:#x}, after its map")

    def set_title(self, rec: XWin) -> None:
        title = rec.w.windowTitle() or APP_NAME
        # WM_NAME is Latin-1 (python-xlib raised on the panel title "λ–t"); the full title goes into _NET_WM_NAME
        self.c.change_property(rec.xid, X.ATOM_WM_NAME, X.ATOM_STRING, 8, title.encode("latin-1", "replace"))
        self.c.change_property(rec.xid, self.atoms["_NET_WM_NAME"], self.atoms["UTF8_STRING"], 8,
                               title.encode("utf-8"))

    def normal_hints(self, rec: XWin) -> None:
        w, g = rec.w, rec.w.geometry()
        flags = 8 | 512                                 # PSize, PWinGravity
        if w.testAttribute(Qt.WidgetAttribute.WA_Moved):
            flags |= 4                                  # PPosition: placed by the program; else the manager places it
        mn, mx = w.minimumSize(), w.maximumSize()
        if mn.width() > 0 or mn.height() > 0:
            flags |= 16
        if mx.width() < WIDGET_SIZE_MAX or mx.height() < WIDGET_SIZE_MAX:
            flags |= 32
        vals = [flags, g.x(), g.y(), g.width(), g.height(), mn.width(), mn.height(), min(mx.width(), 32767),
                min(mx.height(), 32767), 0, 0, 0, 0, 0, 0, 0, 0, STATIC_GRAVITY]
        # of type WM_SIZE_HINTS (ICCCM 4.1.2.3): a manager asks for that type, and of another one it reads nothing
        self.c.change_property(rec.xid, X.ATOM_WM_NORMAL_HINTS, X.ATOM_WM_SIZE_HINTS, 32, vals)

    def destroy(self, w) -> XWin | None:
        rec = self.by_widget.pop(w, None)
        if rec is None:
            return None
        log.debug("X window %#x of %r destroyed", rec.xid, w.windowTitle())
        if self.trace is not None:
            self.trace.write("DESTROY", rec.xid, "")
        self.by_xid.pop(rec.xid, None)
        if rec.grab and not any(r.grab for r in self.by_widget.values()):
            self.c.ungrab_pointer(self.xtime)
        self.c.destroy_window(rec.xid)
        self.c.flush()
        if self.on_destroyed is not None:
            self.on_destroyed(rec)
        return rec

    # ---- geometry from Qt
    def configure(self, rec: XWin, **kw) -> None:
        """Ask X for a geometry, remembering the request's number: notices older than it are echoes."""
        rec.cfg_seq = self.c.configure_window(rec.xid, **kw)
        want = QtCore.QRect(rec.want)
        if "x" in kw or "y" in kw:
            want.moveTo(kw.get("x", want.x()), kw.get("y", want.y()))
        if "width" in kw or "height" in kw:
            want.setSize(QtCore.QSize(kw.get("width", want.width()), kw.get("height", want.height())))
        rec.want = want
        rec.asked.append((want.x(), want.y(), want.width(), want.height()))
        # X will have another geometry than the one it last told: kept, it matched Qt going back to that geometry
        # and the request was skipped (an edge drag left X 60 px larger than Qt, audit F23)
        rec.xg = None
        self.stats["configures"] += 1
        if self.trace is not None:
            self.trace.write("CONF", rec.xid, " ".join(f"{k}={v}" for k, v in kw.items()))

    def qt_geometry(self, rec: XWin, resized: bool) -> None:
        """Qt moved or resized a top-level: ask X, unless X told Qt this geometry."""
        g = rec.w.geometry()
        if g == rec.xg:
            return
        if rec.popup:
            self.configure(rec, x=g.x(), y=g.y(), width=max(1, g.width()), height=max(1, g.height()))
        elif resized:
            self.configure(rec, width=max(1, g.width()), height=max(1, g.height()))
        else:
            self.configure(rec, x=g.x(), y=g.y())
        self.c.flush()

    # ---- notices from X
    def configured(self, rec: XWin, e, apply) -> None:
        """A ConfigureNotify of our window; apply(rec, x, y, w, h) makes Qt agree (on this thread)."""
        self.stats["notices"] += 1
        tr = self.trace

        def say(what: str) -> None:
            if tr is not None:
                tr.write("NOTICE", rec.xid, f"{'synthetic' if e.sent else 'real'} "
                                            f"{rect(e.x, e.y, e.width, e.height)}: {what}")
        if rec.cfg_seq is not None and 0 < ((rec.cfg_seq - e.seq) & 0xFFFF) < 0x8000:
            self.stats["echoes"] += 1
            say("an echo, older than the last request")
            return                                      # generated before our last request reached the server
        got = (e.x, e.y, e.width, e.height)
        if e.sent and rec.asked and got == rec.asked[-1]:
            say("applied (the last asked)")
            apply(rec, e.x, e.y, e.width, e.height)     # ICCCM 4.1.5: a synthetic notice is in root coordinates
        elif e.sent and got in rec.asked:
            self.stats["echoes"] += 1                   # the notice of an older request: X moved on since
            say("an echo, asked before the last")
        elif e.sent or rec.popup or not rec.reparented:
            say("applied")
            apply(rec, e.x, e.y, e.width, e.height)
        else:                                           # inside the manager's frame: ask where that is, not waiting
            say("framed: where it is asked of X")
            # an answer that comes after Qt asked for another geometry is where the window was: taken, it set Qt
            # back and Qt asked again (through XQuartz the glass panels jumped about for 1.2 s). An answer that is a
            # geometry asked before the last one is where the window was too, before the manager acted on the last
            # request (through ssh -Y a glass panel went back to its first geometry, over the main window)
            asked = rec.cfg_seq

            def where(r, err, w=e.width, h=e.height):
                if err is not None or rec.cfg_seq != asked:
                    return
                x, y = struct.unpack_from("<hh", r, 12)
                if rec.asked and (x, y, w, h) != rec.asked[-1] and (x, y, w, h) in rec.asked:
                    self.stats["echoes"] += 1
                    if tr is not None:
                        tr.write("WHERE", rec.xid, f"({x}, {y}): an echo, dropped")
                    return
                if tr is not None:
                    tr.write("WHERE", rec.xid, f"({x}, {y}): applied")
                apply(rec, x, y, w, h, True)
            self.c.translate_coordinates(rec.xid, self.scr.root).then(where)

    # ---- state
    def minimize(self, rec: XWin) -> None:
        """ICCCM: ask the manager to iconify."""
        self.c.client_message(self.scr.root, rec.xid, self.atoms["WM_CHANGE_STATE"], [3], ROOT_MSG)
        self.c.flush()

    def set_net_state(self, rec: XWin, add: bool, *names: str) -> bool:
        """_NET_WM_STATE add or remove (maximized, fullscreen), when the manager supports it."""
        if not self.wm_supports("_NET_WM_STATE") or not all(self.wm_supports(n) for n in names):
            return False
        a = [self.atoms[n] for n in names] + [0]
        self.c.client_message(self.scr.root, rec.xid, self.atoms["_NET_WM_STATE"], [int(add), a[0], a[1], 1],
                              ROOT_MSG)
        self.c.flush()
        return True

    def activate(self, rec: XWin) -> None:
        """Give rec the keyboard: through the manager (EWMH, source 1: an application, with a server time), or,
        with no manager (Xvfb), by setting the X focus once the window is viewable."""
        if self.wm_supports("_NET_ACTIVE_WINDOW"):
            cur = 0
            self.c.client_message(self.scr.root, rec.xid, self.atoms["_NET_ACTIVE_WINDOW"],
                                  [1, self.xtime, cur], ROOT_MSG)
            self.stats["activations"] += 1
        elif rec.viewable:
            self.c.set_input_focus(rec.xid, self.xtime)
            self.stats["focus_set"] += 1
        else:
            rec.activate_on_map = True
        self.c.flush()

    def take_focus(self, rec: XWin, time: int) -> None:
        """WM_TAKE_FOCUS: the manager offers the focus; take it with its time."""
        self.c.set_input_focus(rec.xid, time)
        self.c.flush()

    def pong(self, e) -> None:
        """_NET_WM_PING: send it back to the root."""
        d = list(e.data)
        self.c.client_message(self.scr.root, self.scr.root, e.type, d, ROOT_MSG)
        self.c.flush()

    def raise_owned(self, rec: XWin) -> None:
        """The panels of a window that got the focus go above it, whatever the manager does with transients
        (quartz-wm kept them above only when it activated the owner itself, audit F23c)."""
        for r in self.by_widget.values():
            if r.owner is rec and not r.iconic:
                self.c.configure_window(r.xid, stack_mode=0)
        self.c.flush()

    # ---- shape and cursor
    def sync_shape(self, rec: XWin) -> None:
        """The window's mask as its X SHAPE. Offscreen keeps no masks, so a window may publish its shape as a QRegion
        in the attribute SHAPE_ATTR (the title bar's rounded corners): without it the corners were square, and a
        press at a corner that xcb leaves outside the window resized it."""
        m = rec.w.mask()
        if m.isEmpty():
            published = getattr(rec.w, SHAPE_ATTR, None)
            if isinstance(published, QtGui.QRegion):
                m = published
        if rec.mask is not None and m == rec.mask:
            return
        if rec.mask is None and m.isEmpty():
            rec.mask = QtGui.QRegion(m)
            return
        if self.c.ext("SHAPE") is None:
            return
        if m.isEmpty():
            # no mask: no shape (a rectangle of the window's size stayed that size when the window grew, audit F23a)
            self.c.shape_reset(rec.xid)
            if self.trace is not None:
                self.trace.write("SHAPE", rec.xid, "none (rectangular)")
        else:
            rects = [(r.x(), r.y(), r.width(), r.height()) for r in iter(m)]     # type: ignore[call-overload]
            self.c.shape_rectangles(rec.xid, rects)
            if self.trace is not None:
                self.trace.write("SHAPE", rec.xid, f"{len(rects)} rects in {_rect(m.boundingRect())}")
        self.c.flush()
        rec.mask = QtGui.QRegion(m)

    def sync_cursor(self, rec: XWin, shape) -> None:
        if rec.cursor == shape:
            return
        rec.cursor = shape
        g = CURSORS.get(shape, 68)
        cid = self._cursors.get(g)
        if cid is None:
            if not self._font:
                self._font = self.c.new_id()
                self.c.open_font(self._font, "cursor")
            cid = self._cursors[g] = self.c.new_id()
            self.c.create_glyph_cursor(cid, self._font, g)
        self.c.change_attributes(rec.xid, {X.CW_CURSOR: cid})
        self.c.flush()
