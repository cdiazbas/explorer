"""Pixel series (lambda-t of one Stokes, and everything at a pixel) read from the image cube: explorer's
FrameReader.series against the prototype's Cube.series, same process, ABBA rounds (ROADMAP E1.3).

    python bench/series_vs_prototype.py <cube_im.fits> [--prototype DIR] [--per-round 6] [--rounds 4]
                                        [--threads 64] [--out F]

Pixels are drawn at random; in the first-touch case each is read by one implementation only (shared caches are
not evicted, so the ABBA order is what makes the comparison fair); the warm case reads it again. Both use the
same numba thread count on the same thread, one parallel call at a time. Results are compared bit for bit.
"""
import argparse
import json
import os
import socket
import statistics
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("NUMBA_CACHE_DIR", tempfile.mkdtemp(prefix="bench_numba_"))   # never inside the prototype
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cube")
    ap.add_argument("--prototype", default=os.path.join(ROOT, "..", "prototype"))
    ap.add_argument("--per-round", type=int, default=6)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--threads", type=int, default=64)
    ap.add_argument("--out")
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(os.path.abspath(a.prototype), "viewer"))
    import numba
    from cube import Cube

    from explorer.data import formats
    from explorer.data.io import FrameReader

    numba.set_num_threads(min(a.threads, numba.config.NUMBA_NUM_THREADS))
    proto = Cube.from_fits(a.cube, cache_bytes=0)
    ours = FrameReader(formats.open_layout(a.cube))
    ny, nx = ours.shape[-2:]
    zero = (0,) * len(ours.shape[-3::-1])
    cases = {"lambda-t": [0, 2], "everything": [0, 1, 2]}
    impls = {"prototype": lambda y, x, f: proto.series(y, x, zero, f),
             "explorer": lambda y, x, f: ours.series(y, x, zero, f)}
    for f in cases.values():                                      # compile (or load from cache) before timing
        impls["prototype"](ny // 2, nx // 2, f)
        impls["explorer"](ny // 2, nx // 2, f)
    rng = np.random.default_rng(int(time.time()))
    res = dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
               cube=os.path.basename(a.cube), shape=list(ours.shape), threads=numba.get_num_threads(),
               load=os.getloadavg(), cases={})
    mismatches = 0
    for cname, free in cases.items():
        rows = []
        for r in range(a.rounds):
            order = ["prototype", "explorer"] if r % 2 == 0 else ["explorer", "prototype"]
            row = dict(order=order)
            for name in order:
                t_first, t_warm = [], []
                for _ in range(a.per_round // 2):
                    y, x = int(rng.integers(ny // 8, ny - ny // 8)), int(rng.integers(nx // 8, nx - nx // 8))
                    q = time.perf_counter()
                    s = impls[name](y, x, free)
                    t_first.append(time.perf_counter() - q)
                    q = time.perf_counter()
                    impls[name](y, x, free)
                    t_warm.append(time.perf_counter() - q)
                    other = impls["explorer" if name == "prototype" else "prototype"](y, x, free)
                    mismatches += not np.array_equal(s, other, equal_nan=True)
                row[name] = dict(first_ms=round(statistics.median(t_first) * 1e3, 1),
                                 warm_ms=round(statistics.median(t_warm) * 1e3, 2))
            rows.append(row)
            cells = [f"{n}: first {row[n]['first_ms']:7.1f} ms, warm {row[n]['warm_ms']:6.2f} ms" for n in impls]
            print(f"  {cname:10s} round {r + 1}: " + "   ".join(cells), flush=True)
        med = {k: {n: round(statistics.median(x[n][k] for x in rows), 2) for n in impls}
               for k in ("first_ms", "warm_ms")}
        res["cases"][cname] = dict(rounds=rows, **med)
        print(f"  {cname:10s} median: first {res['cases'][cname]['first_ms']}, warm {res['cases'][cname]['warm_ms']}")
    res["mismatches"] = mismatches
    print(f"series differing: {mismatches}")
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
    ours.close()
    proto.close()
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
