"""explorer through its real start-up (ui.app.start, the bridge) zoomed, then switched to glass and back to classic as
M does; at each step where Qt and the X server have the window and the panels, one JSON line a step
(test_bridge_glass_zoomed.py).

    python tests/xvfb/glass_zoom_app.py <cube_im.fits> maximised|titlebar

maximised: Qt's maximised state, as a window manager's maximise leaves it (the bridge follows _NET_WM_STATE) and a
Mac's green button on a local Mac; titlebar: our title bar's zoom, a geometry.
"""
import json
import os
import sys
import tempfile


def main() -> int:
    os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())
    from PySide6 import QtCore
    from Xlib import display

    from explorer.look import get_look
    from explorer.platform.screens import monitor_rect
    from explorer.ui.app import start

    case = sys.argv[2]
    zoom = QtCore.Qt.WindowState.WindowMaximized | QtCore.Qt.WindowState.WindowFullScreen
    s = start(sys.argv[1], look="classic", saved_layout=False, x11="bridge")
    if s is None:
        return 1
    w = s.shell
    ops = w.window_ops
    assert ops is not None
    x = display.Display(os.environ.get("EXPLORER_TEST_XDISPLAY") or os.environ["DISPLAY"])  # the server

    def rect(r):
        return [r.x(), r.y(), r.width(), r.height()]

    def on_x(widget):
        """Where the X server has the widget's window: its place on the root and its size."""
        rec = next(r for r in s.disp.bridge.windows if r.w is widget)
        win = x.create_resource_object("window", rec.xid)
        t, g = win.translate_coords(x.screen().root, 0, 0), win.get_geometry()
        return [-t.x, -t.y, g.width, g.height]

    def step(name):
        print(json.dumps(dict(
            step=name, zoomed=bool(w.windowState() & zoom), frame=rect(w.frameGeometry()), x=on_x(w),
            monitor=rect(monitor_rect(s.app, w.frameGeometry().center())),
            unzoomed=rect(ops.unzoomed) if ops.unzoomed is not None else None,
            docks={d.objectName(): dict(floating=d.isFloating(), visible=d.isVisible(), frame=rect(d.frameGeometry()),
                                        x=on_x(d) if d.isFloating() and d.isVisible() else None)
                   for d in (w.spec_dock, w.lt_dock)})), flush=True)

    # each step timed from the one before: timers of 2 s and more are coarse (5 %), and two set from the start at
    # 3.5 and 3.6 s came in the other order
    plan = [(2500, {"maximised": w.showMaximized, "titlebar": ops.zoom}[case]),
            (1000, lambda: step("zoomed")),
            (100, lambda: w.set_look(get_look("glass"))),
            (2900, lambda: step("glass")),
            (100, lambda: w.set_look(get_look("classic"))),
            (1900, lambda: step("classic")),
            (100, s.app.quit)]

    def then(i):
        ms, fn = plan[i]

        def run():
            fn()
            if i + 1 < len(plan):
                then(i + 1)
        QtCore.QTimer.singleShot(ms, run)
    then(0)
    try:
        return s.app.exec()
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())
