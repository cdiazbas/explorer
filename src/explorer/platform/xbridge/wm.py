"""The X windows that show Qt's top-level windows, and what the window manager is told and tells back (ICCCM, EWMH,
Motif hints): creation, transient panels, geometry both ways, iconify, activation, shapes, cursors. From the
prototype's app/xbridge.py (the window half of XBridge), mixed into bridge.Bridge, whose state it shares.

Each Qt top-level widget has a record in Bridge.wins:
    x         its X window                   dirty    QRegion to send (transport)     popup   override-redirect
    born      serial of its CreateWindow     owner    the window it is transient for  want    geometry last asked
    asked     recent geometries asked        xg       geometry X last told            force   region to resend whole
    qt_moves  Qt places it, not the manager  unmapped iconified                       mask    SHAPE last sent
    shape     the mask WindowOps.set_shape gave   resizer  edge resizer (legacy input)     cursor  shape last set
"""
import collections
import time

from PySide6 import QtCore, QtGui, QtWidgets

from ..._name import APP_NAME
from .state import Shared

Qt = QtCore.Qt
CS, WT = Qt.CursorShape, Qt.WindowType

# _NET_WM_MOVERESIZE directions, from Qt edges (top, left, right, bottom) (EWMH)
MOVERESIZE = {(True, True, False, False): 0, (True, False, False, False): 1, (True, False, True, False): 2,
              (False, False, True, False): 3, (False, False, True, True): 4, (False, False, False, True): 5,
              (False, True, False, True): 6, (False, True, False, False): 7}

# Qt cursors -> X cursor-font glyphs (XQuartz draws them as bitmaps)
XCURSOR = {CS.ArrowCursor: 68, CS.UpArrowCursor: 22, CS.CrossCursor: 34, CS.WaitCursor: 150, CS.IBeamCursor: 152,
           CS.SizeVerCursor: 116, CS.SizeHorCursor: 108, CS.SizeBDiagCursor: 12, CS.SizeFDiagCursor: 14,
           CS.SizeAllCursor: 52, CS.SplitVCursor: 116, CS.SplitHCursor: 108, CS.PointingHandCursor: 60,
           CS.ForbiddenCursor: 24, CS.WhatsThisCursor: 92, CS.BusyCursor: 150, CS.OpenHandCursor: 58,
           CS.ClosedHandCursor: 52, CS.BitmapCursor: 86}   # a pixmap cursor (the slit's pencil) as a pencil glyph


class WindowManager(Shared):
    """The window half of the bridge."""

    def move_window(self, w, x, y):
        """Move a top-level window (its own title bar is being dragged): X first, then Qt to match."""
        rec = self.wins.get(w)
        if rec:
            self._configure(rec, x=x, y=y)
            self.ev.flush()
        w.move(x, y)

    def _configure(self, rec, **kw):
        """Configure an X window of ours, remembering the request's serial: ConfigureNotify events older than it are
        echoes of an earlier request (_configured)."""
        rec["x"].configure(**kw)
        rec["cfg_serial"] = (self.ev.display.request_serial - 1) % 65536
        want = QtCore.QRect(rec["want"])                    # the whole geometry asked for, to recognise its notice
        if "x" in kw or "y" in kw:
            want.moveTo(kw.get("x", want.x()), kw.get("y", want.y()))
        if "width" in kw or "height" in kw:
            want.setSize(QtCore.QSize(kw.get("width", want.width()), kw.get("height", want.height())))
        rec["want"] = want
        rec["asked"].append((want.x(), want.y(), want.width(), want.height()))
        # X will have another geometry than the one it last told us (_configured sets it again). Kept, it matched Qt
        # going back to that old geometry and the request was skipped: after an edge drag (resize, then move: the
        # resize's notice predates the move request and is dropped as an echo) the reset to the size before left the X
        # window 60 px larger than Qt for the rest of a conformance run (Xvfb)
        rec["xg"] = None

    def minimize(self, w):
        rec = self.wins.get(w)
        if rec:                                             # ICCCM: ask the window manager to iconify
            from Xlib.protocol import event

            ev = event.ClientMessage(window=rec["x"], client_type=self.ev.intern_atom("WM_CHANGE_STATE"),
                                     data=(32, [3, 0, 0, 0, 0]))
            self.scr.root.send_event(ev, event_mask=self.X.SubstructureRedirectMask | self.X.SubstructureNotifyMask)
            self.ev.flush()

    def activate(self, w):
        """Ask the window manager to activate w and give it the keyboard (EWMH _NET_ACTIVE_WINDOW, source 1: an
        application; quartz-wm and GNOME/KDE support it, read from _NET_SUPPORTED on XQuartz)."""
        rec = self.wins.get(w)
        if rec is None or self.dead or not self._wm_supports("_NET_ACTIVE_WINDOW"):
            return
        from Xlib.protocol import event

        ev = event.ClientMessage(window=rec["x"], client_type=self.ev.intern_atom("_NET_ACTIVE_WINDOW"),
                                 data=(32, [1, self.X.CurrentTime, 0, 0, 0]))
        self.scr.root.send_event(ev, event_mask=self.X.SubstructureRedirectMask | self.X.SubstructureNotifyMask)
        self.ev.flush()

    def _wm_supports(self, atom):
        if self._net_supported is None:
            try:
                from Xlib import Xatom

                p = self.scr.root.get_full_property(self.ev.intern_atom("_NET_SUPPORTED"), Xatom.ATOM)
                self._net_supported = {self.ev.get_atom_name(a) for a in p.value} if p else set()
            except Exception:
                self._net_supported = set()
        return atom in self._net_supported

    def wm_moveresize(self, w, edges=None):
        """Let the window manager move (edges None) or resize the window, as GNOME/KDE do for their own frames; False
        when it cannot (XQuartz's quartz-wm has no _NET_WM_MOVERESIZE): the caller does it."""
        rec = self.wins.get(w)
        if rec is None or not self._wm_supports("_NET_WM_MOVERESIZE"):
            return False
        if edges is None:
            direction = 8
        else:
            key = (bool(edges & Qt.Edge.TopEdge), bool(edges & Qt.Edge.LeftEdge), bool(edges & Qt.Edge.RightEdge),
                   bool(edges & Qt.Edge.BottomEdge))
            d = MOVERESIZE.get(key)
            if d is None:
                return False
            direction = d
        from Xlib.protocol import event

        p = QtGui.QCursor.pos()
        self.ev.ungrab_pointer(self.X.CurrentTime)          # the manager takes the pointer from here on
        ev = event.ClientMessage(window=rec["x"], client_type=self.ev.intern_atom("_NET_WM_MOVERESIZE"),
                                 data=(32, [p.x(), p.y(), direction, 1, 1]))
        self.scr.root.send_event(ev, event_mask=self.X.SubstructureRedirectMask | self.X.SubstructureNotifyMask)
        self.ev.flush()
        self.buttons, self.grab_target = Qt.MouseButton.NoButton, None  # its release goes to the manager
        return True

    def _add(self, w):
        X = self.X
        # override-redirect (placed by us, never by the window manager), as xcb does: popups, tool tips, and a window
        # that bypasses the manager (a panel while a drag unplugs it). Tested by window type: flags & (Popup | ToolTip)
        # is true for every window type (Window is bit 0 of both), and made the floating panels override-redirect,
        # never managed, and never transient for their owner
        popup = (w.windowType() in (WT.Popup, WT.ToolTip)
                 or bool(w.windowFlags() & WT.X11BypassWindowManagerHint)) and not isinstance(w, QtWidgets.QMainWindow)
        g = w.geometry()
        owned = None                                        # the window this one belongs to (transient for)
        born = self.ev.display.request_serial % 65536       # the serial of the CreateWindow below
        xw = self.scr.root.create_window(
            g.x(), g.y(), max(1, g.width()), max(1, g.height()), 0, self.depth, X.InputOutput, X.CopyFromParent,
            background_pixel=self.scr.black_pixel, override_redirect=popup,
            event_mask=(X.ExposureMask | X.PointerMotionMask | X.ButtonPressMask | X.ButtonReleaseMask
                        | X.KeyPressMask | X.KeyReleaseMask | X.StructureNotifyMask | X.FocusChangeMask
                        | X.EnterWindowMask | X.LeaveWindowMask))
        if not popup:
            # WM_NAME is Latin-1 (python-xlib raises on a title like "λ–t"); the full title goes into _NET_WM_NAME as
            # UTF-8, as xcb does
            title = w.windowTitle() or APP_NAME
            xw.set_wm_name(title.encode("latin-1", "replace").decode("latin-1"))
            xw.change_property(self.ev.intern_atom("_NET_WM_NAME"), self.ev.intern_atom("UTF8_STRING"), 8,
                               title.encode("utf-8"))
            xw.set_wm_class(APP_NAME, APP_NAME)
            xw.set_wm_protocols([self.WM_DELETE])
            # static gravity: the position asked is the X window's own, frame or no frame. quartz-wm frames a utility
            # window with a 16-px strip and, by default, put that frame at the position asked: the window landed 16 px
            # lower, Qt followed, asked again, and it crept down 16 px per round trip (XQuartz)
            xw.set_wm_normal_hints(flags=self.Xutil.PPosition | self.Xutil.PSize | self.Xutil.PWinGravity,
                                   x=g.x(), y=g.y(), width=g.width(), height=g.height(), win_gravity=X.StaticGravity)
            # without a window of our own frame (no title bar of ours), the main window has the manager's frame, and
            # so do the panels
            wm_frames = not self.own_frame
            panel = isinstance(w, QtWidgets.QDockWidget)
            if w in self.own_frame or (w.windowFlags() & WT.FramelessWindowHint and not (wm_frames and panel)):
                # Motif hints: flags = decorations, decorations = none. Also floating docks with a title bar of ours:
                # Qt makes them frameless and draws the frame itself
                mh = self.ev.intern_atom("_MOTIF_WM_HINTS")
                xw.change_property(mh, mh, 32, [2, 0, 0, 0, 0])
            owner = w.parentWidget().window() if w.parentWidget() is not None else None
            if owner in self.wins:
                owned = owner
                # a window of another one (floating dock, dialog): the manager keeps it above its owner, as xcb asks.
                # Without it, activating the main window buried the floating docks behind it on XQuartz. A normal
                # window, not a utility one: quartz-wm adds its own 16-px title strip to a utility window even without
                # decorations, and keeps a transient window of any type above its owner when the owner is activated
                # (measured on XQuartz with a python-xlib probe)
                xw.set_wm_transient_for(self.wins[owner]["x"])
                from Xlib import Xatom

                # with the manager's frames a panel is a utility window, as xcb makes it: quartz-wm gives it its thin
                # strip, which macOS moves locally (fluid), and static gravity keeps it from creeping. Normal
                # otherwise: quartz-wm leaves a transient normal window unframed
                kind = "_NET_WM_WINDOW_TYPE_UTILITY" if (wm_frames and panel) else "_NET_WM_WINDOW_TYPE_NORMAL"
                xw.change_property(self.ev.intern_atom("_NET_WM_WINDOW_TYPE"), Xatom.ATOM, 32,
                                   [self.ev.intern_atom(kind)])
        xw.map()
        self.ev.flush()
        rec = dict(x=xw, dirty=QtGui.QRegion(w.rect()), popup=popup, born=born, owner=owned,
                   want=QtCore.QRect(g), asked=collections.deque(maxlen=64),
                   # a floating dock is moved by Qt itself (its title is Qt's), not by the manager
                   qt_moves=isinstance(w, QtWidgets.QDockWidget) and bool(w.windowFlags() & WT.FramelessWindowHint))
        if self.plat is not None and w.windowType() == WT.Popup:
            # as xcb: an open popup (combo list, menu) holds the pointer, so a press anywhere, also on another
            # application's window, reaches it and closes it
            xw.grab_pointer(True, X.ButtonPressMask | X.ButtonReleaseMask | X.PointerMotionMask
                            | X.EnterWindowMask | X.LeaveWindowMask, X.GrabModeAsync, X.GrabModeAsync,
                            X.NONE, X.NONE, X.CurrentTime)
            rec["grab"] = True
        self.wins[w] = rec
        self.by_xid[xw.id] = w

    def _remove(self, w):
        rec = self.wins.pop(w, None)
        if rec:
            self.by_xid.pop(rec["x"].id, None)
            if rec.get("grab") and not any(r.get("grab") for r in self.wins.values()):
                self.ev.ungrab_pointer(self.X.CurrentTime)
            rec["x"].destroy()
            self.ev.flush()
        if self.grab_target is not None and self.grab_target.window() is w:
            self.grab_target = None

    def _configured(self, w, e):
        """The window manager moved or resized an X window: make Qt agree (sizes and global coordinates). Not with an
        echo of an earlier request of ours: through ssh to XQuartz, un-zooming (1920x1050 -> 1200x800) met the late
        ConfigureNotify of the zoom, Qt went back to 1920x1050 and X and Qt ended up swapped (Xvfb answers too fast to
        show it)."""
        rec = self.wins[w]
        s = rec.get("cfg_serial")
        if s is not None and 0 < ((s - e.sequence_number) & 0xffff) < 0x8000:
            return                                          # generated before our last configure reached the server
        got = (e.x, e.y, e.width, e.height)
        if e.send_event and rec["asked"] and got == rec["asked"][-1]:
            # ICCCM 4.1.5: a synthetic notice (the window manager's) carries root coordinates; this one confirms our
            # last request. Asking X instead (translate_coords) is a round trip that blocks the interface: on XQuartz
            # every panel move brought ~2 notices, all synthetic, 2.4 ms each on a fast link (21 % of a 60-Hz drag),
            # ~14 ms on a slower one (a drag no longer fluid)
            x, y = e.x, e.y
        elif e.send_event and got in rec["asked"]:
            # the notice of an older request: X has moved on since. Taken, it set Qt back (a panel ended 250 px behind
            # its X window, a left-edge resize 20 px off, XQuartz)
            return
        else:                                               # not ours (the manager placed it), or a real notice
            t = rec["x"].translate_coords(self.scr.root, 0, 0)
            x, y = -t.x, -t.y
        g = w.geometry()
        # what X has now: Qt taking it must not become a request of ours. Through a window manager the notices of a
        # burst of requests arrive late, each one set Qt back to an older size, and Qt's resize asked X for it again:
        # 15 resize steps on XQuartz ended at 690x281 instead of 790x341
        rec["xg"] = QtCore.QRect(x, y, e.width, e.height)
        if (e.width, e.height) != (g.width(), g.height()):
            w.resize(e.width, e.height)                     # Qt's Resize event re-dirties the whole window
        if (x, y) != (g.x(), g.y()) and not rec["popup"]:
            w.move(x, y)                                    # Qt global coordinates = X root coordinates

    def _mapped(self, w, mapped):
        """The window manager iconified (unmapped) or restored one of our windows. Qt is told, as xcb tells it from
        WM_STATE; nothing is sent to an unmapped window (it kept streaming frames while minimised). The other way, Qt
        minimising (showMinimized, a title bar's yellow light) or restoring, goes to the window manager from
        Bridge.eventFilter (WindowStateChange)."""
        rec = self.wins[w]
        if rec.get("unmapped", False) == (not mapped):
            return
        rec["unmapped"] = not mapped
        st = w.windowState()
        if mapped:
            rec["dirty"] = QtGui.QRegion(w.rect())
            rec["force"] = QtGui.QRegion(w.rect())
            if st & Qt.WindowState.WindowMinimized:
                w.setWindowState(st & ~Qt.WindowState.WindowMinimized)
        elif not st & Qt.WindowState.WindowMinimized:
            w.setWindowState(st | Qt.WindowState.WindowMinimized)

    def _shape(self, w, rec):
        """Copy the window's mask (rounded corners of a title bar of ours, WindowOps.set_shape; else Qt's own mask) to
        its X window as a SHAPE."""
        m = rec.get("shape")
        m = w.mask() if m is None else m
        if rec.get("mask") == m or not self.ev.has_extension("SHAPE"):
            return
        from Xlib.ext import shape

        if m.isEmpty():
            # no mask: no SHAPE. A rectangle of the window's size stayed that size when the window grew, and a floating
            # panel made larger was cut off at its first size, the new part neither shown nor clickable
            if rec.get("mask") is not None:
                rec["x"].shape_mask(shape.SO.Set, shape.SK.Bounding, 0, 0, self.X.NONE)
        else:
            rects = [dict(x=r.x(), y=r.y(), width=r.width(), height=r.height()) for r in m]
            rec["x"].shape_rectangles(shape.SO.Set, shape.SK.Bounding, 0, 0, 0, rects)
        self.ev.flush()
        rec["mask"] = QtGui.QRegion(m)

    # ---- activation: Qt's active window follows the X input focus, as on xcb
    def _x_focus(self, w, focus_in):
        self._focus_known = True
        if focus_in:
            self.xfocus, self._focus_out_at = w, None
            if self.clip is not None:
                self.clip.focus_in()
            # its floating panels above it, whatever the window manager does with transient windows: quartz-wm keeps
            # them above when it activates the owner, not when the owner is raised by a request (XQuartz probe), and
            # xcb's Qt raises them itself while dragging
            for r in self.wins.values():
                if r.get("owner") is w and not r.get("unmapped"):
                    r["x"].configure(stack_mode=self.X.Above)
            self.ev.flush()
        elif self.xfocus is w:
            self.xfocus, self._focus_out_at = None, time.perf_counter()
        if self.plat is None or self.plat.focus is None:
            # no way to tell Qt: a title bar of ours greys its lights from this flag instead (WindowOps.active)
            rec = self.wins.get(w)
            if rec is not None:
                rec["x_active"] = focus_in
            bar = w.menuWidget() if isinstance(w, QtWidgets.QMainWindow) else None
            if bar is not None:
                bar.update()

    def _sync_activation(self):
        """Offscreen activates every window it shows (popups and floating docks too) and leaves none active when a
        popup closes: shortcuts and tool tips then stopped working. Put back the X focus."""
        if not self._focus_known:
            return
        fw = QtGui.QGuiApplication.focusWindow()
        w = self.xfocus
        if w is not None and QtWidgets.QApplication.activePopupWidget() is not None:
            return                                          # Qt's popup mode: activation is Qt's own business
        if w is not None:
            h = w.windowHandle()
            if h is not None and fw is not h and w.isVisible():
                now = time.perf_counter()
                if now - self._activate_t > 0.05:
                    self._activate_t = now
                    h.requestActivate()
        elif fw is not None and self.plat is not None and self.plat.focus is not None \
                and self._focus_out_at is not None and time.perf_counter() - self._focus_out_at > 0.4:
            # nothing active (xcb also waits 400 ms for a FocusIn). Checked every tick: a popup closing hands Qt's
            # focus back to its parent window
            self.plat.focus(None, 3)

    # ---- cursors: what Qt shows (override cursor, else the window's) goes onto each X window
    def _sync_cursors(self):
        """Qt keeps the cursor per window (widgets set it on enter/leave, splitters on hover, an edge resizer as an
        override cursor); xcb copies it to the X window, and so does this."""
        oc = QtGui.QGuiApplication.overrideCursor()
        for w, rec in self.wins.items():
            if oc is not None:
                shape = oc.shape()
            else:
                h = w.windowHandle()
                shape = h.cursor().shape() if h is not None else CS.ArrowCursor
            if rec.get("cursor") != shape:
                rec["cursor"] = shape
                g = XCURSOR.get(shape, 68)
                if g not in self._xcursors:
                    font = self.ev.open_font("cursor")
                    self._xcursors[g] = font.create_glyph_cursor(font, g, g + 1, (0, 0, 0), (65535, 65535, 65535))
                rec["x"].change_attributes(cursor=self._xcursors[g])
                self.ev.flush()
