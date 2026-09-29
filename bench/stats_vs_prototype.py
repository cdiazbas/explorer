"""Statistics and kernels: explorer.data.stats and kernels against the prototype's app/viewer.py, same process, ABBA
rounds (ROADMAP E1.8).

    python bench/stats_vs_prototype.py <cube_im.fits> [--prototype DIR] [--rounds 4] [--threads 64] [--out F]

Three cases, each result compared between the two implementations:
- reduce: a whole frame to u8 in row strips (pgr's reduction as the app patches it), f = 1 and f = 2, CPU only;
- quv: Q U V ranges from the whole frames at one t; first touch at a t each implementation reads alone (shared
  caches are not evicted, so the ABBA order is what makes it fair), then warm at the same t;
- sample: 100 random profiles, from the per-pixel file when there is one and from the image cube; fresh pixels for
  each implementation and round, run on one thread that owns numba's threads, as both apps do.
"""
import argparse
import json
import os
import socket
import statistics
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("NUMBA_CACHE_DIR", tempfile.mkdtemp(prefix="bench_numba_"))   # never inside the prototype
os.environ.pop("DISPLAY", None)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402


def med_ms(ts):
    return round(statistics.median(ts) * 1e3, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cube")
    ap.add_argument("--prototype", default=os.path.join(ROOT, "..", "prototype"))
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--reps", type=int, default=20, help="reductions per implementation and round")
    ap.add_argument("--threads", type=int, default=64)
    ap.add_argument("--skip", default="", help="comma-separated cases to leave out")
    ap.add_argument("--out")
    a = ap.parse_args()
    proto_dir = os.path.abspath(a.prototype)
    sys.path[:0] = [os.path.join(proto_dir, "app"), os.path.join(proto_dir, "viewer")]
    from concurrent.futures import ThreadPoolExecutor

    import numba
    import viewer as V  # the prototype's app/viewer.py
    from cube import Cube
    from sources import SpFits

    from explorer.data import axes, formats, kernels, stats
    from explorer.data.executors import Executors
    from explorer.data.io import FrameReader
    from explorer.data.pixel import open_pixel

    skip = set(filter(None, a.skip.split(",")))
    lay = formats.open_layout(a.cube)
    roles = axes.roles(lay.axes, lay.shape)
    cont = axes.from_fits(a.cube).cont
    proto = Cube.from_fits(a.cube, cache_bytes=0)
    fr = FrameReader(lay)
    ex = Executors(gather_threads=a.threads)
    proto_bg = ThreadPoolExecutor(1)                              # the prototype's _bg, numba threads set on it
    proto_bg.submit(numba.set_num_threads, min(a.threads, numba.config.NUMBA_NUM_THREADS)).result()
    rng = np.random.default_rng(int(time.time()))
    res = dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
               cube=os.path.basename(a.cube), shape=list(lay.shape), threads=ex.numba_threads,
               strips=V._STRIPS, load=os.getloadavg(), cases={})
    mism = {}

    def rounds(name, run, n=a.rounds):
        """run(impl, round) -> {measure: seconds}; ABBA order, medians per round and over rounds."""
        rows = []
        for r in range(n):
            order = ["prototype", "explorer"] if r % 2 == 0 else ["explorer", "prototype"]
            row = dict(order=order)
            for impl in order:
                row[impl] = run(impl, r)
            rows.append(row)
            print(f"  {name} round {r + 1} ({order[0]} first): " + "   ".join(
                f"{i}: " + ", ".join(f"{k} {v:.1f} ms" for k, v in row[i].items()) for i in ("prototype", "explorer")),
                flush=True)
        keys = rows[0]["prototype"].keys()
        res["cases"][name] = dict(rounds=rows, median={i: {k: round(statistics.median(r[i][k] for r in rows), 2)
                                                           for k in keys} for i in ("prototype", "explorer")})
        print(f"{name}: median over rounds {res['cases'][name]['median']}; differing results: {mism.get(name, 0)}")

    # ---- reduce
    if "reduce" not in skip:
        idx = [0] * len(lay.shape[:-2])
        img = fr.read(tuple(idx))
        lo, hi = stats.limits(img)
        ny, nx = img.shape

        def reduce_run(impl, r):
            out = {}
            for f in (1, 2):
                o = np.empty((ny // f, nx // f), np.uint8)
                ts = []
                for _ in range(a.reps):
                    q = time.perf_counter()
                    if impl == "prototype":
                        V._reduce_u8_strips(img, 0, 0, f, lo, hi, o)
                    else:
                        kernels.reduce_u8(img, 0, 0, f, lo, hi, o, ex.strips, V._STRIPS)
                    ts.append(time.perf_counter() - q)
                ref = np.empty_like(o)
                V._reduce_u8_serial(img, 0, 0, f, lo, hi, ref)
                mism["reduce"] = mism.get("reduce", 0) + int(not np.array_equal(o, ref))
                out[f"f{f}"] = med_ms(ts)
            return out

        rounds("reduce", reduce_run)

    # ---- Q U V ranges from whole frames
    if "quv" not in skip and roles.s is not None and roles.ns > 1:
        thr = stats.quv_threads(fr.frame_bytes, ex.numba_threads)
        res["quv_threads"] = thr
        ts_free = list(rng.permutation(roles.nt))                  # a t per implementation and round; cycles if
        used = [0]                                                 # the cube has fewer (then not a first touch)

        def quv(impl, t):
            if impl == "prototype":
                return V.quv_amplitude_ranges(proto, roles.t, roles.s, roles.l, cont, t, roles.ns, roles.nl,
                                              threads=thr)
            return ex.background.submit(stats.quv_amplitude_ranges, fr, roles, cont, t, threads=thr,
                                        strips=ex.strips, parts=V._STRIPS).result()

        def quv_run(impl, r):
            t = int(ts_free[used[0] % len(ts_free)])
            used[0] += 1
            q = time.perf_counter()
            h = quv(impl, t)
            first = time.perf_counter() - q
            q = time.perf_counter()
            quv(impl, t)
            warm = time.perf_counter() - q
            other = quv("explorer" if impl == "prototype" else "prototype", t)
            mism["quv"] = mism.get("quv", 0) + int(repr(h[:2]) != repr(other[:2]))
            return dict(first=first * 1e3, warm=warm * 1e3)

        rounds("quv", quv_run)

    # ---- the random profile sample
    if "sample" not in skip:
        img = fr.read(tuple(0 if i != roles.l else roles.nl // 2 for i in range(len(lay.shape[:-2]))))
        ours_sp = open_pixel(a.cube, fr)
        proto_sp = (SpFits(ours_sp.layout.path, (roles.ns, roles.nt, roles.nl))
                    if ours_sp is not None and ours_sp.kind == "sp.fits" else None)
        got = {}

        def proto_sample(ys, xs, ts, sp):
            fake = types.SimpleNamespace(sp=sp, cube=proto, ns=roles.ns, nl=roles.nl, ta=roles.t, sa=roles.s,
                                         la=roles.l, gather_threads=ex.numba_threads,
                                         _ysampled=types.SimpleNamespace(ready=types.SimpleNamespace(
                                             emit=lambda _r, payload: got.__setitem__("prof", payload[0]))))
            proto_bg.submit(V.Viewer._sample_job, fake, ys, xs, ts, time.perf_counter()).result()
            return got.pop("prof")

        def sample(impl, pix, sp_on):
            ys, xs, ts = pix
            if impl == "prototype":
                return proto_sample(ys, xs, ts, proto_sp if sp_on else None)
            return ex.numba.submit(stats.sample_profiles, ys, xs, ts, fr, roles, ours_sp if sp_on else None,
                                   ex.numba_threads).result()

        def sample_run_for(sp_on, key):
            def run(impl, r):
                pix = stats.sample_pixels(img, f"{rng.integers(1 << 30)}", roles.nt)     # fresh draw
                q = time.perf_counter()
                p = sample(impl, pix, sp_on)
                first = time.perf_counter() - q
                other = sample("explorer" if impl == "prototype" else "prototype", pix, sp_on)
                mism[key] = mism.get(key, 0) + int(not np.array_equal(p, other, equal_nan=True))
                return dict(first=first * 1e3)
            return run

        if proto_sp is not None:
            rounds("sample_sp", sample_run_for(True, "sample_sp"))
        rounds("sample_cube", sample_run_for(False, "sample_cube"))

    res["mismatches"] = mism
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
    ex.close()
    proto_bg.shutdown()
    fr.close()
    proto.close()
    return 1 if any(mism.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
