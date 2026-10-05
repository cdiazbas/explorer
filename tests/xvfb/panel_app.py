"""explorer through its real start-up (ui.app.start, the bridge): classic, then glass as M does (the panels floated
and placed), the slit's panel shown (S), and the spectrum's panel dragged (30 moves of (8, 3) px, 15 ms apart, as its
title moves it); at each step where Qt and the X server have every window, with the bridge's counts. One JSON line a
step (test_bridge_panels.py).

    python tests/xvfb/panel_app.py <cube_im.fits>
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
    from explorer.ui.app import start

    s = start(sys.argv[1], look="classic", saved_layout=False, x11="bridge")
    if s is None:
        return 1
    w, bridge = s.shell, s.disp.bridge
    x = display.Display(os.environ.get("EXPLORER_TEST_XDISPLAY") or os.environ["DISPLAY"])

    def rect(r):
        return [r.x(), r.y(), r.width(), r.height()]

    def on_x(rec):
        win = x.create_resource_object("window", rec.xid)
        t, g = win.translate_coords(x.screen().root, 0, 0), win.get_geometry()
        return [-t.x, -t.y, g.width, g.height]

    def step(name):
        wins = {}
        for rec in bridge.windows:
            if rec.popup or not rec.w.isVisible():
                continue
            n = "main" if rec.w is w else rec.w.objectName() or rec.w.windowTitle()
            wins[n] = dict(qt=rect(rec.w.geometry()), x=on_x(rec))
        if bridge.trace is not None:
            bridge.trace.write("MARK", None, name)
        print(json.dumps(dict(step=name, windows=wins, stats=dict(bridge.windows.stats),
                              applied=bridge.stats["applied"])), flush=True)

    drag_from: list = []

    def drag(i=0):
        d = w.spec_dock
        if i == 0:
            drag_from[:] = [d.x(), d.y()]
            if bridge.trace is not None:
                bridge.trace.write("MARK", None, "drag")
        d.move(drag_from[0] + 8 * (i + 1), drag_from[1] + 3 * (i + 1))
        if i < 29:
            QtCore.QTimer.singleShot(15, lambda: drag(i + 1))

    plan = [(2500, lambda: step("classic")),
            (100, lambda: w.set_look(get_look("glass"))),
            (2500, lambda: step("glass")),
            (100, lambda: w.set_slit_mode(True)),
            (2000, lambda: step("slit")),
            (100, drag),
            (2500, lambda: step("dragged")),
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
