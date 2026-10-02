"""The usable rectangle of the monitor a point is on: what a first window is sized in and what a zoom fills (ROADMAP
E5.2). From the prototype's app/viewer.py: monitor_rect, _monitor_rect_raw, _leave_mac_bars, _screen_insets
(2421-2488) and app/xconn.py (heads, is_xquartz), on explorer's own X client (xbridge.xproto), so no other X library
is needed.

- Qt sees each monitor as a screen (a local Mac, the bridge, most X servers): that screen's available geometry.
- One X screen over several monitors (XQuartz reports two monitors as one RandR screen): Xinerama's heads, and
  without them a screen wider than ~2.4:1 taken as monitors side by side.
- Over X11 to a Mac: XQuartz leaves the menu bar out of its screen but not the Dock, and publishes no work area, so
  a window filling the screen went under the Dock. The Mac's own insets when the launcher passes them
  (EXPLORER_SCREEN_INSETS="WxH:top,right,bottom,left;..." in points, NSScreen visibleFrame), else the Dock's
  default size at the bottom.
"""
import os

from PySide6 import QtCore, QtGui

DOCK_GUESS = 70         # pt: the Dock at its default place and size, when the Mac does not tell
INSETS_ENV = "EXPLORER_SCREEN_INSETS"
_X: dict = {}           # per DISPLAY: {"heads": [...], "xquartz": bool}


def _x_facts() -> dict:
    """Xinerama's heads and whether the server is XQuartz (it announces Apple-WM), asked once per DISPLAY over one
    short connection; nothing when there is no X display or it does not answer."""
    key = os.environ.get("DISPLAY", "")
    if key in _X:
        return _X[key]
    facts: dict = {"heads": [], "xquartz": False}
    if key:
        try:
            from .xbridge import xproto as X

            c = X.Connection(key, name="screens")
            try:
                facts["heads"] = [QtCore.QRect(*h) for h in c.xinerama_screens()]
                facts["xquartz"] = c.ext("Apple-WM") is not None
            finally:
                c.close()
        except Exception:                               # no display, refused, closed: Qt's own screens then
            pass
    _X[key] = facts
    return facts


def screen_insets(env=None) -> list[tuple[int, int, int, int, int, int]]:
    """The Mac's screens as (w, h, top, right, bottom, left) in points, from EXPLORER_SCREEN_INSETS."""
    out = []
    for part in (env if env is not None else os.environ).get(INSETS_ENV, "").split(";"):
        try:
            size, ins = part.split(":")
            w, h = (int(float(v)) for v in size.lower().split("x"))
            t, r, b, l = (int(float(v)) for v in ins.split(","))  # noqa: E741
            out.append((w, h, t, r, b, l))
        except ValueError:
            continue
    return out


def leave_mac_bars(app, rect: QtCore.QRect) -> QtCore.QRect:
    """Over X11 to a Mac, rect without the Dock (and the menu bar when XQuartz has not left it out already)."""
    if app.platformName() not in ("xcb", "offscreen"):
        return rect
    ins = screen_insets()
    for w, h, t, r, b, l in ins:  # noqa: E741
        if abs(rect.width() - w) <= 2 and h - t - 2 <= rect.height() <= h + 2:
            top = t if rect.height() > h - t + 2 else 0    # XQuartz has already left the menu bar out
            return rect.adjusted(l, top, -r, -b)
    # xcb, or the bridge (Qt on offscreen, the X server at DISPLAY): ssh -Y to a Mac goes through the bridge, and with
    # xcb alone the window went under the Dock there (the prototype's app/viewer.py:2452-2461, its F44)
    if not ins and _x_facts()["xquartz"]:
        return rect.adjusted(0, 0, 0, -DOCK_GUESS)
    return rect


def _raw(app, point) -> QtCore.QRect:
    scr = app.screenAt(point) or app.primaryScreen()
    if scr is None:                                     # no screen at all: any sane size
        return QtCore.QRect(0, 0, 1600, 1000)
    a = scr.availableGeometry()
    if len(app.screens()) > 1:                          # Qt already sees each monitor
        return a
    heads = _x_facts()["heads"] if app.platformName() == "xcb" else []
    if len(heads) > 1:
        r = scr.devicePixelRatio()
        rects = [QtCore.QRect(int(h.x() / r), int(h.y() / r), int(h.width() / r), int(h.height() / r)) for h in heads]
        hit = [q for q in rects if q.contains(point)]
        return (hit[0] if hit else rects[0]).intersected(a)
    # no Xinerama: wider than ~2.4:1 is taken as n monitors side by side; only on X11, where XQuartz can report two
    # monitors as one screen (a local Mac separates them itself)
    n = round(a.width() / a.height() / (16 / 9)) if app.platformName() in ("xcb", "offscreen") else 1
    if n > 1:
        w = a.width() // n
        i = min(n - 1, max(0, (point.x() - a.x()) // w))
        return QtCore.QRect(a.x() + i * w, a.y(), w, a.height())
    return a


def monitor_rect(app, point: QtCore.QPoint | None = None) -> QtCore.QRect:
    """The usable rectangle of the monitor containing point (default: the pointer), in Qt's coordinates."""
    return leave_mac_bars(app, _raw(app, QtGui.QCursor.pos() if point is None else point))
