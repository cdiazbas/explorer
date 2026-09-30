"""X input into Qt through public API only: QMouseEvent, QWheelEvent and QKeyEvent sent to the QWindow of the top-level
widget (QCoreApplication.sendEvent), QCursor.setPos, and QWindow.requestActivate. No private Qt symbol, so no tie to
one Qt build (the prototype reached QWindowSystemInterface through ctypes).

What Qt's widget layer does with an event sent to a QWindow (QWidgetWindow), measured on offscreen (Qt 6.11.2): it
picks the child under the pointer, keeps the pressed widget as the receiver of a drag (the implicit grab), sends
Enter/Leave and Hover between widgets, gives focus by click, makes a ContextMenu from a right press, routes
everything to an open popup (a press outside closes it) and to a modal window; the widgets receive the mouse events
as spontaneous (tool tips after a rest work). Key events reach the focus widget, and shortcuts fire (QShortcut),
with text, auto-repeat and native codes. QGuiApplication.mouseButtons() and keyboardModifiers() follow the mouse
events. What it does not do, and this module does instead:
- double clicks: Qt makes them from a platform's presses only; here from the X server's times (same button, within
  the double-click interval and distance); widgets then see press, release, double click, release, as with xcb;
- wheel propagation: a wheel event sent to a window reaches the widget under the pointer as non-spontaneous, and
  Qt does not pass it on to the parents (a QSpinBox's line edit ignored it); here each widget up the chain gets it
  until one accepts it, with Qt's popup and modal rules;
- the cursor position: QCursor.setPos on offscreen also makes Qt's window Enter/Leave (by window geometry); it is
  set when the pointer enters or leaves, at each press and release, and once the pointer rests. Offscreen also
  sends a mouse move for each setPos (source MouseEventSynthesizedByQt) that xcb never sends: after a pan, the one
  after the release moved the crosshair to another pixel. Those moves are dropped (is_own_synthetic_move);
- activation: offscreen activates every window it shows; Qt's active window is set from the X focus with
  requestActivate, and with no X focus in the application, a plain QWindow (no widgets) is activated, so that no
  widget window is active.
Not covered (Qt has no public way in, stated with the tests): QGuiApplication.keyboardModifiers() follows mouse
events and key presses, but the release of a modifier key alone leaves it stale until the next of those (xcb clears
it); input methods (no IME); drag and drop between applications.
"""
import time

from PySide6 import QtCore, QtGui, QtWidgets

from . import keys as K
from . import xproto as X

Qt, E = QtCore.Qt, QtCore.QEvent
BUTTONS = {1: Qt.MouseButton.LeftButton, 2: Qt.MouseButton.MiddleButton, 3: Qt.MouseButton.RightButton,
           8: Qt.MouseButton.BackButton, 9: Qt.MouseButton.ForwardButton}
STATE_BUTTONS = ((0x100, Qt.MouseButton.LeftButton), (0x200, Qt.MouseButton.MiddleButton),
                 (0x400, Qt.MouseButton.RightButton))
REST_MS = 60                                            # the pointer at rest: Qt's cursor position is set
OFF_SCREEN = (-(1 << 20), -(1 << 20))                   # Qt's cursor where no window is
OWN_MOVE_S = 1.0                                        # a setPos's answering move comes within this
POPUPS_MAX = 16                                         # nested popups closed when the X focus leaves
FOCUS_OUT_MS = 400                                      # X focus gone from every window of ours (xcb waits the same)


def _app() -> QtGui.QGuiApplication:
    app = QtGui.QGuiApplication.instance()
    assert isinstance(app, QtGui.QGuiApplication)
    return app


def _qt_key(name_or_code) -> int:
    if isinstance(name_or_code, int):
        return name_or_code
    return int(getattr(Qt.Key, name_or_code).value)


class QtInput:
    """keymap(): the current keys.Keymap. geometry_hit(x, y): whether a root point is inside a Qt window of ours by
    geometry (then a Leave has to be forced)."""

    def __init__(self, keymap, windows_at=None):
        self.keymap = keymap
        self.windows_at = windows_at or (lambda x, y: False)
        self.buttons = Qt.MouseButton.NoButton
        self._last_press = None                         # (button, X time, root x, y): double clicks
        self._grabbed: QtWidgets.QWidget | None = None  # the widget of a double click's press
        self._root = None                               # last pointer position, root coordinates
        self._own_moves: list = []                      # (x, y, time) of our setPos: offscreen answers with a move
        self._rest = QtCore.QTimer()
        self._rest.setSingleShot(True)
        self._rest.setInterval(REST_MS)
        self._rest.timeout.connect(self._at_rest)
        self._sink: QtGui.QWindow | None = None
        self.xfocus = None                              # the top-level widget with the X focus, None: none of ours
        self._focus_out = QtCore.QTimer()
        self._focus_out.setSingleShot(True)
        self._focus_out.setInterval(FOCUS_OUT_MS)
        self._focus_out.timeout.connect(self._focus_left)
        self._following = False
        self._known = False                             # an X focus event has come: until then Qt keeps its own
        _app().focusWindowChanged.connect(self._qt_focus_changed)
        self.stats = dict(mouse=0, keys=0, wheel=0, dblclick=0, activations=0)

    # ---------------------------------------------------------------- helpers
    def mods(self, state: int, sym: int | None = None) -> QtCore.Qt.KeyboardModifier:
        km = self.keymap()
        m = Qt.KeyboardModifier.NoModifier
        if state & K.MOD_SHIFT:
            m |= Qt.KeyboardModifier.ShiftModifier
        if state & K.MOD_CONTROL:
            m |= Qt.KeyboardModifier.ControlModifier
        if km is not None:
            if state & km.alt:
                m |= Qt.KeyboardModifier.AltModifier
            if state & km.meta:
                m |= Qt.KeyboardModifier.MetaModifier
            if (km.mode_switch and state & km.mode_switch) or (km.level3 and state & km.level3):
                m |= Qt.KeyboardModifier.GroupSwitchModifier
        if sym is not None and K.is_keypad(sym):
            m |= Qt.KeyboardModifier.KeypadModifier
        return m

    @staticmethod
    def _state_buttons(state: int) -> QtCore.Qt.MouseButton:
        b = Qt.MouseButton.NoButton
        for bit, qb in STATE_BUTTONS:
            if state & bit:
                b |= qb
        return b

    def _send_mouse(self, h: QtGui.QWindow, typ, e, button, buttons, mods) -> None:
        loc, glob = QtCore.QPointF(e.x, e.y), QtCore.QPointF(e.root_x, e.root_y)
        ev = QtGui.QMouseEvent(typ, loc, loc, glob, button, buttons, mods)
        ev.setTimestamp(e.time)
        QtCore.QCoreApplication.sendEvent(h, ev)
        self.stats["mouse"] += 1

    def _set_cursor(self, x: int, y: int, force: bool = False) -> None:
        """Qt's cursor position. force: even where it already is, so that offscreen finds again which window holds it
        (a window that moved or resized under a still pointer gets its Leave or Enter). QCursor.setPos does nothing
        where the cursor already is, so it goes off every screen first."""
        if QtGui.QCursor.pos() == QtCore.QPoint(x, y):
            if not force:
                return
            self._own_set_pos(*OFF_SCREEN)
        self._own_set_pos(x, y)

    def _own_set_pos(self, x: int, y: int) -> None:
        now = time.monotonic()
        self._own_moves = [m for m in self._own_moves if now - m[2] < OWN_MOVE_S] + [(x, y, now)]
        QtGui.QCursor.setPos(x, y)

    def is_own_synthetic_move(self, e) -> bool:
        """e (a MouseMove to a QWindow) is offscreen's answer to one of our setPos, not input: dropped."""
        if e.source() != Qt.MouseEventSource.MouseEventSynthesizedByQt or not self._own_moves:
            return False
        g = e.globalPosition().toPoint()
        now = time.monotonic()
        for i, (x, y, t) in enumerate(self._own_moves):
            if (x, y) == (g.x(), g.y()) and now - t < OWN_MOVE_S:
                del self._own_moves[i]
                return True
        return False

    def _at_rest(self) -> None:
        if self._root is not None and self.buttons == Qt.MouseButton.NoButton:
            self._set_cursor(*self._root)

    # ---------------------------------------------------------------- the pointer
    def motion(self, w: QtWidgets.QWidget, e) -> None:
        h = w.windowHandle()
        if h is None:
            return
        self._root = (e.root_x, e.root_y)
        buttons = self._state_buttons(e.state)
        self.buttons = buttons
        if buttons == Qt.MouseButton.NoButton:
            self._end_double_grab()                     # its release went to a window that was gone
        self._send_mouse(h, E.Type.MouseMove, e, Qt.MouseButton.NoButton, buttons, self.mods(e.state))
        if buttons == Qt.MouseButton.NoButton:
            self._rest.start()

    def button(self, w: QtWidgets.QWidget, e) -> None:
        h = w.windowHandle()
        if h is None:
            return
        press = e.code == X.ButtonPress
        mods = self.mods(e.state)
        if e.detail in (4, 5, 6, 7):
            if press:
                self._wheel(w, e, mods)
            return
        b = BUTTONS.get(e.detail)
        if b is None:
            return
        before = self._state_buttons(e.state)
        if press and before == Qt.MouseButton.NoButton:
            # a double click's grab whose release never came: its widget's window was unmapped under the pointer (a
            # floating panel docked by the double click), so X sent the release nowhere; the grab kept every later
            # press away from the other windows
            self._end_double_grab()
        self.buttons = (before | b) if press else (before & ~b)
        self._root = (e.root_x, e.root_y)
        if not press:
            self._send_mouse(h, E.Type.MouseButtonRelease, e, b, self.buttons, mods)
            if self.buttons == Qt.MouseButton.NoButton:
                self._end_double_grab()
                self._set_cursor(e.root_x, e.root_y)    # not followed during the drag
            return
        self._set_cursor(e.root_x, e.root_y)            # menus opened by a click appear at QCursor.pos()
        if self._is_double(b, e):
            # Qt's widgets see press, release, double click, release: the platform's second press is marked as
            # part of a double click and not delivered to widgets (QWidgetWindow); the double click takes its place.
            # That press also makes its widget the receiver of the moves and the release that follow; without it
            # Qt drops them, so the widget holds the mouse (QWidget.grabMouse) until the buttons are up
            self._last_press = None
            self._double_grab(w, e)
            self._send_mouse(h, E.Type.MouseButtonDblClick, e, b, self.buttons, mods)
            self.stats["dblclick"] += 1
        else:
            self._last_press = (b, e.time, e.root_x, e.root_y)
            self._send_mouse(h, E.Type.MouseButtonPress, e, b, self.buttons, mods)

    def _double_grab(self, w: QtWidgets.QWidget, e) -> None:
        if QtWidgets.QWidget.mouseGrabber() is not None or QtWidgets.QApplication.activePopupWidget() is not None:
            return
        target = w.childAt(QtCore.QPoint(e.x, e.y)) or w
        target.grabMouse()
        self._grabbed = target

    def _end_double_grab(self) -> None:
        g, self._grabbed = self._grabbed, None
        if g is not None and QtWidgets.QWidget.mouseGrabber() is g:
            g.releaseMouse()

    def _is_double(self, b, e) -> bool:
        lp = self._last_press
        if lp is None or lp[0] != b:
            return False
        hints = QtGui.QGuiApplication.styleHints()
        dist = hints.mouseDoubleClickDistance() if hasattr(hints, "mouseDoubleClickDistance") \
            else hints.startDragDistance()
        dt = (e.time - lp[1]) & 0xFFFFFFFF
        return dt < hints.mouseDoubleClickInterval() and abs(e.root_x - lp[2]) + abs(e.root_y - lp[3]) <= dist

    def _wheel(self, w: QtWidgets.QWidget, e, mods) -> None:
        d = 120 if e.detail in (4, 6) else -120
        horizontal = e.detail in (6, 7) or bool(mods & Qt.KeyboardModifier.AltModifier)     # as xcb
        delta = QtCore.QPoint(d, 0) if horizontal else QtCore.QPoint(0, d)
        glob = QtCore.QPointF(e.root_x, e.root_y)
        root: QtWidgets.QWidget = w
        popup = QtWidgets.QApplication.activePopupWidget()
        if popup is not None and popup is not w:
            if not popup.geometry().contains(glob.toPoint()):
                return                                  # Qt ignores the wheel outside an open popup
            root = popup
        modal = QtWidgets.QApplication.activeModalWidget()
        if modal is not None and root.window() is not modal and not modal.isAncestorOf(root):
            return
        pos = root.mapFromGlobal(glob.toPoint())
        target: QtWidgets.QWidget | None = root.childAt(pos) or root
        while target is not None:
            local = QtCore.QPointF(target.mapFromGlobal(glob.toPoint()))
            ev = QtGui.QWheelEvent(local, glob, QtCore.QPoint(), delta, self._state_buttons(e.state), mods,
                                   Qt.ScrollPhase.NoScrollPhase, False)
            ev.setTimestamp(e.time)
            ev.setAccepted(False)
            QtCore.QCoreApplication.sendEvent(target, ev)
            if ev.isAccepted() or target.isWindow() or target.testAttribute(Qt.WidgetAttribute.WA_NoMousePropagation):
                break
            target = target.parentWidget()
        self.stats["wheel"] += 1

    def crossing(self, w: QtWidgets.QWidget, e) -> None:
        """The pointer entered or left an X window of ours. Not while a button is down (the drag owns the pointer),
        not for grab changes nor virtual crossings (xcb's rules)."""
        if self.buttons != Qt.MouseButton.NoButton or e.mode not in (X.NotifyNormal, X.NotifyUngrab) \
                or e.detail in (X.NotifyVirtual, X.NotifyNonlinearVirtual):
            return
        self._root = (e.root_x, e.root_y)
        # forced: the crossing may come from the window moving under a still pointer (a zoomed window restored away
        # from it), where Qt's cursor is already at that point and offscreen would not look again
        if e.code == X.EnterNotify:
            self._set_cursor(e.root_x, e.root_y, force=True)
            return
        self._rest.stop()
        if self.windows_at(e.root_x, e.root_y):
            # still inside a Qt window by geometry (another client above it, or a shaped corner): offscreen would
            # not send the Leave, so Qt's cursor goes where no window is
            self._set_cursor(*OFF_SCREEN, force=True)
        else:
            self._set_cursor(e.root_x, e.root_y, force=True)

    # ---------------------------------------------------------------- keys
    def key(self, w: QtWidgets.QWidget, e, repeat: bool) -> None:
        km = self.keymap()
        if km is None:
            return
        sym = km.keysym(e.detail, e.state)
        mods = self.mods(e.state, sym)
        got = K.translate(sym, bool(e.state & K.MOD_CONTROL))
        if got is None:
            return
        key, text = got
        popup = QtWidgets.QApplication.activePopupWidget()
        h = (popup or w).windowHandle()                 # an open popup takes the keys, as with xcb's keyboard grab
        if h is None:
            return
        typ = E.Type.KeyPress if e.code == X.KeyPress else E.Type.KeyRelease
        ev = QtGui.QKeyEvent(typ, _qt_key(key), mods, e.detail, sym, e.state, text, repeat, 1)
        ev.setTimestamp(e.time)
        QtCore.QCoreApplication.sendEvent(h, ev)
        self.stats["keys"] += 1

    # ---------------------------------------------------------------- activation
    def _sink_window(self, parent: QtGui.QWindow) -> QtGui.QWindow:
        """A 1x1 QWindow without widgets, far from every screen: activating it leaves no widget window active. It is
        shown only while in use, as a secondary window of the one that was active (transient parent): a visible
        window of its own would keep the application from quitting when its last widget window closes."""
        if self._sink is None:
            s = QtGui.QWindow()
            s.setObjectName("xbridge2-focus-sink")
            s.setFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
            s.setGeometry(-(1 << 21), -(1 << 21), 1, 1)
            self._sink = s
        self._sink.setTransientParent(parent)
        self._sink.show()
        return self._sink

    def is_sink(self, h) -> bool:
        return h is not None and h is self._sink

    def x_focus(self, w, focus_in: bool) -> None:
        """The X focus came to top-level w or left it."""
        self._known = True
        if focus_in:
            self.xfocus = w
            self._focus_out.stop()
            self.follow()
        elif self.xfocus is w:
            self.xfocus = None
            self._focus_out.start()

    def _focus_left(self) -> None:
        if self.xfocus is None:
            self.follow()

    def follow(self) -> None:
        """Make Qt's active window the one with the X focus (or none). While a popup is open Qt's popup mode manages
        activation itself, unless the X focus has left the application: then its popups close first, as with xcb
        (a combo's list stayed open, and the window active, when the X focus went to another client)."""
        if not self._known:
            return
        if QtWidgets.QApplication.activePopupWidget() is not None:
            if self.xfocus is not None or self._focus_out.isActive():
                return
            for _ in range(POPUPS_MAX):
                p = QtWidgets.QApplication.activePopupWidget()
                if p is None:
                    break
                p.close()
        fw = QtGui.QGuiApplication.focusWindow()
        w = self.xfocus
        if w is not None:
            h = w.windowHandle()
            if h is not None and fw is not h and w.isVisible():
                self._activate(h)
            if self._sink is not None and self._sink.isVisible():
                self._sink.hide()
        elif fw is not None and not self.is_sink(fw) and not self._focus_out.isActive():
            self._activate(self._sink_window(fw))

    def _activate(self, h: QtGui.QWindow) -> None:
        self._following = True
        try:
            h.requestActivate()
            self.stats["activations"] += 1
        finally:
            self._following = False

    def _qt_focus_changed(self, _win) -> None:
        # offscreen activates each window it shows, and a closing popup hands activation to its parent: put the
        # X focus back, once the change is done
        if not self._following:
            QtCore.QTimer.singleShot(0, self.follow)

    def close(self) -> None:
        self._rest.stop()
        self._focus_out.stop()
        try:
            _app().focusWindowChanged.disconnect(self._qt_focus_changed)
        except (RuntimeError, TypeError):
            pass
        if self._sink is not None:
            self._sink.destroy()
            self._sink = None

