"""A per-pixel file opened alone (ROADMAP E1.23): what the viewer pays for its images, and what writing its image cube
costs. No Qt: the Dataset the window reads through, and data.transpose.

    python bench/sp_alone_view.py view <cube_sp.fits> [--steps 2] [--lam 7] [--out res.json]
    python bench/sp_alone_view.py transpose <dir> [--shape 400,400,1,49,15] [--block-mb 256] [--out res.json]

view: Dataset.open on the per-pixel file (its images from it, io.PerPixelFrames, whatever is beside it), the
sheet's estimate (data.transpose.estimate: the file's size over a few reads timed now), then the first image at
(t=0, s=0, lambda) and `steps` steps in t, each timed to its array: one pass over the file each.
transpose: a synthetic per-pixel file of that shape (float32, random) written in <dir>/src, then transposed to
<dir>/out, timed (reading and writing apart), and the copy checked against the source at a few images. Removes both.
Fine timings: pinned, one measurement at a time; /proc/loadavg before and after.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))


def load() -> str:
    with open("/proc/loadavg") as f:
        return f.read().strip()


def view(a) -> dict:
    from explorer.data.dataset import Dataset
    from explorer.data.transpose import estimate

    out: dict = {"file": os.path.basename(a.sp), "load_before": load()}
    q = time.perf_counter()
    ds = Dataset.open(a.sp)
    out["open_s"] = time.perf_counter() - q
    try:
        out["shape"] = list(ds.layout.shape)
        out["bytes"] = ds.frames.sp.nbytes
        out["record_bytes"] = ds.frames.record
        out["block_rows"] = ds.frames.block_rows
        q = time.perf_counter()
        est = estimate(ds.frames)
        out["estimate"] = dict(image_s=est.image_s, how=est.how, factor=est.factor, copy_gb=est.copy_bytes / 1e9,
                               took_s=time.perf_counter() - q)
        times = []
        for t in range(a.steps + 1):
            q = time.perf_counter()
            img = ds.image((t, 0, a.lam)).result()
            times.append(time.perf_counter() - q)
            print(f"image t={t}: {times[-1]:.2f} s, {np.isfinite(img).mean():.3f} finite", flush=True)
        out["images_s"] = times
        out["passes_s"] = list(ds.frames.passes)
        q = time.perf_counter()
        ds.pixel_block(ds.ny // 2, ds.nx // 2).result()
        out["pixel_block_s"] = time.perf_counter() - q
    finally:
        ds.close()
    out["load_after"] = load()
    return out


def transpose_bench(a) -> dict:
    from astropy.io import fits

    from explorer.data.transpose import transpose

    ny, nx, ns, nt, nl = (int(v) for v in a.shape.split(","))
    for d in ("src", "out"):                    # the copy never beside its per-pixel file (data.transpose)
        os.makedirs(os.path.join(a.dir, d), exist_ok=True)
    sp, im = os.path.join(a.dir, "src", "bench_sp.fits"), os.path.join(a.dir, "out", "bench_im.fits")
    h = fits.Header()
    h["SIMPLE"], h["BITPIX"], h["NAXIS"] = True, -32, 5
    for i, n in enumerate((nl, nt, ns, nx, ny), 1):
        h[f"NAXIS{i}"] = n
    for i, c in enumerate(("WAVE", "UTC", "STOKES", "HPLN", "HPLT"), 1):
        h[f"CTYPE{i}"] = c
    rng = np.random.default_rng(0)
    s = fits.StreamingHDU(sp, h)
    for y0 in range(0, ny, 16):
        s.write(rng.random((min(16, ny - y0), nx, ns, nt, nl), np.float32).astype(">f4"))
    s.close()
    out: dict = {"shape": [ny, nx, ns, nt, nl], "bytes": os.path.getsize(sp), "dir": a.dir, "load_before": load()}
    try:
        r = transpose(sp, im, block=a.block_mb << 20)
        out.update(r)
        out["MB_per_s"] = r["bytes"] / r["seconds"] / 1e6
        rec = np.memmap(sp, ">f4", "r", 2880, (ny, nx, ns * nt * nl))         # the header: one block
        with fits.open(im, memmap=True) as f:
            for t, st, lam in ((0, 0, 0), (nt - 1, ns - 1, nl - 1), (nt // 2, 0, nl // 2)):
                k = (st * nt + t) * nl + lam
                assert np.array_equal(np.asarray(f[0].data[t, st, lam]), np.asarray(rec[:, :, k])), (t, st, lam)
        del rec
        out["checked"] = 3
    finally:
        out["load_after"] = load()
        for p in (sp, im):
            if os.path.exists(p):
                os.remove(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="what", required=True)
    v = sub.add_parser("view")
    v.add_argument("sp")
    v.add_argument("--steps", type=int, default=2)
    v.add_argument("--lam", type=int, default=7)
    v.add_argument("--out")
    t = sub.add_parser("transpose")
    t.add_argument("dir")
    t.add_argument("--shape", default="400,400,1,49,15")
    t.add_argument("--block-mb", type=int, default=256)
    t.add_argument("--out")
    a = ap.parse_args()
    res = view(a) if a.what == "view" else transpose_bench(a)
    print(json.dumps(res, indent=1, default=str))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
