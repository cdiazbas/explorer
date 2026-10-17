"""What Q U V's noise levels cost (core.noise, the +-sigma trial of ui.spectra): a step in t and a cursor move with
them on and off, through the core (testing.Driver), and the parts of one sigma: its four frames' reads and the
computation. On and off are two Drivers over the same file, each with its own Dataset; the rounds alternate which goes
first (ABBA).

    python bench/noise_cost.py <cube_im.fits> [--nosp] [--rounds 6] [--per-round 8] [--out F]

- step: t + 1 until the image and the spectra at the new t are in the sink (spectra_ms), and with sigma on, until
  its sigma is too (sigma_ms). Each t's sigma is forgotten before its step, so that every step reads it, as the first
  visit of each t does; the frames of a t seen before come from the page cache, unless the cube is larger than memory;
- cursor: a move to another pixel until its spectra and lambda-t are in the sink, the t not changing (sigma is not
  asked for);
- parts: the four frames at (t, continuum) read without the frame cache (Dataset.read_frame on frames not cached),
  then data.stats.stokes_noise on them, and its robust variant (1.4826 MAD) with the difference between both.
The JSON has host, date, the load before and after, the cube and the Dataset's description.
"""
import argparse
import dataclasses
import json
import os
import socket
import statistics
import sys
import time

import numpy as np


def until(drv, cond, timeout=30.0):
    end = time.perf_counter() + timeout
    while not cond():
        if drv.pump() == 0:
            time.sleep(0.0002)
        if time.perf_counter() > end:
            raise TimeoutError("the sink did not get it")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cube")
    ap.add_argument("--nosp", action="store_true")
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--per-round", type=int, default=8)
    ap.add_argument("--out")
    ap.add_argument("--same", action="store_true", help="both Drivers without sigma: the difference between two "
                                                        "Drivers of the same code, the noise of the comparison")
    a = ap.parse_args()
    from explorer.data.stats import stokes_noise
    from explorer.testing.driver import Driver

    drivers = {"on": Driver.open(a.cube, noise=not a.same, no_sp=a.nosp), "off": Driver.open(a.cube, no_sp=a.nosp)}
    on = drivers["on"]
    ds, r = on.dataset, on.dataset.roles
    cont = ds.axes.cont
    if not a.same and (on.scheduler.noise is None or not on.scheduler.noise.applies):
        raise SystemExit(f"{a.cube}: no noise levels here (4 Stokes and a continuum tuning needed)")
    if cont is None:
        raise SystemExit(f"{a.cube}: no continuum tuning")
    res = dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
               cube=os.path.basename(a.cube), shape=list(ds.shape), describe=ds.describe(), nosp=a.nosp,
               load_before=os.getloadavg(), cases={})
    rng = np.random.default_rng(int(time.time()))
    seen: dict = {}                                     # (driver, kind) -> when the sink got it last

    def stamped(label, kind, fn):
        def call(*args):
            fn(*args)
            seen[label, kind] = time.perf_counter()
        return call

    for label, drv in drivers.items():                  # times taken in the sink, not after the pass that called it
        sink = drv.scheduler.sink
        for kind in ("image", "spectra", "lambda_t", "noise"):
            setattr(sink, kind, stamped(label, kind, getattr(sink, kind)))
        if drv.scheduler.noise is not None:             # it holds the sink's method from its start
            drv.scheduler.noise._show = sink.noise

    def step(label):
        drv = drivers[label]
        st = drv.state()
        t = (st.t + 1) % r.nt
        sigma = label == "on" and not a.same
        if sigma:
            drv.scheduler.noise.known.pop(t, None)
        q = time.perf_counter()
        drv.step("t", 1, wrap=True)
        until(drv, lambda: drv.shown.spectra_at is not None and drv.shown.spectra_at[1] == t
              and drv.shown.image_idx is not None and drv.shown.image_idx[r.t] == t)
        spec = max(seen[label, "spectra"], seen[label, "image"]) - q
        sig = None
        if sigma:
            until(drv, lambda: drv.shown.noise_t == t)
            sig = seen[label, "noise"] - q
        drv.wait_idle()
        return spec, sig

    def cursor(label):
        drv = drivers[label]
        img = drv.shown.image
        for _ in range(1000):
            y, x = int(rng.integers(ds.ny // 8, ds.ny * 7 // 8)), int(rng.integers(ds.nx // 8, ds.nx * 7 // 8))
            if (y, x) != drv.state().cursor and (img is None or np.isfinite(img[y, x])):
                break
        n = drv.shown.counts.get("lambda_t", 0)
        q = time.perf_counter()
        drv.hover(y, x)
        until(drv, lambda: drv.shown.spectra_at is not None and drv.shown.spectra_at[0] == (y, x)
              and drv.shown.counts.get("lambda_t", 0) > n)
        dt = max(seen[label, "spectra"], seen[label, "lambda_t"]) - q
        drv.wait_idle()
        return dt

    rows = {"step": [], "cursor": []}
    for rd in range(a.rounds):
        order = ["on", "off"] if rd % 2 == 0 else ["off", "on"]
        row_s, row_c = {"order": order}, {"order": order}
        for label in order:
            got = [step(label) for _ in range(a.per_round)]
            row_s[f"{label}_spectra"] = round(statistics.median(g[0] for g in got) * 1e3, 3)
            if label == "on" and not a.same:
                row_s["on_sigma"] = round(statistics.median(g[1] for g in got) * 1e3, 3)
            row_c[label] = round(statistics.median(cursor(label) for _ in range(a.per_round)) * 1e3, 3)
        rows["step"].append(row_s)
        rows["cursor"].append(row_c)
        print(f"round {rd}: step {row_s}; cursor {row_c}", flush=True)
    for name, rr in rows.items():
        keys = [k for k in rr[0] if k != "order"]
        res["cases"][name] = dict(rounds=rr, median={k: round(statistics.median(x[k] for x in rr), 3) for k in keys})
        print(f"{name}: " + ", ".join(f"{k} {v} ms" for k, v in res["cases"][name]["median"].items()), flush=True)

    # the parts of one sigma, on frames not in the cache
    reads, comp, robust, diff = [], [], [], []
    st = on.state()
    for t in range(min(r.nt, a.rounds * 2)):
        idx = [on.session.index_of(0, dataclasses.replace(st, t=t, s=s, l=cont)) for s in range(4)]
        ds.cache.set_budget(0)                          # nothing kept: every frame read
        q = time.perf_counter()
        fr = [ds.read_frame(i)[0] for i in idx]
        reads.append(time.perf_counter() - q)
        q = time.perf_counter()
        sd = stokes_noise(fr[0], {s: fr[s] for s in (1, 2, 3)})
        comp.append(time.perf_counter() - q)
        q = time.perf_counter()
        md = stokes_noise(fr[0], {s: fr[s] for s in (1, 2, 3)}, robust=True)
        robust.append(time.perf_counter() - q)
        diff.append({s: round(100 * (md[s] / sd[s] - 1), 2) for s in sd if s in md})
        print(f"t={t}: sigma std {sd}, MAD/std - 1 [%] {diff[-1]}", flush=True)
    res["cases"]["parts"] = dict(reads_ms=[round(v * 1e3, 3) for v in reads], std_ms=[round(v * 1e3, 3) for v in comp],
                                 mad_ms=[round(v * 1e3, 3) for v in robust], mad_vs_std_pct=diff,
                                 median=dict(reads=round(statistics.median(reads) * 1e3, 3),
                                             std=round(statistics.median(comp) * 1e3, 3),
                                             mad=round(statistics.median(robust) * 1e3, 3)))
    print("parts: " + ", ".join(f"{k} {v} ms" for k, v in res["cases"]["parts"]["median"].items()), flush=True)
    res["load_after"] = os.getloadavg()
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1)
    for d in drivers.values():
        d.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
