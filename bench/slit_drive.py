"""The slit driven as a user drives it, through the real Shell, offscreen, one process per run: what each pointer step
costs while a slit is drawn, the slit finished, and A/D along it. Runs any version of explorer (PYTHONPATH), so that
two commits can be compared, ABBA, or bisected.

    QT_QPA_PLATFORM=offscreen PYTHONPATH=<src> python bench/slit_drive.py one <cube> <out.json>
        [--link <other cube>] [--on K] [--look L] [--profile out.prof] [--seed N] [--slits 3] [--steps 40]
        [--walk 10] [--label NAME]
    python bench/slit_drive.py abba <cube> <out_dir> --a-src DIR --b-src DIR [--rounds 4] [same options]

--on K draws on the image of linked cube K (0: the main one). Per slit (a straight line about a third of the image
long, its place drawn from --seed):
- S, the first point (SlitTool.add), then --steps pointer moves along the line, each a mouse move sent to the
  image's viewport, and the loop run until the step has settled: the draft line painted (the main image's dashed
  band, PlotCurveItem.paint), the time slice painted with an image given after the move, no read in flight, then
  30 ms more. Per step: line_ms and slices_ms (from the move), busy_ms (the UI thread's time inside the move's
  handling and the passes of the loop that did work, > 50 us each), the paints of the main image (ImageItem.paint)
  and of the image's viewport (Paint events);
- the same moves at the pointer's pace (16 ms apart, without waiting), then the time to settle: how many time
  slices were painted, the busy time, the image paints;
- the second point and the slit finished (SlitTool.finish): the time to its slices complete and painted;
- --walk A steps back from the far end (Shell.slit_step), each settled as above: settle_ms, busy_ms, paints.
The JSON has the host, the date, the load before and after, the CPUs the process may run on and every number.
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
QUIET_S = 0.030
BUSY_S = 50e-6


def args():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=("one", "abba"))
    ap.add_argument("cube")
    ap.add_argument("out")
    ap.add_argument("--link", default=None)
    ap.add_argument("--on", type=int, default=0)
    ap.add_argument("--look", default="classic")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--slits", type=int, default=3)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--walk", type=int, default=10)
    ap.add_argument("--label", default=None)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--a-src", default=None)
    ap.add_argument("--b-src", default=None)
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


def run_one(a):
    os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())
    os.environ.setdefault("EXPLORER_LAYOUT", os.path.join(tempfile.mkdtemp(), "layout.ini"))
    os.environ["EXPLORER_TERMINAL_KEYS"] = "0"
    import pyqtgraph as pg
    from PySide6 import QtCore, QtGui, QtWidgets

    from explorer.ui.app import start as start_app

    st = start_app(a.cube, look=a.look, saved_layout=False, linked=[a.link] if a.link else ())
    app, w = st.app, st.shell
    w.resize(1400, 900)
    ds = w.dataset
    on = w.cubes[a.on] if a.on else None                # the image drawn on: the main one, or a linked cube's
    view = on.view if on is not None else w.view
    img, vb = view.widget, view.vb
    tool = w.slit_tool
    panel = getattr(on, "slit_panel", None) if on is not None else None
    ts_item = (panel or w.slit_panel).ts_img            # the drawn-on cube's tab, where there is one
    main_item = view.img

    def add(x, y):
        try:
            tool.add(x, y, a.on)
        except TypeError:                               # a version without a slit per cube
            tool.add(x, y)

    def schedulers():
        out = [w.scheduler]
        for c in getattr(w, "cubes", []):
            s = getattr(c, "scheduler", None)
            if s is not None and s not in out:
                out.append(s)
        return out

    def idle():
        for s in schedulers():
            if s.in_flight() or getattr(s.slit, "_busy", False):
                return False
        return True

    # ---- what is painted, and when
    ev = dict(band=None, ts_ver=0, ts_at=0, ts_t=None, main=0, vp=0, area=0, others=0)
    band = next((m.band for m in tool.marks if m.band.getViewBox() is vb), tool.marks[0].band)
    orig_curve = pg.PlotCurveItem.paint

    def curve_paint(self, *x, **k):
        if self is band and ev["band"] is None:
            ev["band"] = time.perf_counter()
        return orig_curve(self, *x, **k)
    pg.PlotCurveItem.paint = curve_paint
    orig_set = ts_item.setImage

    def ts_set(*x, **k):
        ev["ts_ver"] += 1
        return orig_set(*x, **k)
    ts_item.setImage = ts_set
    orig_img = pg.ImageItem.paint

    def img_paint(self, *x, **k):
        if self is ts_item and ev["ts_at"] != ev["ts_ver"]:
            ev["ts_at"] = ev["ts_ver"]
            ev["ts_t"] = time.perf_counter()
        elif self is main_item:
            ev["main"] += 1
        return orig_img(self, *x, **k)
    pg.ImageItem.paint = img_paint

    class Paints(QtCore.QObject):
        def eventFilter(self, obj, e):
            if e.type() == QtCore.QEvent.Type.Paint:
                r = e.region().boundingRect()
                if obj is img.viewport():
                    ev["vp"] += 1
                    ev["area"] += r.width() * r.height()
                else:
                    ev["others"] += r.width() * r.height()
            return False
    paints = Paints()
    img.viewport().installEventFilter(paints)
    for c in getattr(w, "cubes", []):
        v = getattr(c, "view", None)
        if v is not None and v.widget is not img:
            v.widget.viewport().installEventFilter(paints)
    vp_px = img.viewport().width() * img.viewport().height()

    busy = [0.0]
    cpu = [0.0]

    def pump():
        q, c = time.perf_counter(), time.thread_time()
        app.processEvents()
        d = time.perf_counter() - q
        cpu[0] += time.thread_time() - c
        if d > BUSY_S:
            busy[0] += d
        else:
            time.sleep(0.0003)                          # as the loop blocks when idle: the readers get the GIL

    def spin(until, timeout=10.0):
        end = time.perf_counter() + timeout
        while not until() and time.perf_counter() < end:
            pump()
        return until()

    def quiet(s=QUIET_S):
        end = time.perf_counter() + s
        while time.perf_counter() < end:
            pump()

    def move(x, y):
        vp = img.viewport()
        p = QtCore.QPointF(img.mapFromScene(vb.mapViewToScene(QtCore.QPointF(x, y))))
        e = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, p, vp.mapToGlobal(p), QtCore.Qt.MouseButton.NoButton,
                              QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
        q, c = time.perf_counter(), time.thread_time()
        QtWidgets.QApplication.sendEvent(vp, e)
        busy[0] += time.perf_counter() - q
        cpu[0] += time.thread_time() - c

    def reset():
        ev["band"] = None
        ev["ts_t"] = None
        ev["main"] = ev["vp"] = ev["area"] = ev["others"] = 0
        busy[0] = cpu[0] = 0.0

    def ms(t, t0):
        return None if t is None else round((t - t0) * 1e3, 2)

    spin(lambda: w.first_image_s is not None, 60)
    quiet(1.0)
    res = dict(program=a.label, on=a.on, look=a.look, host=socket.gethostname().split(".")[0],
               date=time.strftime("%Y-%m-%dT%H:%M:%S"),
               cube=os.path.basename(a.cube), link=os.path.basename(a.link) if a.link else None, seed=a.seed,
               load_before=os.getloadavg(), cpus=sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity")
               else None, slits=[])
    prof = None
    if a.profile:                                       # the UI thread's functions over every phase
        import cProfile
        prof = cProfile.Profile()
        prof.enable()
    for k, (p0, p1) in enumerate(lines(a.seed, a.slits, ds.ny, ds.nx)):
        row: dict = dict(k=k, p0=p0, p1=p1)
        w.set_slit_mode(True)
        add(*p0)
        spin(idle)
        quiet(0.2)
        steps = []
        for j in range(1, a.steps + 1):
            f = j / a.steps
            reset()
            ver = ev["ts_ver"]
            t0 = time.perf_counter()
            move(p0[0] + f * (p1[0] - p0[0]), p0[1] + f * (p1[1] - p0[1]))
            spin(lambda ver=ver: ev["band"] is not None and ev["ts_ver"] > ver and ev["ts_t"] is not None
                 and ev["ts_at"] == ev["ts_ver"] and idle(), 5.0)
            done = time.perf_counter()
            quiet()
            steps.append(dict(line_ms=ms(ev["band"], t0), slices_ms=ms(ev["ts_t"], t0),
                              settle_ms=round((done - t0) * 1e3, 2), busy_ms=round(busy[0] * 1e3, 2),
                              cpu_ms=round(cpu[0] * 1e3, 2), main_paints=ev["main"], vp_paints=ev["vp"],
                              vp_frac=round(ev["area"] / vp_px, 3), others_frac=round(ev["others"] / vp_px, 3)))
        row["steps"] = steps
        # back to the first point, then the same moves at the pointer's pace
        tool.undo()
        add(*p0)
        spin(idle)
        quiet(0.2)
        reset()
        v0 = ev["ts_ver"]
        painted = [0]
        at = [ev["ts_at"]]

        def watch(at=at, painted=painted):
            if ev["ts_at"] != at[0]:
                at[0] = ev["ts_at"]
                painted[0] += 1
        t0 = time.perf_counter()
        for j in range(1, a.steps + 1):
            f = j / a.steps
            move(p0[0] + f * (p1[0] - p0[0]), p0[1] + f * (p1[1] - p0[1]))
            end = t0 + j * MOVE_S
            while time.perf_counter() < end:
                pump()
                watch()
        motion = time.perf_counter() - t0
        q = time.perf_counter()
        spin(lambda: ev["ts_at"] == ev["ts_ver"] and idle())
        watch()
        row["paced"] = dict(motion_s=round(motion, 3), settle_ms=round((time.perf_counter() - q) * 1e3, 1),
                            given=ev["ts_ver"] - v0, painted=painted[0], busy_ms=round(busy[0] * 1e3, 1),
                            cpu_ms=round(cpu[0] * 1e3, 1),
                            main_paints=ev["main"], vp_paints=ev["vp"], vp_frac=round(ev["area"] / vp_px, 3),
                            others_frac=round(ev["others"] / vp_px, 3))
        quiet()
        # the second point and the slit finished
        add(*p1)
        reset()
        ver = ev["ts_ver"]
        t0 = time.perf_counter()
        tool.finish()
        spin(lambda ver=ver: ev["ts_ver"] > ver and ev["ts_at"] == ev["ts_ver"] and idle())
        row["finish"] = dict(slices_ms=ms(ev["ts_t"], t0), busy_ms=round(busy[0] * 1e3, 1),
                             cpu_ms=round(cpu[0] * 1e3, 1),
                             settle_ms=round((time.perf_counter() - t0) * 1e3, 1), main_paints=ev["main"])
        quiet(0.2)
        walk = []
        for _ in range(a.walk):
            reset()
            t0 = time.perf_counter()
            c0 = tuple(w.session.state.cursor)
            w.slit_step(-1)
            pump()
            spin(idle)
            done = time.perf_counter()
            quiet()
            walk.append(dict(settle_ms=round((done - t0) * 1e3, 2), busy_ms=round(busy[0] * 1e3, 2),
                             cpu_ms=round(cpu[0] * 1e3, 2),
                             moved=tuple(w.session.state.cursor) != c0,
                             main_paints=ev["main"], vp_paints=ev["vp"]))
        row["walk"] = walk
        w.clear_slit()
        quiet(0.3)
        res["slits"].append(row)
        med = summarize([row])
        print(f"{a.label} slit {k}: " + ", ".join(f"{k_} {v}" for k_, v in med.items()), flush=True)
    if prof is not None:
        prof.disable()
        prof.dump_stats(a.profile)
    res["reads"] = [list(getattr(sc.slit, "reads", []))[-400:] for sc in schedulers()]   # each cube's slit reads
    res["load_after"] = os.getloadavg()
    res["summary"] = summarize(res["slits"])
    json.dump(res, open(a.out, "w"), indent=1)
    st.close() if hasattr(st, "close") else None
    app.quit()


def summarize(slits):
    def med(v):
        v = [x for x in v if x is not None]
        return round(statistics.median(v), 2) if v else None
    steps = [s for r in slits for s in r["steps"]]
    walk = [s for r in slits for s in r["walk"]]
    return dict(
        step_line_ms=med([s["line_ms"] for s in steps]), step_slices_ms=med([s["slices_ms"] for s in steps]),
        step_busy_ms=med([s["busy_ms"] for s in steps]), step_cpu_ms=med([s["cpu_ms"] for s in steps]),
        step_main_paints=med([s["main_paints"] for s in steps]),
        step_vp_paints=med([s["vp_paints"] for s in steps]), step_vp_frac=med([s.get("vp_frac") for s in steps]),
        step_others_frac=med([s.get("others_frac") for s in steps]),
        paced_vp_frac=med([r["paced"].get("vp_frac") for r in slits]),
        paced_motion_s=med([r["paced"]["motion_s"] for r in slits]),
        paced_painted=med([r["paced"]["painted"] for r in slits]),
        paced_busy_ms=med([r["paced"]["busy_ms"] for r in slits]),
        paced_cpu_ms=med([r["paced"]["cpu_ms"] for r in slits]),
        paced_settle_ms=med([r["paced"]["settle_ms"] for r in slits]),
        paced_main_paints=med([r["paced"]["main_paints"] for r in slits]),
        finish_slices_ms=med([r["finish"]["slices_ms"] for r in slits]),
        finish_busy_ms=med([r["finish"]["busy_ms"] for r in slits]),
        finish_cpu_ms=med([r["finish"]["cpu_ms"] for r in slits]),
        walk_settle_ms=med([s["settle_ms"] for s in walk]), walk_busy_ms=med([s["busy_ms"] for s in walk]),
        walk_cpu_ms=med([s["cpu_ms"] for s in walk]),
        walk_main_paints=med([s["main_paints"] for s in walk]))


def run_abba(a):
    os.makedirs(a.out, exist_ok=True)
    srcs = {"A": a.a_src, "B": a.b_src}
    rows = []
    for r in range(a.rounds):
        order = ("A", "B") if r % 2 == 0 else ("B", "A")
        for which in order:
            out = os.path.join(a.out, f"r{r}_{which}.json")
            cmd = [sys.executable, os.path.abspath(__file__), "one", a.cube, out, "--seed", str(a.seed * 100 + r),
                   "--slits", str(a.slits), "--steps", str(a.steps), "--walk", str(a.walk), "--label", which] + (
                       ["--link", a.link] if a.link else [])
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=os.path.abspath(srcs[which]))
            env.pop("DISPLAY", None)
            print(f"round {r + 1}: {which}", flush=True)
            subprocess.run(cmd, env=env, check=True)
            rows.append(json.load(open(out)))
    summary = dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
                   cube=os.path.basename(a.cube), link=a.link and os.path.basename(a.link), rounds=a.rounds,
                   srcs=srcs, programs={})
    for which in ("A", "B"):
        mine = [s for x in rows if x["program"] == which for s in x["slits"]]
        summary["programs"][which] = dict(summarize(mine), load=[x["load_before"][0] for x in rows
                                                                 if x["program"] == which])
    json.dump(summary, open(os.path.join(a.out, "summary.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    a = args()
    run_abba(a) if a.which == "abba" else run_one(a)
