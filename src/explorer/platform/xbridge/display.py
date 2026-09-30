"""The Display the plan asks for when it chooses the bridge: the bridge connects before Qt starts and turns Qt's
platform into offscreen with the X monitors as its screens; the window is mirrored once shown. From the prototype's
app/startup.py (prepare, make_app, show, start_link_probe) and xbridge.BridgeMover.
"""
import os
import sys
from collections.abc import MutableMapping
from typing import Any

from PySide6 import QtCore, QtGui

from ..._name import APP_NAME
from ..display import Display, LinkInfo, NoDisplay, WindowOps

# Bytes per image-panel pixel per image shown, measured through ssh -Y in the prototype: grey tiles ~1.3 (0.64-0.8 MB
# per update for a 754x815 panel), without them ~2.5 (Qt's own X11: ~4.8). The bridge is then CPU-bound, not
# link-bound (asked 12 fps -> 12.2 shown, 0.04 s behind; asked 23 -> 15.5 shown, 0.48 s behind, bellatrix), so its
# playback is capped at 12 (to be measured with a Mac as the host).
BYTES_PER_PX_GREY, BYTES_PER_PX_COLOUR, FPS_CAP = 1.3, 2.5, 12


class BridgeWindowOps(WindowOps):
    """A window shown through the bridge: the X window moves first and Qt follows; the window manager moves and
    resizes it when it can (_NET_WM_MOVERESIZE); zoom fills the X monitor under the window's centre."""

    def __init__(self, window, display: "BridgeDisplay"):
        super().__init__(window, display)
        self.b: Any = display.bridge
        self._unzoomed: QtCore.QRect | None = None

    @property
    def qwindow_events(self) -> bool:
        """Mouse input reaches the QWindow (Qt's platform entry), so an edge resizer can watch it there."""
        return self.b.plat is not None

    def activate(self) -> None:
        self.b.activate(self.w)

    def move(self, x: int, y: int) -> None:
        self.b.move_window(self.w, x, y)

    def set_geometry(self, r) -> None:
        self.w.resize(r.size())
        self.b.move_window(self.w, r.x(), r.y())

    def begin_drag(self) -> bool:
        return self.b.wm_moveresize(self.w)

    def begin_resize(self, edges) -> bool:
        return self.b.wm_moveresize(self.w, edges)

    def zoom(self) -> None:
        """Fill the X monitor the window is on, or go back to the geometry it had."""
        if self._unzoomed is not None:
            g, self._unzoomed = self._unzoomed, None
        else:
            c = self.w.geometry().center()
            hs = [QtCore.QRect(*h) for h in self.b.heads()]
            g, self._unzoomed = next((h for h in hs if h.contains(c)), hs[0]), self.w.geometry()
        self.set_geometry(g)

    def set_shape(self, region) -> None:
        """The window's outline (rounded corners of a title bar of ours) as an X SHAPE; None or empty: rectangular.
        Offscreen Qt has no masks, so it is kept here and sent on the next tick."""
        rec = self.b.wins.get(self.w)
        if rec is not None:
            rec["shape"] = QtGui.QRegion() if region is None else QtGui.QRegion(region)

    def set_resizer(self, resizer) -> None:
        """An edge resizer (mouse(kind, pos, global pos, buttons) -> bool) that legacy input feeds first; with Qt's
        platform entry it watches the QWindow instead."""
        rec = self.b.wins.get(self.w)
        if rec is not None:
            rec["resizer"] = resizer

    @property
    def active(self) -> bool:
        rec = self.b.wins.get(self.w) or {}
        return rec.get("x_active", self.w.isActiveWindow())


class BridgeDisplay(Display):
    def __init__(self, plan):
        super().__init__(plan)
        self.bridge: Any = None

    def prepare_env(self, env: MutableMapping | None = None) -> None:
        """Connect to the X display, then offscreen Qt with the X monitors as its screens."""
        if self.plan.stop:
            raise NoDisplay(f"[{APP_NAME}] {self.plan.stop}")
        from .bridge import Bridge

        try:
            self.bridge = Bridge()
        except ImportError as e:
            raise NoDisplay(f"[{APP_NAME}] the X11 bridge needs python-xlib ({e}): run scripts/setup_env.sh "
                            "again") from e
        except Exception as e:
            from .xconn import diagnose

            raise NoDisplay(f"[{APP_NAME}] cannot open the X display {os.environ.get('DISPLAY')!r} ({e}).\n    "
                            f"{diagnose()}") from e
        target = os.environ if env is None else env
        for k, v in self.plan.env.items():
            target[k] = v
        target["QT_QPA_PLATFORM"] = self.bridge.qpa()

    def make_app(self, argv=None):
        app = super().make_app(argv)
        self.bridge.sync_cursor()                           # the window opens on the monitor under the X pointer
        return app

    def attach(self, app, window) -> WindowOps:
        """Show the window and mirror it; the window manager is asked to activate it once it has taken it in. A window
        without Qt's frame (a title bar of ours) asks the manager for none."""
        ops = BridgeWindowOps(window, self)
        window.show()
        self.bridge.attach(app, window, own_frame=bool(window.windowFlags() & QtCore.Qt.WindowType.FramelessWindowHint))
        # the bridge's traffic, at quit
        app.aboutToQuit.connect(lambda: print(f"[{APP_NAME}] {self.bridge.describe()}", file=sys.stderr))
        return ops

    def link(self) -> LinkInfo:
        grey = self.bridge is None or self.bridge.grey_on
        return LinkInfo(bytes_per_px=BYTES_PER_PX_GREY if grey else BYTES_PER_PX_COLOUR, fps_cap=FPS_CAP)

    def stats(self) -> dict:
        d = super().stats()
        b = self.bridge
        if b is not None:
            d["input"] = "legacy" if b.plat is None else "platform"
            d["input_missing"] = [] if b.plat is None else b.plat.missing()
            d["xbridge"] = b.summary()
        return d

    def close(self) -> None:
        if self.bridge is not None:
            self.bridge.close()
