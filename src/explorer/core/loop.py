"""When things run, given to the core by whoever drives it (docs/decisions/0007).

A Loop has three operations:
- call_soon(fn): run fn on the next pass of the loop, on the main thread. The Store uses it to send one notice
  per burst of changes, as the prototype's 0-ms QTimer grouped mouse moves (Viewer._hover_timer).
- post(fn): from any thread, run fn on the main thread. Reads finish on worker threads; what they show must be
  applied on the thread that owns the display.
- call_later(seconds, fn): run fn on the main thread after a delay (the spectra's refit at rest, the sample after
  the first image). No cancel: a timer that restarts marks the old call stale and the call checks it.
The UI gives a Qt implementation (E3); tests and testing.Driver use ManualLoop, which runs nothing until pump(),
and whose clock moves only with advance(), so the order in which things happen is chosen by the test.
"""
import queue
import threading
from collections.abc import Callable
from typing import Protocol


class Loop(Protocol):
    def call_soon(self, fn: Callable[[], None]) -> None: ...

    def post(self, fn: Callable[[], None]) -> None: ...

    def call_later(self, seconds: float, fn: Callable[[], None]) -> None: ...


class ManualLoop:
    """Callbacks wait until pump(), which runs them on the calling thread, in the order they came."""

    def __init__(self):
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self.main = threading.get_ident()
        self.now = 0.0                                  # virtual seconds, moved by advance()
        self._timers: list[tuple[float, int, Callable[[], None]]] = []
        self._seq = 0

    def call_soon(self, fn: Callable[[], None]) -> None:
        self._q.put(fn)

    post = call_soon                                    # thread-safe: SimpleQueue

    def call_later(self, seconds: float, fn: Callable[[], None]) -> None:
        self._seq += 1
        self._timers.append((self.now + float(seconds), self._seq, fn))

    def advance(self, seconds: float) -> int:
        """Move the clock: the timers now due go to the queue, in the order they fall due; returns how many."""
        self.now += float(seconds)
        due = sorted(t for t in self._timers if t[0] <= self.now)
        self._timers = [t for t in self._timers if t[0] > self.now]
        for _, _, fn in due:
            self._q.put(fn)
        return len(due)

    def timers(self) -> int:
        return len(self._timers)

    def pending(self) -> int:
        return self._q.qsize()

    def pump(self, limit: int = 10_000) -> int:
        """Run what is pending, and what those callbacks add, up to limit callbacks; returns how many ran."""
        n = 0
        while n < limit:
            try:
                fn = self._q.get_nowait()
            except queue.Empty:
                break
            fn()
            n += 1
        return n
