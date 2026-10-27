"""Padding in 4-Stokes cubes: where Stokes I is negative the pixel lies outside the observation, and every value
there (I, Q, U and V) is no data, NaN, as the blank value (FITS BLANK, LP nan_rplcmnt) already is. Sample by
sample: I negative at one (t, lambda) blanks the four Stokes at that (t, lambda) only.

An intensity is never negative; SSTRED's padding value is. Aligning a cube to another line's grid (an
_im.aligned6173 cube) interpolates across the field's edge and smears that value into its neighbours: near
nan_rplcmnt but not equal to it (-1.76914732e-08, -1.76914714e-08, ... against -1.7691475e-08 in a Ca II 8542
cube, 0.2 % of a frame), so the exact test of the blank value (formats.lp_values) misses them, and Q, U and V
hold the same numbers as I there. Only cubes with exactly 4 Stokes: a cube of one Stokes may be a Doppler map
or a difference, negative by nature, and maps (B, v) have no Stokes axis.

Applied where values leave the data layer: FrameReader (frames, rows, slit bands, series, points), RowBands, the
per-pixel readers and the Q U V ranges (stats.quv_amplitude_ranges). Q, U and V need I at the same (t, lambda):
a block or a series holding every Stokes has it already; a series of one of them reads I's along with it; a
frame takes the pixels where I is negative from NegativeI, filled by every frame of I read, else reads I's
frame at the same time as its own.
"""
import threading
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future

import numpy as np

STOKES = 4                  # the rule holds for cubes of exactly I, Q, U, V
MAX_BYTES = 32 << 20        # NegativeI: 0.2 % of a 2k frame is ~34 kB of indices


def stokes_axis(roles) -> int | None:
    """The leading axis the rule masks along (Stokes I at its index 0), or None when the cube has not 4 Stokes (an
    inversion's parameters are not: data.axes.Roles.planes)."""
    planes = getattr(roles, "planes", "stokes")
    return roles.s if roles.s is not None and roles.ns == STOKES and planes == "stokes" else None


def mask_along(a: np.ndarray, axis: int) -> np.ndarray:
    """In place: every Stokes NaN where I (index 0 along axis) is negative. Returns a."""
    neg = np.take(a, [0], axis=axis) < 0
    if neg.any():
        a[np.broadcast_to(neg, a.shape)] = np.nan
    return a


def mask_where(a: np.ndarray, i: np.ndarray) -> np.ndarray:
    """In place: a NaN where i, I's values at the same samples, is negative. Returns a."""
    a[i < 0] = np.nan
    return a


def negative(i: np.ndarray) -> np.ndarray:
    """The sorted flat indices where i is negative (int32 below 2**31 values). Its minimum first, NaN ignored: with
    nothing negative, one pass of 0.28 ms on a 2k frame against 1.5 ms for the comparison (Mac, page cache); with
    a border, 2.4 ms (numba measured no better: 2.1 ms)."""
    flat = i.reshape(-1)
    if not flat.size or not np.fmin.reduce(flat) < 0:
        return np.empty(0, np.int32)
    idx = np.flatnonzero(flat < 0)
    return idx.astype(np.int32) if flat.size < 2 ** 31 else idx


def in_sorted(sorted_idx: np.ndarray, pos: np.ndarray) -> np.ndarray:
    """Bool over pos: True where the value is in sorted_idx."""
    n = sorted_idx.size
    if not n:
        return np.zeros(np.shape(pos), bool)
    j = np.minimum(np.searchsorted(sorted_idx, pos), n - 1)
    return sorted_idx[j] == pos


class NegativeI:
    """Where Stokes I is negative, per frame of I (its leading-axes index): sorted flat pixel indices, an LRU within
    max_bytes. A frame computed on another thread is waited for, never read twice: the 2x2 view asks for I, Q, U
    and V at once. Thread-safe."""

    def __init__(self, max_bytes: int = MAX_BYTES):
        self.max_bytes = int(max_bytes)
        self._lru: OrderedDict = OrderedDict()
        self._bytes = 0
        self._busy: dict[tuple, Future] = {}
        self._lock = threading.Lock()

    def peek(self, key: tuple):
        with self._lock:
            got = self._lru.get(key)
            if got is not None:
                self._lru.move_to_end(key)
            return got

    def put(self, key: tuple, flat: np.ndarray) -> None:
        with self._lock:
            if key not in self._lru:
                self._lru[key] = flat
                self._bytes += flat.nbytes
                while self._bytes > self.max_bytes and self._lru:
                    self._bytes -= self._lru.popitem(last=False)[1].nbytes

    def get(self, key: tuple, compute: Callable[[], np.ndarray], wait: bool = True) -> np.ndarray:
        """Cached, being computed on another thread (waited for when `wait`, else computed again), or compute() now
        on the calling thread. A thread of the pool that compute() may use passes wait False: never waiting, it
        never holds a thread that compute() needs."""
        with self._lock:
            got = self._lru.get(key)
            if got is not None:
                self._lru.move_to_end(key)
                return got
            busy = self._busy.get(key)
            if busy is None:
                mine: Future = Future()
                self._busy[key] = mine
        if busy is not None:
            if wait:
                return busy.result()
            flat = compute()
            self.put(key, flat)
            return flat
        try:
            flat = compute()
        except BaseException as e:
            with self._lock:
                self._busy.pop(key, None)
            mine.set_exception(e)
            raise
        self.put(key, flat)
        with self._lock:
            self._busy.pop(key, None)
        mine.set_result(flat)
        return flat

    def nbytes(self) -> int:
        return self._bytes

    def clear(self) -> None:
        with self._lock:
            self._lru.clear()
            self._bytes = 0
