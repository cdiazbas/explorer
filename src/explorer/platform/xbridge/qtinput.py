"""X input into Qt. From the prototype's app/xbridge.py (_Platform, the key tables, the input half of XBridge).

Two ways in, measured against Qt's xcb plugin on Xvfb by the prototype's conformance check:
- "platform", the default: X input enters Qt where a platform plugin's does (Platform: qt_handleMouseEvent,
  qt_handleWheelEvent, qt_handleKeyEvent), so Qt itself makes double clicks from the X timestamps, Enter/Leave and
  hover chains, focus by click, context-menu events, the popup taking every press, mouse grabs, the tool-tip timer,
  wheel propagation and shortcuts, as on xcb;
- "legacy" (when this Qt lacks those symbols, or EXPLORER_XB_INPUT=legacy): QMouseEvents made here and sent to the
  widget under the pointer; that way 77 of 89 conformance steps ended in another state than on xcb.
Every X event reaches Qt from a zero timer of its own (QtInput._later), never from inside the bridge's tick.
"""
import sys
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from .state import Shared

Qt = QtCore.Qt
KM, MB = Qt.KeyboardModifier, Qt.MouseButton

# X keysyms that are not printable characters -> Qt keys
KEYS = {0xff08: "Key_Backspace", 0xff09: "Key_Tab", 0xff0d: "Key_Return", 0xff1b: "Key_Escape",
        0xffff: "Key_Delete", 0xff50: "Key_Home", 0xff51: "Key_Left", 0xff52: "Key_Up", 0xff53: "Key_Right",
        0xff54: "Key_Down", 0xff55: "Key_PageUp", 0xff56: "Key_PageDown", 0xff57: "Key_End",
        0xff8d: "Key_Enter", 0xff63: "Key_Insert", 0xfe20: "Key_Backtab", 0xff67: "Key_Menu",
        0xff61: "Key_Print", 0xff13: "Key_Pause", 0xff14: "Key_ScrollLock",
        0xffe1: "Key_Shift", 0xffe2: "Key_Shift", 0xffe3: "Key_Control", 0xffe4: "Key_Control",
        0xffe7: "Key_Meta", 0xffe8: "Key_Meta", 0xffe9: "Key_Alt", 0xffea: "Key_Alt",
        0xffeb: "Key_Super_L", 0xffec: "Key_Super_R", 0xffe5: "Key_CapsLock", 0xff7f: "Key_NumLock",
        0xfe03: "Key_AltGr", 0xff7e: "Key_Mode_switch"}
KEYS.update({0xffbe + i: f"Key_F{i + 1}" for i in range(12)})
# numeric keypad without NumLock: the same Qt keys as the main block
KEYS.update({0xff95: "Key_Home", 0xff96: "Key_Left", 0xff97: "Key_Up", 0xff98: "Key_Right", 0xff99: "Key_Down",
             0xff9a: "Key_PageUp", 0xff9b: "Key_PageDown", 0xff9c: "Key_End", 0xff9f: "Key_Delete",
             0xff9e: "Key_Insert", 0xff9d: "Key_Clear"})
# keypad with NumLock: digits and operators, text included (Qt adds KeypadModifier, as xcb)
KEYS.update({0xffb0 + i: f"Key_{i}" for i in range(10)})
KEYS.update({0xffaa: "Key_Asterisk", 0xffab: "Key_Plus", 0xffad: "Key_Minus", 0xffae: "Key_Period",
             0xffaf: "Key_Slash", 0xffac: "Key_Comma", 0xffbd: "Key_Equal"})
# the text xkb gives these keys (xcb passes it on; Return is "\r", not "")
KEY_TEXT = {0xff08: "\x08", 0xff09: "\t", 0xff0d: "\r", 0xff1b: "\x1b", 0xffff: "\x7f", 0xff8d: "\r",
            0xfe20: "\t", 0xffaa: "*", 0xffab: "+", 0xffad: "-", 0xffae: ".", 0xffaf: "/", 0xffac: ",", 0xffbd: "="}
KEY_TEXT.update({0xffb0 + i: str(i) for i in range(10)})
MOD_OF_KEY = {0xffe1: KM.ShiftModifier, 0xffe2: KM.ShiftModifier, 0xffe3: KM.ControlModifier,
              0xffe4: KM.ControlModifier, 0xffe9: KM.AltModifier, 0xffea: KM.AltModifier,
              0xffe7: KM.MetaModifier, 0xffe8: KM.MetaModifier}
BUTTONS = {1: MB.LeftButton, 2: MB.MiddleButton, 3: MB.RightButton, 8: MB.BackButton, 9: MB.ForwardButton}


def _iv(x) -> int:
    return x.value if hasattr(x, "value") else int(x)


def ctrl_char(ch: str) -> str:
    """What xkb (libxkbcommon's XkbToControl) makes of a character typed with Ctrl."""
    c = ord(ch)
    if 0x40 <= c < 0x7f or ch == " ":
        return chr(c & 0x1f)
    return {"2": "\x00", "8": "\x7f", "/": "\x1f"}.get(ch, chr(c - ord("3") + 0x1b) if "3" <= ch <= "7" else ch)


def key_of(sym: int, mods):
    """(Qt key, text, modifiers) for a keysym, or None for a key Qt has no name for. Latin-1 and Unicode keysyms are
    code points; Qt's key is the upper case (ß has none of one letter)."""
    text = ""
    if 0x20 <= sym <= 0x7e or 0xa0 <= sym <= 0xff or sym & 0xff000000 == 0x01000000:
        ch = chr(sym & 0xffffff if sym > 0xff else sym)
        u = ch.upper()
        try:
            key = Qt.Key(ord(u if len(u) == 1 else ch))
        except ValueError:
            return None
        text = ch
        if mods & KM.ControlModifier and ch.isascii():
            text = ctrl_char(ch)                            # as xkb: Ctrl+A gives "\x01"
    elif sym in KEYS:
        key = getattr(Qt.Key, KEYS[sym])
        text = KEY_TEXT.get(sym, "")
    else:
        return None
    if 0xff80 <= sym <= 0xffbd:                             # keypad keysyms, as xcb
        mods |= KM.KeypadModifier
    return key, text, mods


def qtgui_path() -> str | None:
    """File of the QtGui library this process loaded: ctypes must reach that copy."""
    if sys.platform.startswith("linux"):
        with open("/proc/self/maps") as f:
            for line in f:
                if "libQt6Gui.so" in line:
                    return line.split()[-1]
    elif sys.platform == "darwin":
        import ctypes

        dyld = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        dyld._dyld_get_image_name.restype = ctypes.c_char_p
        dyld._dyld_get_image_name.argtypes = [ctypes.c_uint32]
        for i in range(dyld._dyld_image_count()):
            n = (dyld._dyld_get_image_name(i) or b"").decode()
            if n.endswith("QtGui.framework/Versions/A/QtGui"):
                return n
    return None


class Platform:
    """Qt's own entry for platform input, reached through ctypes: qt_handleMouseEvent, qt_handleWheelEvent and
    qt_handleKeyEvent are exported by QtGui for QTest (called from its inline code, so they stay in the Qt 6 ABI);
    QTest's own mouse functions cannot be used, because they set their own timestamps and add a double-click interval
    after every release. The focus handler is private API (exported, not promised): without it Qt's active window
    cannot follow the X focus out of the application. Measured with Qt 6.11.2 on bellatrix, offscreen: events arrive
    spontaneous, Qt makes the double click, the context-menu event, wheel propagation; the key texts keep ñ and control
    characters. Enter and Leave of a window (private too) fall back to sending QEvent.Enter/Leave to the QWindow."""
    MOUSE = ("_Z19qt_handleMouseEventP7QWindowRK7QPointFS3_6QFlagsIN2Qt11MouseButtonEES6_N6QEvent4Type"
             "ES4_INS5_16KeyboardModifierEEi")
    WHEEL = "_Z19qt_handleWheelEventP7QWindowRK7QPointFS3_6QPointS4_6QFlagsIN2Qt16KeyboardModifierEENS6_11ScrollPhaseE"
    KEY = "_Z17qt_handleKeyEventP7QWindowN6QEvent4TypeEi6QFlagsIN2Qt16KeyboardModifierEERK7QStringbt"
    FOCUS = ("_ZN22QWindowSystemInterface24handleFocusWindowChangedINS_19SynchronousDeliveryEEEvP7QWindow"
             "N2Qt11FocusReasonE")
    ENTER = "_ZN22QWindowSystemInterface16handleEnterEventINS_19SynchronousDeliveryEEEvP7QWindowRK7QPointFS6_"
    LEAVE = "_ZN22QWindowSystemInterface16handleLeaveEventINS_19SynchronousDeliveryEEEvP7QWindow"
    c: Any                                              # ctypes
    ptr: Any                                            # a Qt object -> its C++ pointer
    _strings: dict
    mouse: Any                                          # the entry points; key, focus, enter, leave may be None
    wheel: Any
    key: Any
    focus: Any
    enter: Any
    leave: Any

    @classmethod
    def load(cls, legacy: bool = False) -> "Platform | None":
        """The entry points of this process's QtGui; None (the legacy path) when the mouse or wheel ones are missing."""
        if legacy or sys.maxsize < 2 ** 32:
            return None
        try:
            import ctypes as c

            import shiboken6

            path = qtgui_path()
            if path is None:
                return None
            lib, p = c.CDLL(path), cls()
            p.c, p.ptr, p._strings = c, (lambda o: shiboken6.getCppPointer(o)[0]), {}
            # QFlags, enums and ints go as int; QPoint by value as one 64-bit register (x in the low half: x86-64
            # System V and arm64 alike); const references as pointers
            p.mouse = lib[cls.MOUSE]
            p.mouse.argtypes = [c.c_void_p, c.c_void_p, c.c_void_p, c.c_int, c.c_int, c.c_int, c.c_int, c.c_int]
            p.wheel = lib[cls.WHEEL]
            p.wheel.argtypes = [c.c_void_p, c.c_void_p, c.c_void_p, c.c_uint64, c.c_uint64, c.c_int, c.c_int]
            p.mouse.restype = p.wheel.restype = None
            p.key = p.focus = None
            try:
                p.key = lib[cls.KEY]
                p.key.restype = None
                p.key.argtypes = [c.c_void_p, c.c_int, c.c_int, c.c_int, c.c_void_p, c.c_bool, c.c_ushort]
            except AttributeError:
                pass
            try:
                p.focus = lib[cls.FOCUS]
                p.focus.restype = None
                p.focus.argtypes = [c.c_void_p, c.c_int]
            except AttributeError:
                pass
            p.enter = p.leave = None
            try:
                p.enter = lib[cls.ENTER]
                p.enter.restype = None
                p.enter.argtypes = [c.c_void_p, c.c_void_p, c.c_void_p]
                p.leave = lib[cls.LEAVE]
                p.leave.restype = None
                p.leave.argtypes = [c.c_void_p]
            except AttributeError:
                p.enter = p.leave = None
            return p
        except Exception:
            return None

    def missing(self) -> list[str]:
        """The optional entry points this Qt lacks (each has a fallback)."""
        return [n for n in ("key", "focus", "enter", "leave") if getattr(self, n) is None]

    def qstring(self, text):
        """A QString over our own UTF-16 buffer (Qt 6 layout: d, ptr, size; d null = raw data, never freed by Qt).
        Copies of it share the buffer, so every text is kept for the life of the process: key texts are a few
        characters, and few distinct ones."""
        s = self._strings.get(text)
        if s is None:
            c = self.c
            raw = text.encode("utf-16-le")
            buf = c.create_string_buffer(raw + b"\0\0", len(raw) + 2)
            q = (c.c_void_p * 3)(None, c.addressof(buf), len(raw) // 2)
            s = self._strings[text] = (q, buf)
        return self.c.addressof(s[0])


class QtInput(Shared):
    """The input half of the bridge (mixed into bridge.Bridge, whose state it shares: plat, wins, ev, X, app)."""

    def _later(self, fn, *a):
        """Hand one X event to Qt from a zero timer of its own, in arrival order, never from inside the tick. A click
        that opens a menu or a dialog runs a nested event loop inside its handler, and Qt does not fire a timer again
        while its previous call is still running: a click handled inside the tick stopped the tick, nothing read X any
        more, the menu waited for a click that never came and the viewer hung (reproduced on Xvfb with a real X click:
        0 ticks in the 3 s after it). Now the tick returns at once and keeps running inside any nested loop, which then
        receives the next events like any other."""
        QtCore.QTimer.singleShot(0, lambda: self._deliver(fn, a))

    def _deliver(self, fn, a):
        if self.dead:
            return
        try:
            fn(*a)
        except Exception as e:                              # as in the tick: a display gone closes, else a bug
            if not x_gone(e):
                raise
            self._lost(e)

    def _key_repeat(self, w, e, r):
        self._repeat = r
        self._key(w, e)

    def _crossing(self, w, e):
        """The pointer entered or left an X window of ours: the same for Qt's window. xcb's rules: not while a button
        is down (the drag owns the pointer), not for grab changes nor virtual crossings. A window's rounded shape is
        only known to X: Qt's geometry still contains a pointer that left through a corner."""
        X = self.X
        if self.plat is None or self.buttons != MB.NoButton or e.mode not in (X.NotifyNormal, X.NotifyUngrab) \
                or e.detail in (X.NotifyVirtual, X.NotifyNonlinearVirtual):
            return
        h = w.windowHandle()
        if h is None:
            return
        P = self.plat
        if e.type == X.EnterNotify:
            QtGui.QCursor.setPos(e.root_x, e.root_y)
            loc, glob = QtCore.QPointF(e.event_x, e.event_y), QtCore.QPointF(e.root_x, e.root_y)
            if P.enter is not None:
                P.enter(P.ptr(h), P.ptr(loc), P.ptr(glob))
            else:
                QtCore.QCoreApplication.sendEvent(h, QtGui.QEnterEvent(loc, loc, glob))
        elif P.leave is not None:
            P.leave(P.ptr(h))
        else:
            QtCore.QCoreApplication.sendEvent(h, QtCore.QEvent(QtCore.QEvent.Type.Leave))

    # ---- mouse
    @staticmethod
    def _mods(state):
        m = KM.NoModifier
        if state & 1:
            m |= KM.ShiftModifier
        if state & 4:
            m |= KM.ControlModifier
        if state & 8:
            m |= KM.AltModifier
        if state & 64:
            m |= KM.MetaModifier
        return m

    def _mouse(self, w, e, typ, button):
        """One mouse event through Qt's platform entry, with the X server's timestamp (double clicks)."""
        h = w.windowHandle()
        if h is None:
            return
        P, t = self.plat, e.time & 0xffffffff
        loc, glob = QtCore.QPointF(e.event_x, e.event_y), QtCore.QPointF(e.root_x, e.root_y)
        P.mouse(P.ptr(h), P.ptr(loc), P.ptr(glob), _iv(self.buttons), _iv(button), _iv(typ),
                _iv(self._mods(e.state)), t - (1 << 32) if t >= 1 << 31 else t)

    def _target(self, w, x, y):
        """legacy: the widget that gets a mouse event at (x, y) of top-level w, and the point in its coordinates."""
        t = self.grab_target if self.grab_target is not None else (w.childAt(x, y) or w)
        g = w.mapToGlobal(QtCore.QPoint(x, y))
        return t, t.mapFromGlobal(g)

    def _resizer(self, w, kind, e, buttons):
        """legacy: the edge resizer of a window with its own frame (WindowOps.set_resizer) takes the event first."""
        r = self.wins.get(w, {}).get("resizer")
        return bool(r) and r.mouse(kind, QtCore.QPoint(e.event_x, e.event_y), QtCore.QPoint(e.root_x, e.root_y),
                                   buttons)

    def _motion(self, w, e):
        # QCursor.pos(); offscreen also turns it into Enter/Leave of Qt's windows by their geometry, which during a
        # drag out of the window would be a Leave that xcb does not send (the edge resizer lost its cursor): not
        # while a button is down
        if self.plat is None or self.buttons == MB.NoButton:
            QtGui.QCursor.setPos(e.root_x, e.root_y)
        if self.plat is not None:
            self._mouse(w, e, QtCore.QEvent.Type.MouseMove, MB.NoButton)
            return
        if self._resizer(w, QtCore.QEvent.Type.MouseMove, e, self.buttons):
            return
        t, p = self._target(w, e.event_x, e.event_y)
        if t is not getattr(self, "_under", None):          # Qt's Enter/Leave, which sendEvent does not make
            old = getattr(self, "_under", None)
            if old is not None:
                try:
                    QtWidgets.QApplication.sendEvent(old, QtCore.QEvent(QtCore.QEvent.Type.Leave))
                except RuntimeError:                        # widget already deleted
                    pass
            QtWidgets.QApplication.sendEvent(t, QtGui.QEnterEvent(QtCore.QPointF(p), QtCore.QPointF(p),
                                                                  QtCore.QPointF(e.root_x, e.root_y)))
            self._under = t
        ev = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(p), QtCore.QPointF(e.root_x, e.root_y),
                               MB.NoButton, self.buttons, self._mods(e.state))
        QtWidgets.QApplication.sendEvent(t, ev)

    def _button(self, w, e):
        mods = self._mods(e.state)
        press = e.type == self.X.ButtonPress
        if e.detail in (4, 5, 6, 7):                        # wheel: 4 up, 5 down, 6 left, 7 right
            if not press:
                return
            d = 120 if e.detail in (4, 6) else -120
            # as xcb: 6/7, and 4/5 with Alt, are horizontal
            dx, dy = (d, 0) if e.detail in (6, 7) or mods & KM.AltModifier else (0, d)
            if self.plat is not None:
                h = w.windowHandle()
                if h is not None:
                    P = self.plat
                    loc, glob = QtCore.QPointF(e.event_x, e.event_y), QtCore.QPointF(e.root_x, e.root_y)
                    P.wheel(P.ptr(h), P.ptr(loc), P.ptr(glob), 0, (dx & 0xffffffff) | ((dy & 0xffffffff) << 32),
                            _iv(mods), 0)
                return
            t, p = self._target(w, e.event_x, e.event_y)
            wev = QtGui.QWheelEvent(QtCore.QPointF(p), QtCore.QPointF(e.root_x, e.root_y), QtCore.QPoint(),
                                    QtCore.QPoint(dx, dy), self.buttons, mods, Qt.ScrollPhase.NoScrollPhase, False)
            QtWidgets.QApplication.sendEvent(t, wev)
            return
        b = BUTTONS.get(e.detail)
        if b is None:
            return
        E = QtCore.QEvent.Type
        if self.plat is not None:
            self.buttons = (self.buttons | b) if press else (self.buttons & ~b)
            self._mouse(w, e, E.MouseButtonPress if press else E.MouseButtonRelease, b)
            if self.buttons == MB.NoButton:
                QtGui.QCursor.setPos(e.root_x, e.root_y)    # not updated during the drag (_motion)
            return
        if self._resizer(w, E.MouseButtonPress if press else E.MouseButtonRelease, e,
                         (self.buttons | b) if press else self.buttons):
            return
        if press:
            for pw in list(self.wins):                      # a click outside an open popup closes it, as Qt would
                if self.wins[pw]["popup"] and pw is not w:
                    pw.close()
        t, p = self._target(w, e.event_x, e.event_y)
        if press:
            self.buttons |= b
            self.grab_target = t
            if t.focusPolicy() & Qt.FocusPolicy.ClickFocus:
                t.setFocus(Qt.FocusReason.MouseFocusReason)
        else:
            self.buttons &= ~b
        ev = QtGui.QMouseEvent(E.MouseButtonPress if press else E.MouseButtonRelease,
                               QtCore.QPointF(p), QtCore.QPointF(e.root_x, e.root_y), b, self.buttons, mods)
        QtWidgets.QApplication.sendEvent(t, ev)
        if press:
            # Qt makes double clicks out of the platform's events; sendEvent skips that step, so a title bar never saw
            # one. Qt's rule: same button, second press within the double-click interval and the drag distance; a
            # third press starts again
            hints, lp = QtGui.QGuiApplication.styleHints(), self._last_press
            if (lp is not None and lp[0] == b and (e.time - lp[1]) & 0xffffffff <= hints.mouseDoubleClickInterval()
                    and abs(e.root_x - lp[2]) + abs(e.root_y - lp[3]) <= hints.startDragDistance()):
                self._last_press = None
                QtWidgets.QApplication.sendEvent(t, QtGui.QMouseEvent(
                    E.MouseButtonDblClick, QtCore.QPointF(p), QtCore.QPointF(e.root_x, e.root_y),
                    b, self.buttons, mods))
            else:
                self._last_press = (b, e.time, e.root_x, e.root_y)
        if not press and self.buttons == MB.NoButton:
            self.grab_target = None

    # ---- keyboard
    def _keysym(self, e):
        """Keysym of a key event: shift level from the state; group 2 when Mode_switch is down (XQuartz's Option key,
        core protocol: python-xlib does not speak XKB)."""
        if self._mode_switch is None:
            ms = 0
            for i, codes in enumerate(self.ev.get_modifier_mapping()):
                if any(c and self.ev.keycode_to_keysym(c, 0) in (0xff7e, 0xfe03) for c in codes):
                    ms |= 1 << i
            self._mode_switch = ms
        shift = 1 if e.state & 1 else 0
        grp = 2 if self._mode_switch and e.state & self._mode_switch else 0
        return (self.ev.keycode_to_keysym(e.detail, grp + shift) or self.ev.keycode_to_keysym(e.detail, grp)
                or self.ev.keycode_to_keysym(e.detail, shift) or self.ev.keycode_to_keysym(e.detail, 0))

    def _key(self, w, e):
        from PySide6.QtTest import QTest

        sym = self._keysym(e)
        got = key_of(sym, self._mods(e.state))
        if got is None:                                     # no Qt key for it: ignored
            return
        key, text, mods = got
        press = e.type == self.X.KeyPress
        rep = self._repeat == e.detail
        if press:
            self._repeat = None
        if self.plat is not None and self.plat.key is not None:
            # an open popup takes the keys, as with xcb's keyboard grab: the key goes to its window, so a Return that
            # closes it in ShortcutOverride still reaches its list
            pop = QtWidgets.QApplication.activePopupWidget()
            h = (pop or w).windowHandle()
            if h is not None:
                P = self.plat
                P.key(P.ptr(h), _iv(QtCore.QEvent.Type.KeyPress if press else QtCore.QEvent.Type.KeyRelease),
                      _iv(key), _iv(mods), P.qstring(text), rep, 1)
            return
        target = self.app.focusWidget() or w
        # QTest delivers keys the way the platform would, shortcuts included (sendEvent skips QShortcut).
        # sendKeyEvent takes key and text apart: the text keeps its case and non-ASCII letters (ñ, é); keyPress(widget,
        # "ñ") passed the first UTF-8 byte instead ("Ã")
        if sym in MOD_OF_KEY:
            return                                          # QTest adds the modifier keys itself
        act = QTest.KeyAction.Press if press else QTest.KeyAction.Release
        QTest.sendKeyEvent(act, target, key, text if text and text.isprintable() else "", mods)


def x_gone(e) -> bool:
    """True for the errors of a lost X connection (python-xlib's, or the socket's)."""
    from Xlib import error as xerror

    return isinstance(e, (xerror.ConnectionClosedError, ConnectionError, BrokenPipeError, OSError))

