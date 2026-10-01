"""The display a plan chose, on Qt: the environment before Qt starts, the application, and what a window needs from
the platform. The views see WindowOps only; nothing else in the UI branches on the operating system (docs/plan.md
§3.5). From the prototype's app/startup.py (prepare, make_app, show, _mac_zoom_not_fullscreen, start_link_probe).
The X11 bridge is another Display (xbridge.BridgeDisplay); for_plan() picks the one a plan asks for.
"""
import os
import sys
from collections.abc import MutableMapping
from dataclasses import dataclass

from .._name import APP_NAME
from .plan import DisplayPlan

# Qt's offscreen platform says so for every raise() and size-hint update (under the bridge, one line per mouse move
# while a panel was dragged); only these messages are dropped, everything else still prints (the prototype's
# _quiet_offscreen)
OFFSCREEN_NOISE = ("This plugin does not support raise()", "This plugin does not support propagateSizeHints()",
                   "This plugin does not support grabbing the mouse",
                   "This plugin does not support grabbing the keyboard",
                   "This plugin does not support setting window masks")


def _quiet_offscreen() -> None:
    from PySide6 import QtCore

    def handler(mode, ctx, msg):
        if msg not in OFFSCREEN_NOISE:
            sys.stderr.write(msg + "\n")
    QtCore.qInstallMessageHandler(handler)


class NoDisplay(SystemExit):
    """The app cannot show a window here; the message says why and what to do."""


@dataclass(frozen=True)
class LinkInfo:
    """What the link to the screen carries: bytes per pixel of the image panel per image shown, and the playback
    rate not to go above. None: a local screen, no limit. Measured 2026-09-24 (the prototype's start_link_probe):
    Qt's own X11 ~4.8 B/px (4 B/px plus the side panels), capped at 30 fps; the bridge's in its Display. The
    link's own rate is measured by platform.linkprobe when playback sets its default (ROADMAP E4)."""
    bytes_per_px: float | None
    fps_cap: int | None


class WindowOps:
    """What a view may ask of its window: here, of a window Qt shows itself (cocoa, xcb, offscreen); the bridge's
    windows have their own (xbridge.BridgeWindowOps). The moving, shaping, zoom and cursor calls are the prototype's
    Mover (app/titlebar.py), what its title bar and edges ask of a window (ROADMAP E5.2)."""

    qwindow_events = True                               # the mouse reaches the window's QWindow (xcb, the bridge)

    def __init__(self, window, display: "Display"):
        self.w, self._display = window, display
        self.unzoomed = None                            # the geometry before a zoom, while zoomed
        self._override = False

    def resize(self, w: int, h: int) -> None:
        self.w.resize(int(w), int(h))

    def move(self, x: int, y: int) -> None:
        self.w.move(x, y)

    def set_geometry(self, r) -> None:
        self.w.setGeometry(r)

    def begin_drag(self) -> bool:
        """Let the window manager move the window (GNOME and KDE then also snap it); False: the caller moves it."""
        h = self.w.windowHandle()
        return bool(h and h.startSystemMove())

    def begin_resize(self, edges) -> bool:
        h = self.w.windowHandle()
        return bool(h and h.startSystemResize(edges))

    def set_shape(self, region) -> None:
        """The window's outline as a mask (Qt makes it an X SHAPE on xcb); None or empty: rectangular. Offscreen has
        no masks, and says so."""
        from PySide6 import QtGui

        if QtGui.QGuiApplication.platformName() == "offscreen":
            return
        if region is None or region.isEmpty():
            self.w.clearMask()
        else:
            self.w.setMask(region)

    @property
    def active(self) -> bool:
        return self.w.isActiveWindow()

    def activate(self) -> None:
        """Raise the window and give it the keyboard. Launched from a terminal, the first key (Space to play) went
        to the terminal otherwise (the prototype's show); on a Mac this also brings the app to the front."""
        self.w.raise_()
        self.w.activateWindow()

    def zoom(self) -> None:
        """Fill the monitor the window is on, or go back to the geometry it had: by geometry, so without a window
        manager too (Xvfb; XQuartz's offers no maximise to a frameless window)."""
        if self.unzoomed is not None:
            g, self.unzoomed = self.unzoomed, None
        else:
            from PySide6 import QtWidgets

            from .screens import monitor_rect

            app = QtWidgets.QApplication.instance()
            g, self.unzoomed = monitor_rect(app, self.w.geometry().center()), self.w.geometry()
        self.set_geometry(g)

    def minimize(self) -> None:
        self.w.showMinimized()

    def set_cursor(self, shape) -> None:
        """An override cursor (the widget under an edge may set its own), or none: only this one is removed, never
        other overrides on the stack. The bridge copies Qt's cursor to its X window."""
        from PySide6 import QtWidgets

        if self._override:
            QtWidgets.QApplication.restoreOverrideCursor()
            self._override = False
        if shape is not None:
            QtWidgets.QApplication.setOverrideCursor(shape)
            self._override = True


class Display:
    def __init__(self, plan: DisplayPlan):
        self.plan = plan

    @property
    def kind(self) -> str:
        return self.plan.kind

    def prepare_env(self, env: MutableMapping | None = None) -> None:
        """Before Qt starts: stop with the plan's message if there is no way to show a window, else set what the plan
        asks (QT_QPA_PLATFORM)."""
        if self.plan.stop:
            raise NoDisplay(f"[{APP_NAME}] {self.plan.stop}")
        target = os.environ if env is None else env
        for k, v in self.plan.env.items():
            target[k] = v

    def make_app(self, argv=None):
        """The QApplication (the running one if there is one), named after the app. Stops when Qt sees no screen: a
        Mac reached by ssh without X11 starts Qt and has none (the prototype's make_app)."""
        from typing import cast

        from PySide6 import QtWidgets

        app = cast(QtWidgets.QApplication,
                   QtWidgets.QApplication.instance() or QtWidgets.QApplication(list(argv or sys.argv[:1])))
        app.setApplicationName(APP_NAME)
        if not app.screens():
            where = ("macOS over ssh has no window server: connect with ssh -Y (the window then comes through X11), "
                     "or run it in a Terminal on that Mac" if sys.platform == "darwin"
                     else "no display: check DISPLAY or ssh -Y")
            raise NoDisplay(f"[{APP_NAME}] no screen to show the window on. {where}.")
        if app.platformName() != "cocoa":
            app.setStyle("Fusion")                      # over X11 there is no desktop theme; the look comes in E5
        if app.platformName() == "offscreen":
            _quiet_offscreen()
        return app

    def ops(self, window) -> WindowOps:
        """What a view may ask of window (move, resize, zoom, shape, cursor), before it is shown: a title bar of ours
        makes the window frameless first."""
        return WindowOps(window, self)

    def attach(self, app, window, ops: WindowOps | None = None) -> WindowOps:
        """Show the window, raise it and give it the keyboard; on a local Mac, its green button zooms rather than
        opening a full-screen space. ops: the window's, when its title bar already holds them."""
        ops = ops or self.ops(window)
        window.show()
        ops.activate()
        if sys.platform == "darwin" and app.platformName() == "cocoa":
            _mac_zoom_not_fullscreen(window)
        return ops

    def link(self) -> LinkInfo:
        if self.plan.remote and not self.plan.bridge:
            return LinkInfo(bytes_per_px=4.8, fps_cap=30)
        return LinkInfo(bytes_per_px=None, fps_cap=None)

    def stats(self) -> dict:
        return {"kind": self.kind, "platform": self.plan.platform, "remote": self.plan.remote,
                "bridge": self.plan.bridge, "notes": list(self.plan.notes)}

    def close(self) -> None:
        pass


def for_plan(plan: DisplayPlan) -> Display:
    """The Display a plan asks for: the X11 bridge's, or Qt's own platform."""
    if plan.bridge:
        from .xbridge import BridgeDisplay

        return BridgeDisplay(plan)
    return Display(plan)


def _mac_zoom_not_fullscreen(window) -> None:
    """A local Mac: the green button zooms (fills the screen without the menu bar and the Dock) instead of opening a
    full-screen space (decided by the user). Qt's WindowFullscreenButtonHint does not reach it: the NSWindow's
    collectionBehavior is set directly, FullScreenPrimary (128) out, FullScreenNone (512) in. Measured in the
    prototype: 128 -> 512, and a maximised window at the screen's visible frame."""
    import ctypes

    try:
        objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
        sel = objc.sel_registerName
        sel.restype, sel.argtypes = ctypes.c_void_p, [ctypes.c_char_p]
        get = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(("objc_msgSend", objc))
        put = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)(("objc_msgSend", objc))
        win = get(ctypes.c_void_p(int(window.winId())), sel(b"window"))      # the NSView's NSWindow
        if win:
            b = int(get(win, sel(b"collectionBehavior")) or 0)
            put(win, sel(b"setCollectionBehavior:"), (b & ~128) | 512)
    except (OSError, AttributeError, ValueError):
        pass                                            # an unexpected Qt or macOS: the system's green button
