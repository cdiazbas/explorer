"""Slits: explorer.data.slits against the prototype's app/viewer.py, same process, ABBA rounds (ROADMAP E1.9).

    python bench/slits_vs_prototype.py <cube_im.fits> [--prototype DIR] [--rounds 4] [--length 600] [--threads 64]
                                       [--out F]

Each round draws one slit shape (three points, about --length pixels, random angle): the reads a slit costs
depend on it (the rows it spans, its runs of neighbouring pixels), so both implementations read the same shape,
each in its own half of the field (upper or lower, swapped every round) so that neither reads rows the other has
already brought into the page cache; ABBA order. Then each reads its slit again (warm), and the other
implementation reads it too for a bit-for-bit comparison. With --aa both columns run the prototype: the
noise floor of the design, order effects included. Cases, with the thread counts the viewer uses:
- slab: everything along the slit from the per-pixel file, when there is one (explorer on a pool kept open);
- bands t: without it, one band of rows per t at one (Stokes, lambda), the slit's t slice;
- bands lambda: one band per lambda at one (t, Stokes), the lambda slice.
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
os.environ.pop("DISPLAY", None)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cube")
    ap.add_argument("--prototype", default=os.path.join(ROOT, "..", "prototype"))
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--length", type=float, default=600.0)
    ap.add_argument("--threads", type=int, default=64)
    ap.add_argument("--skip", default="", help="comma-separated cases to leave out")
    ap.add_argument("--aa", action="store_true", help="control: the prototype against itself (the noise floor)")
    ap.add_argument("--out")
    a = ap.parse_args()
    proto_dir = os.path.abspath(a.prototype)
    sys.path[:0] = [os.path.join(proto_dir, "app"), os.path.join(proto_dir, "viewer")]
    import viewer as V  # the prototype's app/viewer.py
    from cube import Cube
    from sources import SpFits

    from explorer.data import axes, formats, slits
    from explorer.data.io import FrameReader
    from explorer.data.pixel import open_pixel

    lay = formats.open_layout(a.cube)
    roles = axes.roles(lay.axes, lay.shape)
    nlead = len(lay.shape) - 2
    proto = Cube.from_fits(a.cube, cache_bytes=0)
    fr = FrameReader(lay)
    ours_sp = open_pixel(a.cube, fr)
    proto_sp = (SpFits(ours_sp.layout.path, (roles.ns, roles.nt, roles.nl))
                if ours_sp is not None and ours_sp.kind == "sp.fits" else None)
    band_threads = min(16, a.threads)
    slab_pool = ThreadPoolExecutor(a.threads, thread_name_prefix="slab")    # kept open, as the app keeps its pools
    rng = np.random.default_rng(int(time.time()))
    ny, nx = fr.ny, fr.nx
    res = dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
               cube=os.path.basename(a.cube), shape=list(lay.shape), threads=a.threads, band_threads=band_threads,
               length=a.length, load=os.getloadavg(), cases={})
    mism = {}

    def slit_shape():
        """Three points about `length` px apart end to end, relative to the slit's centre."""
        ang = rng.uniform(0, np.pi)
        d = np.array([np.cos(ang), np.sin(ang)]) * a.length / 2
        return np.array([-d, rng.normal(0, a.length / 8, 2), d])

    def place(shape, half):
        """The shape centred in the upper (0) or lower (1) half of the field, at a random x."""
        c = np.array([rng.uniform(nx * 0.35, nx * 0.65), ny * (0.28 if half == 0 else 0.72)])
        pts = np.clip(shape + c, 1, [nx - 2, ny - 2]) + 0.5
        return slits.slit_pixels(slits.slit_path(pts), ny, nx)

    skip = set(filter(None, a.skip.split(",")))
    res["aa"] = a.aa

    def run_case(name, proto_fn, ours_fn):
        if name in skip:
            return
        if a.aa:                                            # the "explorer" column runs the prototype too
            ours_fn = proto_fn
        rows = []
        for r in range(a.rounds):
            order = ["prototype", "explorer"] if r % 2 == 0 else ["explorer", "prototype"]
            row = dict(order=order)
            shape = slit_shape()
            for k, impl in enumerate(order):
                iy, ix = place(shape, (k + r // 2) % 2)
                fn, other = (proto_fn, ours_fn) if impl == "prototype" else (ours_fn, proto_fn)
                q = time.perf_counter()
                got = fn(iy, ix)
                row[impl] = round((time.perf_counter() - q) * 1e3, 1)
                q = time.perf_counter()
                fn(iy, ix)
                row[f"{impl}_warm"] = round((time.perf_counter() - q) * 1e3, 1)
                mism[name] = mism.get(name, 0) + int(not np.array_equal(got, other(iy, ix), equal_nan=True))
                row[f"{impl}_npath"] = len(iy)
                row[f"{impl}_rows"] = int(iy.max() - iy.min() + 1)
            rows.append(row)
            print(f"  {name} round {r + 1} ({order[0]} first, {row['prototype_npath']} px, "
                  f"{row['prototype_rows']} rows): prototype {row['prototype']:.1f} ms (warm "
                  f"{row['prototype_warm']:.1f}), explorer {row['explorer']:.1f} ms (warm {row['explorer_warm']:.1f})",
                  flush=True)
        med = {i: round(statistics.median(r[i] for r in rows), 1)
               for i in ("prototype", "explorer", "prototype_warm", "explorer_warm")}
        res["cases"][name] = dict(rounds=rows, median=med)
        print(f"{name}: median over rounds {med}; differing results: {mism.get(name, 0)}", flush=True)

    if proto_sp is not None:
        run_case("slab", lambda iy, ix: V.read_slit_slab(proto_sp, iy, ix, threads=a.threads)[0],
                 lambda iy, ix: slits.read_slit_slab(ours_sp, iy, ix, pool=slab_pool)[0])
    s, lam, t = min(3, roles.ns - 1), roles.nl // 2, roles.nt // 2
    t_idx = [axes.frame_index(nlead, roles, t=k, s=s, l=lam) for k in range(roles.nt)]
    l_idx = [axes.frame_index(nlead, roles, t=t, s=s, l=k) for k in range(roles.nl)]
    run_case("bands_t", lambda iy, ix: V.read_slit_bands(proto, [list(j) for j in t_idx], iy, ix, band_threads),
             lambda iy, ix: slits.read_slit_bands(fr, t_idx, iy, ix, band_threads))
    run_case("bands_lambda", lambda iy, ix: V.read_slit_bands(proto, [list(j) for j in l_idx], iy, ix, band_threads),
             lambda iy, ix: slits.read_slit_bands(fr, l_idx, iy, ix, band_threads))

    res["mismatches"] = mism
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
    if ours_sp is not None:
        ours_sp.close()
    fr.close()
    proto.close()
    return 1 if any(mism.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
