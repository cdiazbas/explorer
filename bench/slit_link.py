"""The slit drawn through the X11 bridge and an emulated link (bench/xlink.py), seen from the X server's side: per
pointer step, when the draft line's pixels reach the server and when the slit panel's do, and what the bridge sent
for each. Runs any version of explorer (--src), so that two commits can be compared, ABBA.

    python bench/slit_link.py one <cube> <out.json> --src <explorer/src> --xdisplay :N [--delay-ms 6] [--mbps 30]
        [--no-live] [--link <other cube>] [--on K] [--look classic] [--seed 1] [--slits 3] [--steps 40]

Three processes: the link (localhost:M to the X server :N, `delay` each way, `mbps` from client to server), the
application (this file's `app`, explorer through the bridge on localhost:M) and this one, which talks to :N directly,
as the screen and the mouse are on the far side of an ssh -Y link:
- the pointer is moved with XTEST; the application sees each move after the link's delay, as through ssh;
- per step, a small box of the root window around the pointer's new place is read with GetImage until pixels of the
  slit's colour appear there (the draft line reached its free end on the screen): line_ms;
- and three thin bands across the slit panel until they change (its new slices on the screen): panel_ms, the first
  change, and panel_last_ms, the last one before the step settled.
The application logs each update the bridge's sender takes (when it starts and when the last byte left), with the
bytes of each region grabbed (32x32 tiles that changed: grey at 1 B/px, colour at 4), split here into the main
image's viewport, the slit panel and the rest. The slit mode and its first point are set through a command file (not
timed); everything timed goes through X.

Per slit: the same 40 moves twice, first settled (each move waited out: the line arrived and the panel quiet 150 ms,
or 1.5 s), then at the pointer's pace (16 ms apart). --no-live: the slit panel shows nothing while a slit is drawn
(SlitPanel.show skipped while the tool has points), the slices otherwise as they are.
"""
import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MOVE_S = 0.016
QUIET_S = 0.150
STEP_TIMEOUT_S = 1.5
BOX = 4                                                 # half side of the box read around the pointer's new place
CROSS_IN = 14                                           # px inside the viewport's edge: the cross's lines start ~9 in


def args():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=("one", "app"))
    ap.add_argument("cube")
    ap.add_argument("out")
    ap.add_argument("--src", default=None)
    ap.add_argument("--xdisplay", default=None)
    ap.add_argument("--delay-ms", type=float, default=6.0)
    ap.add_argument("--mbps", type=float, default=30.0)
    ap.add_argument("--no-live", action="store_true")
    ap.add_argument("--link", default=None)
    ap.add_argument("--on", type=int, default=0)
    ap.add_argument("--look", default="classic")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--slits", type=int, default=3)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--label", default=None)
    ap.add_argument("--io", default=None, help="app: the folder of the command, answer and log files")
    return ap.parse_args()


def lines(seed, n, ny, nx):
    import numpy as np

    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        ang = rng.uniform(0, np.pi)
        half = min(nx, ny) / 6
        c = np.array([rng.uniform(nx * 0.35, nx * 0.65), rng.uniform(ny * 0.35, ny * 0.65)])
        d = np.array([np.cos(ang), np.sin(ang)]) * half
        out.append([tuple(map(float, c - d)), tuple(map(float, c + d))])
    return out


# ------------------------------------------------------------------------------------------------ the application
def run_app(a):
    os.environ["EXPLORER_TERMINAL_KEYS"] = "0"
    from PySide6 import QtCore, QtWidgets

    from explorer.platform.xbridge import kernels as K
    from explorer.platform.xbridge import transport as T
    from explorer.ui.app import start as start_app

    updates = []
    cur: list = []
    orig_cp = K.changed_pieces

    def cp(arr, last, force, grey):
        r = orig_cp(arr, last, force, grey)
        cur.append(r)
        return r
    K.changed_pieces = cp
    orig_up = T.Transport._update

    def up(self, items):
        cur.clear()
        t0 = time.time()
        orig_up(self, items)
        t1 = time.time()
        regions = []
        split = dict(viewport=0, panel=0, other=0)
        if len(cur) == len(items):
            for it, r in zip(items, cur, strict=True):
                xid, _W, _H, x, y, arr = it[:6]
                h, w = arr.shape
                nb = 0
                for kind, rx, ry, rw, rh in (r.tolist() if len(r) else ()):
                    b = rw * rh * (1 if kind == 1 else 4)
                    nb += b
                    tile = [x + rx, y + ry, rw, rh]
                    key = "other"
                    for name in ("viewport", "panel"):
                        if xid == rects.get("xid") and name in rects and inter(tile, rects[name]):
                            key = name
                            break
                    split[key] += b
                    if key == "other":
                        ob = split.setdefault("other_box", [1 << 30, 1 << 30, -1, -1])
                        ob[:] = [min(ob[0], tile[0]), min(ob[1], tile[1]), max(ob[2], tile[0] + rw),
                                 max(ob[3], tile[1] + rh)]
                regions.append([int(xid), int(x), int(y), int(w), int(h), int(nb)])
        updates.append(dict(t0=t0, t1=t1, n=len(items), regions=regions, split=split,
                            matched=len(cur) == len(items)))
    T.Transport._update = up
    rects: dict = {}
    events: list = []                                   # (time, what): the move reaching Qt, the paints

    from explorer.platform.xbridge import qtinput as QI

    orig_motion = QI.QtInput.motion

    def motion(self, w, e):
        events.append((time.time(), "motion"))
        return orig_motion(self, w, e)
    QI.QtInput.motion = motion
    from explorer.platform.xbridge import bridge as BR

    orig_flush = BR.Bridge._flush

    def flush(self):
        events.append((time.time(), "flush" if self.transport.ready.is_set() else "flush-busy"))
        return orig_flush(self)
    BR.Bridge._flush = flush

    class Paints(QtCore.QObject):
        def eventFilter(self, obj, e):
            if every and e.type() != QtCore.QEvent.Type.Paint:
                events.append((time.time(), f"event {int(e.type())} {type(obj).__name__}"))
            if e.type() == QtCore.QEvent.Type.Paint and isinstance(obj, QtWidgets.QWidget):
                r = e.region().boundingRect()
                if r.width() * r.height() > 0:
                    events.append((time.time(), f"paint {type(obj).__name__} {r.width()}x{r.height()}"))
            return False
    paints = Paints()
    every = bool(os.environ.get("SLITLINK_EVENTS"))     # every event's type and receiver, to trace a wait

    st = start_app(a.cube, x11="bridge", look=a.look, saved_layout=False, linked=[a.link] if a.link else ())
    app, w = st.app, st.shell
    w.resize(1400, 900)
    w.move(0, 0)
    app.installEventFilter(paints)
    on = w.cubes[a.on] if a.on else None
    view = on.view if on is not None else w.view
    img, vb = view.widget, view.vb
    tool = w.slit_tool
    panel = (getattr(on, "slit_panel", None) if on is not None else None) or w.slit_panel
    import pyqtgraph as pg

    band = next((m.band for m in tool.marks if m.band.getViewBox() is vb), tool.marks[0].band)
    orig_curve = pg.PlotCurveItem.paint

    def curve_paint(self, *x, **k):
        if self is band:
            events.append((time.time(), "band"))
        return orig_curve(self, *x, **k)
    pg.PlotCurveItem.paint = curve_paint
    orig_img = pg.ImageItem.paint

    def img_paint(self, *x, **k):
        if self is panel.ts_img or self is panel.sl_img:
            events.append((time.time(), "slice"))
        return orig_img(self, *x, **k)
    pg.ImageItem.paint = img_paint
    if a.no_live:
        from explorer.ui import slitpanel as SP

        orig_show = SP.SlitPanel.show

        def show(self, *x, **k):
            if tool.mode and tool.pts:
                return None
            return orig_show(self, *x, **k)
        SP.SlitPanel.show = show
    ds = w.dataset
    plan = lines(a.seed, a.slits, int(ds.ny), int(ds.nx))
    io = a.io
    state = dict(n=-1)

    def glob(x, y):
        p = img.mapFromScene(vb.mapViewToScene(QtCore.QPointF(x, y)))     # viewport coordinates
        g = img.viewport().mapToGlobal(p)
        return [g.x(), g.y()]

    def rect_global(wid):
        g = wid.mapToGlobal(QtCore.QPoint(0, 0))
        return [g.x(), g.y(), wid.width(), wid.height()]

    def rect_in_window(wid):
        g = wid.mapTo(w, QtCore.QPoint(0, 0))
        return [g.x(), g.y(), wid.width(), wid.height()]

    def answer(d):
        tmp = os.path.join(io, "ans.tmp")
        with open(tmp, "w") as f:
            json.dump(d, f)
        os.replace(tmp, os.path.join(io, "ans.json"))

    def poll():
        try:
            with open(os.path.join(io, "cmd.json")) as f:
                cmd = json.load(f)
        except (OSError, ValueError):
            return
        if cmd["n"] == state["n"]:
            return
        state["n"] = cmd["n"]
        op = cmd["op"]
        out = dict(n=cmd["n"], op=op)
        if op == "plan":
            out["points"] = []
            for (x0, y0), (x1, y1) in plan:
                out["points"].append([glob(x0 + (x1 - x0) * k / a.steps, y0 + (y1 - y0) * k / a.steps)
                                      for k in range(a.steps + 1)])
            out["window"] = rect_global(w)
            out["viewport_global"] = rect_global(img.viewport())
            c = tool.colour
            c = c() if callable(c) else c
            out["colour"] = [c.red(), c.green(), c.blue()]
        elif op == "start":
            (x0, y0), _ = plan[cmd["slit"]]
            tool.set_mode(True)
            try:
                tool.add(x0, y0, a.on)
            except TypeError:
                tool.add(x0, y0)
        elif op == "where":
            out["panel_global"] = rect_global(panel.widget)
            out["panel_window"] = rect_in_window(panel.widget)
            out["viewport_window"] = rect_in_window(img.viewport())
            out["panel_visible"] = panel.widget.isVisible()
            br = st.disp.bridge
            out["main_xid"] = next((r.xid for r in br.windows if r.w is w), None)
            rects.update(xid=out["main_xid"], viewport=out["viewport_window"], panel=out["panel_window"])
        elif op == "stop":
            tool.set_mode(False)
        elif op == "quit":
            with open(os.path.join(io, "updates.json"), "w") as f:
                json.dump(dict(updates=updates, events=events), f)
            answer(out)
            app.quit()
            return
        answer(out)

    timer = QtCore.QTimer()
    timer.setInterval(20)
    timer.timeout.connect(poll)
    timer.start()
    try:
        app.exec()
    finally:
        st.close()


# ------------------------------------------------------------------------------------------------ the driver
class Driver:
    def __init__(self, a):
        from Xlib import X, display
        from Xlib.ext import xtest

        self.X, self.xtest = X, xtest
        self.d = display.Display(a.xdisplay)
        self.root = self.d.screen().root
        self.io = tempfile.mkdtemp(prefix="slitlink_io_")
        self.n = 0

    def cmd(self, op, timeout=30.0, **k):
        self.n += 1
        d = dict(n=self.n, op=op, **k)
        tmp = os.path.join(self.io, "cmd.tmp")
        with open(tmp, "w") as f:
            json.dump(d, f)
        os.replace(tmp, os.path.join(self.io, "cmd.json"))
        end = time.time() + timeout
        while time.time() < end:
            try:
                with open(os.path.join(self.io, "ans.json")) as f:
                    r = json.load(f)
                if r["n"] == self.n:
                    return r
            except (OSError, ValueError):
                pass
            time.sleep(0.01)
        raise RuntimeError(f"no answer to {op}")

    def move(self, x, y):
        self.xtest.fake_input(self.d, self.X.MotionNotify, x=int(x), y=int(y))
        self.d.sync()

    def grab(self, x, y, w, h):
        return self.root.get_image(int(x), int(y), int(w), int(h), self.X.ZPixmap, 0xFFFFFFFF).data

    def reds(self, x, y):
        import numpy as np

        raw = self.grab(x - BOX, y - BOX, 2 * BOX + 1, 2 * BOX + 1)
        a = np.frombuffer(raw, np.uint8).reshape(2 * BOX + 1, -1, 4)[:, : 2 * BOX + 1, :3].astype(int)
        b, g, r = a[..., 0], a[..., 1], a[..., 2]
        R, G, B = self.colour
        return int(((abs(r - R) + abs(g - G) + abs(b - B)) < 120).sum())

    def ppm(self, path, x, y, w, h):
        import numpy as np

        a = np.frombuffer(self.grab(x, y, w, h), np.uint8).reshape(h, -1, 4)[:, :w, 2::-1]
        with open(path, "wb") as f:
            f.write(b"P6 %d %d 255\n" % (w, h) + np.ascontiguousarray(a).tobytes())

    def cross(self):
        """Where the cursor's cross is on the screen: the column of its vertical line along the viewport's top, the
        row of its horizontal one along its left edge (None where not one line of the slit's colour)."""
        import numpy as np

        x, y, w, h = self.viewport
        R, G, B = self.colour

        def red(raw, rows, cols):
            a = np.frombuffer(raw, np.uint8).reshape(rows, -1, 4)[:, :cols, :3].astype(int)
            return (abs(a[..., 2] - R) + abs(a[..., 1] - G) + abs(a[..., 0] - B)) < 120

        top = red(self.grab(x, y + CROSS_IN, w, 4), 4, w).any(axis=0)
        left = red(self.grab(x + CROSS_IN, y, 4, h), h, 4).any(axis=1)
        out = []
        for m, o in ((top, x), (left, y)):
            idx = np.flatnonzero(m)
            out.append(o + float(idx.mean()) if len(idx) and idx.max() - idx.min() <= 3 else None)
        return out

    def panel(self):
        x, y, w, h = self.panel_rect
        return b"".join(self.grab(x + 2, y + int(h * f), w - 4, 2) for f in (0.25, 0.5, 0.75))


def run_one(a):
    xl_port = None
    for _ in range(20):
        s = socket.socket()
        try:
            n = 600 + (os.getpid() + _) % 99
            s.bind(("127.0.0.1", 6000 + n))
            xl_port = n
            break
        except OSError:
            continue
        finally:
            s.close()
    stats = tempfile.mktemp(prefix="slitlink_link_", suffix=".json")
    to = a.xdisplay.rsplit(":", 1)[1]
    link = subprocess.Popen([sys.executable, os.path.join(HERE, "xlink.py"), "--display", str(xl_port), "--to", to,
                             "--delay-ms", str(a.delay_ms), "--mbps", str(a.mbps), "--stats", stats],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert link.stdout.readline().startswith("xlink:")
    drv = Driver(a)
    env = {k: v for k, v in os.environ.items() if k not in ("QT_QPA_PLATFORM", "EXPLORER_X11")}
    env.update(DISPLAY=f"localhost:{xl_port}", PYTHONPATH=a.src)
    cmdline = [sys.executable, os.path.abspath(__file__), "app", a.cube, a.out, "--io", drv.io, "--look", a.look,
               "--seed", str(a.seed), "--slits", str(a.slits), "--steps", str(a.steps), "--on", str(a.on)]
    if a.link:
        cmdline += ["--link", a.link]
    if a.no_live:
        cmdline.append("--no-live")
    log = open(os.path.join(drv.io, "app.log"), "w")
    load0 = open("/proc/loadavg").read().split()[:3] if os.path.exists("/proc/loadavg") else None
    app = subprocess.Popen(cmdline, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        time.sleep(1.0)
        p = drv.cmd("plan", timeout=120)
        time.sleep(3.0)                                 # the first image and the side panels through the link
        drv.colour = p["colour"]
        drv.viewport = p["viewport_global"]
        slits = []
        for i, pts in enumerate(p["points"]):
            res = dict(slit=i)
            for mode in ("settled", "paced"):
                wx, wy, ww, wh = p["window"]
                drv.move(wx + ww // 2, wy + wh - 10)     # off the image: the cursor's cross stays where it is
                time.sleep(0.3)
                drv.cmd("start", slit=i)
                drv.move(*pts[0])
                time.sleep(0.8)
                where = drv.cmd("where")
                drv.panel_rect = where["panel_global"]
                res["where"] = where
                shot = os.environ.get("SLITLINK_SHOT")
                if shot and i == 0 and mode == "settled":
                    drv.ppm(shot, *p["window"])
                res[mode] = settled(drv, pts) if mode == "settled" else paced(drv, pts)
                drv.cmd("stop")
                time.sleep(0.5)
            slits.append(res)
        drv.cmd("quit")
        app.wait(30)
    finally:
        if app.poll() is None:
            app.kill()
        link.terminate()
    load1 = open("/proc/loadavg").read().split()[:3] if os.path.exists("/proc/loadavg") else None
    with open(os.path.join(drv.io, "updates.json")) as f:
        logged = json.load(f)
    updates, events = logged["updates"], logged["events"]
    linkstats = json.load(open(stats))
    out = dict(host=socket.gethostname(), date=time.strftime("%Y-%m-%d %H:%M:%S"), label=a.label, src=a.src,
               cube=a.cube, link=a.link, on=a.on, look=a.look, delay_ms=a.delay_ms, mbps=a.mbps, live=not a.no_live,
               load=[load0, load1], cpus=sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
               plan=p, slits=slits, updates=updates, events=events, linkstats=linkstats)
    out["summary"] = summarize(out)
    with open(a.out, "w") as f:
        json.dump(out, f)
    print(json.dumps(dict(label=a.label, **out["summary"])))


def settled(drv, pts):
    rows = []
    for k in range(1, len(pts)):
        x, y = pts[k]
        base = drv.reds(x, y)
        pan = drv.panel()
        t0 = time.time()
        drv.move(x, y)
        line = first = last = None
        changes = 0
        end = t0 + STEP_TIMEOUT_S
        while True:
            now = time.time()
            if line is None and drv.reds(x, y) > base:
                line = now
            q = drv.panel()
            if q != pan:
                pan = q
                changes += 1
                first = first or now
                last = now
            ref = max(v for v in (line, last, t0) if v is not None)
            if (line is not None and now - ref > QUIET_S) or now > end:
                break
        rows.append(dict(t=t0, line_ms=ms(line, t0), panel_ms=ms(first, t0), panel_last_ms=ms(last, t0),
                         panel_changes=changes, base=base))
    return rows


def paced(drv, pts):
    """The moves 16 ms apart. Per step: when the box at its place first shows more of the slit's colour than before
    the moves (line_ms: early when the cursor's cross of an earlier step crosses that box), and when the cursor's cross
    is shown at its place (cross_ms: the cross's vertical line read in a strip along the viewport's top, its
    horizontal one in a strip along its left edge; drawn in the same repaint of the viewport as the draft line). A
    step whose cross is never shown was skipped on the screen (the bridge sends only the latest pixels)."""
    n = len(pts) - 1
    base = [drv.reds(*pts[k]) for k in range(1, n + 1)]
    t0 = time.time()
    due = [t0 + (k - 1) * MOVE_S for k in range(1, n + 1)]
    moved: list = [None] * n
    line: list = [None] * n
    cross: list = [None] * n
    pan = drv.panel()
    pchanges = []
    nxt = 0
    end = due[-1] + 1.5
    while time.time() < end:
        now = time.time()
        if nxt < n and now >= due[nxt]:
            drv.move(*pts[nxt + 1])
            moved[nxt] = time.time()
            nxt += 1
        for k in range(nxt):
            if line[k] is None and drv.reds(*pts[k + 1]) > base[k]:
                line[k] = time.time()
        xc, yc = drv.cross()
        if xc is not None and yc is not None:
            t = time.time()
            for k in range(nxt - 1, -1, -1):
                if abs(pts[k + 1][0] - xc) <= 2 and abs(pts[k + 1][1] - yc) <= 2:
                    if cross[k] is None:
                        cross[k] = t
                    break
        q = drv.panel()
        if q != pan:
            pan = q
            pchanges.append(time.time())
    return dict(moved=moved, line=line, line_ms=[ms(line[k], moved[k]) for k in range(n)],
                cross_ms=[ms(cross[k], moved[k]) for k in range(n)], panel_changes=pchanges, t_last_move=moved[-1])


def ms(t, t0):
    return None if t is None or t0 is None else round((t - t0) * 1e3, 2)


def inter(r, rect):
    x, y, w, h = r
    X, Y, W, H = rect
    return x < X + W and X < x + w and y < Y + H and Y < y + h


def summarize(out):
    def med(v):
        v = [x for x in v if x is not None]
        return round(statistics.median(v), 2) if v else None

    line, pfirst, plast, missed = [], [], [], 0
    by_step = []
    pline = []
    pcross: list = []
    pshown: list = []
    p_painted = []
    ev = out["events"]
    for s in out["slits"]:
        ts = [r["t"] for r in s["settled"]] + [s["settled"][-1]["t"] + 2.0]
        for i, r in enumerate(s["settled"]):
            t0, t1 = ts[i], ts[i + 1]
            line.append(r["line_ms"])
            pfirst.append(r["panel_ms"])
            plast.append(r["panel_last_ms"])
            missed += r["line_ms"] is None
            ups = [u for u in out["updates"] if t0 <= u["t0"] < t1]
            b = dict(viewport=0, panel=0, other=0)
            for u in ups:
                for k in b:
                    b[k] += u["split"].get(k, 0)

            def first(kind, t0=t0, t1=t1):
                return next((ms(t, t0) for t, k in ev if k == kind and t0 <= t < t1), None)
            carrier = next((u for u in ups if u["split"]["viewport"] > 0), None)
            by_step.append(dict(updates=len(ups), **b, motion_ms=first("motion"), band_ms=first("band"),
                                slice_paint_ms=first("slice"),
                                grab_ms=ms(ups[0]["t0"], t0) if ups else None,
                                carrier_sent_ms=ms(carrier["t1"], t0) if carrier else None,
                                carrier_kB=sum(carrier["split"][k] for k in b) / 1e3 if carrier else None,
                                carrier_panel_kB=carrier["split"]["panel"] / 1e3 if carrier else None))
        pace = s["paced"]
        pline += pace["line_ms"]
        pcross += pace.get("cross_ms", [])
        pshown.append(sum(v is not None for v in pace.get("cross_ms", [])))
        p_painted.append(len([t for t in pace["panel_changes"] if t <= pace["t_last_move"] + 0.05]))
    out["steps"] = by_step

    def tot(k, scale=1.0):
        v = med([b[k] for b in by_step])
        return None if v is None else round(v * scale, 1)
    return dict(line_ms=med(line), line_p90=pct(line, 90), panel_ms=med(pfirst), panel_last_ms=med(plast),
                missed=missed, updates_per_step=tot("updates"), kB_viewport=tot("viewport", 1e-3),
                kB_panel=tot("panel", 1e-3), kB_other=tot("other", 1e-3), motion_ms=tot("motion_ms"),
                band_ms=tot("band_ms"), slice_paint_ms=tot("slice_paint_ms"), grab_ms=tot("grab_ms"),
                carrier_sent_ms=tot("carrier_sent_ms"), carrier_kB=tot("carrier_kB"),
                carrier_panel_kB=tot("carrier_panel_kB"), paced_line_ms=med(pline), paced_line_p90=pct(pline, 90),
                paced_cross_ms=med(pcross), paced_cross_p90=pct(pcross, 90), paced_cross_shown=med(pshown),
                paced_panel_changes=med(p_painted), load=out["load"])


def pct(v, q):
    v = sorted(x for x in v if x is not None)
    return round(v[min(len(v) - 1, int(len(v) * q / 100))], 2) if v else None


if __name__ == "__main__":
    a = args()
    if a.which == "app":
        run_app(a)
    else:
        run_one(a)
