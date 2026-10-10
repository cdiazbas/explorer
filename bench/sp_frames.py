"""Images out of a per-pixel file alone (ROADMAP E1.23): one frame (y, x) at (t, s, lambda) read from the per-pixel
file against the same frame from its image cube, and one pixel's (s, t, lambda) block the other way round. Numpy and
preads only, no Qt: what the cost of opening a _sp without its _im would be, before writing it.

    python bench/sp_frames.py <cube_im> <cube_sp> [--frames 3] [--reps 3] [--warm] [--out res.json]

Per frame:
- im: the frame from the image cube, one pread of ny * nx samples (as FrameReader reads it, in one part);
- sp fresh: a new numpy.memmap of the per-pixel file and the frame taken from it, one sample per pixel: with a
  pixel's samples closer together than a page, every page of the file is touched (a whole-file pass);
- sp reused: the same, through a mapping whose pages another frame has already touched (the file resident and
  mapped), on 1 and on 16 threads (bands of rows);
- sp stream: the file read with preads 256 rows at a time and the one sample per pixel kept.
Per block: the per-pixel file's one pread against the image cube's nt * ns * nl samples, one per frame, through a
mapping first fresh and then reused. Every frame and block is checked equal between the two files.
--warm reads both files once first (page cache; nothing is evicted). Fine timings: pinned, one measurement at a time.
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from explorer.data.formats import open_layout


def warm(path, chunk=1 << 20) -> float:
    """Read the file once, 1 MiB at a time (StorNext reads larger ones past the page cache); GB/s."""
    t0, n = time.perf_counter(), 0
    buf = bytearray(chunk)
    with open(path, "rb", buffering=0) as f:
        while k := f.readinto(buf):
            n += k
    return n / (time.perf_counter() - t0) / 1e9


class Pair:
    """The image cube and its per-pixel file, both as (t, s, lambda, y, x) and (y, x, s, t, lambda)."""

    def __init__(self, im_path, sp_path):
        self.li, self.ls = open_layout(im_path), open_layout(sp_path)
        if len(self.li.shape) == 5:                     # (t, s, l, y, x); per pixel (s, t, l)
            self.nt, self.ns, self.nl, self.ny, self.nx = self.li.shape
        else:                                           # LP without its axes: (frames, y, x), (pixel-Stokes, t, l)
            nf, self.ny, self.nx = self.li.shape
            _, self.nt, self.nl = self.ls.shape[-3:]
            self.ns = nf // (self.nt * self.nl)
        self.per = self.nt * self.ns * self.nl
        self.fdi, self.fds = os.open(im_path, os.O_RDONLY), os.open(sp_path, os.O_RDONLY)

    def sp_map(self):
        mm = np.memmap(self.ls.path, dtype=self.ls.dtype, mode="r", offset=self.ls.offset, shape=self.ls.shape)
        return mm.reshape(self.ny, self.nx, self.ns, self.nt, self.nl)

    def im_map(self):
        return np.memmap(self.li.path, dtype=self.li.dtype, mode="r", offset=self.li.offset,
                         shape=(self.per, self.ny, self.nx))

    def frame_im(self, t, s, lam):
        n = self.ny * self.nx * self.li.dtype.itemsize
        b = os.pread(self.fdi, n, self.li.offset + ((t * self.ns + s) * self.nl + lam) * n)
        return np.frombuffer(b, self.li.dtype).reshape(self.ny, self.nx).astype(np.float32)

    def frame_sp(self, mm, t, s, lam, threads=1):
        out = np.empty((self.ny, self.nx), mm.dtype)
        v = mm[:, :, s, t, lam]
        if threads == 1:
            out[...] = v
        else:
            def part(r):
                out[r[0]:r[-1] + 1] = v[r[0]:r[-1] + 1]
            with ThreadPoolExecutor(threads) as ex:
                list(ex.map(part, np.array_split(np.arange(self.ny), threads * 4)))
        return out.astype(np.float32)

    def frame_stream(self, t, s, lam, band=256):
        isz, k = self.ls.dtype.itemsize, (s * self.nt + t) * self.nl + lam
        out = np.empty((self.ny, self.nx), np.float32)
        for y0 in range(0, self.ny, band):
            y1 = min(self.ny, y0 + band)
            b = os.pread(self.fds, (y1 - y0) * self.nx * self.per * isz, self.ls.offset + y0 * self.nx * self.per * isz)
            out[y0:y1] = np.frombuffer(b, self.ls.dtype).reshape(y1 - y0, self.nx, self.per)[:, :, k]
        return out

    def block_sp(self, y, x):
        isz = self.ls.dtype.itemsize
        b = os.pread(self.fds, self.per * isz, self.ls.offset + (y * self.nx + x) * self.per * isz)
        return np.frombuffer(b, self.ls.dtype).astype(np.float32).reshape(self.ns, self.nt, self.nl)

    def block_im(self, mm, y, x):
        return np.array(mm[:, y, x], np.float32).reshape(self.nt, self.ns, self.nl).transpose(1, 0, 2)


def ms(f, *a):
    t0 = time.perf_counter()
    r = f(*a)
    return (time.perf_counter() - t0) * 1e3, r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("im")
    ap.add_argument("sp")
    ap.add_argument("--frames", type=int, default=3)
    ap.add_argument("--blocks", type=int, default=5)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--warm", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    p = Pair(a.im, a.sp)
    res: dict = {"im": [p.li.kind, list(p.li.shape), str(p.li.dtype), os.path.getsize(os.path.realpath(a.im))],
                 "sp": [p.ls.kind, list(p.ls.shape), str(p.ls.dtype), os.path.getsize(os.path.realpath(a.sp))],
                 "pixel_stride_bytes": p.per * p.ls.dtype.itemsize, "frames": [], "blocks": []}
    print(json.dumps({k: res[k] for k in ("im", "sp", "pixel_stride_bytes")}), flush=True)
    if a.warm:
        res["warm_GBps"] = [warm(a.im), warm(a.sp), warm(a.im), warm(a.sp)]
        print("warm (im, sp, im, sp) GB/s:", [f"{v:.2f}" for v in res["warm_GBps"]], flush=True)
    res["load_before"] = open("/proc/loadavg").read().strip() if os.path.exists("/proc/loadavg") else ""
    rng = np.random.default_rng(1)
    for _ in range(a.frames):
        t, s, lam = int(rng.integers(p.nt)), int(rng.integers(p.ns)), int(rng.integers(p.nl))
        im = [ms(p.frame_im, t, s, lam)[0] for _ in range(a.reps)]
        ref = p.frame_im(t, s, lam)
        mm = p.sp_map()
        fresh, got = ms(p.frame_sp, mm, t, s, lam)
        del mm
        mm = p.sp_map()
        p.frame_sp(mm, (t + 1) % p.nt, s, lam)          # this mapping's pages touched by another frame
        reused = [ms(p.frame_sp, mm, t, s, lam)[0] for _ in range(a.reps)]
        reused16 = [ms(p.frame_sp, mm, t, s, lam, 16)[0] for _ in range(a.reps)]
        del mm
        stream, got2 = ms(p.frame_stream, t, s, lam)
        equal = bool(np.array_equal(ref, got, equal_nan=True) and np.array_equal(ref, got2, equal_nan=True))
        row = dict(t=t, s=s, l=lam, im=im, sp_fresh=fresh, sp_reused=reused, sp_reused16=reused16, sp_stream=stream,
                   equal=equal)
        res["frames"].append(row)
        print(json.dumps(row), flush=True)
    mmi = p.im_map()
    for _ in range(a.blocks):
        y, x = int(rng.integers(p.ny)), int(rng.integers(p.nx))
        sp = [ms(p.block_sp, y, x)[0] for _ in range(a.reps)]
        fresh_map = p.im_map()
        fresh = ms(p.block_im, fresh_map, y, x)[0]
        del fresh_map
        im = [ms(p.block_im, mmi, y, x)[0] for _ in range(a.reps)]
        equal = bool(np.array_equal(p.block_sp(y, x), p.block_im(mmi, y, x), equal_nan=True))
        row = dict(y=y, x=x, sp=sp, im_fresh=fresh, im_reused=im, equal=equal)
        res["blocks"].append(row)
        print(json.dumps(row), flush=True)
    res["load_after"] = open("/proc/loadavg").read().strip() if os.path.exists("/proc/loadavg") else ""
    if a.out:
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
