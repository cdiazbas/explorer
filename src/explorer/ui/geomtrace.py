"""A trace of every move and resize of the window and its panels (ROADMAP E6.7), for faults seen where they cannot be
watched again (through ssh -Y on someone's Mac). On 2026-10-02 such a trace found in minutes why lambda-t crept down
through XQuartz: each move came from the bridge applying the manager's notices, none from explorer's own code.

    EXPLORER_GEOMETRY_TRACE=1 explorer cube_im.fits   ->  ~/.cache/explorer/logs/geometry-<pid>.log

One line per event, milliseconds since the trace began:

    1203.1 EVT  lambda_t  Move   (541, 369, 560, 314)  buttons 0  pointer (320, 358)
    1302.4 CALL lambda_t  move (561, 389)  <- bridge.py:509 _apply_geometry <- windows.py:257 configured
    1303.0 LOOK glass
    1310.2 SHOW Spectrum

EVT is what the window or a panel underwent (Qt's Move, Resize); CALL is explorer's Python asking for it (setGeometry,
move, resize, setFloating on the main window and the panels), with the frames that asked, innermost first. An EVT with
no CALL just before it came from Qt itself, the window manager or the bridge. LOOK is M or --look; SHOW and HIDE a
panel or a window appearing or going. Nothing is wrapped or watched unless the trace is asked for.

    tracer = install_from_env()      # None unless EXPLORER_GEOMETRY_TRACE is set (and not 0)
    tracer = Tracer(path); ...; tracer.stop()
"""
import os
import sys
import time
import traceback
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .._name import ENV_PREFIX
from .._paths import cache_dir
from .shell import Shell

ENV = f"{ENV_PREFIX}GEOMETRY_TRACE"            # not EXPLORER_TRACE: that is the spans' Perfetto file
WATCHED = ("setGeometry", "move", "resize")
HERE = os.path.abspath(__file__)
_SKIP = (os.sep + "site-packages" + os.sep, os.sep + "lib" + os.sep + "python")   # Qt's, pyqtgraph's, the stdlib's
E = QtCore.QEvent.Type


def wanted(env=None) -> bool:
    """EXPLORER_GEOMETRY_TRACE set, and not to 0."""
    return (env if env is not None else os.environ).get(ENV, "").strip() not in ("", "0")


def install_from_env(env=None) -> "Tracer | None":
    if not wanted(env):
        return None
    d = cache_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    t = Tracer(d / f"geometry-{os.getpid()}.log")
    print(f"[geometry] tracing moves and resizes to {t.path}", file=sys.stderr)
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
        app = QtWidgets.QApplication.instance()
        assert app is not None                           # made before the window, as the tracer
        app.installEventFilter(self)
        self.write(f"START pid {os.getpid()}, {QtGui.QGuiApplication.platformName()}")

    def _wrap(self, cls, name) -> None:
        orig = getattr(cls, name)
        self._kept.append((cls, name, orig, name in vars(cls)))      # setGeometry is QWidget's: not the class's own

        def call(w, *a, _o=orig, _n=name, _t=self):
            _t.write(f"CALL {_who(w):9s} {_n} {_args(a)}  <- {_origin()}")
            return _o(w, *a)
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
