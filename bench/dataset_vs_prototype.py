"""The Dataset facade against the prototype's objects as its window uses them, same process, ABBA rounds
(ROADMAP E1.10). Run it pinned to one NUMA node on a machine with several (taskset; docs/measured.md).

    python bench/dataset_vs_prototype.py <cube_im.fits> [--prototype DIR] [--rounds 8] [--per-round 6] [--out F]

Cases, each on data the implementation has not read yet in this process (shared caches are not evicted, so the
ABBA order is what makes it fair), then again (cached), results compared bit for bit:
- image: Cube.image(idx) against Dataset.image(idx).result();
- series: lambda-t of one Stokes, Cube.series on a reader thread that owns numba's threads (as the prototype's
  _bg, capped at the core count as its own process is) against Dataset.series(...).result();
- block: SpFits.block(y, x) (called on the window's thread in the prototype) against
  Dataset.pixel_block(y, x).result(); then a pixel of the same strip, which both serve from memory.
"""
import argparse
import json
import os
import socket
import statistics
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("NUMBA_CACHE_DIR", tempfile.mkdtemp(prefix="bench_numba_"))   # never inside the prototype
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cube")
    ap.add_argument("--prototype", default=os.path.join(ROOT, "..", "prototype"))
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--per-round", type=int, default=6, help="reads per implementation, case and round")
    ap.add_argument("--out")
    a = ap.parse_args()
    proto_dir = os.path.abspath(a.prototype)
    sys.path[:0] = [os.path.join(proto_dir, "app"), os.path.join(proto_dir, "viewer")]
    from explorer.data.dataset import Dataset

    numba = sys.modules["numba"]
    from cube import Cube
    from policy import StorageProbe as ProtoProbe
    from sources import SpFits

    ds = Dataset.open(a.cube)
    r = ds.roles
    proto = Cube.from_fits(a.cube, cache_bytes=ds.budgets.images)
    pprobe = ProtoProbe(proto)
    proto_sp = (SpFits(ds.pixel.layout.path, (r.ns, r.nt, r.nl), strip=pprobe.strip)
                if ds.pixel is not None and ds.pixel.kind == "sp.fits" else None)
    proto_bg = ThreadPoolExecutor(1)                      # the prototype's _bg: numba's threads set on it
    # the prototype caps its threads at numba's default pool, the core count
    n_thr = min(getattr(pprobe, "gather_threads", 32), os.cpu_count() or 1)
    proto_bg.submit(numba.set_num_threads, n_thr).result()
    zero = (0,) * len(ds.shape[:-2])
    lt_axes = sorted(x for x in (r.t, r.l) if x is not None)
    rng = np.random.default_rng(int(time.time()))
    res = dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
               cube=os.path.basename(a.cube), shape=list(ds.shape), describe=ds.describe(),
               proto_numba_threads=n_thr, ours_numba_threads=ds.executors.numba_threads,
               affinity=sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
               load=os.getloadavg(), cases={})
    mism = {}

    def frame():
        return tuple(int(rng.integers(n)) for n in ds.shape[:-2])

    def pixel(strip):
        y = int(rng.integers(ds.ny // 8, ds.ny - ds.ny // 8))
        x = int(rng.integers(ds.nx // 8, ds.nx - ds.nx // 8)) // strip * strip   # a strip start: x + 1 is in it
        return y, x

    cases = {
        "image": (frame, lambda i: proto.image(list(i)), lambda i: ds.image(i).result(), lambda i: i),
        "series": (lambda: pixel(1),
                   lambda p: proto_bg.submit(proto.series, p[0], p[1], zero, lt_axes).result(),
                   lambda p: ds.series(p[0], p[1], zero, lt_axes).result(), lambda p: p),
    }
    if proto_sp is not None:
        cases["block"] = (lambda: pixel(ds.probe.strip), lambda p: proto_sp.block(*p),
                          lambda p: ds.pixel_block(*p).result(), lambda p: (p[0], p[1] + 1))
    for name, (draw, pf, of, again) in cases.items():
        impl = {"prototype": pf, "explorer": of}
        pf(draw()), of(draw())                           # compile / open paths before timing
        rows = []
        for rd in range(a.rounds):
            order = ["prototype", "explorer"] if rd % 2 == 0 else ["explorer", "prototype"]
            row = dict(order=order)
            for impl_name in order:
                first, hit = [], []
                for _ in range(a.per_round):
                    k = draw()
                    q = time.perf_counter()
                    got = impl[impl_name](k)
                    first.append(time.perf_counter() - q)
                    q = time.perf_counter()
                    impl[impl_name](again(k))
                    hit.append(time.perf_counter() - q)
                    other = impl["explorer" if impl_name == "prototype" else "prototype"](k)
                    mism[name] = mism.get(name, 0) + int(not np.array_equal(got, other, equal_nan=True))
                row[impl_name] = round(statistics.median(first) * 1e3, 2)
                row[impl_name + "_hit_us"] = round(statistics.median(hit) * 1e6, 1)
            rows.append(row)
            print(f"  {name} round {rd + 1} ({order[0]} first): prototype {row['prototype']:.2f} ms "
                  f"(again {row['prototype_hit_us']:.0f} us), explorer {row['explorer']:.2f} ms "
                  f"(again {row['explorer_hit_us']:.0f} us)", flush=True)
        ratio = [x["explorer"] / x["prototype"] for x in rows]
        ratio_hit = [x["explorer_hit_us"] / x["prototype_hit_us"] for x in rows]
        med = {k: round(statistics.median(x[k] for x in rows), 2)
               for k in ("prototype", "explorer", "prototype_hit_us", "explorer_hit_us")}
        res["cases"][name] = dict(rounds=rows, median=med, paired=round(statistics.median(ratio), 3),
                                  faster=sum(x < 1 for x in ratio), paired_hit=round(statistics.median(ratio_hit), 3),
                                  faster_hit=sum(x < 1 for x in ratio_hit))
        c = res["cases"][name]
        print(f"{name}: {med}; paired first {c['paired']} (explorer faster in {c['faster']}/{len(rows)}), again "
              f"{c['paired_hit']} ({c['faster_hit']}/{len(rows)}); differing results: {mism.get(name, 0)}", flush=True)
    res["mismatches"] = mism
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
    proto_bg.shutdown()
    ds.close()
    proto.close()
    return 1 if any(mism.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
