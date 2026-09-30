"""explorer's self-test, with the prototype's procedure (its app/selftest.py) so the two compare (ROADMAP E3.7).

    python bench/explorer_selftest.py <cube_im.fits> [--nosp] [--out r.json]

The display is the caller's: QT_QPA_PLATFORM=offscreen, or xcb with DISPLAY and XAUTHORITY of a private Xvfb, or
EXPLORER_X11=bridge2 (the rewritten X11 bridge) with that DISPLAY; then its traffic is recorded too ("bridge2").
Under a bridge the times are until Qt has the image, as the prototype's self-test measures; what reaches the X
server is measured by bench/bridge_vs_prototype.py.
- open_to_first_frame_s: from after the application exists to the first image on screen (as the prototype's t0);
- step in t / step in lambda: 10 steps each (wrapping), each timed until the new image is on screen;
- change Stokes: 2 x ns changes, the same way.
What the prototype's steps also did and explorer does not draw yet: the spectra (ROADMAP E4); its cursor numbers
include drawing spectra and lambda-t, so the cursor is left out here until then.
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
    ap.add_argument("--out")
    a = ap.parse_args()
    from explorer.data.dataset import Dataset
    from explorer.platform.display import for_plan
    from explorer.platform.plan import choose_display
    from explorer.ui.shell import Shell

    disp = for_plan(choose_display(os.environ, sys.platform))
    disp.prepare_env()
    app = disp.make_app()
    t0 = time.perf_counter()
    ds = Dataset.open(a.cube, no_sp=a.nosp)
    w = Shell(ds, t0=t0)
    w.resize(1400, 900)                                 # the prototype's self-test size
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
               platform=app.platformName(), bridge=disp.plan.variant,
               display=os.environ.get("DISPLAY") if app.platformName() == "xcb" or disp.plan.bridge else None,
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
    r = ds.roles
    if r.t is not None and r.nt > 1:
        rec("step in t", step("t", 10))
    if r.l is not None and r.nl > 1:
        rec("step in λ", step("l", 10))
    if r.s is not None and r.ns > 1:
        rec("change Stokes", step("s", 2 * r.ns))
    bridge = getattr(disp, "bridge", None)
    if bridge is not None:
        spin(lambda: not bridge.transport.busy, 10.0)
        res["bridge2"] = bridge.summary()
        print(f"  {bridge.describe()}", flush=True)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
    w.close()
    ds.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
