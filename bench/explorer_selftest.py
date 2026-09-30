"""explorer's self-test, with the prototype's procedure (its app/selftest.py) so the two compare (ROADMAP E3.7).

    python bench/explorer_selftest.py <cube_im.fits> [--nosp] [--out r.json]

The display is the caller's: QT_QPA_PLATFORM=offscreen, or xcb with DISPLAY and XAUTHORITY of a private Xvfb.
- open_to_first_frame_s: from after the application exists to the first image on screen (as the prototype's t0);
- the cursor phase before the steps, as the prototype's (app/selftest.py:58-103): 30 positions from
  default_rng(1) in [50, n-50), at least 40 px apart, each waiting for lambda-t without a per-pixel file; 30 moves
  over padding; a burst of 50 moves in one pass. Stepping right after opening instead (the y-range sample still
  reading) made the steps without a per-pixel file look 1.4-2.9x slower (ROADMAP E3.8);
- step in t / step in lambda: 10 steps each (wrapping), each timed until the new image is on screen;
- change Stokes: 2 x ns changes, the same way.
What the prototype's cursor and steps also do and explorer does not draw yet: the spectra and lambda-t (ROADMAP E4);
explorer reads them but only keeps them, so its cursor numbers are not comparable until then.
"""
import argparse
import json
import os
import sys
import time

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cube")
    ap.add_argument("--nosp", action="store_true")
    ap.add_argument("--panel", default="772x803", help="the image panel's size: the prototype's at 1400x900 (its "
                    "panels share the window; explorer's image had it all, twice the pixels to draw per step)")
    ap.add_argument("--out")
    a = ap.parse_args()
    from explorer.data.dataset import Dataset
    from explorer.platform.display import Display
    from explorer.platform.plan import choose_display
    from explorer.ui.shell import Shell

    disp = Display(choose_display(os.environ, sys.platform))
    disp.prepare_env()
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

    spin(lambda: w.first_image_s is not None)
    for _ in range(10):
        app.processEvents()
    res = dict(cube=os.path.basename(a.cube), shape=list(ds.shape), sp=ds.pixel.kind if ds.pixel else None,
               panel=[w.view.widget.width(), w.view.widget.height()],
               platform=app.platformName(), display=os.environ.get("DISPLAY") if app.platformName() == "xcb" else None,
               probe=ds.probe.describe(), open_to_first_frame_s=round(float(w.first_image_s or np.nan), 2), actions={})

    def rec(name, ts):
        ts = np.asarray(ts) * 1e3
        d = dict(median=round(float(np.median(ts)), 2), p95=round(float(np.percentile(ts, 95)), 2), n=len(ts))
        res["actions"][name] = d
        print(f"  {name:34s} median {d['median']:8.2f} ms   p95 {d['p95']:8.2f} ms   n={d['n']}", flush=True)

    def step(axis, n):
        ts = []
        for _ in range(n):
            q = time.perf_counter()
            w.session.step(axis, 1, wrap=True)
            want = w.session.index()
            spin(lambda want=want: w.scheduler.img_idx == want)
            app.processEvents()                         # painted, as the prototype's settle()
            ts.append(time.perf_counter() - q)
        return ts

    print(f"{res['cube']} {res['shape']} sp={res['sp']} platform={res['platform']} display={res['display']}"
          f"\n  {res['probe']}\n  open to first frame {res['open_to_first_frame_s']} s", flush=True)
    # the prototype's cursor phase (app/selftest.py:58-103), before its steps: the same state when stepping
    rng = np.random.default_rng(1)
    my, mx = min(50, ds.ny // 4), min(50, ds.nx // 4)   # the prototype's 50 px; less only on a small (synthetic) cube
    ts_c, lt_lat, prev = [], [], None
    for _ in range(30):
        while True:
            y, x = int(rng.integers(my, ds.ny - my)), int(rng.integers(mx, ds.nx - mx))
            if prev is None or abs(y - prev[0]) + abs(x - prev[1]) > min(40, (ds.ny + ds.nx) // 8):
                break
        prev = (y, x)
        q = time.perf_counter()
        w.session.hover(y, x)
        app.processEvents()
        app.processEvents()
        ts_c.append(time.perf_counter() - q)
        if ds.pixel is None:                            # lambda-t arrives from the reader
            end = time.perf_counter() + 5
            while (w.last.get("lambda_t") or (None, None))[1] != (y, x) and time.perf_counter() < end:
                app.processEvents()
                time.sleep(0.001)
            if (w.last.get("lambda_t") or (None, None))[1] == (y, x):
                lt_lat.append(time.perf_counter() - q)
    rec("cursor (no drawing of the panels yet)", ts_c)
    if lt_lat:
        rec("cursor: lambda-t arrived (no sp)", lt_lat)
    img = w.scheduler.img
    st = w.session.state
    pad = np.argwhere(~np.isfinite(img) | ((img == 0) & (st.s == 0)))
    if len(pad):
        ts_p = []
        for k in rng.choice(len(pad), size=min(30, len(pad)), replace=False):
            y, x = (int(c) for c in pad[k])
            q = time.perf_counter()
            w.session.hover(y, x)
            app.processEvents()
            app.processEvents()
            ts_p.append(time.perf_counter() - q)
        rec("cursor over padding", ts_p)
    q = time.perf_counter()
    for _ in range(50):
        w.session.hover(int(rng.integers(0, ds.ny)), int(rng.integers(0, ds.nx)))
    app.processEvents()
    app.processEvents()
    rec("burst of 50 moves, coalesced", [time.perf_counter() - q])
    r = ds.roles
    if r.t is not None and r.nt > 1:
        rec("step in t", step("t", 10))
    if r.l is not None and r.nl > 1:
        rec("step in λ", step("l", 10))
    if r.s is not None and r.ns > 1:
        rec("change Stokes", step("s", 2 * r.ns))
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
    w.close()
    ds.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
