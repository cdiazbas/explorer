"""explorer's self-test, with the prototype's procedure (its app/selftest.py) so the two compare (ROADMAP E3.7, E6).

    python bench/explorer_selftest.py <cube_im.fits> [--nosp] [--out r.json] [--wait-x] [--bridge-impl explorer]

The display is the caller's: QT_QPA_PLATFORM=offscreen; xcb with DISPLAY and XAUTHORITY of a private Xvfb; or the
X11 bridge on that Xvfb (EXPLORER_X11=bridge).
- open_to_first_frame_s: from after the application exists to the first image on screen (as the prototype's t0);
- step in t / step in lambda: 10 steps each (wrapping), each timed until the new image is on screen;
- change Stokes: 2 x ns changes, the same way.
What the prototype's steps also did and explorer does not draw yet: the spectra (ROADMAP E4); its cursor numbers
include drawing spectra and lambda-t, so the cursor is left out here until then.

Through the bridge it also records every update the bridge's sender finished (bridge_log: [time, bytes]) and every
step asked (marks: [time, axis]), from which phase_traffic() gives the bytes per step of each phase; and first_x_s,
the first image handed to X (the bridge idle after it). --wait-x: each step also waits until the bridge has sent it
("... on X"), so the next one never overlaps it; only for comparing bridges, as the prototype's steps do not wait.
--bridge-impl prototype: the prototype's app/xbridge.py (from EXPLORER_PROTOTYPE, read-only: no bytecode, numba's
cache elsewhere) under explorer's window, to compare the two bridges and nothing else.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


class FrameLog(dict):
    """A bridge's stats dict that notes when each update's bytes were counted (by the sender thread, at its end)."""

    def __init__(self, d):
        super().__init__(d)
        self.log: list = []

    def __setitem__(self, k, v):
        if k == "bytes":
            self.log.append((time.perf_counter(), v - self.get("bytes", 0)))
        super().__setitem__(k, v)


def phase_traffic(log, marks, lag_s=0.3):
    """Per phase (a run of steps of one axis: the first 10 in t, 10 in lambda, 2 ns in Stokes, in the self-tests'
    order), the updates with bytes that finished between its first step and the next step after it (the prototype's
    playback follows its Stokes changes), or lag_s after its last step when none follows:
    {axis: dict(steps, updates, bytes, bytes_per_step, bytes_per_update)}. An update finishing just after the next
    phase started is counted there: about one update per boundary, alike for both programs."""
    out, i = {}, 0
    phases = []
    while i < len(marks):
        a, j = marks[i][1], i
        while j < len(marks) and marks[j][1] == a:
            j += 1
        if a in (p[0] for p in phases):                 # playback and stress after the steps: not phases
            break
        phases.append((a, i, j))
        i = j
    for a, i, j in phases:
        t0 = marks[i][0]
        t1 = marks[j][0] if j < len(marks) else marks[j - 1][0] + lag_s
        got = [b for t, b in log if t0 <= t < t1 and b > 0]
        out[a] = dict(steps=j - i, updates=len(got), bytes=int(sum(got)), bytes_per_step=int(sum(got) / (j - i)),
                      bytes_per_update=int(sum(got) / max(1, len(got))))
    return out


def prototype_bridge_display(plan, proto):
    """The prototype's XBridge as an explorer Display (bench only)."""
    from explorer.platform.display import Display, WindowOps

    class PrototypeBridge(Display):
        def prepare_env(self, env=None):
            from explorer.data._numba import numba  # its cache directory: the user's, or NUMBA_CACHE_DIR

            if not numba.config.CACHE_DIR:              # numba would write its cache next to the prototype's code
                sys.exit("numba's cache directory is not set: refusing to import the prototype's bridge")
            sys.dont_write_bytecode = True
            sys.path.insert(0, os.path.join(proto, "app"))
            import xbridge  # the prototype's app/xbridge.py

            self.bridge = xbridge.XBridge()
            os.environ["QT_QPA_PLATFORM"] = self.bridge.qpa()

        def make_app(self, argv=None):
            app = super().make_app(argv)
            self.bridge.sync_cursor()
            return app

        def attach(self, app, window):
            window.show()
            self.bridge.attach(app, window)
            return WindowOps(window, self)

    return PrototypeBridge(plan)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cube")
    ap.add_argument("--nosp", action="store_true")
    ap.add_argument("--panel", default="772x803", help="the image panel's size: the prototype's at 1400x900 (its "
                    "panels share the window; explorer's image had it all, twice the pixels to draw per step)")
    ap.add_argument("--wait-x", action="store_true", help="bridge: each step also waits until it is sent to X")
    ap.add_argument("--bridge-impl", choices=("explorer", "prototype"), default="explorer")
    ap.add_argument("--out")
    a = ap.parse_args()
    from explorer.data.dataset import Dataset
    from explorer.platform import xbridge
    from explorer.platform.display import for_plan
    from explorer.platform.plan import choose_display
    from explorer.ui.shell import Shell

    plan = choose_display(os.environ, sys.platform, bridge_available=xbridge.available())
    if a.bridge_impl == "prototype":
        proto = os.path.abspath(os.environ.get("EXPLORER_PROTOTYPE", os.path.join(HERE, "..", "..", "prototype")))
        disp = prototype_bridge_display(plan, proto)
    else:
        disp = for_plan(plan)
    disp.prepare_env()
    b = getattr(disp, "bridge", None)
    holder = getattr(b, "transport", b)                 # where the bridge keeps its stats
    if holder is not None:
        holder.stats = FrameLog(holder.stats)
    app = disp.make_app()
    t0 = time.perf_counter()
    ds = Dataset.open(a.cube, no_sp=a.nosp)
    w = Shell(ds, t0=t0)
    w.resize(1400, 900)                                 # the prototype's self-test size
    if a.panel:
        w.view.widget.setFixedSize(*(int(v) for v in a.panel.split("x")))
    disp.attach(app, w)

    def spin(until, timeout=30.0):
        end = time.perf_counter() + timeout
        while not until() and time.perf_counter() < end:
            app.processEvents()
        return until()

    def sent_to_x(since):
        """Time the bridge finished its last update with bytes, once it is idle and has taken what Qt painted
        after `since` (two ticks)."""
        def idle():
            return (time.perf_counter() > since + 0.01 and b.inflight == 0
                    and all(r["dirty"].isEmpty() for r in b.wins.values()))
        spin(idle, 10.0)
        got = [t for t, n in holder.stats.log if n > 0]
        return got[-1] if got else float("nan")

    spin(lambda: w.first_image_s is not None)
    first_x = None
    if b is not None:
        first_x = sent_to_x(t0 + (w.first_image_s or 0)) - t0
    for _ in range(10):
        app.processEvents()
    res = dict(cube=os.path.basename(a.cube), shape=list(ds.shape), sp=ds.pixel.kind if ds.pixel else None,
               panel=[w.view.widget.width(), w.view.widget.height()],
               platform=app.platformName(), x11_bridge=a.bridge_impl if b is not None else None,
               display=os.environ.get("DISPLAY") if app.platformName() == "xcb" or b is not None else None,
               probe=ds.probe.describe(), open_to_first_frame_s=round(float(w.first_image_s or np.nan), 2),
               actions={})
    if first_x is not None:
        res["first_x_s"] = round(first_x, 3)
    marks: list = []

    def rec(name, ts):
        ts = np.asarray(ts) * 1e3
        d = dict(median=round(float(np.median(ts)), 2), p95=round(float(np.percentile(ts, 95)), 2), n=len(ts))
        res["actions"][name] = d
        print(f"  {name:34s} median {d['median']:8.2f} ms   p95 {d['p95']:8.2f} ms   n={d['n']}", flush=True)

    def step(axis, n):
        ts, tx = [], []
        for _ in range(n):
            q = time.perf_counter()
            marks.append((q, axis))
            w.session.step(axis, 1, wrap=True)
            want = w.session.index()
            spin(lambda want=want: w.scheduler.img_idx == want)
            app.processEvents()                         # painted, as the prototype's settle()
            ts.append(time.perf_counter() - q)
            if a.wait_x and b is not None:
                tx.append(sent_to_x(time.perf_counter()) - q)
        return ts, tx

    print(f"{res['cube']} {res['shape']} sp={res['sp']} platform={res['platform']} bridge={res['x11_bridge']} "
          f"display={res['display']}\n  {res['probe']}\n  open to first frame {res['open_to_first_frame_s']} s"
          + (f", sent to X {res['first_x_s']} s" if first_x is not None else ""), flush=True)
    r = ds.roles
    for name, axis, n, ok in (("step in t", "t", 10, r.t is not None and r.nt > 1),
                              ("step in λ", "l", 10, r.l is not None and r.nl > 1),
                              ("change Stokes", "s", 2 * r.ns, r.s is not None and r.ns > 1)):
        if ok:
            ts, tx = step(axis, n)
            rec(name, ts)
            if tx:
                rec(name + " on X", tx)
    if b is not None:
        spin(lambda: b.inflight == 0, 5.0)
        res["bridge_log"] = [[round(t, 5), n] for t, n in holder.stats.log]
        res["marks"] = [[round(t, 5), ax] for t, ax in marks]
        res["bridge_phases"] = phase_traffic(holder.stats.log, marks)
        res["xbridge"] = b.summary()
        for ax, d in res["bridge_phases"].items():
            print(f"  X11 bridge, {ax} steps: {d['updates']} updates, {d['bytes_per_step'] / 1e3:.0f} kB per step, "
                  f"{d['bytes_per_update'] / 1e3:.0f} kB per update", flush=True)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
    w.close()
    ds.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
