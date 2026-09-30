"""What explorer.core adds on top of the reads (ROADMAP E2.7): a cursor move and a step in t through the core
(testing.Driver: state, notice, scheduler, levels, y ranges, the sink) against the same reads made directly on the
Dataset. Run it pinned to one NUMA node on a machine with several (taskset; docs/measured.md).

    python bench/core_overhead.py <cube_im.fits> [--nosp] [--rounds 8] [--per-round 10] [--out F]

Cases, alternating which goes first in each round (ABBA):
- cursor: a move to a pixel on a row not read yet ("first") until its spectra and lambda-t are in the sink, then to
  the pixel next to it ("warm": in the per-pixel strip or the row block explorer keeps), against Dataset.pixel_block
  (or, without a per-pixel file, read_series of the spectrum then of the lambda-t);
- step: t + 1 until the image, its levels and the spectra at the new t are in the sink, against the same reads on the
  Dataset (the image, then the spectrum at the cursor); the core reads frames ahead, so both images come from the
  frame cache: the difference is the layers' cost, not the reads'.
The difference of the medians is the cost of the layers; the prototype's cursor (6-15 ms) and step in t (15-17 ms)
on bellatrix are the budget it is judged against (docs/journal.md, E0.8).
"""
import argparse
import json
import os
import socket
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cube")
    ap.add_argument("--nosp", action="store_true")
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--per-round", type=int, default=10)
    ap.add_argument("--out")
    a = ap.parse_args()
    from explorer.testing.driver import Driver

    drv = Driver.open(a.cube, no_sp=a.nosp)
    ds, r = drv.dataset, drv.dataset.roles
    rng = np.random.default_rng(int(time.time()))
    used = set()
    res = dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
               cube=os.path.basename(a.cube), describe=ds.describe(), nosp=a.nosp, load=os.getloadavg(), cases={})

    def fresh_pixel():
        for _ in range(100_000):                        # a row no one has read in this process
            y = int(rng.integers(ds.ny // 8, ds.ny * 7 // 8))
            if not used & {y - 1, y, y + 1}:
                used.add(y)
                img = drv.shown.image
                strip = getattr(ds.probe, "strip", 1)
                x = int(rng.integers(ds.nx // 4, ds.nx * 3 // 4)) // strip * strip   # x + 1: in the same strip
                if img is None or np.isfinite(img[y, x]):
                    return y, x
        raise RuntimeError(f"no fresh rows left in {ds.ny}: fewer rounds or per-round reads")

    def core_cursor(p):
        q = time.perf_counter()
        drv.hover(*p)
        drv.wait_idle()
        return time.perf_counter() - q

    def direct_cursor(p):
        idx = drv.index()
        q = time.perf_counter()
        if ds.pixel is not None:
            ds.pixel_block(*p).result()
        else:
            spec_axes = sorted(ax for ax in (r.s, r.l) if ax is not None)
            ds.executors.numba.submit(ds.read_series, *p, idx, spec_axes).result()
            ds.executors.numba.submit(ds.read_series, *p, idx, sorted((r.t, r.l))).result()
        return time.perf_counter() - q

    def core_step(_):
        q = time.perf_counter()
        drv.step("t", 1, wrap=True)
        drv.wait_idle()
        return time.perf_counter() - q

    def direct_step(_):
        st = drv.state()
        idx = list(drv.index())
        idx[r.t] = (st.t + 1) % r.nt
        drv.set_index("t", idx[r.t])                    # keep the Driver's t in step, without timing its work
        y, x = st.cursor
        q = time.perf_counter()
        ds.image(tuple(idx)).result()                   # the image, and the spectrum at the new t, as the core
        if ds.pixel is not None:
            ds.pixel_block(y, x).result()
        else:
            spec_axes = sorted(ax for ax in (r.s, r.l) if ax is not None)
            ds.executors.numba.submit(ds.read_series, y, x, tuple(idx), spec_axes).result()
        dt = time.perf_counter() - q
        drv.wait_idle()
        return dt

    cases = {"cursor": (core_cursor, direct_cursor, fresh_pixel), "step": (core_step, direct_step, lambda: None)}
    for name, (core, direct, draw) in cases.items():
        rows = []
        for rd in range(a.rounds):
            order = [("core", core), ("direct", direct)] if rd % 2 == 0 else [("direct", direct), ("core", core)]
            row = {"order": [o[0] for o in order]}
            for label, fn in order:
                first, warm = [], []
                for _ in range(a.per_round):
                    p = draw()
                    first.append(fn(p))
                    warm.append(fn((p[0], p[1] + 1)) if name == "cursor" else 0.0)     # the next pixel: cached
                row[label] = round(statistics.median(first) * 1e3, 3)
                if name == "cursor":
                    row[label + "_warm"] = round(statistics.median(warm) * 1e3, 4)
            rows.append(row)
        keys = [k for k in rows[0] if k != "order"]
        med = {k: round(statistics.median(x[k] for x in rows), 4) for k in keys}
        res["cases"][name] = dict(rounds=rows, median=med)
        print(f"{name}: " + ", ".join(f"{k} {v} ms" for k, v in med.items())
              + f"; core - direct: {med['core'] - med['direct']:+.3f} ms first"
              + (f", {med['core_warm'] - med['direct_warm']:+.4f} ms warm" if name == "cursor" else ""), flush=True)
    res["counters"] = __import__("explorer.obs", fromlist=["summary"]).summary().get("counters", {})
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
    drv.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
