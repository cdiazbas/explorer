"""A trace of every move and resize of the window and its panels (ROADMAP E6.7), for faults seen where they cannot be
watched again (through ssh -Y on someone's Mac). Such a trace found in minutes why lambda-t crept down
through XQuartz: each move came from the bridge applying the manager's notices, none from explorer's own code.

    explorer --log cube_im.fits   ->  ~/.cache/explorer/logs/geometry-<pid>.log   (or EXPLORER_GEOMETRY_TRACE=1)

Asked for, not on by default: on every start it cost 3 % per cursor move offscreen and 7 % through the bridge
(bellatrix, ABBA). The newest sessions are kept (_paths.KEEP_LOGS).

One line per event, milliseconds since the trace began:

    1203.1 EVT  lambda_t  Move   (541, 369, 560, 314)  buttons 0  pointer (320, 358)
    1302.4 CALL lambda_t  move (561, 389)  <- bridge.py:509 _apply_geometry <- windows.py:257 configured
    1303.0 LOOK glass
    1310.2 SHOW Spectrum
    1520.7 RESET panels
    1520.9 PLACE monitor (0, 25, 1512, 912)  window (102, 25, 900, 887)  panels spectrum, lambda_t

EVT is what the window or a panel underwent (Qt's Move, Resize); CALL is explorer's Python asking for it (setGeometry,
move, resize, setFloating on the main window and the panels), with the frames that asked, innermost first. An EVT with
no CALL just before it came from Qt itself, the window manager or the bridge. LOOK is M or --look; SHOW and HIDE a
panel or a window appearing or going. SCREENS, at the start: the screens Qt sees and, with an X display, Xinerama's
heads (through the bridge one XQuartz screen can be two monitors). RESET: the reset button; PLACE: the glass look
placing its panels, from the monitor and the window frame it starts from. XIN: a pointer event (motion, press, release)
the X11 bridge takes, with the X server's time in ms and the root position. Nothing is wrapped or watched unless the
trace is asked for.

The keys, for keys that do nothing on someone's screen: what the X server sent and what Qt did with it.

     465.8 XIN  focus   in  mode Normal detail Nonlinear  main 0x400002
     726.5 ACTIVE main
    8033.9 FOCUS QSpinBox < QToolBar[nav] < main  reason Mouse
    8596.2 XIN  key     x_time 2099915765 keycode 22 state 0x0 keysym 0xff08 -> Key_Backspace  main 0x400002
    8597.1 KEY  Key_Backspace text '\x08' mods none  to main  focus QSpinBox < QToolBar[nav] < main  active main
    9003.6 XIN  key     x_time 2099916173 keycode 54 state 0x0 keysym 0x63 -> 'C'  main 0x400002
    9004.1 KEY  Key_C text 'c' mods none  to main  focus QSpinBox < QToolBar[nav] < main  active main

(the frames-per-second box took the focus at a click, and kept Backspace and C: no shortcut fired; with the focus on
the image, each KEY is followed by "KEY  shortcut Backspace  on main").

XIN key: a key press as the bridge reads it (its keysym through the server's keyboard map, the Qt key it becomes, or
why it goes no further); XIN focus: the X focus coming to or leaving a window of ours, and the window manager's
WM_TAKE_FOCUS. KEY: a key press reaching a window of Qt's (the widget with the keyboard focus, the active window), and
each shortcut it fires; a KEY with no shortcut after it fired none: a widget with the focus may keep the key (a spin
box keeps Backspace and letters). FOCUS: the widget that gets the keyboard focus, and why; ACTIVE and INACTIVE: a
window becoming Qt's active window or ceasing to be. Only key presses, not releases; the keys typed are in the file.

    tracer = install_from_env()      # None unless EXPLORER_GEOMETRY_TRACE is set (and not 0)
    tracer = Tracer(path); ...; tracer.stop()
"""
import os
import time
import traceback
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .._name import ENV_PREFIX
from .._paths import trace_log
from ..obs import say
from .shell import Shell

ENV = f"{ENV_PREFIX}GEOMETRY_TRACE"            # not EXPLORER_TRACE: that is the spans' Perfetto file
WATCHED = ("setGeometry", "move", "resize")
HERE = os.path.abspath(__file__)
_SKIP = (os.sep + "site-packages" + os.sep, os.sep + "lib" + os.sep + "python")   # Qt's, pyqtgraph's, the stdlib's
E = QtCore.QEvent.Type
KEYS = (E.KeyPress, E.Shortcut, E.FocusIn, E.WindowActivate, E.WindowDeactivate)    # Tracer._keys
X_MODES = ("Normal", "Grab", "Ungrab", "WhileGrabbed")
X_DETAILS = ("Ancestor", "Virtual", "Inferior", "Nonlinear", "NonlinearVirtual", "Pointer", "PointerRoot", "None")


def wanted(env=None) -> bool:
    """EXPLORER_GEOMETRY_TRACE set, and not to 0 (explorer --log sets it)."""
    return (env if env is not None else os.environ).get(ENV, "").strip() not in ("", "0")


def install_from_env(env=None) -> "Tracer | None":
    if not wanted(env):
        return None
    t = Tracer(trace_log("geometry"))
    say.info(f"geometry: tracing moves and resizes to {t.path}")
    return t


def _who(w) -> str:
    if isinstance(w, QtWidgets.QMainWindow):
        return "main"
    return w.objectName() or w.windowTitle() or type(w).__name__


def _chain(w, depth: int = 3) -> str:
    """A widget and its parents, innermost first, each by class and object name: QSpinBox < QToolBar[nav]."""
    out: list[str] = []
    while w is not None and len(out) < depth:
        if isinstance(w, QtWidgets.QMainWindow):
            out.append("main")
            break
        out.append(type(w).__name__ + (f"[{w.objectName()}]" if w.objectName() else ""))
        w = w.parentWidget()
    return " < ".join(out) or "none"


def _window(win) -> str:
    """A QWindow by the widget it holds: main, a panel's name."""
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.windowHandle() is win:
            return _who(w)
    return win.objectName() or win.title() or type(win).__name__


def _active() -> str:
    w = QtWidgets.QApplication.activeWindow()
    return _who(w) if w is not None else "none"


MODS = (("Shift", QtCore.Qt.KeyboardModifier.ShiftModifier), ("Ctrl", QtCore.Qt.KeyboardModifier.ControlModifier),
        ("Alt", QtCore.Qt.KeyboardModifier.AltModifier), ("Meta", QtCore.Qt.KeyboardModifier.MetaModifier),
        ("Keypad", QtCore.Qt.KeyboardModifier.KeypadModifier),
        ("Group", QtCore.Qt.KeyboardModifier.GroupSwitchModifier))


def _mods(m) -> str:
    return "+".join(n for n, f in MODS if m & f) or "none"


def _key_name(key: int) -> str:
    try:
        return QtCore.Qt.Key(key).name
    except ValueError:
        return f"{key:#x}"


def _rect(r: QtCore.QRect) -> str:
    return f"({r.x()}, {r.y()}, {r.width()}, {r.height()})"


def _arg(x) -> str:
    if isinstance(x, QtCore.QRect):
        return _rect(x)
    if isinstance(x, QtCore.QPoint):
        return f"({x.x()}, {x.y()})"
    if isinstance(x, QtCore.QSize):
        return f"({x.width()}, {x.height()})"
    return repr(x)


def _args(a) -> str:
    """One argument as it is, (x, y, w, h) for a rectangle; several in parentheses: move(561, 389)."""
    return _arg(a[0]) if len(a) == 1 else "(" + ", ".join(_arg(x) for x in a) + ")"


def _origin(limit: int = 3) -> str:
    """The frames that asked, innermost first: explorer's (and its tests'), not Qt's, the stdlib's nor this file's."""
    out = []
    for f in reversed(traceback.extract_stack()[:-1]):
        if f.filename == HERE or any(s in f.filename for s in _SKIP):
            continue
        out.append(f"{os.path.basename(f.filename)}:{f.lineno} {f.name}")
        if len(out) == limit:
            break
    return " <- ".join(out) or "?"


def _screens() -> str:
    """The screens Qt sees (geometry, available) and, with an X display, Xinerama's heads and whether it is XQuartz."""
    out = [f"{i}: {_rect(sc.geometry())} available {_rect(sc.availableGeometry())}"
           for i, sc in enumerate(QtGui.QGuiApplication.screens())]
    if os.environ.get("DISPLAY"):
        from ..platform.screens import _x_facts

        f = _x_facts()
        out.append(f"X heads {[_rect(h) for h in f['heads']] or 'none'}{', XQuartz' if f['xquartz'] else ''}")
    return "; ".join(out) or "none"


class Tracer(QtCore.QObject):
    def __init__(self, path):
        super().__init__(QtWidgets.QApplication.instance())
        self.path = Path(path)
        self._out = open(self.path, "w", buffering=1, encoding="utf-8")
        self._t0 = time.perf_counter()
        self._kept: list[tuple[type, str, object, bool]] = []      # class, name, what it had, whether its own
        for cls in (QtWidgets.QMainWindow, QtWidgets.QDockWidget):
            for name in WATCHED + (("setFloating",) if cls is QtWidgets.QDockWidget else ()):
                self._wrap(cls, name)
        orig = Shell.set_look
        self._kept.append((Shell, "set_look", orig, True))

        def set_look(shell, look, _o=orig, _t=self):
            _t.write(f"LOOK {look.name}")
            return _o(shell, look)
        Shell.set_look = set_look                        # type: ignore[method-assign]
        self._wrap_said(Shell, "reset_panels", lambda shell: "RESET panels")
        from ..platform.screens import monitor_rect
        from .glass import GlassChrome

        def placing(chrome):
            w = chrome.w
            m = monitor_rect(QtWidgets.QApplication.instance(), w.frameGeometry().center())
            shown = ", ".join(d.objectName() for d in chrome.docks() if not d.isHidden()) or "none"
            return f"PLACE monitor {_rect(m)}  window {_rect(w.frameGeometry())}  panels {shown}"
        self._wrap_said(GlassChrome, "place_panels", placing)
        self._wrap_pointer_events()
        app = QtWidgets.QApplication.instance()
        assert app is not None                           # made before the window, as the tracer
        app.installEventFilter(self)
        self.write(f"START pid {os.getpid()}, {QtGui.QGuiApplication.platformName()}")
        self.write("SCREENS " + _screens())

    def _wrap(self, cls, name) -> None:
        orig = getattr(cls, name)
        self._kept.append((cls, name, orig, name in vars(cls)))      # setGeometry is QWidget's: not the class's own

        def call(w, *a, _o=orig, _n=name, _t=self):
            _t.write(f"CALL {_who(w):9s} {_n} {_args(a)}  <- {_origin()}")
            return _o(w, *a)
        setattr(cls, name, call)

    def _wrap_pointer_events(self) -> None:
        """Each pointer event the X11 bridge takes, with the X server's time: bursts of events stamped close together
        were delayed on the way (the link, explorer); events stamped far apart came late from the server. Each key
        press and each change of the X focus too (_x_key, _x_focus)."""
        from ..platform.xbridge import xproto
        from ..platform.xbridge.bridge import Bridge

        orig = Bridge._event
        self._kept.append((Bridge, "_event", orig, True))
        kinds = {xproto.MotionNotify: "motion", xproto.ButtonPress: "press", xproto.ButtonRelease: "release"}

        def event(bridge, raw, _o=orig, _t=self):
            code = raw[0] & 0x7F
            kind = kinds.get(code)
            if kind is not None:
                e = xproto.decode_event(raw)
                _t.write(f"XIN  {kind:7s} x_time {e.time} at ({e.root_x}, {e.root_y})")
            elif code == xproto.KeyPress:
                _t._x_key(bridge, xproto.decode_event(raw))
            elif code in (xproto.FocusIn, xproto.FocusOut, xproto.ClientMessage):
                _t._x_focus(bridge, xproto.decode_event(raw))
            return _o(bridge, raw)
        Bridge._event = event                            # type: ignore[method-assign]

    def _x_key(self, bridge, e) -> None:
        from ..platform.xbridge import keys

        km = bridge.keymap
        head = f"XIN  key     x_time {e.time} keycode {e.detail} state {e.state:#x}"
        if km is None:
            self.write(f"{head} -> no keyboard map from the X server: dropped  {self._x_window(bridge, e.window)}")
            return
        sym = km.keysym(e.detail, e.state)
        got = keys.translate(sym, bool(e.state & keys.MOD_CONTROL))
        to = "no Qt key: dropped" if got is None else got[0] if isinstance(got[0], str) else repr(chr(got[0]))
        self.write(f"{head} keysym {sym:#x} -> {to}  {self._x_window(bridge, e.window)}")

    def _x_focus(self, bridge, e) -> None:
        from ..platform.xbridge import xproto

        if e.code == xproto.ClientMessage:
            atoms = bridge.windows.atoms
            if e.format == 32 and e.type == atoms.get("WM_PROTOCOLS") and e.data[0] == atoms.get("WM_TAKE_FOCUS"):
                self.write(f"XIN  focus   WM_TAKE_FOCUS x_time {e.data[1]}  {self._x_window(bridge, e.window)}")
            return
        mode = X_MODES[e.mode] if e.mode < len(X_MODES) else str(e.mode)
        detail = X_DETAILS[e.detail] if e.detail < len(X_DETAILS) else str(e.detail)
        self.write(f"XIN  focus   {'in ' if e.code == xproto.FocusIn else 'out'} mode {mode} detail {detail}  "
                   f"{self._x_window(bridge, e.window)}")

    @staticmethod
    def _x_window(bridge, xid: int) -> str:
        rec = bridge.windows.by_xid.get(xid)
        return f"{_who(rec.w) if rec is not None else 'not ours'} {xid:#x}"

    def _wrap_said(self, cls, name, say) -> None:
        """cls.name writes say(obj) to the trace before it runs."""
        orig = getattr(cls, name)
        self._kept.append((cls, name, orig, True))

        def call(obj, *a, _o=orig, _t=self, **k):
            _t.write(say(obj))
            return _o(obj, *a, **k)
        setattr(cls, name, call)

    def write(self, line: str) -> None:
        if not self._out.closed:
            self._out.write(f"{(time.perf_counter() - self._t0) * 1e3:9.1f} {line}\n")

    def eventFilter(self, obj, e):
        t = e.type()
        if t in KEYS:
            self._keys(obj, e, t)
        if t in (E.Move, E.Resize, E.Show, E.Hide) and isinstance(obj, (QtWidgets.QMainWindow, QtWidgets.QDockWidget)):
            if t in (E.Move, E.Resize):
                p = QtGui.QCursor.pos()
                self.write(f"EVT  {_who(obj):9s} {t.name:6s} {_rect(obj.geometry())}  buttons "
                           f"{int(QtWidgets.QApplication.mouseButtons().value)}  pointer ({p.x()}, {p.y()})")
            else:
                self.write(f"{'SHOW' if t == E.Show else 'HIDE'} {_who(obj)}")
        return False

    def _keys(self, obj, e, t) -> None:
        """A key press where it reaches a window (the first stop on its way to the focus widget: one line a press),
        the shortcuts it fires, the keyboard focus and the active window as they change."""
        if t == E.KeyPress and isinstance(obj, QtGui.QWindow):
            fw = QtWidgets.QApplication.focusWidget()
            self.write(f"KEY  {_key_name(e.key())} text {e.text()!r} mods {_mods(e.modifiers())}"
                       f"{' repeat' if e.isAutoRepeat() else ''}  to {_window(obj)}  focus {_chain(fw)}  "
                       f"active {_active()}")
        elif t == E.Shortcut and isinstance(obj, QtGui.QShortcut):
            p = obj.parent()
            self.write(f"KEY  shortcut {e.key().toString()}  on {_who(p) if isinstance(p, QtWidgets.QWidget) else p}")
        elif t == E.FocusIn and isinstance(obj, QtWidgets.QWidget):
            self.write(f"FOCUS {_chain(obj)}  reason {e.reason().name.removesuffix('FocusReason')}")
        elif t in (E.WindowActivate, E.WindowDeactivate) and isinstance(obj, QtWidgets.QWidget) and obj.isWindow():
            self.write(f"{'ACTIVE' if t == E.WindowActivate else 'INACTIVE'} {_who(obj)}")

    def stop(self) -> None:
        """Everything back as it was (the tests); the file closed."""
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        for cls, name, orig, own in reversed(self._kept):
            if own:
                setattr(cls, name, orig)
            else:
                delattr(cls, name)
        self._kept = []
        self._out.close()
