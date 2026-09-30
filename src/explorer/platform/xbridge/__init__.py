"""The X11 bridge: Qt draws offscreen and this package shows its top-level windows on an X display (docs/plan.md
§3.5; from the prototype's app/xbridge.py, xconn.py and xrender.py, brought over as they are, split by concern).

Why. Over ssh -Y Qt's own X11 (xcb) needs 2.3-2.5 s just to start (~150 round trips at ~16 ms each to XQuartz); Qt's
offscreen platform starts in 0.16 s and python-xlib opens its connection in 0.32 s. Through ssh -Y the bridge showed
~12 images/s against ~8.5 with xcb, with less than half the bytes, and the same state as xcb in every conformance
and smoke check of the prototype: it is the default on a remote X display (platform/plan.py).

How. The regions Qt repainted are copied from its backing store into X windows, as 32x32 tiles that changed, grey
ones at 1 byte per pixel through RENDER, into a server-side pixmap shown with one CopyArea (transport); the X
requests are written by a numba kernel on a connection of their own, in their own thread, so the interface never
waits on the link. Mouse, wheel, keyboard, focus, crossing, resize and close events come back to Qt through the
entry Qt's own platform plugins use (qtinput). The X side of what offscreen Qt keeps to itself is done here too:
window-manager hints, transient panels, shapes, cursors, iconified windows (wm) and the CLIPBOARD (clipboard). Qt's
global coordinates are kept equal to X root coordinates (each Qt window is moved to where the window manager put
its X window), so popups and tool tips land where Qt expects them.

    display.BridgeDisplay(plan)   the Display the plan asks for when plan.bridge (ui/app.py)

Limits: private Qt symbols (PySide6 pinned exactly), dpr 1, no drag and drop nor input methods, clipboard text
without INCR (docs/plan.md §3.5).
"""
import importlib.util


def available() -> bool:
    """This install can run the bridge: python-xlib is importable (numba and PySide6 are dependencies anyway)."""
    return importlib.util.find_spec("Xlib") is not None
