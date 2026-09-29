"""The data layer's threads, and the rule that keeps a fast mouse from queueing stale work.

Threads (from the prototype's Viewer and viewer.py):
- numba: one thread runs every parallel numba call (gather). With the 'workqueue' threading layer two parallel
  regions at once abort the process, and numba's thread count is set per calling thread, so it is set on this
  one. Scattered reads wait on the disk, so the count comes from the storage probe (64 on StorNext, 16 on SSD).
- io: preads of frame chunks and frames read ahead.
- strips: serial nogil kernels (reduction to u8, running maxima) split in row strips; never parallel numba.
- background: long jobs (Q U V ranges from whole frames, slabs along a slit) on a thread of their own, so they
  never delay the reads the cursor waits for.

Latest wins, in two parts (prototype Viewer._series_job and _lt_ready):
- before a job starts, and between its steps, it is skipped if a newer request for the same key arrived
  (Generations.stale);
- a result is shown unless a NEWER one is already on screen (ShownGate.accept). Showing only the latest
  request's result froze the panels while the mouse moved: each read outlasts the gap between two moves, so
  every result arrived stale (1-11 spectra shown during 1.5 s of motion, against 108-131, docs/measured.md).
"""
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor

from ._numba import numba


class Generations:
    """A request counter per key (e.g. "cursor", "slit"): new() for each request, stale() to check a job's."""

    def __init__(self):
        self._gen: dict[str, int] = {}
        self._lock = threading.Lock()

    def new(self, key: str) -> int:
        with self._lock:
            g = self._gen.get(key, 0) + 1
            self._gen[key] = g
            return g

    def current(self, key: str) -> int:
        with self._lock:
            return self._gen.get(key, 0)

    def stale(self, key: str, gen: int) -> bool:
        return gen != self.current(key)


class ShownGate:
    """Per key, the newest generation shown: accept(gen) is False only when a newer one was shown already."""

    def __init__(self):
        self._shown: dict[str, int] = {}
        self._lock = threading.Lock()

    def accept(self, key: str, gen: int) -> bool:
        with self._lock:
            if gen < self._shown.get(key, 0):
                return False
            self._shown[key] = gen
            return True


class Executors:
    def __init__(self, gather_threads: int = 16, io_threads: int = 16, strips: int | None = None):
        self.numba = ThreadPoolExecutor(1, thread_name_prefix="numba")
        n = max(1, min(int(gather_threads), numba.config.NUMBA_NUM_THREADS))  # type: ignore[attr-defined]
        self.numba_threads = self.numba.submit(_set_threads, n).result()
        self.io = ThreadPoolExecutor(max(1, io_threads), thread_name_prefix="io")
        strips = min(8, os.cpu_count() or 1) if strips is None else strips
        self.strips = ThreadPoolExecutor(max(1, strips), thread_name_prefix="strips")
        self.background = ThreadPoolExecutor(1, thread_name_prefix="background")
        self.generations = Generations()

    def submit_latest(self, key: str, fn, *args, pool: ThreadPoolExecutor | None = None) -> tuple[int, Future]:
        """Run fn(still_current, *args) for a new request of key, on the numba thread unless another pool is
        given. fn is not called at all if a newer request arrived before it started, and can call
        still_current() between its steps to stop early. The future then resolves to None."""
        gen = self.generations.new(key)

        def still_current() -> bool:
            return not self.generations.stale(key, gen)

        def run():
            if not still_current():
                return None
            return fn(still_current, *args)

        return gen, (pool or self.numba).submit(run)

    def close(self) -> None:
        for p in (self.background, self.strips, self.io, self.numba):
            p.shutdown(wait=True, cancel_futures=True)


def _set_threads(n: int) -> int:
    numba.set_num_threads(n)
    return numba.get_num_threads()
