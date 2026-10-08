"""Reading samples with explicit preads: the only module that holds file descriptors and computes offsets.

FrameReader reads a whole image (or a band of rows) of an image cube and returns native float32. Explicit
preadv, never numpy.memmap: on a cold cache memmap was 5x slower for a 2k frame (docs/measured.md). A frame is
read in `chunks` parts at once, the calling thread taking the first and a pool the others, so a pool thread
never waits on the pool; more than 4 parts does not help on StorNext.
In a cube of 4 Stokes every value read leaves with the negative-I rule applied (masking.py): NaN at every Stokes
where I is negative. read_raw and row_band give the values as stored; whoever converts them applies it.
"""
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ..obs import span
from . import masking
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
        self.gather_threads: int | None = None          # scattered reads: threads at most (None: as numba is set)
        self.stokes: int | None = None                  # the axis of 4 Stokes the negative-I rule masks along (Dataset)
        self.neg_i = masking.NegativeI()                # where I is negative, per frame of I read
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
        return self._read_raws([idx], chunks)[0]

    def _read_raws(self, idxs, chunks: int | None = None) -> list[np.ndarray]:
        """Frames as stored, each in `chunks` parts, every part at once: the calling thread takes the first and the
        pool the others; with one part per frame all on the calling thread (a pool thread never waits on the pool)."""
        fb, k = self.frame_bytes, self.chunks if chunks is None else max(1, int(chunks))
        step = -(-fb // k)
        raws = [np.empty((self.ny, self.nx), self.layout.dtype) for _ in idxs]
        parts = [(memoryview(raw).cast("B")[a:min(fb, a + step)], base + a)
                 for raw, base in zip(raws, (self.frame_offset(i) for i in idxs), strict=True)
                 for a in range(0, fb, step)]
        if k == 1:
            for v, at in parts:
                _preadv_exact(self.fd, v, at)
            return raws
        futs = [self.pool.submit(_preadv_exact, self.fd, v, at) for v, at in parts[1:]]
        _preadv_exact(self.fd, *parts[0])
        for f in futs:
            f.result()
        return raws

    def read(self, idx, chunks: int | None = None) -> np.ndarray:
        """The frame as native float32 in physical units (FITS BSCALE/BZERO applied, BLANK -> NaN, and NaN where
        I is negative in a cube of 4 Stokes). A frame of I keeps where it is negative (neg_i) for Q, U and V. With
        I's frame not read yet, Q, U or V reads it at the same time as its own, in parts on the pool as its own; a
        second asking for it meanwhile waits for it, unless it reads in one part (a pool thread: read ahead), and
        then reads it too."""
        with span("data.frame.read"):
            key = None if self.stokes is None else self.i_index(idx)
            if key is None:
                out = self.to_float32(self.read_raw(idx, chunks))
                if self.stokes is not None:                     # I: where it is negative, kept for Q, U and V
                    flat = masking.negative(out)
                    self.neg_i.put(tuple(int(i) for i in idx), flat)
                    out.reshape(-1)[flat] = np.nan
                return out
            got: list[np.ndarray] = []

            def both():
                raw, i = self._read_raws([idx, key], chunks)
                got.append(raw)
                return masking.negative(self.to_float32(i))

            k = self.chunks if chunks is None else max(1, int(chunks))
            flat = self.neg_i.get(key, both, wait=k > 1)
            out = self.to_float32(got[0] if got else self.read_raw(idx, chunks))
            out.reshape(-1)[flat] = np.nan
            return out

    def i_index(self, idx, free_axes=()) -> tuple | None:
        """The index of I's frame at idx's (t, lambda) when values at idx need I's from elsewhere to apply the
        negative-I rule: a cube of 4 Stokes, Stokes not among free_axes and not I. Else None."""
        s = self.stokes
        if s is None or s in free_axes or int(idx[s]) == 0:
            return None
        return tuple(0 if a == s else int(i) for a, i in enumerate(idx))

    def negative_i(self, idx) -> np.ndarray | None:
        """Sorted flat pixel indices where Stokes I is negative at the frame idx's (t, lambda); None when the rule
        does not apply (not 4 Stokes). From neg_i, else one read of I's frame in one part on the calling thread,
        which must not be one of the pool's."""
        if self.stokes is None:
            return None
        key = tuple(0 if a == self.stokes else int(i) for a, i in enumerate(idx))
        return self.neg_i.get(key, lambda: masking.negative(self.to_float32(self.read_raw(key, chunks=1))))

    def _masked(self, idx, v: np.ndarray, y0: int, y1: int, at=None) -> np.ndarray:
        """v, values of the frame idx at flat positions `at` of its rows y0..y1-1 (every one when None), with the
        negative-I rule applied in place: I's own for I; for Q, U, V I's from neg_i when it holds the frame, else
        from I's rows, one more read."""
        if self.stokes is None:
            return v
        key = self.i_index(idx)
        if key is None:
            return masking.mask_where(v, v)
        flat = self.neg_i.peek(key)
        pos = np.arange(v.size) if at is None else at
        if flat is not None:
            v.reshape(-1)[masking.in_sorted(flat, y0 * self.nx + pos)] = np.nan
            return v
        i = self.to_float32(self.read_rows_raw(key, y0, y1)).reshape(-1)
        return masking.mask_where(v, (i if at is None else i[at]).reshape(v.shape))

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
            return self._masked(j, self.to_float32(np.frombuffer(b, dt)[at]), y0, y1, at)

        idxs = list(idxs)
        if not idxs:
            return np.empty((0, at.size), np.float32)
        with span("data.bands.read"), ThreadPoolExecutor(max(1, min(threads, len(idxs)))) as ex:
            return np.stack(list(ex.map(one, idxs)))

    def read_rows(self, idx, y0: int, y1: int) -> np.ndarray:
        """Rows y0..y1-1 of a frame as native float32 in physical units, the negative-I rule applied."""
        return self._masked(idx, self.to_float32(self.read_rows_raw(idx, y0, y1)), y0, y1)

    def series_frames(self, idx, free_axes):
        """(sizes, frame numbers): the frames a series along free_axes (the other leading axes fixed at idx) reads,
        one per value, in axis order; frame numbers in file order."""
        free = sorted(int(a) for a in free_axes)
        idx = tuple(int(i) for i in idx)
        sizes = [self.shape[a] for a in free]
        fixed = sum(i * s for a, (i, s) in enumerate(zip(idx, self.strides, strict=True)) if a not in free)
        grid = np.zeros(sizes, np.int64)
        for k, a in enumerate(free):
            shp = [1] * len(sizes)
            shp[k] = sizes[k]
            grid = grid + np.arange(sizes[k], dtype=np.int64).reshape(shp) * self.strides[a]
        return sizes, (fixed + grid).ravel()

    def series(self, y: int, x: int, idx, free_axes) -> np.ndarray:
        """Values at pixel (y, x) along the leading axes in free_axes, the others fixed at idx: one dimension per
        free axis, in axis order (profile: (nl,), lambda-t: (nt, nl), everything: (nt, ns, nl)). Read from the
        file every time, in the numba reader's threads (call it from the one thread that runs parallel numba).
        A series of Q, U or V gathers I's in the same call, for the negative-I rule (twice the requests)."""
        from .gather import gather_limited

        if not 0 <= y < self.ny or not 0 <= x < self.nx:
            raise IndexError(f"pixel ({y}, {x}) outside {self.ny}x{self.nx}")
        sizes, fn = self.series_frames(idx, free_axes)
        n = fn.size
        if self.i_index(idx, free_axes) is not None:
            assert self.stokes is not None
            fn = np.concatenate([fn, fn - int(idx[self.stokes]) * self.strides[self.stokes]])
        it = self.layout.dtype.itemsize
        offs = (self.layout.offset + fn * self.frame_bytes + (int(y) * self.nx + int(x)) * it).astype(np.int64)
        out = np.empty(offs.size * it, np.uint8)
        with span("data.series.read"):
            if gather_limited(self.fd, offs, it, out, self.gather_threads):
                raise ShortRead(f"short reads for pixel ({y}, {x}) in {self.layout.path}")
        v = self.to_float32(out.view(self.layout.dtype))
        return self.mask_series(v[:n].reshape(sizes), idx, free_axes, v[n:].reshape(sizes) if v.size > n else None)

    def mask_series(self, v: np.ndarray, idx, free_axes, i: np.ndarray | None = None) -> np.ndarray:
        """The negative-I rule on a series v along free_axes (the other axes fixed at idx), in place: along the
        Stokes axis when it is free, else by I's series i (Q, U, V: i_index) or by v itself (I)."""
        s = self.stokes
        if s is None:
            return v
        free = sorted(int(a) for a in free_axes)
        if s in free:
            return masking.mask_along(v, free.index(s))
        if self.i_index(idx, free) is not None:
            if i is None:
                raise ValueError(f"a series at {tuple(idx)} needs I's values for the negative-I rule")
            return masking.mask_where(v, i)
        return masking.mask_where(v, v)

    def row_band(self, idx, free_axes, y0: int, y1: int) -> np.ndarray:
        """Rows y0..y1-1 of every frame a series along free_axes reads, as stored: (sizes..., y1 - y0, nx), one
        read per frame in the numba reader's threads (call it from the one thread that runs parallel numba). On
        StorNext a whole row per request costs what 4 bytes do (rowbands.py), so the series of every pixel in the
        rows comes with the one asked for."""
        from .gather import gather_limited

        if not 0 <= y0 < y1 <= self.ny:
            raise IndexError(f"rows {y0}..{y1} outside 0..{self.ny}")
        sizes, fn = self.series_frames(idx, free_axes)
        n = (y1 - y0) * self.nx * self.layout.dtype.itemsize
        offs = (self.layout.offset + fn * self.frame_bytes + y0 * self.nx * self.layout.dtype.itemsize)
        out = np.empty(offs.size * n, np.uint8)
        with span("data.rowband.read"):
            if gather_limited(self.fd, offs.astype(np.int64), n, out, self.gather_threads):
                raise ShortRead(f"short reads for rows {y0}..{y1} in {self.layout.path}")
        return out.view(self.layout.dtype).reshape(*sizes, y1 - y0, self.nx)

    def points(self, ys, xs, frame_numbers) -> np.ndarray:
        """Values at pixels (ys[i], xs[i]), each at the frames frame_numbers[i, ...] (frame numbers in file order:
        the dot product of a leading-axes index with self.strides): float32 of frame_numbers' shape, in one gather
        (call it from the one thread that runs parallel numba). The negative-I rule takes I's value from the same
        request when it holds it (a profile of every Stokes), else gathers the missing ones in a second call."""
        fn = np.asarray(frame_numbers, np.int64)
        ys, xs = np.asarray(ys, np.int64), np.asarray(xs, np.int64)
        if fn.shape[:1] != ys.shape or ys.shape != xs.shape:
            raise ValueError(f"{len(ys)} pixels and frame numbers of shape {fn.shape}")
        if ((ys < 0) | (ys >= self.ny) | (xs < 0) | (xs >= self.nx)).any():
            raise IndexError(f"pixels outside {self.ny}x{self.nx}")
        if ((fn < 0) | (fn >= int(np.prod(self.shape[:-2], dtype=np.int64)))).any():
            raise IndexError(f"frame numbers outside {self.shape[:-2]}")
        v = self._gather_points(ys, xs, fn)
        if self.stokes is None:
            return v
        st, ns = self.strides[self.stokes], self.shape[self.stokes]
        s = fn // st % ns
        pid = np.broadcast_to(np.arange(len(ys)).reshape((-1,) + (1,) * (fn.ndim - 1)), fn.shape)
        total = int(np.prod(self.shape[:-2], dtype=np.int64))
        key = (pid * total + fn).ravel()
        have = key[(s == 0).ravel()]
        order = np.argsort(have)
        have, have_v = have[order], v.ravel()[(s == 0).ravel()][order]
        want = (pid * total + fn - s * st).ravel()
        found = masking.in_sorted(have, want)
        i = np.empty(want.size, np.float32)
        i[found] = have_v[np.minimum(np.searchsorted(have, want[found]), have.size - 1)]
        miss = ~found
        if miss.any():
            p, f = pid.ravel()[miss], (fn - s * st).ravel()[miss]
            i[miss] = self._gather_points(ys[p], xs[p], f)
        return masking.mask_where(v, i.reshape(v.shape))

    def _gather_points(self, ys, xs, fn) -> np.ndarray:
        from .gather import gather_limited

        it = self.layout.dtype.itemsize
        pix = ((ys * self.nx + xs) * it).reshape((-1,) + (1,) * (fn.ndim - 1))
        offs = (self.layout.offset + fn * self.frame_bytes + pix).ravel().astype(np.int64)
        out = np.empty(offs.size * it, np.uint8)
        with span("data.points.read"):
            if gather_limited(self.fd, offs, it, out, self.gather_threads):
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
            out[raw == raw.dtype.type(lay.blank)] = np.nan  # a float blank compared at the file's precision
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
