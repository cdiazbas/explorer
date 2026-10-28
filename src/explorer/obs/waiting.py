"""A line on the terminal every EVERY_S while the start waits for something (its cube's header, its first image): what
it waits for and for how long, so that a slow read (a file brought back from tape, a slow disk) is not taken for a
hang. Standard library only: a daemon thread waiting on an Event, which a read blocked in the kernel does not hold up
(it releases the GIL)."""
import sys
import threading
import time
from collections.abc import Callable

EVERY_S = 10.0


class Waiting:
    def __init__(self, prefix: str, t0: float, every: float = EVERY_S, out=None,
                 extra: Callable[[], str] | None = None):
        """prefix: the lines' ("explorer"); t0: when the wait began (time.perf_counter); out: where (stderr);
        extra: more to say each time ("12.3 of 91.9 GB on disk"), "" for nothing."""
        self.prefix, self.t0, self.every, self.out = prefix, t0, float(every), out
        self.what = "starting"
        self.extra = extra
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="waiting", daemon=True)
        self._thread.start()

    def doing(self, what: str) -> None:
        """What the start waits for now: "opening <file>", "reading the first image"."""
        self.what = what

    def stop(self) -> None:
        """No more lines (the first image is on screen, or the start gave up)."""
        self._stop.set()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def _run(self) -> None:
        while not self._stop.wait(self.every):
            more = ""
            if self.extra is not None:
                try:
                    more = self.extra()
                except Exception:                       # a line without it rather than none
                    more = ""
            line = f"[{self.prefix}] still {self.what}: {time.perf_counter() - self.t0:.0f} s"
            print(line + (f" ({more})" if more else ""), file=self.out or sys.stderr, flush=True)
