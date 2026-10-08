"""Series without a per-pixel file, a row at a time: the lambda-t or the spectrum of one pixel is read with the
whole row it lies in, and every pixel of that row is then served from memory.

On StorNext a read costs per request, not per byte, for small reads: the lambda-t of the 6173 cube is 2604 requests
(one per frame), and with the whole row (8 kB) per request instead of 4 bytes its first read cost the same (1.009,
explorer faster in 4/8, bellatrix); the pixel next to it then takes 0.10 ms from memory, against 17.6 ms from the
system's cache or 0.3-1.4 s from the storage. Blocks of 8 rows (64 kB) cost the first read 34 % more when the
storage was fast (1.339, 1/8) and nothing when it was slow (0.96x), docs/journal.md: one row, which serves every
horizontal move, is the default. Blocks are aligned (rows [k*rows, (k+1)*rows)). On local disks bytes are not free:
Dataset uses this on network storage only.
A series of Q, U or V in a cube of 4 Stokes needs I's for the negative-I rule (masking.py): I's block of rows is
kept beside it, in the same LRU, so the pixels along the row find both in memory.
"""
import threading
from collections import OrderedDict

import numpy as np

from .io import FrameReader

ROWS = 1


class RowBands:
    """LRU of blocks of rows per series (the fixed index and the free axes), within a byte budget; values identical to
    FrameReader.series."""

    def __init__(self, frames: FrameReader, rows: int = ROWS, max_bytes: int = 1 << 30):
        self.frames, self.rows, self.max_bytes = frames, max(1, int(rows)), int(max_bytes)
        self._lru: OrderedDict = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def _key(self, y, idx, free_axes):
        free = tuple(sorted(int(a) for a in free_axes))
        fixed = tuple(-1 if a in free else int(i) for a, i in enumerate(idx))
        return fixed, free, int(y) // self.rows

    def _band(self, y, idx, free_axes, read: bool):
        """The block of rows around y for the series at idx along free_axes: in memory, else read when `read` (else
        None)."""
        key = self._key(y, idx, free_axes)
        with self._lock:
            band = self._lru.get(key)
            if band is not None:
                self._lru.move_to_end(key)
                return band
        if not read:
            return None
        y0 = int(y) // self.rows * self.rows
        band = self.frames.row_band(idx, free_axes, y0, min(self.frames.ny, y0 + self.rows))
        with self._lock:
            if key not in self._lru:
                self._lru[key] = band
                self._bytes += band.nbytes
                self._trim()
        return band

    def _values(self, band, y, x, idx, free_axes, read: bool):
        """The series at (y, x) from its block, the negative-I rule applied; None when I's block is needed and not
        in memory (read False)."""
        fr, r = self.frames, int(y) % self.rows
        v = fr.to_float32(band[..., r, int(x)])
        ii = fr.i_index(idx, free_axes)
        if ii is None:
            return fr.mask_series(v, idx, free_axes)
        ib = self._band(y, ii, free_axes, read)
        return None if ib is None else fr.mask_series(v, idx, free_axes, fr.to_float32(ib[..., r, int(x)]))

    def peek(self, y: int, x: int, idx, free_axes):
        """The series from a block in memory, or None; never reads."""
        band = self._band(y, idx, free_axes, read=False)
        return None if band is None else self._values(band, y, x, idx, free_axes, read=False)

    def series(self, y: int, x: int, idx, free_axes) -> np.ndarray:
        """As FrameReader.series; reads the block of rows around (y, x) when it is not in memory. When one block
        does not fit in the budget, reads the pixel alone (call it from the one thread that runs parallel numba)."""
        if not 0 <= y < self.frames.ny or not 0 <= x < self.frames.nx:
            raise IndexError(f"pixel ({y}, {x}) outside {self.frames.ny}x{self.frames.nx}")
        got = self.peek(y, x, idx, free_axes)
        if got is not None:
            return got
        sizes, _ = self.frames.series_frames(idx, free_axes)
        y0 = int(y) // self.rows * self.rows
        y1 = min(self.frames.ny, y0 + self.rows)
        need = int(np.prod(sizes, dtype=np.int64)) * (y1 - y0) * self.frames.nx * self.frames.layout.dtype.itemsize
        if self.frames.i_index(idx, free_axes) is not None:
            need *= 2                                   # I's block beside it
        if need > self.max_bytes:
            return self.frames.series(y, x, idx, free_axes)
        got = self._values(self._band(y, idx, free_axes, read=True), y, x, idx, free_axes, read=True)
        assert got is not None
        return got

    def nbytes(self) -> int:
        return self._bytes

    def set_budget(self, max_bytes: int) -> None:
        with self._lock:
            self.max_bytes = int(max_bytes)
            self._trim()

    def _trim(self) -> None:
        while self._bytes > self.max_bytes and self._lru:
            self._bytes -= self._lru.popitem(last=False)[1].nbytes

    def clear(self) -> None:
        with self._lock:
            self._lru.clear()
            self._bytes = 0
