"""Every interaction through the X11 bridge and an emulated link (bench/xlink.py), seen from the X server's side, per
input step: when the first region that changes shows its new pixels on the server and when the last one does, the
bytes the bridge sent per region, the bridge's updates and the Qt paints per region. Runs any version of explorer
(--src), so that two commits can be compared, ABBA. bench/slit_link.py measures the slit the same way.

    python bench/bridge_link.py one <cube> <out.json> --src <explorer/src> --xdisplay :N [--delay-ms 6] [--mbps 30]
        [--link <other cube> [--detach]] [--look classic] [--only cursor,t,...]

Three processes: the link (localhost:M to the X server :N), the application (this file's `app`, explorer through the
bridge on localhost:M) and this one, which talks to :N directly, as the screen, the keyboard and the mouse are on the
far side of an ssh -Y link. Input goes in with XTEST.

Regions: per cube k, its image's viewport (img<k>), its colour key (key<k>), its spectra (sp<k>) and lambda-t (lt<k>)
panels, and the main window's status bar (status); the rest of each X window is other@<window>. The application says
where each is on the screen and in its X window. Per poll the driver reads each of our X windows whole with GetImage
and compares each region with the poll before (the poll's period is the timing's resolution: poll_ms in the output).

Scenarios (--only picks some), each step settled (no region changed for QUIET_S, or STEP_TIMEOUT_S):
- cursor: the pointer over the main image in STEPS moves; then cursor_paced, 40 moves 16 ms apart: how many times
  each region changed on the server while the pointer moved, and how long after the last move the screen settled;
- t, lam: the arrow keys (up: t + 1, right: lambda + 1), the pointer resting on the image;
- play: Space, PLAY_S of playback, Space: the image's changes on the server per second against the frames stepped;
- zoom: the wheel over the image, in then out; pan: a press and a drag across the image;
- keydrag: the pointer onto the colour key, then its upper handle dragged; gamma: the wheel over the key.
The application logs each update the bridge's sender takes, with the bytes of each grabbed region (32x32 tiles that
changed: grey at 1 B/px, colour at 4) split by region, each paint per region and each input reaching Qt.
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
QUIET_S = 0.150
STEP_TIMEOUT_S = 2.0
STEPS = 12
PACED_S = 0.016
PLAY_S = 4.0
BAND_PX = 60000                                         # regions larger are read as bands (Driver.snap)
SCENARIOS = ("cursor", "t", "lam", "zoom", "pan", "keydrag", "gamma", "play")


def args():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=("one", "app"))
    ap.add_argument("cube")
    ap.add_argument("out")
    ap.add_argument("--src", default=None)
    ap.add_argument("--xdisplay", default=None)
    ap.add_argument("--delay-ms", type=float, default=6.0)
    ap.add_argument("--mbps", type=float, default=30.0)
    ap.add_argument("--link", default=None)
    ap.add_argument("--detach", action="store_true", help="the linked cube in a window of its own")
    ap.add_argument("--native", action="store_true", help="no bridge, no link: Qt's xcb straight on the X server")
    ap.add_argument("--probe", action="store_true", help="after each step, the pixels the server shows that Qt "
                    "no longer has, per region")
    ap.add_argument("--look", default="classic")
    ap.add_argument("--only", default=",".join(SCENARIOS))
    ap.add_argument("--label", default=None)
    ap.add_argument("--io", default=None, help="app: the folder of the command, answer and log files")
    return ap.parse_args()


# ------------------------------------------------------------------------------------------------ the application
def run_app(a):
    os.environ["EXPLORER_TERMINAL_KEYS"] = "0"
    from PySide6 import QtCore, QtGui, QtWidgets

    from explorer.platform.xbridge import kernels as K
    from explorer.platform.xbridge import transport as T
    from explorer.ui.app import start as start_app

    updates: list = []
    events: list = []                                   # (time, what, region)
    regions: dict = {}                                  # name -> (xid, [x, y, w, h] in its window)
    cur: list = []
    orig_cp = K.changed_pieces

    def cp(arr, last, force, grey):
        r = orig_cp(arr, last, force, grey)
        cur.append(r)
        return r
    K.changed_pieces = cp
    orig_up = T.Transport._update

    def region_of(xid, tile):
        for name, (rx, r) in regions.items():
            if rx == xid and inter(tile, r):
                return name
        return f"other@{xid:#x}"

    def up(self, items):
        cur.clear()
        t0 = time.time()
        orig_up(self, items)
        t1 = time.time()
        split: dict = {}
        if len(cur) == len(items):
            for it, r in zip(items, cur, strict=True):
                xid, _W, _H, x, y = it[:5]
                for kind, rx, ry, rw, rh in (r.tolist() if len(r) else ()):
                    key = region_of(xid, [x + rx, y + ry, rw, rh])
                    split[key] = split.get(key, 0) + rw * rh * (1 if kind == 1 else 4)
        updates.append(dict(t0=t0, t1=t1, n=len(items), split=split, matched=len(cur) == len(items)))
    T.Transport._update = up

    from explorer.platform.xbridge import bridge as BR
    from explorer.platform.xbridge import qtinput as QI

    for meth in ("motion", "button", "key"):
        orig = getattr(QI.QtInput, meth)

        def wrapped(self, *x, _o=orig, _m=meth, **k):
            events.append((time.time(), "xinput", _m))
            return _o(self, *x, **k)
        setattr(QI.QtInput, meth, wrapped)
    orig_flush = BR.Bridge._flush

    def flush(self):
        events.append((time.time(), "flush" if self.transport.ready.is_set() else "flush-busy", ""))
        return orig_flush(self)
    BR.Bridge._flush = flush

    widgets: dict = {}                                  # widget -> region name

    class Paints(QtCore.QObject):
        def eventFilter(self, obj, e):
            if e.type() in INPUT and isinstance(obj, QtGui.QWindow):
                events.append((time.time(), "input", int(e.type())))
                events.append((time.time(), "cpu", time.thread_time()))
            if e.type() == QtCore.QEvent.Type.Paint and isinstance(obj, QtWidgets.QWidget):
                r = e.region().boundingRect()
                if r.width() * r.height() > 0:
                    o, name = obj, None
                    while o is not None and name is None:
                        name = widgets.get(o)
                        o = o.parentWidget() if not o.isWindow() else None
                    events.append((time.time(), "paint", f"{name or 'other'}:{type(obj).__name__}"))
            return False
    E = QtCore.QEvent.Type
    INPUT = (E.MouseMove, E.MouseButtonPress, E.KeyPress, E.Wheel)
    paints = Paints()

    st = start_app(a.cube, x11="native" if a.native else "bridge", look=a.look, saved_layout=False,
                   linked=[a.link] if a.link else ())
    app, w = st.app, st.shell
    w.resize(1400, 900)
    w.move(0, 0)
    if a.link and a.detach:
        w.detach_cubes(True)
    app.installEventFilter(paints)
    br = getattr(st.disp, "bridge", None)
    orig_step = type(w)._play_step

    def play_step(self):
        events.append((time.time(), "play_step", ""))
        return orig_step(self)
    type(w)._play_step = play_step
    io = a.io
    state = dict(n=-1)

    def named():
        out = []
        for k, c in enumerate(w.cubes):
            out.append((f"key{k}", c.key))
            for nm, p in (("img", c.view), ("sp", c.spectra), ("lt", c.lambda_t)):
                if p is not None:
                    wid = p.widget.viewport() if nm == "img" else p.widget
                    out.append((f"{nm}{k}", wid))
        out.append(("status", w.statusBar()))
        return out

    def where():
        regions.clear()
        widgets.clear()
        out: dict = dict(regions={}, windows=[])
        for name, wid in named():
            if not wid.isVisible() or wid.width() <= 1:
                continue
            top = wid.window()
            rec = br.windows.get(top) if br is not None else _Native(top)
            if rec is None:
                continue
            p = wid.mapTo(top, QtCore.QPoint(0, 0))
            g = wid.mapToGlobal(QtCore.QPoint(0, 0))
            regions[name] = (rec.xid, [p.x(), p.y(), wid.width(), wid.height()])
            widgets[wid] = name
            out["regions"][name] = dict(xid=rec.xid, win=[p.x(), p.y(), wid.width(), wid.height()],
                                        glob=[g.x(), g.y(), wid.width(), wid.height()])
        tops = list(br.windows) if br is not None else [_Native(t) for t in QtWidgets.QApplication.topLevelWidgets()
                                                          if t.isVisible() and t.isWindow() and t.width() > 1]
        for rec in tops:
            if rec.w.isVisible():
                g = rec.w.geometry()
                out["windows"].append(dict(xid=rec.xid, glob=[g.x(), g.y(), g.width(), g.height()],
                                           name=type(rec.w).__name__))
        return out

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
        if op == "where":
            out.update(where())
        elif op == "keyhandles":
            key = w.cubes[0].key
            lo, hi = key.levels()
            r = key._bar()
            g = key.mapToGlobal(QtCore.QPoint(0, 0))
            out.update(hot=key.hot, lo=[g.x() + key.x_of(lo), g.y() + r.center().y()],
                       hi=[g.x() + key.x_of(hi), g.y() + r.center().y()],
                       glob=[g.x(), g.y(), key.width(), key.height()])
        elif op == "probe":                             # what Qt has now, per window, to compare with the server
            out["files"] = []
            for rec in (br.windows if br is not None else ()):
                if rec.w.isVisible():
                    img = br._grab(rec.w, rec.w.rect())
                    if img is not None:
                        fn = os.path.join(io, f"probe_{rec.xid:x}.raw")
                        with open(fn, "wb") as f:
                            f.write(BR._pixels(img).copy().tobytes())
                        out["files"].append([rec.xid, fn, img.width(), img.height()])
        elif op == "mark":
            events.append((time.time(), "mark", cmd.get("what", "")))
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
        import numpy as np
        from Xlib import XK, X, display
        from Xlib.ext import xtest

        self.np, self.X, self.XK, self.xtest = np, X, XK, xtest
        self.d = display.Display(a.xdisplay)
        self.root = self.d.screen().root
        self.io = tempfile.mkdtemp(prefix="bridgelink_io_")
        self.n = 0
        self.polls: list = []
        self.probe = a.probe

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

    def setup(self, where):
        self.windows = where["windows"]
        self.regions = {}
        for name, r in where["regions"].items():
            x, y, w, h = r["glob"]
            win = next(i for i, ww in enumerate(self.windows) if ww["xid"] == r["xid"])
            wx, wy = self.windows[win]["glob"][:2]
            self.regions[name] = (win, x - wx, y - wy, w, h)

    def move(self, x, y):
        self.xtest.fake_input(self.d, self.X.MotionNotify, x=int(x), y=int(y))
        self.d.sync()

    def button(self, b, press):
        self.xtest.fake_input(self.d, self.X.ButtonPress if press else self.X.ButtonRelease, b)
        self.d.sync()

    def key(self, name):
        code = self.d.keysym_to_keycode(self.XK.string_to_keysym(name))
        self.xtest.fake_input(self.d, self.X.KeyPress, code)
        self.xtest.fake_input(self.d, self.X.KeyRelease, code)
        self.d.sync()

    def snap(self):
        """Each region's pixels now, {name: bytes}: a small region whole, a large one as three 2-px bands across and
        three down (at a quarter, half and three quarters): a cursor's lines cross them, a new image or curve changes
        them, and a poll takes a few ms instead of 12 for whole windows."""
        t0 = time.time()
        out = {}
        for name, (i, x, y, w, h) in self.regions.items():
            gx, gy = self.windows[i]["glob"][:2]
            gx, gy = gx + x, gy + y
            if w * h <= BAND_PX:
                boxes = [(gx, gy, w, h)]
            else:
                boxes = [(gx, gy + int(h * f), w, 2) for f in (0.25, 0.5, 0.75)] + \
                        [(gx + int(w * f), gy, 2, h) for f in (0.25, 0.5, 0.75)]
            out[name] = b"".join(self.root.get_image(*b, self.X.ZPixmap, 0xFFFFFFFF).data for b in boxes)
        self.polls.append(time.time() - t0)
        return out

    def stale(self):
        """Pixels the server shows that are not what Qt has now, per region (a missed repaint), right after a step
        settled (the periodic whole-window check, every second, would send them later)."""
        np = self.np
        r = self.cmd("probe")
        out: dict = {}
        for xid, fn, w, h in r["files"]:
            i = next(k for k, ww in enumerate(self.windows) if ww["xid"] == xid)
            x, y = self.windows[i]["glob"][:2]
            qt = np.fromfile(fn, np.uint32).reshape(h, w)
            got = np.frombuffer(self.root.get_image(x, y, w, h, self.X.ZPixmap, 0xFFFFFFFF).data,
                                np.uint32).reshape(h, -1)[:, :w]
            bad = ((qt ^ got) & 0xFFFFFF) != 0
            for name, (j, rx, ry, rw, rh) in self.regions.items():
                if j == i:
                    out[name] = int(bad[ry:ry + rh, rx:rx + rw].sum())
            out[f"window{i}"] = int(bad.sum())
        return out

    def step(self, act, settle=True):
        """Do act() and watch every region until the screen is quiet: per region, first and last change (ms from
        the input) and the number of changes seen."""
        before = self.snap()
        t0 = time.time()
        act()
        seen: dict = {}
        last_change = None
        end = t0 + STEP_TIMEOUT_S
        while True:
            now_snap = self.snap()
            now = time.time()
            for k, v in now_snap.items():
                if v != before[k]:
                    s = seen.setdefault(k, [ms(now, t0), None, 0])
                    s[1] = ms(now, t0)
                    s[2] += 1
                    last_change = now
            before = now_snap
            ref = last_change or t0
            if not settle:
                break
            if (last_change is not None and now - ref > QUIET_S) or now > end or \
                    (last_change is None and now - t0 > 0.8):
                break
        out = dict(t=t0, regions=seen)
        if self.probe:
            out["stale"] = self.stale()
        return out


def scenario(drv, name, where):
    img = where["regions"]["img0"]["glob"]
    cx, cy = img[0] + img[2] // 2, img[1] + img[3] // 2
    rows = []
    if name in ("cursor", "t", "lam", "zoom", "gamma"):
        drv.move(cx, cy)
        time.sleep(0.4)
    if name == "cursor":
        for k in range(STEPS):
            f = (k + 1) / (STEPS + 1)
            x, y = img[0] + img[2] * (0.2 + 0.6 * f), img[1] + img[3] * (0.25 + 0.5 * f)
            rows.append(drv.step(lambda x=x, y=y: drv.move(x, y)))
    elif name == "cursor_paced":
        drv.move(img[0] + img[2] * 0.2, img[1] + img[3] * 0.3)
        time.sleep(0.6)
        before = drv.snap()
        t0 = time.time()
        n = 40
        changes: dict = {}
        k = 0
        last_move = None
        last_change = None
        while True:
            now = time.time()
            if k < n and now >= t0 + k * PACED_S:
                f = k / (n - 1)
                drv.move(img[0] + img[2] * (0.2 + 0.6 * f), img[1] + img[3] * (0.3 + 0.4 * f))
                last_move = time.time()
                k += 1
            s = drv.snap()
            t = time.time()
            for r, v in s.items():
                if v != before[r]:
                    changes.setdefault(r, []).append(ms(t, t0))
                    last_change = t
            before = s
            if k >= n and (t - (last_change or t) > QUIET_S or t - last_move > STEP_TIMEOUT_S):
                break
        rows.append(dict(t=t0, moves=n, moves_ms=ms(last_move, t0), changes=changes,
                         settle_after_last_ms=ms(last_change, last_move)))
    elif name in ("t", "lam"):
        keys = ("Up", "Down") if name == "t" else ("Right", "Left")
        for k in range(STEPS):
            rows.append(drv.step(lambda kk=keys[0] if k < STEPS // 2 else keys[1]: drv.key(kk)))
    elif name == "zoom":
        for k in range(STEPS):
            b = 4 if k < STEPS // 2 else 5
            rows.append(drv.step(lambda b=b: (drv.button(b, True), drv.button(b, False))))
    elif name == "pan":
        drv.move(cx, cy)
        time.sleep(0.3)
        drv.button(1, True)
        time.sleep(0.2)
        for k in range(STEPS):
            rows.append(drv.step(lambda k=k: drv.move(cx - 15 * (k + 1), cy - 10 * (k + 1))))
        drv.button(1, False)
        time.sleep(0.4)
    elif name in ("keydrag", "gamma"):
        h = drv.cmd("keyhandles")
        gx, gy, gw, gh = h["glob"]
        drv.move(gx + gw // 2, gy + gh // 2)
        time.sleep(0.6)
        h = drv.cmd("keyhandles")
        if name == "gamma":
            for k in range(STEPS):
                b = 4 if k < STEPS // 2 else 5
                rows.append(drv.step(lambda b=b: (drv.button(b, True), drv.button(b, False))))
        else:
            hx, hy = h["hi"]
            lx = h["lo"][0]
            drv.move(hx, hy)
            time.sleep(0.3)
            drv.button(1, True)
            time.sleep(0.3)
            for k in range(STEPS):
                rows.append(drv.step(lambda k=k: drv.move(hx - (hx - lx) * 0.04 * (k + 1), hy)))
            drv.button(1, False)
            time.sleep(0.3)
            drv.key("Escape")
        drv.move(cx, cy)
        time.sleep(0.5)
    elif name == "play":
        drv.move(cx, cy)
        time.sleep(0.4)
        before = drv.snap()
        drv.cmd("mark", what="play")
        t0 = time.time()
        drv.key("space")
        ch: list = []
        while time.time() < t0 + PLAY_S:
            s = drv.snap()
            if s["img0"] != before["img0"]:
                ch.append(ms(time.time(), t0))
            before = s
        drv.key("space")
        t1 = time.time()
        time.sleep(1.0)
        rows.append(dict(t=t0, t_end=t1, img_changes=ch))
    return rows


class _Native:
    """A top-level window shown by Qt's xcb (--native), as the bridge's records name one."""

    def __init__(self, w):
        self.w, self.xid = w, int(w.winId())


def run_one(a):
    xl_port = None
    for i in range(20):
        s = socket.socket()
        try:
            n = 700 + (os.getpid() + i) % 99
            s.bind(("127.0.0.1", 6000 + n))
            xl_port = n
            break
        except OSError:
            continue
        finally:
            s.close()
    stats = tempfile.mktemp(prefix="bridgelink_link_", suffix=".json")
    to = a.xdisplay.rsplit(":", 1)[1]
    link = subprocess.Popen([sys.executable, os.path.join(HERE, "xlink.py"), "--display", str(xl_port), "--to", to,
                             "--delay-ms", str(a.delay_ms), "--mbps", str(a.mbps), "--stats", stats],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert link.stdout.readline().startswith("xlink:")
    drv = Driver(a)
    env = {k: v for k, v in os.environ.items() if k not in ("QT_QPA_PLATFORM", "EXPLORER_X11")}
    env.update(DISPLAY=a.xdisplay if a.native else f"localhost:{xl_port}", PYTHONPATH=a.src)
    cmdline = [sys.executable, os.path.abspath(__file__), "app", a.cube, a.out, "--io", drv.io, "--look", a.look]
    if a.link:
        cmdline += ["--link", a.link]
    if a.detach:
        cmdline.append("--detach")
    if a.native:
        cmdline.append("--native")
    log = open(os.path.join(drv.io, "app.log"), "w")
    load0 = open("/proc/loadavg").read().split()[:3] if os.path.exists("/proc/loadavg") else None
    app = subprocess.Popen(cmdline, env=env, stdout=log, stderr=subprocess.STDOUT)
    res: dict = {}
    try:
        time.sleep(1.0)
        where = drv.cmd("where", timeout=120)
        time.sleep(3.0)                                 # the first image and the side panels through the link
        where = drv.cmd("where")
        drv.setup(where)
        names = [s for s in a.only.split(",") if s]
        if "cursor" in names:
            names.insert(names.index("cursor") + 1, "cursor_paced")
        for name in names:
            drv.cmd("mark", what=name)
            res[name] = scenario(drv, name, where)
            time.sleep(0.5)
        drv.cmd("quit")
        app.wait(30)
    finally:
        if app.poll() is None:
            app.kill()
        link.terminate()
    load1 = open("/proc/loadavg").read().split()[:3] if os.path.exists("/proc/loadavg") else None
    with open(os.path.join(drv.io, "updates.json")) as f:
        logged = json.load(f)
    out = dict(host=socket.gethostname(), date=time.strftime("%Y-%m-%d %H:%M:%S"), label=a.label, src=a.src,
               cube=a.cube, link=a.link, detach=a.detach, native=a.native, look=a.look, delay_ms=a.delay_ms,
               mbps=a.mbps,
               load=[load0, load1], cpus=sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
               where=where, res=res, updates=logged["updates"], events=logged["events"],
               poll_ms=round(statistics.median(drv.polls) * 1e3, 2), linkstats=json.load(open(stats)))
    out["summary"] = summarize(out)
    with open(a.out, "w") as f:
        json.dump(out, f)
    print(json.dumps(dict(label=a.label, poll_ms=out["poll_ms"], load=out["load"], summary=out["summary"])))


def summarize(out):
    """Per scenario, medians over its steps: first and last region on the server (ms from the input), the bridge's
    updates and kB per step by region, Qt's paints per step by region; cursor_paced: changes per region while the
    pointer moved and the settle after the last move; play: the image's changes on the server per second against
    the frames stepped."""
    ups, ev = out["updates"], out["events"]
    summ: dict = {}
    for name, rows in out["res"].items():
        if name == "cursor_paced":
            r = rows[0]
            summ[name] = dict(moves=r["moves"], moves_ms=r["moves_ms"], settle_ms=r["settle_after_last_ms"],
                              changes={k: len(v) for k, v in r["changes"].items()})
            t0, t1 = r["t"], r["t"] + (r["moves_ms"] + (r["settle_after_last_ms"] or 0)) / 1e3
            u = [x for x in ups if t0 <= x["t0"] < t1]
            summ[name].update(updates=len(u), kB=round(sum(sum(x["split"].values()) for x in u) / 1e3, 1))
            continue
        if name == "play":
            r = rows[0]
            dur = (r["t_end"] - r["t"])
            steps = [t for t, k, _ in ev if k == "play_step" and r["t"] <= t < r["t_end"]]
            ch = r["img_changes"]
            u = [x for x in ups if r["t"] <= x["t0"] < r["t_end"]]
            summ[name] = dict(stepped_fps=round(len(steps) / dur, 2), shown_fps=round(len(ch) / dur, 2),
                              updates_per_s=round(len(u) / dur, 2),
                              kB_per_s=round(sum(sum(x["split"].values()) for x in u) / 1e3 / dur, 1))
            continue
        first, last, nupd, kb, paints, kbr = [], [], [], [], {}, {}
        per_region_first: dict = {}
        ts = [r["t"] for r in rows] + [rows[-1]["t"] + STEP_TIMEOUT_S]
        for i, r in enumerate(rows):
            reg = r["regions"]
            if reg:
                first.append(min(v[0] for v in reg.values()))
                last.append(max(v[1] for v in reg.values()))
            for k, v in reg.items():
                per_region_first.setdefault(k, []).append(v[0])
            u = [x for x in ups if ts[i] <= x["t0"] < ts[i + 1]]
            nupd.append(len(u))
            kb.append(sum(sum(x["split"].values()) for x in u) / 1e3)
            for x in u:
                for k, b in x["split"].items():
                    kbr.setdefault(k, [0.0] * len(rows))[i] += b / 1e3
            for t, kind, what in ev:
                if kind == "paint" and ts[i] <= t < ts[i + 1]:
                    reg_name = what.split(":")[0]
                    paints.setdefault(reg_name, [0] * len(rows))[i] += 1
        tl: dict = {}
        for i in range(len(rows)):
            t0, t1 = ts[i], ts[i + 1]
            for t, kind, what in ev:
                if t0 <= t < t1:
                    key = {"input": "input", "flush": "flush", "flush-busy": "flush_busy"}.get(kind)
                    if kind == "paint":
                        key = "paint_" + what.split(":")[0]
                    if key is not None and key not in tl.setdefault(i, {}):
                        tl[i][key] = ms(t, t0)
            cpu = [float(w) for t, k, w in ev if k == "cpu" and t0 <= t < t1 + 0.5]
            nxt = [float(w) for t, k, w in ev if k == "cpu" and t >= t1]
            if cpu and nxt:
                tl.setdefault(i, {})["cpu_ms"] = round((nxt[0] - cpu[0]) * 1e3, 2)
            u = [x for x in ups if t0 <= x["t0"] < t1]
            for j, x in enumerate(u[:3]):
                tl.setdefault(i, {})[f"upd{j}_start"] = ms(x["t0"], t0)
                tl[i][f"upd{j}_sent"] = ms(x["t1"], t0)
                tl[i][f"upd{j}_kB"] = round(sum(x["split"].values()) / 1e3, 1)
        keys = sorted({k for d in tl.values() for k in d})
        timeline = {k: med([d.get(k) for d in tl.values()]) for k in keys}
        summ[name] = dict(steps=len(rows), first_ms=med(first), last_ms=med(last), last_p90=pct(last, 90),
                          timeline=timeline,
                          updates=med(nupd), kB=med(kb),
                          kB_by_region={k: med(v) for k, v in sorted(kbr.items())},
                          paints_by_region={k: med(v) for k, v in sorted(paints.items())},
                          first_ms_by_region={k: med(v) for k, v in sorted(per_region_first.items())})
    return summ


def ms(t, t0):
    return None if t is None or t0 is None else round((t - t0) * 1e3, 2)


def med(v):
    v = [x for x in v if x is not None]
    return round(statistics.median(v), 2) if v else None


def pct(v, q):
    v = sorted(x for x in v if x is not None)
    return round(v[min(len(v) - 1, int(len(v) * q / 100))], 2) if v else None


def inter(r, rect):
    x, y, w, h = r
    X, Y, W, H = rect
    return x < X + W and X < x + w and y < Y + H and Y < y + h


if __name__ == "__main__":
    a = args()
    if a.which == "app":
        run_app(a)
    else:
        run_one(a)
