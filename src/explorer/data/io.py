"""Reading samples with explicit preads: the only module that holds file descriptors and computes offsets.

FrameReader reads a whole image (or a band of rows) of an image cube and returns native float32. Explicit
preadv, never numpy.memmap: on a cold cache memmap was 5x slower for a 2k frame (docs/measured.md). A frame is
read in `chunks` parts at once, the calling thread taking the first and a pool the others, so a pool thread
never waits on the pool; more than 4 parts does not help on StorNext.
In a cube of 4 Stokes every value read leaves with the negative-I rule applied (masking.py): NaN at every Stokes
where I is negative. read_raw and row_band give the values as stored; whoever converts them applies it.
abort() stops the reads made of many steps (a pass over a per-pixel file, the files of a series, the frames along
a slit) at their next step: a window closed with one of them in flight closes without waiting for it.
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import numpy as np

from ..obs import span
from . import masking
from .formats import Layout, SeriesLayout


class Closing:
    """`with x:` closes x at the end: the readers, a mask, a dataset, a driver."""

    def close(self) -> None:
        raise NotImplementedError

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class ShortRead(OSError):
    """The file returned fewer bytes than asked for: truncated file, or an I/O error on network storage."""


class ReadAborted(Exception):
    """A read stopped between two of its steps: its reader was aborted (FrameReader.abort), the cube is closing."""


def _preadv_exact(fd, view, offset):
    n = os.preadv(fd, [view], offset)
    if n != len(view):
        raise ShortRead(f"read {n} of {len(view)} bytes at offset {offset}")


class FrameReader(Closing):
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
        self._aborted = threading.Event()

    def abort(self) -> None:
        """From now on every read of many steps raises ReadAborted at its next step, and every new one at once:
        closing does not wait for a long read in flight. For good: the reader is being closed."""
        self._aborted.set()

    def _step(self) -> None:
        """Between two steps of a long read: raise ReadAborted once abort() was called."""
        if self._aborted.is_set():
            raise ReadAborted(f"reading {self.layout.path} stopped: closing")

    def frame_offset(self, idx) -> int:
        idx = tuple(int(i) for i in idx)
        if len(idx) != len(self.strides) or any(not 0 <= i < n for i, n in zip(idx, self.shape[:-2], strict=True)):
            raise IndexError(f"frame index {idx} outside {self.shape[:-2]}")
        return self.layout.offset + sum(i * s for i, s in zip(idx, self.strides, strict=True)) * self.frame_bytes

    def playback_cap(self) -> float | None:
        """Frames a second that reading can deliver when that, not the screen, bounds playback; None when the
        reads overlap (preads on the read-ahead's threads) and nothing is known to bound it."""
        return None

    def sample_at(self, k: int, y: int, x: int) -> tuple[int, int]:
        """(file descriptor, byte offset) of pixel (y, x) of frame number k (file order): where the storage probe
        times a small read."""
        return self.fd, self.layout.offset + k * self.frame_bytes + (y * self.nx + x) * self.layout.dtype.itemsize

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

    def _rows(self, y0: int, y1: int) -> None:
        """IndexError unless rows y0..y1-1 are in the image."""
        if not 0 <= y0 < y1 <= self.ny:
            raise IndexError(f"rows {y0}..{y1} outside 0..{self.ny}")

    def read_rows_raw(self, idx, y0: int, y1: int) -> np.ndarray:
        """Rows y0..y1-1 of a frame as stored, one read: the band a slit crosses, without the rest of the image.
        Read-only (a view of the bytes read): os.pread into bytes costs 7-15 us less per band than preadv into a
        new numpy array, and a slit reads one band per frame (bellatrix, 3.9 MB bands, pinned to one NUMA node)."""
        self._rows(y0, y1)
        n = (y1 - y0) * self.nx * self.layout.dtype.itemsize
        b = os.pread(self.fd, n, self.frame_offset(idx) + y0 * self.nx * self.layout.dtype.itemsize)
        if len(b) != n:
            raise ShortRead(f"read {len(b)} of {n} bytes of rows {y0}..{y1} in {self.layout.path}")
        return np.frombuffer(b, self.layout.dtype).reshape(y1 - y0, self.nx)

    def band_values(self, idxs, y0: int, y1: int, at, threads: int = 8) -> np.ndarray:
        """For each frame index in idxs, rows y0..y1-1, then the values at flat positions `at` in that band:
        (len(idxs), len(at)) float32 in physical units. The values along a slit without a per-pixel file."""
        self._rows(y0, y1)
        at = np.asarray(at, np.int64)
        if at.size and not (0 <= at.min() and at.max() < (y1 - y0) * self.nx):
            raise IndexError(f"positions outside a band of {y1 - y0} rows of {self.nx}")
        idxs = list(idxs)
        if not idxs:
            return np.empty((0, at.size), np.float32)
        return self._band_values(idxs, y0, y1, at, threads)

    def _band_values(self, idxs: list, y0: int, y1: int, at: np.ndarray, threads: int) -> np.ndarray:
        """band_values, checked: one read of the rows per frame, on `threads` threads started for the call. Each
        worker computes its frame's offset and converts its own values, as the prototype's read_slit_bands does:
        with 16 workers a leaner one (offsets computed up front) measured 8-15 % slower, the reads then contending
        harder for the GIL (bellatrix, 186 frames of 3.9 MB, pinned to one NUMA node)."""
        isz = self.layout.dtype.itemsize
        n = (y1 - y0) * self.nx * isz
        skip = y0 * self.nx * isz
        fd, dt = self.fd, self.layout.dtype

        def one(j):
            self._step()
            b = os.pread(fd, n, self.frame_offset(j) + skip)
            if len(b) != n:
                raise ShortRead(f"read {len(b)} of {n} bytes of frame {j} in {self.layout.path}")
            return self._masked(j, self.to_float32(np.frombuffer(b, dt)[at]), y0, y1, at)

        with span("data.bands.read"), ThreadPoolExecutor(max(1, min(threads, len(idxs)))) as ex:
            return np.stack(list(ex.map(one, idxs)))

    def read_rows(self, idx, y0: int, y1: int) -> np.ndarray:
        """Rows y0..y1-1 of a frame as native float32 in physical units, the negative-I rule applied."""
        return self._masked(idx, self.to_float32(self.read_rows_raw(idx, y0, y1)), y0, y1)

    def series_frames(self, idx, free_axes, at=None):
        """(sizes, frame numbers): the frames a series along free_axes (the other leading axes fixed at idx) reads,
        one per value, in axis order; frame numbers in file order. at: {axis: indices} reads only those along a free
        axis (data.tsample: the t steps a temporal panel shows)."""
        free = sorted(int(a) for a in free_axes)
        idx = tuple(int(i) for i in idx)
        along = {a: np.asarray(at[a], np.int64) if at and a in at else np.arange(self.shape[a], dtype=np.int64)
                 for a in free}
        sizes = [len(along[a]) for a in free]
        fixed = sum(i * s for a, (i, s) in enumerate(zip(idx, self.strides, strict=True)) if a not in free)
        grid = np.zeros(sizes, np.int64)
        for k, a in enumerate(free):
            shp = [1] * len(sizes)
            shp[k] = sizes[k]
            grid = grid + along[a].reshape(shp) * self.strides[a]
        return sizes, (fixed + grid).ravel()

    def series(self, y: int, x: int, idx, free_axes, at=None) -> np.ndarray:
        """Values at pixel (y, x) along the leading axes in free_axes, the others fixed at idx: one dimension per
        free axis, in axis order (profile: (nl,), lambda-t: (nt, nl), everything: (nt, ns, nl)); at: only those
        indices along an axis (series_frames). Read from the file every time, in the numba reader's threads (call it
        from the one thread that runs parallel numba).
        A series of Q, U or V gathers I's in the same call, for the negative-I rule (twice the requests)."""
        if not 0 <= y < self.ny or not 0 <= x < self.nx:
            raise IndexError(f"pixel ({y}, {x}) outside {self.ny}x{self.nx}")
        sizes, fn = self.series_frames(idx, free_axes, at)
        n = fn.size
        if self.i_index(idx, free_axes) is not None:
            assert self.stokes is not None
            fn = np.concatenate([fn, fn - int(idx[self.stokes]) * self.strides[self.stokes]])
        v = self._pixel_values(y, x, fn)
        return self.mask_series(v[:n].reshape(sizes), idx, free_axes, v[n:].reshape(sizes) if v.size > n else None)

    def _pixel_values(self, y: int, x: int, fn: np.ndarray) -> np.ndarray:
        """Pixel (y, x) of frames number fn, float32 in physical units: one gathered request per frame."""
        from .gather import gather_limited

        it = self.layout.dtype.itemsize
        offs = (self.layout.offset + fn * self.frame_bytes + (int(y) * self.nx + int(x)) * it).astype(np.int64)
        out = np.empty(offs.size * it, np.uint8)
        with span("data.series.read"):
            if gather_limited(self.fd, offs, it, out, self.gather_threads):
                raise ShortRead(f"short reads for pixel ({y}, {x}) in {self.layout.path}")
        return self.to_float32(out.view(self.layout.dtype))

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

    def row_band(self, idx, free_axes, y0: int, y1: int, at=None) -> np.ndarray:
        """Rows y0..y1-1 of every frame a series along free_axes (at: series_frames) reads, as stored: (sizes...,
        y1 - y0, nx), one read per frame in the numba reader's threads (call it from the one thread that runs
        parallel numba). On StorNext a whole row per request costs what 4 bytes do (rowbands.py), so the series of
        every pixel in the rows comes with the one asked for."""
        from .gather import gather_limited

        self._rows(y0, y1)
        sizes, fn = self.series_frames(idx, free_axes, at)
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



def image_of_per_pixel(sp: Layout) -> Layout:
    """The image cube a per-pixel file holds, as its _im would be laid out: numpy (y, x, s, t, lambda) read as
    (t, s, lambda, y, x), each axis keeping its name; offset, dtype and values as the per-pixel file's. Only a
    description: PerPixelFrames reads it."""
    if len(sp.shape) != 5:
        raise ValueError(f"{sp.path}: a per-pixel file has 5 axes (y, x, s, t, lambda), not {sp.shape}")
    ny, nx, ns, nt, nl = sp.shape
    a = sp.axes
    return replace(sp, shape=(nt, ns, nl, ny, nx), axes=(a[3], a[2], a[4], a[0], a[1]))


class PerPixelFrames(FrameReader):
    """Images of a cube read from its per-pixel file alone (numpy (y, x, s, t, lambda), SSTRED's _sp.fits), with no
    image cube beside it. A pixel's record (ns * nt * nl samples) is smaller than a page in SSTRED's files (2940
    bytes in Halpha 6563, 1470 in its .icube), so the samples of one image are on every page of the file: an image
    is one pass over the whole file, read in blocks of rows (`block` bytes at most, plus the images asked for), and
    the images asked for together come out of the same pass. 4-26 s an image against 5-21 ms from the _im
    (bench/sp_frames.py, bellatrix). Values at one pixel (series, points) are one read of its record, as the
    per-pixel reader's. passes: seconds of each pass, the latest last."""

    BLOCK = 64 << 20
    cap_reason = "frames read from the per-pixel file in"      # what bounds playback (playback_cap), for the window

    def __init__(self, sp: Layout, pool: ThreadPoolExecutor | None = None, chunks: int = 4, block: int = BLOCK):
        super().__init__(image_of_per_pixel(sp), pool=pool, chunks=chunks)
        self.sp = sp
        self.nt, self.ns, self.nl = self.shape[:3]
        self.record = self.ns * self.nt * self.nl * sp.dtype.itemsize
        self.block_rows = max(1, int(block) // (self.nx * self.record))
        self.passes: list[float] = []
        self._ready: dict[tuple, np.ndarray] = {}       # frames as stored from the pass of read_many, while it runs

    def _record_pos(self, fn) -> np.ndarray:
        """Position in a pixel's record (s, t, lambda) of image frame numbers fn (file order of the _im)."""
        fn = np.asarray(fn, np.int64)
        t, s, lam = fn // (self.ns * self.nl), fn // self.nl % self.ns, fn % self.nl
        return (s * self.nt + t) * self.nl + lam

    def _frame_number(self, idx) -> int:
        idx = tuple(int(i) for i in idx)
        if len(idx) != 3 or any(not 0 <= i < n for i, n in zip(idx, self.shape[:3], strict=True)):
            raise IndexError(f"frame index {idx} outside {self.shape[:-2]}")
        return sum(i * s for i, s in zip(idx, self.strides, strict=True))

    def frame_offset(self, idx) -> int:
        raise NotImplementedError("an image of a per-pixel file is spread over the whole file")

    def sample_at(self, k: int, y: int, x: int) -> tuple[int, int]:
        pos = int(self._record_pos(k))
        return self.fd, self.sp.offset + (y * self.nx + x) * self.record + pos * self.sp.dtype.itemsize

    def rows_raw(self, y0: int, y1: int) -> np.ndarray:
        """Raw records of rows y0..y1-1, (rows, nx, ns * nt * nl) as stored, one read."""
        n = (y1 - y0) * self.nx * self.record
        b = os.pread(self.fd, n, self.sp.offset + y0 * self.nx * self.record)
        if len(b) != n:
            raise ShortRead(f"read {len(b)} of {n} bytes of rows {y0}..{y1} in {self.sp.path}")
        return np.frombuffer(b, self.sp.dtype).reshape(y1 - y0, self.nx, -1)

    def frames_rows(self, fns, y0: int, y1: int) -> np.ndarray:
        """Rows y0..y1-1 of the image frames fns (file order of the _im) as stored, (len(fns), rows, nx), in one
        pass over those rows, blocks of block_rows at a time. A pass over every row is timed into passes."""
        pos = self._record_pos(fns)
        out = np.empty((pos.size, y1 - y0, self.nx), self.sp.dtype)
        q = time.perf_counter()
        with span("data.sp_frames.pass"):
            for a in range(y0, y1, self.block_rows):
                self._step()
                b = min(y1, a + self.block_rows)
                out[:, a - y0:b - y0] = self.rows_raw(a, b)[:, :, pos].transpose(2, 0, 1)
        if y1 - y0 == self.ny:
            self.passes.append(time.perf_counter() - q)
        return out

    def _read_raws(self, idxs, chunks: int | None = None) -> list[np.ndarray]:
        idxs = [tuple(int(i) for i in j) for j in idxs]
        ready = self._ready
        miss = list(dict.fromkeys(j for j in idxs if j not in ready))
        got = (dict(zip(miss, self.frames_rows([self._frame_number(j) for j in miss], 0, self.ny), strict=True))
               if miss else {})
        return [ready[j] if j in ready else got[j] for j in idxs]

    def read_many(self, idxs, join=None) -> dict[tuple, np.ndarray]:
        """The frames at idxs, each as read() gives it, from one pass over the file, by index; in a cube of 4 Stokes
        the frames of I their negative-I rule needs come out of the same pass. join: called between two blocks, the
        frames asked for meanwhile (indices), which join the pass from that block on; their rows before it are read
        after it. A frame asked for while a pass runs then costs one pass's reading, not the rest of that pass and a
        whole other one. Called from one thread at a time (the image thread): other threads' reads meanwhile may
        take frames from this pass, never wrong ones."""
        def with_i(js) -> list[tuple]:
            js = [tuple(int(i) for i in j) for j in js]
            if self.stokes is not None:
                js += [k for k in (self.i_index(j) for j in js) if k is not None]
            return js

        asked = [tuple(int(i) for i in j) for j in idxs]
        raw: dict[tuple, np.ndarray] = {}
        start: dict[tuple, int] = {}                    # the first row each frame was read from in this pass

        def add(js, a: int) -> None:
            for j in with_i(js):
                if j not in raw:
                    self._frame_number(j)               # an index outside the cube raises here, before any read
                    raw[j], start[j] = np.empty((self.ny, self.nx), self.sp.dtype), a

        def fill(a: int, b: int, keys) -> None:
            pos = self._record_pos([self._frame_number(j) for j in keys])
            block = self.rows_raw(a, b)[:, :, pos]
            for k, j in enumerate(keys):
                raw[j][a:b] = block[:, :, k]

        add(asked, 0)
        q = time.perf_counter()
        with span("data.sp_frames.pass"):
            for a in range(0, self.ny, self.block_rows):
                self._step()
                if join is not None and a:
                    more = [tuple(int(i) for i in j) for j in join()]
                    asked += [j for j in more if j not in asked]
                    add(more, a)
                fill(a, min(self.ny, a + self.block_rows), list(raw))
            self.passes.append(time.perf_counter() - q)
            late = [j for j in raw if start[j]]
            for a in range(0, max((start[j] for j in late), default=0), self.block_rows):
                self._step()                            # the rows the frames that joined missed: the start's blocks
                fill(a, a + self.block_rows, [j for j in late if start[j] > a])
        self._ready = raw
        try:
            return {j: self.read(j) for j in asked}
        finally:
            self._ready = {}

    def read_rows_raw(self, idx, y0: int, y1: int) -> np.ndarray:
        self._rows(y0, y1)
        return self.frames_rows([self._frame_number(idx)], y0, y1)[0]

    def _band_values(self, idxs: list, y0: int, y1: int, at: np.ndarray, threads: int) -> np.ndarray:
        raw = self.frames_rows([self._frame_number(j) for j in idxs], y0, y1).reshape(len(idxs), -1)[:, at]
        return np.stack([self._masked(j, self.to_float32(r), y0, y1, at) for j, r in zip(idxs, raw, strict=True)])

    def row_band(self, idx, free_axes, y0: int, y1: int, at=None) -> np.ndarray:
        self._rows(y0, y1)
        sizes, fn = self.series_frames(idx, free_axes, at)
        return self.frames_rows(fn, y0, y1).reshape(*sizes, y1 - y0, self.nx)

    def _pixel_record(self, y: int, x: int) -> np.ndarray:
        b = os.pread(self.fd, self.record, self.sp.offset + (int(y) * self.nx + int(x)) * self.record)
        if len(b) != self.record:
            raise ShortRead(f"read {len(b)} of {self.record} bytes of pixel ({y}, {x}) in {self.sp.path}")
        return np.frombuffer(b, self.sp.dtype)

    def _pixel_values(self, y: int, x: int, fn: np.ndarray) -> np.ndarray:
        with span("data.series.read"):
            return self.to_float32(self._pixel_record(y, x)[self._record_pos(fn)])

    def _gather_points(self, ys, xs, fn) -> np.ndarray:
        with span("data.points.read"):
            raw = np.stack([self._pixel_record(y, x)[self._record_pos(f)] for y, x, f in zip(ys, xs, fn, strict=True)])
        return self.to_float32(raw.reshape(fn.shape))

    def playback_cap(self) -> float | None:
        """One image per pass: one over the latest pass's seconds, once one was timed."""
        return 1.0 / max(1e-6, self.passes[-1]) if self.passes else None

    def throughput(self, reads: int = 4, nbytes: int = 8 << 20) -> float:
        """Bytes a second read from this file now: `reads` reads of nbytes spread over it, timed. Optimistic when the
        file is in the page cache; the first pass then says what a pass costs (passes)."""
        size = self.sp.nbytes
        n = min(nbytes, size)
        q = time.perf_counter()
        for k in range(reads):
            at = self.sp.offset + (size - n) * k // max(1, reads - 1)
            os.pread(self.fd, n, at)
        return reads * n / max(1e-6, time.perf_counter() - q)


# compressed files kept open after a read: astropy keeps each one's compressed table in memory once read from it
# (3900 AIA files of 1986x1986 held 4.9 GB, 1.3 MB a file), so the latest few, not all; another is opened again
# (astropy reads its header: 7-10 ms)
KEEP_OPEN = 16
DECODES_KEPT = 8            # whole-frame decompressions the playback cap is the median of


# a series' descriptors are moved to FD_FLOOR and above, out of select()'s range (FD_SETSIZE, 1024 on Linux and
# macOS): python-xlib waits on its connection with select (the resize outline's, platform.xoutline), and a series
# of 1100 plain files left the next connection at descriptor 1103: "filedescriptor out of range in select()"
FD_FLOOR = 1024


def _above_select(fd: int) -> int:
    """fd moved to FD_FLOOR or above (close-on-exec, as os.open's), or kept where it is when the limit does not
    reach that far."""
    import fcntl

    try:
        high = fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, FD_FLOOR)
    except OSError:
        return fd
    os.close(fd)
    return high


def _room_for_files(n: int, spare: int = 256) -> None:
    """Raise this process's soft limit of open files to hold n more (macOS starts shells at 256), up to the hard
    limit; where it cannot be raised, opening fails later with the system's message."""
    import resource

    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    want = n + spare
    if soft == resource.RLIM_INFINITY or soft >= want:
        return
    top = want if hard == resource.RLIM_INFINITY else min(want, hard)
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (max(soft, top), hard))
    except (ValueError, OSError):
        pass


class SeriesReader(FrameReader):
    """Images of a file series (formats.SeriesLayout): frame t is file t's image. Plain images are read with
    preads at each file's data offset, a frame in parts as FrameReader's; tile-compressed ones are decompressed,
    whole or the rows asked for (astropy's section), one read at a time per file. Values along t (a pixel, a band
    of rows) take one read per file, on threads started for the call: the files have no common offset to gather
    from in one request."""

    layout: SeriesLayout
    cap_reason = "frames decompressed in"

    def __init__(self, layout: SeriesLayout, pool: ThreadPoolExecutor | None = None, chunks: int = 4,
                 threads: int = 16):
        _room_for_files(FD_FLOOR + len(layout.paths))
        super().__init__(layout, pool=pool, chunks=chunks)
        # plain: a descriptor per file (layout.path is the first); compressed: astropy's, opened at the first read
        self.fd = _above_select(self.fd)
        self.fds = [self.fd] + ([] if layout.compressed else
                                [_above_select(os.open(p, os.O_RDONLY)) for p in layout.paths[1:]])
        self.threads = max(1, int(threads))
        self._decode_s: list[float] = []               # the latest whole-frame decompressions, seconds
        if layout.compressed:
            import threading
            from collections import OrderedDict

            self._open: OrderedDict = OrderedDict()     # t -> its HDUList, the latest used last
            # one decompression at a time: astropy's holds the GIL, and several at once slowed each other down far
            # beyond their sum (playing 300 AIA files: a frame read took 2.6 s, 3.7 images a second shown, against
            # 0.12 s a frame one at a time; bellatrix, 2026-10-10)
            self._decoding = threading.Lock()

    def _t(self, idx) -> int:
        idx = tuple(int(i) for i in np.atleast_1d(idx))
        if len(idx) != 1 or not 0 <= idx[0] < self.shape[0]:
            raise IndexError(f"frame index {idx} outside {self.shape[:-2]}")
        return idx[0]

    def frame_offset(self, idx) -> int:
        return self.layout.offsets[self._t(idx)]

    def sample_at(self, k: int, y: int, x: int) -> tuple[int, int]:
        if self.layout.compressed:                      # the first file's table: a small read on its storage
            return self.fd, self.layout.offsets[0]
        return self.fds[k], self.layout.offsets[k] + (y * self.nx + x) * self.layout.dtype.itemsize

    def _decompressed(self, t: int, rows: slice | None = None, x: int | None = None, timed=False) -> np.ndarray:
        """File t's image as stored (BSCALE, BZERO not applied), its rows `rows` (all when None), or its pixel x
        of those rows. timed: a whole frame, its time (once its turn came) kept for playback_cap."""
        from astropy.io import fits

        self._step()
        with self._decoding:
            self._step()                                # the threads that waited for the lock stop here
            q = time.perf_counter()
            h = self._open.pop(t, None)
            if h is None:
                h = fits.open(self.layout.paths[t], memmap=False, do_not_scale_image_data=True)
            self._open[t] = h                           # the latest used last
            while len(self._open) > KEEP_OPEN:
                self._open.popitem(last=False)[1].close()
            # through section, never .data: astropy keeps .data (a whole image per file, outside the cache's
            # budget: +1044 MB after 30 frames of 4096x4096, against +37 MB through section)
            sec = h[self.layout.hdus[t]].section
            lead = (0,) * (len(sec.shape) - 2)         # the axes of length 1 before (y, x), as series_layout drops
            a = sec[(*lead, slice(None), slice(None))] if rows is None else sec[(*lead, rows)] if x is None \
                else sec[(*lead, rows, x)]
            if timed:
                self._decode_s = (self._decode_s + [time.perf_counter() - q])[-DECODES_KEPT:]
        return np.asarray(a).astype(self.layout.dtype, copy=False)

    def _read_raws(self, idxs, chunks: int | None = None) -> list[np.ndarray]:
        if not self.layout.compressed:
            return [self._read_plain(i, chunks) for i in idxs]
        return [self._decompressed(self._t(i), timed=True).reshape(self.ny, self.nx) for i in idxs]

    def playback_cap(self) -> float | None:
        """Compressed: one over the median of the latest frames' decompression, one at a time whatever the
        threads (astropy's Rice decompression holds the GIL: 8 AIA frames of 1986x1986 took 996 ms one after
        another, 1207 ms on 4 threads; bellatrix, 2026-10-10). None before a frame is read, and for plain files."""
        if not self._decode_s:
            return None
        return 1.0 / max(1e-6, float(np.median(self._decode_s)))

    def _read_plain(self, idx, chunks):
        t = self._t(idx)
        fb, k = self.frame_bytes, self.chunks if chunks is None else max(1, int(chunks))
        step = -(-fb // k)
        raw = np.empty((self.ny, self.nx), self.layout.dtype)
        parts = [(memoryview(raw).cast("B")[a:min(fb, a + step)], self.layout.offsets[t] + a)
                 for a in range(0, fb, step)]
        fd = self.fds[t]
        futs = [self.pool.submit(_preadv_exact, fd, v, at) for v, at in parts[1:]] if k > 1 else []
        for v, at in parts if k == 1 else parts[:1]:
            _preadv_exact(fd, v, at)
        for f in futs:
            f.result()
        return raw

    def read_rows_raw(self, idx, y0: int, y1: int) -> np.ndarray:
        self._rows(y0, y1)
        t = self._t(idx)
        if self.layout.compressed:
            return self._decompressed(t, slice(y0, y1)).reshape(y1 - y0, self.nx)
        it = self.layout.dtype.itemsize
        n = (y1 - y0) * self.nx * it
        b = os.pread(self.fds[t], n, self.layout.offsets[t] + y0 * self.nx * it)
        if len(b) != n:
            raise ShortRead(f"read {len(b)} of {n} bytes of rows {y0}..{y1} in {self.layout.paths[t]}")
        return np.frombuffer(b, self.layout.dtype).reshape(y1 - y0, self.nx)

    def _pixel_raw(self, t: int, y: int, x: int):
        if self.layout.compressed:
            return self._decompressed(t, slice(y, y + 1), x).reshape(-1)[0]
        it = self.layout.dtype.itemsize
        b = os.pread(self.fds[t], it, self.layout.offsets[t] + (y * self.nx + x) * it)
        if len(b) != it:
            raise ShortRead(f"read {len(b)} of {it} bytes of pixel ({y}, {x}) in {self.layout.paths[t]}")
        return np.frombuffer(b, self.layout.dtype)[0]

    def _map(self, fn, items) -> list:
        items = list(items)

        def step(i):
            self._step()
            return fn(i)

        if len(items) <= 1:
            return [step(i) for i in items]
        with ThreadPoolExecutor(min(self.threads, len(items))) as ex:
            return list(ex.map(step, items))

    def _band_values(self, idxs: list, y0: int, y1: int, at: np.ndarray, threads: int) -> np.ndarray:
        with span("data.bands.read"):
            return np.stack(self._map(lambda j: self.to_float32(self.read_rows_raw(j, y0, y1).reshape(-1)[at]),
                                      idxs))

    def _pixel_values(self, y: int, x: int, fn: np.ndarray) -> np.ndarray:
        with span("data.series.read"):
            raw = np.array(self._map(lambda t: self._pixel_raw(int(t), int(y), int(x)), fn), self.layout.dtype)
        return self.to_float32(raw)

    def row_band(self, idx, free_axes, y0: int, y1: int, at=None) -> np.ndarray:
        sizes, fn = self.series_frames(idx, free_axes, at)
        with span("data.rowband.read"):
            out = np.stack(self._map(lambda t: self.read_rows_raw((int(t),), y0, y1), fn))
        return out.reshape(*sizes, y1 - y0, self.nx)

    def _gather_points(self, ys, xs, fn) -> np.ndarray:
        pid = np.broadcast_to(np.arange(len(ys)).reshape((-1,) + (1,) * (fn.ndim - 1)), fn.shape).ravel()
        with span("data.points.read"):
            raw = np.array(self._map(lambda k: self._pixel_raw(int(fn.ravel()[k]), int(ys[pid[k]]), int(xs[pid[k]])),
                                     range(fn.size)), self.layout.dtype)
        return self.to_float32(raw.reshape(fn.shape))

    def close(self) -> None:
        for h in getattr(self, "_open", {}).values():
            h.close()
        for fd in getattr(self, "fds", ())[1:]:
            os.close(fd)
        self.fds = []
        super().close()
