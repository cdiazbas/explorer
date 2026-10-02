"""explorer's window through the rewritten X11 bridge, driven by the X tests (test_bridge_xvfb.py): the viewer runs
as the user runs it (BridgeDisplay, Shell) and answers commands on stdin, one per line, with one JSON line on stdout.

    python tests/xvfb/bridge_app.py <cube_im.fits> [--size 800x600]
    state | grab | copy TEXT | bigcopy N | panel | popup | mask | look NAME | stokes | where NAME | menu | idle
    | quit
"""
import argparse
import json
import os
import sys
import tempfile
import time

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cube")
    ap.add_argument("--size", default="800x600")
    ap.add_argument("--float-first", action="store_true",
                    help="the panels floating before the window is shown, as a saved glass layout leaves them")
    a = ap.parse_args()
    from explorer.data.dataset import Dataset
    from explorer.platform.display import for_plan
    from explorer.platform.plan import choose_display

    t0 = time.perf_counter()
    disp = for_plan(choose_display(os.environ, sys.platform, "bridge"))
    disp.prepare_env()
    app = disp.make_app()
    from PySide6 import QtCore, QtGui, QtWidgets

    from explorer.ui.shell import Shell

    ds = Dataset.open(a.cube)
    w = Shell(ds, title="bridge test λ", t0=t0)
    W, H = (int(v) for v in a.size.split("x"))
    w.resize(W, H)
    if a.float_first:
        for d in (w.spec_dock, w.lt_dock):
            d.setFloating(True)
            d.show()
    ops = disp.attach(app, w)
    bridge = disp.bridge
    extra: dict = {}
    if os.environ.get("XB2_TRACE"):                    # who ends the application, and when
        import traceback

        app.lastWindowClosed.connect(lambda: (print("lastWindowClosed", file=sys.stderr), traceback.print_stack()))
        app.aboutToQuit.connect(lambda: (print("aboutToQuit", file=sys.stderr), traceback.print_stack()))
        destroy = bridge.windows.destroy

        def traced(w_):
            print("X window destroyed for", w_.windowTitle(), file=sys.stderr)
            traceback.print_stack()
            return destroy(w_)
        bridge.windows.destroy = traced

    def out(d):
        sys.stdout.write(json.dumps(d) + "\n")
        sys.stdout.flush()

    def settle(timeout=5.0):
        end = time.perf_counter() + timeout
        quiet = 0
        while time.perf_counter() < end:
            app.processEvents()
            busy = bridge.transport.busy or any(not r.dirty.isEmpty() for r in bridge.windows) \
                or bridge._flush_timer.isActive()
            quiet = 0 if busy else quiet + 1
            if quiet > 20:
                return True
            time.sleep(0.002)
        return False

    def state():
        st = w.session.state
        aw = app.activeWindow()
        return dict(t=st.t, l=st.l, s=st.s, cursor=list(st.cursor), locked=st.locked,
                    first_image=w.first_image_s, active=aw.windowTitle() if aw is not None else None,
                    clipboard=QtWidgets.QApplication.clipboard().text()[:200],
                    clipboard_len=len(QtWidgets.QApplication.clipboard().text()),
                    windows=[dict(title=r.w.windowTitle(), xid=r.xid, popup=r.popup, geometry=r.w.geometry().getRect(),
                                  iconic=r.iconic) for r in bridge.windows],
                    popup=bool(QtWidgets.QApplication.activePopupWidget()), hits=list(extra.get("hits", [])),
                    docks={d.objectName(): d.isVisible() for d in (w.spec_dock, w.lt_dock)},
                    minimized=bool(w.windowState() & QtCore.Qt.WindowState.WindowMinimized),
                    maximized=bool(w.windowState() & QtCore.Qt.WindowState.WindowMaximized),
                    summary=bridge.summary())

    grabs = tempfile.mkdtemp(prefix="bridge_app_")      # read back by the test, removed with the system's temp

    def grab(target):
        img = target.screen().grabWindow(target.winId()).toImage().convertToFormat(QtGui.QImage.Format.Format_RGB32)
        arr = np.frombuffer(img.constBits(), np.uint32).reshape(img.height(), img.bytesPerLine() // 4)
        arr = arr[:, :img.width()].copy()
        path = os.path.join(grabs, f"grab_{id(target)}.npy")
        np.save(path, arr)
        return dict(path=path, w=img.width(), h=img.height())

    def command(line):
        cmd, _, arg = line.strip().partition(" ")
        if cmd == "state":
            out(state())
        elif cmd == "idle":
            out(dict(idle=settle()))
        elif cmd == "grab":
            target = extra.get(arg, w) if arg else w
            settle()
            out(grab(target))
        elif cmd == "copy":
            QtWidgets.QApplication.clipboard().setText(arg)
            app.processEvents()
            out(dict(ok=True))
        elif cmd == "bigcopy":
            n = int(arg)
            QtWidgets.QApplication.clipboard().setText("".join(chr(0x61 + i % 26) for i in range(n - 1)) + "λ")
            app.processEvents()
            out(dict(ok=True))
        elif cmd == "panel":
            p = QtWidgets.QWidget(w, QtCore.Qt.WindowType.Tool)
            p.setWindowTitle("panel λ–t")
            p.setStyleSheet("background: rgb(40, 90, 160)")
            p.setGeometry(w.x() + 50, w.y() + 60, 240, 180)
            p.show()
            extra["panel"] = p
            settle()
            out(dict(ok=True))
        elif cmd == "mask":
            p = extra["panel"]
            p.setMask(QtGui.QRegion(0, 0, 240, 180, QtGui.QRegion.RegionType.Ellipse))
            p.update()
            settle()
            out(dict(ok=True))
        elif cmd == "popup":
            m = QtWidgets.QMenu(w)
            hits = extra.setdefault("hits", [])
            for name in ("one", "two", "three"):
                m.addAction(name, lambda n=name: hits.append(n))
            m.popup(QtCore.QPoint(w.x() + 100, w.y() + 100))
            extra["menu"] = m
            settle()
            out(dict(ok=True, geometry=m.geometry().getRect(),
                     items=[m.actionGeometry(act).center().toTuple() for act in m.actions()]))
        elif cmd == "look":
            from explorer.look import get_look

            w.set_look(get_look(arg, {}))
            settle()
            out(dict(ok=True))
        elif cmd == "stokes":                           # the modern look's drop-down, where it is on the screen
            d = w.nav.drop
            settle()

            def centre(b):
                return b.mapToGlobal(b.rect().center()).toTuple()
            out(dict(button=centre(d), open=d.panel.isVisible(), label=d.text(),
                     items=[centre(b) for b in d.segments.group.buttons()] if d.panel.isVisible() else []))
        elif cmd == "where":                            # a toolbar control (its NavBar name): its centre on screen
            b = getattr(w.nav, arg)
            settle()
            out(dict(centre=b.mapToGlobal(b.rect().center()).toTuple()))
        elif cmd == "menu":                             # the open menu's items: text and centre on the screen
            m = QtWidgets.QApplication.activePopupWidget()
            items = [] if not isinstance(m, QtWidgets.QMenu) else [
                dict(text=a.text(), centre=m.mapToGlobal(m.actionGeometry(a).center()).toTuple())
                for a in m.actions() if a.isVisible()]
            out(dict(items=items))
        elif cmd == "activate":
            ops.activate()
            settle()
            out(dict(ok=True))
        elif cmd == "minimize":
            ops.minimize()
            settle()
            out(dict(ok=True))
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
