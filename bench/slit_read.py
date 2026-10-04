"""The slit panel's reads, explorer against the prototype, each through its own start-up, offscreen, one process per
run (ROADMAP E7.3; the prototype's audit F70, F71, F73, its slitc_bench).

    QT_QPA_PLATFORM=offscreen python bench/slit_read.py proto|explorer <cube_im.fits> <out.json>
        [--seed N] [--half 0|1] [--slits 4] [--length 600] [--moves 60] [--no-sp]
    python bench/slit_read.py abba <cube_im.fits> <out_dir> --proto-python P [--rounds 4] [same options]

Per slit, a shape of three points about --length px end to end at a random angle (the same for both programs for a
given --seed), centred at a random x in the upper (--half 0) or lower (1) half of the image, so that the two programs
of a round read different pixels; abba runs the rounds in alternating order and swaps the halves every two rounds.
Two cases per slit, each ending with the slit removed:
- finished: a finished slit given at once (the prototype: its slit, slit_path and slitChanged, as _slit_finish sets
  them; explorer: Session.set_path), so that each reads the whole slit in one job and not a slit drawn point by
  point; then the time until both slices are complete (every pixel's block kept with the per-pixel file, both slices
  read without it) and painted (one more pass of the event loop); io_ms is the time spent inside the reads
  (read_slit_blocks or read_slit_bands, timed around the function each program calls);
- live (variant D): the first point added, then --moves pointer moves 16 ms apart along the slit to its far end,
  sent as mouse moves to the image's viewport; the time slice's updates during the motion, each read's time, and the
  time from the last move until the slices are complete.
The JSON has host, date, the load before and after, the CPUs the process may run on, and every slit's numbers.
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
ROOT = os.path.dirname(HERE)
MOVE_S = 0.016


def args():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=("proto", "explorer", "abba"))
    ap.add_argument("cube")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--half", type=int, default=0)
    ap.add_argument("--slits", type=int, default=4)
    ap.add_argument("--length", type=float, default=600.0)
    ap.add_argument("--moves", type=int, default=60)
    ap.add_argument("--no-sp", action="store_true")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--proto-python", default=sys.executable)
    ap.add_argument("--prototype", default=os.environ.get("EXPLORER_PROTOTYPE", os.path.join(ROOT, "..", "prototype")))
    return ap.parse_args()


def shapes(seed, n, length, ny, nx, half):
    """n slits, (x, y) points in view coordinates on pixel centres."""
    import numpy as np

    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        ang = rng.uniform(0, np.pi)
        d = np.array([np.cos(ang), np.sin(ang)]) * length / 2
        mid = rng.normal(0, length / 8, 2)
        c = np.array([rng.uniform(nx * 0.35, nx * 0.65), ny * (0.28 if half == 0 else 0.72)])
        pts = np.clip(np.array([-d, mid, d]) + c, 1, [nx - 2, ny - 2])
        out.append([(float(np.floor(x)) + 0.5, float(np.floor(y)) + 0.5) for x, y in pts])
    return out


# ---------------------------------------------------------------------------------------------------- one program
def run_one(a):
    os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
    os.environ["EXPLORER_TERMINAL_KEYS"] = "0"
    os.environ.pop("CRISPEX_SLIT", None)                # the prototype's default, D
    io: list = []                                       # (kind, ms) of each read, timed around the read function

    def timed(fn, kind):
        def wrap(*x, **k):
            q = time.perf_counter()
            try:
                return fn(*x, **k)
            finally:
                io.append((kind, (time.perf_counter() - q) * 1e3))
        return wrap

    if a.which == "proto":
        import importlib

        sys.path.insert(0, os.path.join(os.path.abspath(a.prototype), "app"))
        sys.argv = sys.argv[:1]
        import viewer  # noqa: F401  (first: the prototype's import paths, Qt, pyqtgraph)

        V = sys.modules["viewer"]
        startup = importlib.import_module("startup")
        s = startup.prepare("auto", "pgr")
        app, _ = startup.make_app(s, "auto")
        c, probe, guard, sp_file, _cal = startup.open_cube(a.cube, None, a.no_sp)
        w = startup.make_viewer(app, s, c, sp_file, probe, guard, kind="slitbench")
        startup.show(app, s, w, size=(1400, 900))
        V.read_slit_blocks = timed(V.read_slit_blocks, "blocks")    # looked up in the module by _slitc_job
        V.read_slit_bands = timed(V.read_slit_bands, "bands")       # and by _slit_band_job
        ny, nx, sp = c.ny, c.nx, sp_file
        img = w.be.image_widget
        vb = w.be.vb
        from PySide6 import QtCore

        def first_image():
            return True

        def draw(pts):
            w.slit = V.np.asarray(pts)
            w.slit_path = V.slit_path(w.slit)
            w._slit_line.setData(w.slit_path[:, 0], w.slit_path[:, 1])
            w.slitChanged.emit()

        def start(p0):
            w.set_slit_mode(True)
            w._slit_add(QtCore.QPointF(*p0))

        def clear():
            w.set_slit_mode(False)
            w.clear_slit()

        def complete():
            if w._slit_pix is None:
                return False
            if sp is not None:
                pix = zip(w._slit_pix[0].tolist(), w._slit_pix[1].tolist(), strict=True)
                return not w._slitc_busy and all(p in w._slitc_blocks for p in pix)
            return ("ts", w._s(), w._l()) in w._slit_bands and ("sl", w._s(), w._t()) in w._slit_bands

        def npath():
            return 0 if w._slit_pix is None else len(w._slit_pix[0])
        ts_item = w.slit_ts_img
    else:
        from explorer.data import dataset as D
        from explorer.ui.app import start as start_app

        st = start_app(a.cube, look="classic", saved_layout=False, no_sp=a.no_sp)
        app, w = st.app, st.shell
        w.resize(1400, 900)
        D.read_slit_blocks = timed(D.read_slit_blocks, "blocks")    # Dataset.slit_blocks's
        D.read_slit_bands = timed(D.read_slit_bands, "bands")       # Dataset.read_bands's
        ds = w.dataset
        ny, nx, sp = ds.ny, ds.nx, ds.pixel
        img, vb = w.view.widget, w.view.vb
        sr = w.scheduler.slit

        def first_image():
            return w.first_image_s is not None

        def draw(pts):
            w.session.set_path(pts)

        def start(p0):
            w.set_slit_mode(True)
            w.slit_tool.add(*p0)

        def clear():
            w.set_slit_mode(False)
            w.clear_slit()

        def complete():
            if sr.pix is None or w.scheduler.in_flight():
                return False
            if sp is not None:
                pix = zip(sr.pix[0].tolist(), sr.pix[1].tolist(), strict=True)
                return not sr._busy and all(p in sr.blocks for p in pix)
            s_ = w.session.state
            return ((sr.path_id, "ts", s_.s, s_.l) in sr._bands and (sr.path_id, "sl", s_.s, s_.t) in sr._bands)

        def npath():
            return 0 if sr.pix is None else len(sr.pix[0])
        ts_item = w.slit_panel.ts_img

    def counters():
        if a.which == "proto":
            return {}
        from explorer.obs import summary

        return {k: v for k, v in summary().get("counters", {}).items() if k.startswith("core.slit.")}

    from PySide6 import QtCore, QtGui, QtWidgets

    def spin(until, timeout=60.0):
        end = time.perf_counter() + timeout
        while not until() and time.perf_counter() < end:
            app.processEvents()
        return until()

    painted = [0]
    orig_set = ts_item.setImage

    def counted(*x, **k):
        painted[0] += 1
        return orig_set(*x, **k)
    ts_item.setImage = counted

    def move(x, y):
        """A mouse move over the image's viewport at data point (x, y), as the platform delivers it."""
        vp = img.viewport()
        p = QtCore.QPointF(img.mapFromScene(vb.mapViewToScene(QtCore.QPointF(x, y))))
        ev = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, p, vp.mapToGlobal(p), QtCore.Qt.MouseButton.NoButton,
                               QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(vp, ev)

    spin(first_image)
    for _ in range(100):
        app.processEvents()
        time.sleep(0.01)
    res = dict(program=a.which, host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
               cube=os.path.basename(a.cube), per_pixel=sp is not None, seed=a.seed, half=a.half, length=a.length,
               load_before=os.getloadavg(), cpus=sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity")
               else None, slits=[])
    for k, pts in enumerate(shapes(a.seed, a.slits, a.length, ny, nx, a.half)):
        row: dict = dict(k=k, points=pts)
        # finished
        io.clear()
        q = time.perf_counter()
        draw(pts)
        ok = spin(complete)
        app.processEvents()
        row["finished"] = dict(ok=ok, npath=npath(), total_ms=round((time.perf_counter() - q) * 1e3, 1),
                               io_ms=round(sum(m for _k, m in io), 1), reads=len(io))
        clear()
        spin(lambda: False, 0.3)
        # live: the first point, then the pointer along the slit to its far end
        lpts = [(pts[0][0] + 7, pts[0][1] + 7), (pts[2][0] + 7, pts[2][1] + 7)]     # pixels the first case did not read
        io.clear()
        start(lpts[0])
        app.processEvents()
        painted[0] = 0
        c0 = counters()
        t0 = time.perf_counter()
        for j in range(1, a.moves + 1):
            f = j / a.moves
            move(lpts[0][0] + f * (lpts[1][0] - lpts[0][0]), lpts[0][1] + f * (lpts[1][1] - lpts[0][1]))
            spin(lambda: False, max(0.0, t0 + j * MOVE_S - time.perf_counter()))
        motion = time.perf_counter() - t0
        during = painted[0]
        c1 = counters()
        q = time.perf_counter()
        ok = spin(complete)
        app.processEvents()
        reads = [m for _k, m in io]
        row["live"] = dict(ok=ok, npath=npath(), moves=a.moves, motion_s=round(motion, 2), updates=during,
                           reads=len(reads), read_median_ms=round(statistics.median(reads), 1) if reads else None,
                           read_max_ms=round(max(reads), 1) if reads else None,
                           settle_ms=round((time.perf_counter() - q) * 1e3, 1),
                           counters={k: v - c0.get(k, 0) for k, v in c1.items() if v != c0.get(k, 0)} or None)
        clear()
        spin(lambda: False, 0.3)
        res["slits"].append(row)
        f_, l_ = row["finished"], row["live"]
        print(f"{a.which} slit {k}: {f_['npath']} px, finished {f_['total_ms']} ms (I/O {f_['io_ms']} ms in "
              f"{f_['reads']} reads); live {l_['updates']} updates in {l_['motion_s']} s, reads median "
              f"{l_['read_median_ms']} ms, complete {l_['settle_ms']} ms after the last move", flush=True)
    res["load_after"] = os.getloadavg()
    json.dump(res, open(a.out, "w"), indent=1)
    app.quit()


# ---------------------------------------------------------------------------------------------------- ABBA
def run_abba(a):
    os.makedirs(a.out, exist_ok=True)
    progs = {"proto": a.proto_python, "explorer": sys.executable}
    rows = []
    for r in range(a.rounds):
        order = ["proto", "explorer"] if r % 2 == 0 else ["explorer", "proto"]
        seed = a.seed * 1000 + r
        for k, which in enumerate(order):
            half = (k + r // 2) % 2
            out = os.path.join(a.out, f"r{r}_{which}.json")
            cmd = [progs[which], os.path.abspath(__file__), which, a.cube, out, "--seed", str(seed), "--half",
                   str(half), "--slits", str(a.slits), "--length", str(a.length), "--moves", str(a.moves),
                   "--prototype", a.prototype] + (["--no-sp"] if a.no_sp else [])
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
            env.pop("DISPLAY", None)
            if which == "proto":
                env.pop("PYTHONPATH", None)
            print(f"round {r + 1}: {which} (half {half})", flush=True)
            subprocess.run(cmd, env=env, check=True)
            rows.append(json.load(open(out)))
    summary: dict = dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
                         cube=os.path.basename(a.cube), rounds=a.rounds, no_sp=a.no_sp, programs={})
    for which in ("proto", "explorer"):
        mine = [s for x in rows if x["program"] == which for s in x["slits"]]

        def med(case, key, mine=mine):
            v = [s[case][key] for s in mine if s[case].get(key) is not None]
            return round(statistics.median(v), 1) if v else None
        summary["programs"][which] = dict(
            slits=len(mine), npath=med("finished", "npath"), finished_total_ms=med("finished", "total_ms"),
            finished_io_ms=med("finished", "io_ms"), io_ms_range=[min(s["finished"]["io_ms"] for s in mine),
                                                                  max(s["finished"]["io_ms"] for s in mine)],
            live_updates=med("live", "updates"), live_read_median_ms=med("live", "read_median_ms"),
            live_settle_ms=med("live", "settle_ms"), all_ok=all(s["finished"]["ok"] and s["live"]["ok"] for s in mine),
            load=[x["load_before"][0] for x in rows if x["program"] == which])
    json.dump(summary, open(os.path.join(a.out, "summary.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    a = args()
    run_abba(a) if a.which == "abba" else run_one(a)
