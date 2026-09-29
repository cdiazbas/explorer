"""Slits: the path through the points clicked, the pixels under it, and the values along it. From the prototype's
app/viewer.py (slit_path, slit_pixels, read_slit_blocks, read_slit_slab, read_slit_bands).

With a per-pixel file one read per run of neighbouring pixels in a row gives everything along the slit (every
Stokes, t and lambda); without it, one read per frame of the rows the slit spans gives one slice of it.
"""
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .io import FrameReader
from .pixel import PixelReader


def slit_path(pts, step=1.0):
    """Points along a slit about `step` pixels apart, in the image's view coordinates (pixel centres at .5): straight
    between two points, a Catmull-Rom curve through three or more, which passes through every point clicked
    (CRISPEX smooths its loop paths with SPLINE_P, crispex.pro L12804). (N, 2): x, y."""
    P = np.asarray(pts, dtype=np.float64)
    if len(P) < 2:
        return P
    if len(P) == 2:
        dense = P
    else:
        Q = np.vstack([P[:1], P, P[-1:]])               # ends repeated: the curve starts and ends on them
        u = np.linspace(0.0, 1.0, 33)[:-1, None]
        segs = []
        for i in range(1, len(Q) - 2):
            p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
            segs.append(0.5 * (2 * p1 + (p2 - p0) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u ** 2
                               + (3 * p1 - p0 - 3 * p2 + p3) * u ** 3))
        dense = np.vstack([*segs, P[-1:]])
    d = np.r_[0.0, np.cumsum(np.hypot(*np.diff(dense, axis=0).T))]
    if d[-1] == 0:
        return dense[:1]
    at = np.r_[np.arange(0.0, d[-1], step), d[-1]]
    return np.column_stack([np.interp(at, d, dense[:, 0]), np.interp(at, d, dense[:, 1])])


def slit_pixels(path, ny, nx):
    """The pixel under each point of a slit path (view coordinates, pixel centres at .5): nearest pixel, as CRISPEX
    samples its loop paths (crispex.pro L13081-13134). (iy, ix) int64 arrays, one per point."""
    ix = np.clip(np.floor(path[:, 0]).astype(np.int64), 0, nx - 1)
    iy = np.clip(np.floor(path[:, 1]).astype(np.int64), 0, ny - 1)
    return iy, ix


def pixel_runs(pixels) -> list[tuple[int, int, int]]:
    """(y, x0, k) for each run of k neighbouring pixels in a row, over the distinct (y, x) given."""
    uniq = sorted(set(pixels))
    runs, start = [], 0
    for i in range(1, len(uniq) + 1):
        if i == len(uniq) or uniq[i][0] != uniq[i - 1][0] or uniq[i][1] != uniq[i - 1][1] + 1:
            runs.append((uniq[start][0], uniq[start][1], i - start))
            start = i
    return runs


def read_slit_blocks(sp: PixelReader, pixels, threads=16, pool: ThreadPoolExecutor | None = None):
    """{(y, x): (s, t, lambda) float32} for the given pixels from the per-pixel file: each run of neighbouring pixels
    in a row one read, all runs in parallel, on `pool` if given (a pool kept open: starting 64 threads per slit
    cost 10-16 % of a warm slab, 6173 on bellatrix), else on `threads` threads started for this call.
    Returns (blocks, number of reads)."""
    runs = pixel_runs((int(y), int(x)) for y, x in pixels)
    if not runs:
        return {}, 0
    if pool is not None:
        got = list(pool.map(lambda r: sp.strip_read(*r), runs))
    else:
        with ThreadPoolExecutor(max(1, min(threads, len(runs)))) as ex:
            got = list(ex.map(lambda r: sp.strip_read(*r), runs))
    where = {}
    for (y, x0, k), blk in zip(runs, got, strict=True):
        for j in range(k):
            where[(y, x0 + j)] = blk[j]
    return where, len(runs)


def read_slit_slab(sp: PixelReader, iy, ix, threads=16, pool: ThreadPoolExecutor | None = None):
    """[npath, s, t, lambda] float32 along a slit from the per-pixel file, and the number of reads; t, lambda and
    Stokes are then slices of it, with no more reads. Bellatrix StorNext, 64 threads: 600 px in 23-96 ms."""
    where, runs = read_slit_blocks(sp, zip(iy.tolist(), ix.tolist(), strict=True), threads, pool)
    slab = np.stack([where[(y, x)] for y, x in zip(iy.tolist(), ix.tolist(), strict=True)])
    return slab.astype(np.float32, copy=False), runs


def read_slit_bands(frames: FrameReader, idxs, iy, ix, threads=8):
    """Values along a slit from whole-image frames (no per-pixel file): for each frame index in idxs, one read of the
    rows the slit spans, then its pixels. (len(idxs), npath) float32 in physical units."""
    y0, y1 = int(iy.min()), int(iy.max())
    at = (iy - y0) * frames.nx + ix                     # flat, once: 2-D fancy indexing cost ~9 us more per frame
    return frames.band_values([tuple(j) for j in idxs], y0, y1 + 1, at, threads)


def frame_index(nlead: int, roles, t=0, s=0, l=0) -> tuple:  # noqa: E741
    """The leading-axes index of the frame at (t, s, lambda); axes the cube lacks are skipped, others stay 0."""
    j = [0] * nlead
    for a, v in ((roles.t, t), (roles.s, s), (roles.l, l)):
        if a is not None:
            j[a] = int(v)
    return tuple(j)
