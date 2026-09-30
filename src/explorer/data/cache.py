"""Frames kept in memory, and frames read ahead in the background (from the prototype's Cube.image, _store,
prefetch). The operating system's page cache is not relied on for repeats: on StorNext a third access stalled
for ~10 ms (docs/measured.md)."""
import functools
import threading
from collections import OrderedDict
from concurrent.futures import Future

import numpy as np

from .io import FrameReader


class FrameCache:
    """LRU of native float32 frames within a byte budget; prefetch() reads ahead on the reader's pool."""

    def __init__(self, reader: FrameReader, max_bytes: int = 512 << 20):
        self.reader, self.max_bytes = reader, int(max_bytes)
        self.frame_nbytes = reader.ny * reader.nx * 4
        self._lru: OrderedDict = OrderedDict()
        self._pending: dict[tuple, Future] = {}
        self._lock = threading.Lock()

    def get(self, idx) -> np.ndarray:
        """The frame at idx: cached, being read ahead (waited for), or read now."""
        idx = tuple(int(i) for i in idx)
        with self._lock:
            img = self._lru.get(idx)
            if img is not None:
                self._lru.move_to_end(idx)
                return img
            fut = self._pending.get(idx)
        img = fut.result() if fut is not None else self.reader.read(idx)
        self._store(idx, img)
        return img

    def peek(self, idx):
        """The frame at idx if it is cached (marked as just used), else None; never reads nor waits."""
        idx = tuple(int(i) for i in idx)
        with self._lock:
            img = self._lru.get(idx)
            if img is not None:
                self._lru.move_to_end(idx)
            return img

    def prefetch(self, idx) -> None:
        """Start reading idx in the background, unless it is cached, in flight, or outside the cube."""
        idx = tuple(int(i) for i in idx)
        if len(idx) != len(self.reader.shape) - 2 or any(
                not 0 <= i < n for i, n in zip(idx, self.reader.shape[:-2], strict=True)):
            return
        with self._lock:
            if idx in self._lru or idx in self._pending:
                return
            fut = self.reader.pool.submit(self.reader.read, idx, 1)
            self._pending[idx] = fut
        fut.add_done_callback(functools.partial(self._done, idx))

    def _store(self, idx, img) -> None:
        with self._lock:
            self._pending.pop(idx, None)
            if idx not in self._lru:
                self._lru[idx] = img
                self._trim()

    def _done(self, idx, fut: Future) -> None:
        """A read ahead finished: keep the frame, or forget the request if it failed (get() then reads again)."""
        if not fut.cancelled() and fut.exception() is None:   # cancelled: the pool shut down (closing)
            self._store(idx, fut.result())
        else:
            with self._lock:
                self._pending.pop(idx, None)

    def nbytes(self) -> int:
        return len(self._lru) * self.frame_nbytes

    def set_budget(self, max_bytes: int) -> None:
        with self._lock:
            self.max_bytes = int(max_bytes)
            self._trim()

    def _trim(self) -> None:
        while self._lru and len(self._lru) * self.frame_nbytes > self.max_bytes:
            self._lru.popitem(last=False)
