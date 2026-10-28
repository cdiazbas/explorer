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
        were delayed on the way (the link, explorer); events stamped far apart came late from the server."""
        from ..platform.xbridge import xproto
        from ..platform.xbridge.bridge import Bridge

        orig = Bridge._event
        self._kept.append((Bridge, "_event", orig, True))
        kinds = {xproto.MotionNotify: "motion", xproto.ButtonPress: "press", xproto.ButtonRelease: "release"}

        def event(bridge, raw, _o=orig, _t=self):
            kind = kinds.get(raw[0] & 0x7F)
            if kind is not None:
                e = xproto.decode_event(raw)
                _t.write(f"XIN  {kind:7s} x_time {e.time} at ({e.root_x}, {e.root_y})")
            return _o(bridge, raw)
        Bridge._event = event                            # type: ignore[method-assign]

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
        if t in (E.Move, E.Resize, E.Show, E.Hide) and isinstance(obj, (QtWidgets.QMainWindow, QtWidgets.QDockWidget)):
            if t in (E.Move, E.Resize):
                p = QtGui.QCursor.pos()
                self.write(f"EVT  {_who(obj):9s} {t.name:6s} {_rect(obj.geometry())}  buttons "
                           f"{int(QtWidgets.QApplication.mouseButtons().value)}  pointer ({p.x()}, {p.y()})")
            else:
                self.write(f"{'SHOW' if t == E.Show else 'HIDE'} {_who(obj)}")
        return False

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
