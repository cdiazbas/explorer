"""Slits: the path through the points clicked, the pixels under it, and the values along it. From the prototype's
app/viewer.py (slit_path, slit_pixels, read_slit_blocks, read_slit_slab, read_slit_bands).

With a per-pixel file one read per run of neighbouring pixels in a row gives everything along the slit (every
Stokes, t and lambda); without it, one read per frame of the rows the slit spans gives one slice of it.
"""
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .io import FrameReader
from .pixel import PixelReader


def slit_path(pts, step=1.0):
    """Points along a slit about `step` pixels apart, in the image's view coordinates (pixel centres at .5): straight
    between two points, a Catmull-Rom curve through three or more, which passes through every point clicked
    (CRISPEX smooths its loop paths with SPLINE_P, crispex.pro L12804). (N, 2): x, y."""
    return slit_samples(pts, step)[0]


def slit_samples(pts, step=1.0):
    """slit_path's points and the distance along the slit of each, in pixels from its first point: (N, 2) x, y and
    (N,), every `step` along the curve, the last at its whole length."""
    P = np.asarray(pts, dtype=np.float64)
    if len(P) < 2:
        return P, np.zeros(len(P))
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
        return dense[:1], np.zeros(1)
    at = np.r_[np.arange(0.0, d[-1], step), d[-1]]
    return np.column_stack([np.interp(at, d, dense[:, 0]), np.interp(at, d, dense[:, 1])]), at


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


SLIT_BLOCKS = 8000          # pixel blocks kept (the prototype's SLITC_BLOCKS, app/viewer.py:1690): 6173's are 41.7 kB


class SlitCache:
    """The (s, t, lambda) blocks read along slits (read_slit_blocks), kept: a slit moved, redrawn or still being drawn
    reads only its new pixels. At most max_blocks blocks and max_bytes (the Dataset's share of the memory budget);
    over either, only the blocks of the pixels given to keep() (the slit shown) stay, as the prototype's _slit_ready
    (app/viewer.py:1857), even when they alone are over. Each block read is a view of its run's array: the blocks
    that stay are copied, so that a dropped block frees its memory and nbytes() is the memory held. Thread-safe."""

    def __init__(self, max_bytes: int | None = None, max_blocks: int | None = None):
        self.max_bytes = max_bytes
        self.max_blocks = max_blocks
        self._blocks: dict = {}
        self._bytes = 0
        self._keep: set = set()
        self._lock = threading.Lock()
        self.version = 0                                # changes with what is kept: a slice made from it is reused

    def keep(self, pixels) -> None:
        """The pixels whose blocks are never dropped (the slit shown)."""
        with self._lock:
            self._keep = set(pixels)

    def get(self, p):
        return self._blocks.get(p)

    def __contains__(self, p) -> bool:
        return p in self._blocks

    def __len__(self) -> int:
        return len(self._blocks)

    def keys(self) -> list:
        with self._lock:
            return list(self._blocks)

    def missing(self, pixels) -> list:
        """The distinct pixels of `pixels` with no block kept, in order."""
        with self._lock:
            return [p for p in dict.fromkeys(pixels) if p not in self._blocks]

    def along(self, pixels) -> tuple[int, list]:
        """The version, and the block of each pixel, None where none is kept."""
        with self._lock:
            return self.version, [self._blocks.get(p) for p in pixels]

    def add(self, got: dict) -> None:
        """Blocks read, {(y, x): block}; then, over the bounds, only those kept stay."""
        with self._lock:
            for p, b in got.items():
                old = self._blocks.get(p)
                self._bytes += b.nbytes - (old.nbytes if old is not None else 0)
                self._blocks[p] = b
            self.version += 1
            self._trim()

    def set_budget(self, max_bytes: int) -> None:
        with self._lock:
            self.max_bytes = int(max_bytes)
            self._trim()

    def _trim(self) -> None:
        over = ((self.max_blocks is not None and len(self._blocks) > self.max_blocks)
                or (self.max_bytes is not None and self._bytes > self.max_bytes))
        if not over:
            return
        self._blocks = {k: b.copy() for k, b in self._blocks.items() if k in self._keep}
        self._bytes = sum(b.nbytes for b in self._blocks.values())
        self.version += 1

    def nbytes(self) -> int:
        return self._bytes

    def clear(self) -> None:
        with self._lock:
            self._blocks, self._bytes = {}, 0
            self.version += 1


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

