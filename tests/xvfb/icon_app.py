"""explorer's window through the X11 bridge, its panels floating before it is shown, and the application's icon set
when asked, after the windows exist (test_bridge_icon.py). One JSON line on stdout per command on stdin.

    python tests/xvfb/icon_app.py <cube_im.fits>
    state | icon | panel | own | clear | quit

icon: ui.appicon on the application, as ui.app sets it; panel: a tool window made after it; own: an icon of its own
on that window; clear: no application icon. icon and own answer with the _NET_WM_ICON they expect (a .npy file).
"""
import json
import os
import sys
import tempfile
import time

import numpy as np


def main():
    from explorer.data.dataset import Dataset
    from explorer.platform.display import for_plan
    from explorer.platform.plan import choose_display

    t0 = time.perf_counter()
    disp = for_plan(choose_display(os.environ, sys.platform, "bridge"))
    disp.prepare_env()
    app = disp.make_app()
    from PySide6 import QtCore, QtGui, QtWidgets

    from explorer.ui import appicon, titlebar
    from explorer.ui.shell import Shell

    ds = Dataset.open(sys.argv[1])
    w = Shell(ds, title="icon test", t0=t0)
    w.resize(800, 600)
    titlebar.dock_titles(w)
    for d in (w.spec_dock, w.lt_dock):                 # as a saved glass layout: floating before the window shows
        d.setFloating(True)
        d.show()
    disp.attach(app, w)
    bridge = disp.bridge
    extra: dict = {}
    out_dir = tempfile.mkdtemp(prefix="icon_app_")

    def out(d):
        sys.stdout.write(json.dumps(d) + "\n")
        sys.stdout.flush()

    def settle(timeout=5.0):
        end = time.perf_counter() + timeout
        quiet = 0
        while time.perf_counter() < end:
            app.processEvents()
            busy = bridge.transport.busy or any(not r.dirty.isEmpty() for r in bridge.windows) \
                or bridge._flush_posted
            quiet = 0 if busy else quiet + 1
            if quiet > 20:
                return True
            time.sleep(0.002)
        return False

    def expected(ic, name):
        path = os.path.join(out_dir, f"{name}.npy")
        np.save(path, np.array(appicon.net_wm_icon(ic, appicon.NET_WM_SIZES), np.uint32))
        return path

    def command(line):
        cmd = line.strip()
        if cmd == "state":
            out(dict(windows={r.w.windowTitle() or r.w.objectName(): r.xid for r in bridge.windows if not r.popup},
                     max_request=bridge.c.max_request))
        elif cmd == "icon":
            t = time.perf_counter()
            appicon.install(app)
            ms = (time.perf_counter() - t) * 1e3
            settle()
            out(dict(ok=not app.windowIcon().isNull(), ms=ms, expect=expected(app.windowIcon(), "app")))
        elif cmd == "panel":
            p = QtWidgets.QWidget(w, QtCore.Qt.WindowType.Tool)
            p.setWindowTitle("panel made after the icon")
            p.setGeometry(w.x() + 50, w.y() + 60, 240, 180)
            p.show()
            extra["panel"] = p
            settle()
            out(dict(ok=True))
        elif cmd == "own":
            pm = QtGui.QPixmap(32, 32)
            pm.fill(QtGui.QColor(200, 30, 40))
            ic = QtGui.QIcon(pm)
            extra["panel"].setWindowIcon(ic)
            settle()
            out(dict(ok=True, expect=expected(ic, "own")))
        elif cmd == "clear":
            app.setWindowIcon(QtGui.QIcon())
            settle()
            out(dict(ok=app.windowIcon().isNull()))
        elif cmd == "quit":
            out(dict(ok=True))
            w.close()
            app.quit()
        else:
            out(dict(error=f"unknown command {cmd!r}"))

    buf = b""

    def readable():
        nonlocal buf
        chunk = os.read(0, 65536)
        if not chunk:
            app.quit()
            return
        buf += chunk
        while b"\n" in buf:
            line, _, buf = buf.partition(b"\n")
            command(line.decode())

    notifier = QtCore.QSocketNotifier(0, QtCore.QSocketNotifier.Type.Read)
    notifier.activated.connect(readable)
    settle(10.0)
    out(dict(ready=True, first_image=w.first_image_s, pid=os.getpid()))
    rc = app.exec()
    ds.close()
    disp.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
