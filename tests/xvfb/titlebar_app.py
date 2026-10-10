"""explorer through its real start-up (ui.app.start, the bridge) with its own title bar and edges, for the tests of
moving and resizing by them (test_bridge_moveresize.py). One JSON line on stdout per command on stdin.

    python tests/xvfb/titlebar_app.py <cube_im.fits>
    -> {"ready": ...}   the window shown and settled: its X id, geometry, a point of the title bar and one of the
                        right edge (root coordinates)
    <- state            -> its geometry, Qt's mouse buttons, whether the title bar or the edges hold a drag
    <- quit
"""
import json
import os
import sys
import tempfile
import threading


def main() -> int:
    os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())
    from PySide6 import QtCore, QtGui

    from explorer.ui.app import start

    s = start(sys.argv[1], look="classic", saved_layout=False, x11="bridge")
    if s is None:
        return 1
    w, bridge = s.shell, s.disp.bridge
    bar = w.title_bar
    rec = bridge.windows.get(w)

    def rect(r):
        return [r.x(), r.y(), r.width(), r.height()]

    def say(**kw):
        print(json.dumps(kw), flush=True)

    def points():
        g = w.geometry()
        mid = bar.mapTo(w, QtCore.QPoint(bar.width() // 2, bar.height() // 2))
        edge = QtCore.QPoint(g.width() - 2, g.height() // 2)
        return dict(bar=w.mapToGlobal(mid).toTuple(), bar_edges=int(bar.resizer.edges_at(mid).value),
                    edge=w.mapToGlobal(edge).toTuple(), edge_edges=int(bar.resizer.edges_at(edge).value))

    def state():
        return dict(geometry=rect(w.geometry()), buttons=int(QtGui.QGuiApplication.mouseButtons().value),
                    bar_drag=bar._drag is not None, edge_drag=bar.resizer._drag is not None,
                    mouse=bridge.input.stats["mouse"])

    class Commands(QtCore.QObject):
        got = QtCore.Signal(str)
    cmds = Commands()

    def on_command(line):
        if line == "state":
            say(**state())
        elif line == "quit":
            say(ok=True)
            s.app.quit()
    cmds.got.connect(on_command, QtCore.Qt.ConnectionType.QueuedConnection)

    def read_stdin():
        for line in sys.stdin:
            cmds.got.emit(line.strip())
    threading.Thread(target=read_stdin, daemon=True).start()

    QtCore.QTimer.singleShot(1500, lambda: w.move(150, 150))
    QtCore.QTimer.singleShot(3000, lambda: say(ready=True, xid=rec.xid, **points(), **state()))
    try:
        return s.app.exec()
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())
