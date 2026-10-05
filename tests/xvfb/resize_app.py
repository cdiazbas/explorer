"""explorer through its real start-up (ui.app.start, the bridge), resized by its own top-right corner as a user does
(press, move, release on the title bar's EdgeResizer), and what that cost: the sizes Qt went through, the geometry
requests and notices, the window's full resends, the bytes, its moves. Driven over stdin, one JSON line per answer
(test_bridge_resize.py):

    python tests/xvfb/resize_app.py <cube_im.fits>
    -> {"ready": ...}            the window shown and settled, its X id and geometry
    <- go DX DY                  the corner dragged DX right and DY up, released there
    -> {"released": ...}         (again: the report is of the last command)
    <- split DX DY [GAP [resize]] the same geometry asked as move() and then resize(): in one turn, or GAP ms apart;
                                 resize: the resize first
    <- set X Y W H               one setGeometry
    <- drag N STEP               N moves of STEP px to the right, 15 ms apart
    <- report                    -> {"sizes": ..., ...} and the application quits
"""
import json
import os
import sys
import tempfile
import threading
import time


def main() -> int:
    os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())
    from PySide6 import QtCore

    from explorer.ui.app import start

    s = start(sys.argv[1], look="classic", saved_layout=False, x11="bridge")
    if s is None:
        return 1
    w, bridge = s.shell, s.disp.bridge
    rz = w.title_bar.resizer
    rec = bridge.windows.get(w)
    E, Qt = QtCore.QEvent.Type, QtCore.Qt
    t_go = [0.0]
    sizes: list = []
    fresh: list = []
    shots: list = []
    moves: list = []

    class Watch(QtCore.QObject):
        def eventFilter(self, obj, e):
            if obj is w and e.type() == E.Resize and t_go[0]:
                sizes.append([round((time.perf_counter() - t_go[0]) * 1e3, 1), e.size().width(), e.size().height()])
            if obj is w and e.type() == E.Move and t_go[0]:
                moves.append([round((time.perf_counter() - t_go[0]) * 1e3, 1), e.pos().x(), e.pos().y()])
            return False
    watch = Watch()
    w.installEventFilter(watch)

    tr = bridge.transport
    back = tr._back

    def counted_back(xid, W, H):
        b, new = back(xid, W, H)
        if new and xid == rec.xid and t_go[0]:
            fresh.append([round((time.perf_counter() - t_go[0]) * 1e3, 1), W, H])
        return b, new
    tr._back = counted_back

    def counters():
        st, ws = tr.stats, bridge.windows.stats
        return dict(updates=st["updates"], bytes=st["bytes"], wire=st["wire"], configures=ws["configures"],
                    notices=ws["notices"], echoes=ws["echoes"], applied=bridge.stats["applied"])
    before: dict = {}

    def same_tiles(a, b, t=32):
        """Of the 32x32 tiles the two images share (from the top-left), the fraction that is the same: what a back
        pixmap kept across the size change would not send again."""
        import numpy as np

        def px(img):
            img = img.convertToFormat(img.Format.Format_RGB32)
            return np.frombuffer(img.constBits(), np.uint32).reshape(img.height(), img.bytesPerLine() // 4)[
                :, :img.width()]
        pa, pb = px(a), px(b)
        h, w_ = min(pa.shape[0], pb.shape[0]) // t * t, min(pa.shape[1], pb.shape[1]) // t * t
        eq = (pa[:h, :w_] == pb[:h, :w_]).reshape(h // t, t, w_ // t, t).all(axis=(1, 3))
        return dict(shared=int(eq.size), same=int(eq.sum()), of_new=round(eq.sum() * t * t / pb.size, 3))

    def rect(r):
        return [r.x(), r.y(), r.width(), r.height()]

    def say(**kw):
        print(json.dumps(kw), flush=True)

    def go(dx, dy):
        g = w.geometry()
        local = QtCore.QPoint(g.width() - 3, 3)
        start_g = g.topLeft() + local
        end_g = start_g + QtCore.QPoint(dx, -dy)
        before.update(counters())
        del sizes[:], fresh[:], shots[:], moves[:]      # each go is measured on its own
        shots.append(w.grab().toImage())
        t_go[0] = time.perf_counter()
        L = Qt.MouseButton.LeftButton
        assert rz.mouse(E.MouseButtonPress, local, start_g, L), "the corner did not start a resize"
        rz.mouse(E.MouseMove, local + QtCore.QPoint(dx // 2, -dy // 2), start_g + QtCore.QPoint(dx // 2, -dy // 2), L)
        rz.mouse(E.MouseMove, local + QtCore.QPoint(dx, -dy), end_g, L)
        rz.mouse(E.MouseButtonRelease, local + QtCore.QPoint(dx, -dy), end_g, Qt.MouseButton.NoButton)
        say(released=rect(w.geometry()), t_ms=round((time.perf_counter() - t_go[0]) * 1e3, 1))

    def split(dx, dy, gap_ms=0, first="move"):
        """The same geometry as go, asked by the program as a move and a resize, apart: in one turn of the event loop,
        or gap_ms apart; first: which of the two comes first."""
        g = w.geometry()
        before.update(counters())
        del sizes[:], fresh[:], shots[:], moves[:]
        shots.append(w.grab().toImage())
        t_go[0] = time.perf_counter()

        def mv():
            w.move(g.x(), g.y() - dy)

        def rs():
            w.resize(g.width() + dx, g.height() + dy)

        def done():
            say(released=rect(w.geometry()), t_ms=round((time.perf_counter() - t_go[0]) * 1e3, 1))
        a, b = (mv, rs) if first == "move" else (rs, mv)
        a()
        if gap_ms:
            QtCore.QTimer.singleShot(gap_ms, lambda: (b(), done()))
        else:
            b()
            done()

    def setg(x, y, width, height):
        """One setGeometry, as the title bar's edge resize ends."""
        before.update(counters())
        del sizes[:], fresh[:], shots[:], moves[:]
        shots.append(w.grab().toImage())
        t_go[0] = time.perf_counter()
        w.setGeometry(x, y, width, height)
        say(released=rect(w.geometry()), t_ms=round((time.perf_counter() - t_go[0]) * 1e3, 1))

    def drag(n, step):
        """n moves of step px to the right, 15 ms apart, as the title bar moves the window while dragged."""
        before.update(counters())
        del sizes[:], fresh[:], shots[:], moves[:]
        shots.append(w.grab().toImage())
        t_go[0] = time.perf_counter()
        g = w.geometry()

        def one(i):
            w.move(g.x() + step * (i + 1), g.y())
            if i + 1 < n:
                QtCore.QTimer.singleShot(15, lambda: one(i + 1))
            else:
                say(released=rect(w.geometry()), t_ms=round((time.perf_counter() - t_go[0]) * 1e3, 1))
        one(0)

    def report():
        now = counters()
        say(sizes=sizes, fresh=fresh, moves=moves, final=rect(w.geometry()), xid=rec.xid,
            delta={k: now[k] - before.get(k, 0) for k in now}, same_tiles=same_tiles(shots[0], w.grab().toImage()))
        s.app.quit()

    class Commands(QtCore.QObject):
        got = QtCore.Signal(str)
    cmds = Commands()

    def on_command(line):
        parts = line.split()
        if bridge.trace is not None:                    # where each command starts in the bridge's trace
            bridge.trace.write("MARK", None, line)
        if parts and parts[0] == "go":
            go(int(parts[1]), int(parts[2]))
        elif parts and parts[0] == "drag":
            drag(int(parts[1]), int(parts[2]))
        elif parts and parts[0] == "split":
            split(int(parts[1]), int(parts[2]), int(parts[3]) if len(parts) > 3 else 0,
                  parts[4] if len(parts) > 4 else "move")
        elif parts and parts[0] == "set":
            setg(*(int(v) for v in parts[1:5]))
        elif parts and parts[0] == "report":
            report()
    cmds.got.connect(on_command, Qt.ConnectionType.QueuedConnection)

    def read_stdin():
        for line in sys.stdin:
            cmds.got.emit(line.strip())
    threading.Thread(target=read_stdin, daemon=True).start()

    QtCore.QTimer.singleShot(1500, lambda: w.move(150, 250))   # room above and to the right to grow into
    QtCore.QTimer.singleShot(3500, lambda: say(ready=True, xid=rec.xid, geometry=rect(w.geometry())))
    try:
        return s.app.exec()
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())
