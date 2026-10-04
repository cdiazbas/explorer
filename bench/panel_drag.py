"""A floating panel dragged by its title with real X input (XTEST), over the other panel and over the main window,
through each program's own start-up and X11 bridge: the prototype (its app/startup.py) or explorer (ui.app.start).

    DISPLAY=localhost:L EXPLORER_BENCH_OBSERVE=:N EXPLORER_XLINK_STATS=link.json \
        python bench/panel_drag.py proto|explorer <cube_im.fits> <out.json>

The drag: 40 pointer moves 20 ms apart from the spectrum's title, over lambda-t, then over the main window. An observer
on the X server itself (:N, not through the link) presses, moves and releases (XTEST) and samples where X has the
panel. Reported: how long X takes to show the panel where each move puts it (median, p95, the longest, how many took
over 100 ms: a panel that stops mid-drag, as seen through XQuartz; moves never shown), how long
after the release it is where the drag ends and stays, whether it ends there, Qt and X agreeing, its stacking, and the
link and pixel bytes the drag cost. The prototype runs with its own Python (its .venv) and explorer's src on PYTHONPATH.

Measured on bellatrix (2026-10-04, Xvfb 3840x1080, the quartz-like stand-in manager, bench/xlink.py at 8 ms each way,
4 ABBA rounds): a move on X 17.7-18.0 ms median for explorer against 33.4-35.5 for the prototype, 4.0-4.1 MB of pixels
per drag against 5.6-7.1. Not measured: through XQuartz (XTEST is off there unless enabled).
"""
import json
import os
import sys
import tempfile
import threading
import time

which, cube, out = sys.argv[1], sys.argv[2], sys.argv[3]
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["EXPLORER_TERMINAL_KEYS"] = "0"
STEPS, DT = 40, 0.020


def link_up():
    try:
        return json.load(open(os.environ["EXPLORER_XLINK_STATS"]))["up"]
    except (KeyError, OSError, ValueError):
        return None


if which == "proto":
    proto = os.path.abspath(os.environ.get("EXPLORER_PROTOTYPE", "../prototype"))
    sys.path.insert(0, os.path.join(proto, "app"))
    sys.argv = sys.argv[:1]
    import importlib

    import viewer  # noqa: F401  (first: it sets up the prototype's import paths, Qt, pyqtgraph)

    startup = importlib.import_module("startup")        # after viewer, on the paths it set

    s = startup.prepare("bridge", "pgr")
    app, _ = startup.make_app(s, "auto")
    c, probe, guard, sp_file, cal = startup.open_cube(cube, None, False)
    w = startup.make_viewer(app, s, c, sp_file, probe, guard, kind="drag")
    startup.show(app, s, w, size=(1400, 900))
    bridge = s.bridge

    def xid(widget):
        return bridge.wins[widget]["x"].id

    def pixel_bytes():
        return bridge.stats.get("bytes", 0)
else:
    from explorer.ui.app import start

    st = start(cube, look="classic", saved_layout=False, x11="bridge")
    app, w = st.app, st.shell
    w.resize(1400, 900)
    bridge = st.disp.bridge

    def xid(widget):
        return bridge.windows.get(widget).xid

    def pixel_bytes():
        return bridge.transport.stats["bytes"]

from PySide6 import QtCore  # noqa: E402
from Xlib import X, display  # noqa: E402
from Xlib.ext import xtest  # noqa: E402

obs = display.Display(os.environ["EXPLORER_BENCH_OBSERVE"])
root = obs.screen().root
res: dict = dict(program=which)
done = threading.Event()


def x_at(widget_xid):
    t = root.translate_coords(obs.create_resource_object("window", widget_xid), 0, 0)
    return t.x, t.y


def top(widget_xid):
    """The root's child that holds the window (its frame, if the manager framed it)."""
    win = obs.create_resource_object("window", widget_xid)
    while True:
        p = win.query_tree().parent
        if p.id == root.id:
            return win.id
        win = p


def drag(sp, lt, start, sx, sy, path):
    try:
        xtest.fake_input(obs, X.MotionNotify, x=start[0], y=start[1])
        obs.sync()
        time.sleep(0.2)
        # a click first: XQuartz gives an inactive window's first click to the window manager only (its
        # "click-through" preference is off by default), so the drag's press would not reach the panel
        xtest.fake_input(obs, X.ButtonPress, 1)
        xtest.fake_input(obs, X.ButtonRelease, 1)
        obs.sync()
        time.sleep(0.6)
        p0 = x_at(sx)
        xtest.fake_input(obs, X.ButtonPress, 1)
        obs.sync()
        time.sleep(0.1)
        want, seen = [], {}
        l0, b0 = link_up(), pixel_bytes()
        t0 = time.perf_counter()
        for i, (px, py) in enumerate(path):
            xtest.fake_input(obs, X.MotionNotify, x=px, y=py)
            obs.sync()
            want.append(((p0[0] + px - start[0], p0[1] + py - start[1]), time.perf_counter()))
            while time.perf_counter() < t0 + DT * (i + 1):
                at = x_at(sx)
                seen.setdefault(at, time.perf_counter())
                time.sleep(0.002)
        xtest.fake_input(obs, X.ButtonRelease, 1)
        obs.sync()
        released = time.perf_counter()
        end = want[-1][0]
        settled_at, stable_since, last = None, None, None
        while time.perf_counter() < released + 5.0:
            at = x_at(sx)
            seen.setdefault(at, time.perf_counter())
            if at != last:
                last, stable_since = at, time.perf_counter()
            if at == end and settled_at is None:
                settled_at = time.perf_counter()
            if stable_since and time.perf_counter() - stable_since > 0.5 and at == end:
                break
            time.sleep(0.003)
        lags = sorted((seen[pos] - t) * 1e3 for pos, t in want if pos in seen and seen[pos] >= t - 0.001)
        # what X showed, whatever the positions: the distinct ones from the first move to the release, and the
        # longest time between two changes (a panel that stops while the pointer goes on)
        shown_at = sorted(v for v in seen.values() if t0 <= v <= released + 0.05)
        changes = [b - a for a, b in zip([t0] + shown_at, shown_at + [released], strict=True)]
        order = [c.id for c in root.query_tree().children]
        res.update(
            moves=len(want), shown=len(lags), lag_ms_median=round(lags[len(lags) // 2], 1) if lags else None,
            lag_ms_p95=round(lags[int(len(lags) * 0.95) - 1], 1) if lags else None,
            lag_ms_max=round(lags[-1], 1) if lags else None, stalls_over_100ms=sum(lag > 100 for lag in lags),
            x_positions_during_drag=len(shown_at), x_still_ms_max=round(max(changes) * 1e3, 1) if changes else None,
            start_x=list(p0),
            release_to_end_ms=round((settled_at - released) * 1e3, 1) if settled_at else None,
            end_want=list(end), end_x=list(x_at(sx)),
            spectrum_above_lambda_t=order.index(top(sx)) > order.index(top(xid(lt))),
            spectrum_above_main=order.index(top(sx)) > order.index(top(xid(w))),
            link_up_kB=round((link_up() - l0) / 1e3, 1) if l0 is not None else None,
            pixel_kB=round((pixel_bytes() - b0) / 1e3, 1))
    except Exception as e:
        res["error"] = repr(e)
    done.set()


def go():
    sp, lt = w.spec_dock, w.lt_dock
    fg = w.frameGeometry()
    for d, y in ((sp, fg.y()), (lt, fg.y() + 470)):
        d.setFloating(True)
        d.show()
        d.setGeometry(fg.right() + 20, y, 560, 420)

    def later():
        title = sp.titleBarWidget() or sp
        c = title.mapToGlobal(title.rect().center())
        start = (c.x() - 60, c.y())                     # on the title, clear of its buttons
        ltc = lt.frameGeometry().center()
        end = (fg.x() + 300, fg.y() + 200)
        path = [(round(start[0] + (ltc.x() - start[0]) * i / 19), round(start[1] + (ltc.y() - start[1]) * i / 19))
                for i in range(1, 21)]
        path += [(round(ltc.x() + (end[0] - ltc.x()) * i / 20), round(ltc.y() + (end[1] - ltc.y()) * i / 20))
                 for i in range(1, 21)]
        res.update(qt_title=list(start), qt_before=[sp.x(), sp.y()])
        threading.Thread(target=drag, args=(sp, lt, start, xid(sp), None, path), daemon=True).start()
    QtCore.QTimer.singleShot(2500, later)


def poll():
    if done.is_set():
        res["end_qt"] = [w.spec_dock.x(), w.spec_dock.y()]
        json.dump(res, open(out, "w"), indent=1)
        app.quit()
    else:
        QtCore.QTimer.singleShot(100, poll)


QtCore.QTimer.singleShot(4000, go)
QtCore.QTimer.singleShot(4100, poll)
app.exec()
