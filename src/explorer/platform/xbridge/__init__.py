"""The X11 bridge, written anew (ROADMAP E6, decision P4 "rewrite"; docs/decisions/0009): Qt renders offscreen and
its windows reach an X display through X windows of their own. The display plan takes it over ssh, or with --x11
bridge (EXPLORER_X11=bridge); it replaced the prototype's bridge brought over as it was (in the history).

    xproto.py     the X11 wire client (connection, requests, replies and events on a reader thread)
    transport.py  pixels: tile comparison, grey at 1 B/px through RENDER, double buffer, on a thread of its own
    kernels.py    the numba kernels of the transport
    windows.py    X windows for Qt's top-levels: ICCCM/EWMH, geometry, state, shape, cursor, activation
    icon.py       a window's icon as _NET_WM_ICON, in one request (ui.appicon takes the conversion from here)
    qtinput.py    X input into Qt through public API only
    keys.py       X keyboard to Qt keys (no Qt)
    clipboard.py  the X CLIPBOARD, with INCR both ways
    bridge.py     the two stages (before and after the QApplication) and the event flow
    trace.py      what goes to X and comes back, per window, read back from the server (EXPLORER_BRIDGE_TRACE=1)
"""
import os
import sys
from collections.abc import MutableMapping
from typing import TYPE_CHECKING

from ...obs import get_logger
from ..display import Display, LinkInfo, NoDisplay, WindowOps
from ..plan import DisplayPlan

if TYPE_CHECKING:
    from .bridge import Bridge, XLink

log = get_logger("platform.xbridge")


class BridgeWindowOps(WindowOps):
    """Activation, minimising, and moving and resizing by the title bar and the edges asked of the X window manager, as
    a native window would; the shape published for the X SHAPE. Zoom is WindowOps', by geometry, which the bridge
    carries to X."""
    _display: "BridgeDisplay"

    def activate(self) -> None:
        self.w.raise_()
        self.w.activateWindow()
        b = self._display.bridge
        if b is not None:
            b.activate(self.w)

    def minimize(self) -> None:
        self.w.showMinimized()                          # the bridge asks the manager (WindowStateChange)

    def begin_drag(self) -> bool:
        """The window manager moves the window when it can (_NET_WM_MOVERESIZE: GNOME and KDE then also snap it);
        False otherwise (quartz-wm, no manager): the title bar moves it."""
        b = self._display.bridge
        return (b is not None and b.moveresize(self.w)) or super().begin_drag()

    def begin_resize(self, edges) -> bool:
        b = self._display.bridge
        return (b is not None and b.moveresize(self.w, edges)) or super().begin_resize(edges)

    def outline(self, colour):
        """Drawn by the X server, on a connection of its own (platform.xoutline): a Qt window would be sent whole,
        pixels and all, at every step."""
        from ..display import XOutlineOps

        return XOutlineOps(colour)

    def set_shape(self, region) -> None:
        """Offscreen keeps no masks: the region is published where the bridge reads it for the X SHAPE
        (windows.SHAPE_ATTR). None or empty: rectangular."""
        from PySide6 import QtGui

        from .windows import SHAPE_ATTR

        setattr(self.w, SHAPE_ATTR, QtGui.QRegion() if region is None else QtGui.QRegion(region))


class BridgeDisplay(Display):
    def __init__(self, plan: DisplayPlan):
        super().__init__(plan)
        self.xlink: XLink | None = None
        self.bridge: Bridge | None = None

    def prepare_env(self, env: MutableMapping | None = None) -> None:
        """Connect to the X display before Qt starts: Qt's screens are its monitors."""
        super().prepare_env(env)
        from .bridge import XLink

        try:
            link = XLink.open(os.environ.get("DISPLAY"))
        except (OSError, ValueError) as e:
            raise NoDisplay(f"cannot open the X display {os.environ.get('DISPLAY')!r}: {e}") from e
        self.xlink = link
        target = os.environ if env is None else env
        target["QT_QPA_PLATFORM"] = link.qpa()

    def make_app(self, argv=None):
        app = super().make_app(argv)
        from .bridge import Bridge

        if self.xlink is None:
            raise NoDisplay("the X11 bridge needs prepare_env() before the application")
        self.bridge = Bridge(self.xlink, app)
        return app

    def ops(self, window) -> WindowOps:
        return BridgeWindowOps(window, self)

    def attach(self, app, window, ops: WindowOps | None = None) -> WindowOps:
        ops = ops or self.ops(window)
        window.show()
        b = self.bridge
        assert b is not None, "make_app() first"
        b.attach(window)
        app.aboutToQuit.connect(lambda: print(b.describe(), file=sys.stderr, flush=True))
        return ops

    def link(self) -> LinkInfo:
        """Bytes per image-panel pixel and the playback cap. Until measured here (ROADMAP E6): the prototype's bridge,
        1.3 B/px with grey tiles and 12 fps (bellatrix to XQuartz, 2026-09-24)."""
        return LinkInfo(bytes_per_px=1.3, fps_cap=10)       # the default's ceiling (toolbar.FPS)

    def stats(self) -> dict:
        d = super().stats()
        d["xbridge"] = self.bridge.summary() if self.bridge is not None else None
        return d

    def close(self) -> None:
        if self.bridge is not None:
            self.bridge.close()
