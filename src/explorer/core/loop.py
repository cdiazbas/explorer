"""When things run, given to the core by whoever drives it (docs/decisions/0007).

A Loop has two operations:
- call_soon(fn): run fn on the next pass of the loop, on the main thread. The Store uses it to send one notice
  per burst of changes, as the prototype's 0-ms QTimer grouped mouse moves (Viewer._hover_timer).
- post(fn): from any thread, run fn on the main thread. Reads finish on worker threads; what they show must be
  applied on the thread that owns the display.
The UI gives a Qt implementation (E3); tests and testing.Driver use ManualLoop, which runs nothing until pump(),
so the order in which things happen is chosen by the test.
"""
import queue
import threading
from collections.abc import Callable
from typing import Protocol


class Loop(Protocol):
    def call_soon(self, fn: Callable[[], None]) -> None: ...

    def post(self, fn: Callable[[], None]) -> None: ...


class ManualLoop:
    """Callbacks wait until pump(), which runs them on the calling thread, in the order they came."""

    def __init__(self):
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self.main = threading.get_ident()

    def call_soon(self, fn: Callable[[], None]) -> None:
        self._q.put(fn)

    post = call_soon                                    # thread-safe: SimpleQueue

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
