"""The state bridge.Bridge shares with its two halves (wm.WindowManager, qtinput.QtInput), declared once for the type
checker; Bridge.__init__ sets every field."""
from typing import Any


class Shared:
    X: Any                          # python-xlib's X constants and Xutil
    Xutil: Any
    ev: Any                         # the interface thread's X connection
    scr: Any
    depth: int
    WM_DELETE: int
    app: Any
    wins: dict                      # Qt top-level widget -> its record (wm.py)
    by_xid: dict                    # X window id -> Qt top-level widget
    own_frame: set                  # windows with a title bar of ours
    plat: Any                       # qtinput.Platform, or None: legacy input
    clip: Any                       # clipboard.Clipboard, or None
    buttons: Any                    # Qt mouse buttons down
    grab_target: Any                # legacy input: the widget holding the implicit mouse grab
    _last_press: Any                # legacy input: (button, X time, root x, y), for double clicks
    xfocus: Any                     # the window with the X input focus
    _focus_known: bool
    _focus_out_at: float | None
    _activate_t: float
    _repeat: int | None             # keycode of an auto-repeat in progress
    _repeat_rd: int | None
    _mode_switch: int | None        # modifier mask of Mode_switch, once looked up
    xtime: int                      # last X server time seen
    dead: bool                      # the X display went away, or the bridge was closed
    _net_supported: set | None
    _xcursors: dict

    def _lost(self, e) -> None:
        raise NotImplementedError
