"""Reading samples with explicit preads: the only module that holds file descriptors and computes offsets.

FrameReader reads a whole image (or a band of rows) of an image cube and returns native float32. Explicit
preadv, never numpy.memmap: on a cold cache memmap was 5x slower for a 2k frame (docs/measured.md). A frame is
read in `chunks` parts at once, the calling thread taking the first and a pool the others, so a pool thread
never waits on the pool; more than 4 parts does not help on StorNext.
"""
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ..obs import span
from .formats import Layout


class ShortRead(OSError):
    """The file returned fewer bytes than asked for: truncated file, or an I/O error on network storage."""


def _preadv_exact(fd, view, offset):
    n = os.preadv(fd, [view], offset)
    if n != len(view):
        raise ShortRead(f"read {n} of {len(view)} bytes at offset {offset}")


class FrameReader:
    """Images of an image cube (numpy order (..., y, x)), by index over the leading axes."""

    def __init__(self, layout: Layout, pool: ThreadPoolExecutor | None = None, chunks: int = 4):
        if len(layout.shape) < 2:
            raise ValueError("an image cube needs at least (y, x)")
        self.layout, self.chunks = layout, max(1, int(chunks))
        self.shape = layout.shape
        self.ny, self.nx = layout.shape[-2:]
        self.frame_bytes = self.ny * self.nx * layout.dtype.itemsize
        lead = layout.shape[:-2]
        # frames per step of each leading axis, e.g. (ns*nl, nl, 1) for (t, s, lambda)
        self.strides = tuple(int(np.prod(lead[i + 1:], dtype=np.int64)) for i in range(len(lead)))
        self.fd = os.open(layout.path, os.O_RDONLY)
        self._own_pool = pool is None
        self.pool = pool if pool is not None else ThreadPoolExecutor(max(1, self.chunks - 1),
                                                                   thread_name_prefix="frames")

    def frame_offset(self, idx) -> int:
        idx = tuple(int(i) for i in idx)
        if len(idx) != len(self.strides) or any(not 0 <= i < n for i, n in zip(idx, self.shape[:-2], strict=True)):
            raise IndexError(f"frame index {idx} outside {self.shape[:-2]}")
        return self.layout.offset + sum(i * s for i, s in zip(idx, self.strides, strict=True)) * self.frame_bytes

    def read_raw(self, idx, chunks: int | None = None) -> np.ndarray:
        """The frame as stored (dtype and byte order of the file)."""
        raw = np.empty((self.ny, self.nx), self.layout.dtype)
        mv, fb = memoryview(raw).cast("B"), self.frame_bytes
        k = self.chunks if chunks is None else max(1, int(chunks))
        step = -(-fb // k)
        base = self.frame_offset(idx)
        parts = [(i * step, min(fb, (i + 1) * step)) for i in range(k) if i * step < fb]
        futs = [self.pool.submit(_preadv_exact, self.fd, mv[a:b], base + a) for a, b in parts[1:]]
        _preadv_exact(self.fd, mv[parts[0][0]:parts[0][1]], base)
        for f in futs:
            f.result()
        return raw

    def read(self, idx, chunks: int | None = None) -> np.ndarray:
        """The frame as native float32 in physical units (FITS BSCALE/BZERO applied, BLANK -> NaN)."""
        with span("data.frame.read"):
            return self.to_float32(self.read_raw(idx, chunks))

    def read_rows_raw(self, idx, y0: int, y1: int) -> np.ndarray:
        """Rows y0..y1-1 of a frame as stored, one read: the band a slit crosses, without the rest of the image.
        Read-only (a view of the bytes read): os.pread into bytes costs 7-15 us less per band than preadv into a
        new numpy array, and a slit reads one band per frame (bellatrix, 3.9 MB bands, pinned to one NUMA node)."""
        if not 0 <= y0 < y1 <= self.ny:
            raise IndexError(f"rows {y0}..{y1} outside 0..{self.ny}")
        n = (y1 - y0) * self.nx * self.layout.dtype.itemsize
        b = os.pread(self.fd, n, self.frame_offset(idx) + y0 * self.nx * self.layout.dtype.itemsize)
        if len(b) != n:
            raise ShortRead(f"read {len(b)} of {n} bytes of rows {y0}..{y1} in {self.layout.path}")
        return np.frombuffer(b, self.layout.dtype).reshape(y1 - y0, self.nx)

    def band_values(self, idxs, y0: int, y1: int, at, threads: int = 8) -> np.ndarray:
        """For each frame index in idxs, one read of rows y0..y1-1, then the values at flat positions `at` in that
        band: (len(idxs), len(at)) float32 in physical units, reads on `threads` threads started for the call.
        The values along a slit without a per-pixel file. Each worker computes its frame's offset and converts
        its own values, as the prototype's read_slit_bands does: with 16 workers a leaner one (offsets computed
        up front) measured 8-15 % slower, the reads then contending harder for the GIL (bellatrix, 186 frames of
        3.9 MB, pinned to one NUMA node)."""
        if not 0 <= y0 < y1 <= self.ny:
            raise IndexError(f"rows {y0}..{y1} outside 0..{self.ny}")
        at = np.asarray(at, np.int64)
        if at.size and not (0 <= at.min() and at.max() < (y1 - y0) * self.nx):
            raise IndexError(f"positions outside a band of {y1 - y0} rows of {self.nx}")
        isz = self.layout.dtype.itemsize
        n = (y1 - y0) * self.nx * isz
        skip = y0 * self.nx * isz
        fd, dt = self.fd, self.layout.dtype

        def one(j):
            b = os.pread(fd, n, self.frame_offset(j) + skip)
            if len(b) != n:
                raise ShortRead(f"read {len(b)} of {n} bytes of frame {j} in {self.layout.path}")
            return self.to_float32(np.frombuffer(b, dt)[at])

        idxs = list(idxs)
        if not idxs:
            return np.empty((0, at.size), np.float32)
        with span("data.bands.read"), ThreadPoolExecutor(max(1, min(threads, len(idxs)))) as ex:
            return np.stack(list(ex.map(one, idxs)))

    def read_rows(self, idx, y0: int, y1: int) -> np.ndarray:
        """Rows y0..y1-1 of a frame as native float32 in physical units."""
        return self.to_float32(self.read_rows_raw(idx, y0, y1))

    def series(self, y: int, x: int, idx, free_axes) -> np.ndarray:
        """Values at pixel (y, x) along the leading axes in free_axes, the others fixed at idx: one dimension per
        free axis, in axis order (profile: (nl,), lambda-t: (nt, nl), everything: (nt, ns, nl)). Read from the
        file every time, in the numba reader's threads (call it from the one thread that runs parallel numba)."""
        from .gather import gather

        free = sorted(int(a) for a in free_axes)
        if not 0 <= y < self.ny or not 0 <= x < self.nx:
            raise IndexError(f"pixel ({y}, {x}) outside {self.ny}x{self.nx}")
        idx = tuple(int(i) for i in idx)
        sizes = [self.shape[a] for a in free]
        fixed = sum(i * s for a, (i, s) in enumerate(zip(idx, self.strides, strict=True)) if a not in free)
        grid = np.zeros(sizes, np.int64)
        for k, a in enumerate(free):
            shp = [1] * len(sizes)
            shp[k] = sizes[k]
            grid = grid + np.arange(sizes[k], dtype=np.int64).reshape(shp) * self.strides[a]
        it = self.layout.dtype.itemsize
        offs = (self.layout.offset + (fixed + grid.ravel()) * self.frame_bytes
                + (int(y) * self.nx + int(x)) * it).astype(np.int64)
        out = np.empty(offs.size * it, np.uint8)
        with span("data.series.read"):
            if gather(self.fd, offs, it, out):
                raise ShortRead(f"short reads for pixel ({y}, {x}) in {self.layout.path}")
        return self.to_float32(out.view(self.layout.dtype).reshape(sizes))

    def points(self, ys, xs, frame_numbers) -> np.ndarray:
        """Values at pixels (ys[i], xs[i]), each at the frames frame_numbers[i, ...] (frame numbers in file order:
        the dot product of a leading-axes index with self.strides): float32 of frame_numbers' shape, in one gather
        (call it from the one thread that runs parallel numba)."""
        from .gather import gather

        fn = np.asarray(frame_numbers, np.int64)
        ys, xs = np.asarray(ys, np.int64), np.asarray(xs, np.int64)
        if fn.shape[:1] != ys.shape or ys.shape != xs.shape:
            raise ValueError(f"{len(ys)} pixels and frame numbers of shape {fn.shape}")
        if ((ys < 0) | (ys >= self.ny) | (xs < 0) | (xs >= self.nx)).any():
            raise IndexError(f"pixels outside {self.ny}x{self.nx}")
        if ((fn < 0) | (fn >= int(np.prod(self.shape[:-2], dtype=np.int64)))).any():
            raise IndexError(f"frame numbers outside {self.shape[:-2]}")
        it = self.layout.dtype.itemsize
        pix = ((ys * self.nx + xs) * it).reshape((-1,) + (1,) * (fn.ndim - 1))
        offs = (self.layout.offset + fn * self.frame_bytes + pix).ravel().astype(np.int64)
        out = np.empty(offs.size * it, np.uint8)
        with span("data.points.read"):
            if gather(self.fd, offs, it, out):
                raise ShortRead(f"short reads for {len(ys)} pixels in {self.layout.path}")
        return self.to_float32(out.view(self.layout.dtype).reshape(fn.shape))

    def to_float32(self, raw: np.ndarray) -> np.ndarray:
        lay = self.layout
        if not lay.scaled and lay.blank is None:
            return raw.astype(np.float32)               # a copy, native byte order
        out = raw.astype(np.float32)
        if lay.scaled:
            out = out * np.float32(lay.scale) + np.float32(lay.zero)
        if lay.blank is not None:
            out[raw == lay.blank] = np.nan
        return out

    def close(self) -> None:
        if self._own_pool:
            self.pool.shutdown(wait=True)
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
