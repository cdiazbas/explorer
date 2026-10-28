"""A line on the terminal every EVERY_S while the start waits for something (its cube's header, its first image): what
it waits for, for how long, and what has moved meanwhile (bytes read; for files on tape, how much of them is on disk),
so that a slow read is told from a hang. When nothing has moved for STILL_S (no bytes read, no CPU spent, no more of
those files on disk), one warning says so, and how to see where each thread is (SIGUSR1: faulthandler's stacks on
stderr). Standard library only: a daemon thread waiting on an Event, which a read blocked in the kernel does not hold
up (it releases the GIL)."""
import os
import threading
import time
from collections.abc import Callable

from . import say

EVERY_S = 10.0
STILL_S = 60.0
CPU_S = 0.5                     # less CPU than this over STILL_S, with nothing read: the process is not working
READ_B = 1 << 20                # nor is it reading, under this many bytes


def read_bytes() -> int | None:
    """Bytes this process has read so far, the larger of what it asked for and what storage gave (Linux
    /proc/self/io: rchar, read_bytes, which counts the pages a mapped file brought in); None elsewhere."""
    try:
        with open("/proc/self/io") as f:
            io = dict(line.split(":", 1) for line in f if ":" in line)
        return max(int(io.get("rchar", 0)), int(io.get("read_bytes", 0)))
    except (OSError, ValueError):
        return None


def cpu_s() -> float:
    t = os.times()
    return t.user + t.system


class Waiting:
    def __init__(self, t0: float, every: float = EVERY_S, still: float = STILL_S,
                 extra: Callable[[], tuple[str, float]] | None = None):
        """t0: when the wait began (time.perf_counter); extra: more to say each time and a number that grows while
        it moves ("12.3 of 91.9 GB on disk", bytes on disk), None for nothing."""
        self.t0, self.every, self.still = t0, float(every), float(still)
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

    def _extra(self) -> tuple[str, float]:
        if self.extra is None:
            return "", 0.0
        try:
            return self.extra()
        except Exception:                               # a line without it rather than none
            return "", 0.0

    def _run(self) -> None:
        r0 = read_bytes()
        mark = (time.perf_counter(), cpu_s(), r0, self._extra()[1])     # when something last moved, and how far
        warned = False
        while not self._stop.wait(self.every):
            now, cpu, got = time.perf_counter(), cpu_s(), read_bytes()
            text, back = self._extra()
            parts = [f"read {(got - r0) / 1e9:.1f} GB"] if got is not None and r0 is not None else []
            parts += [text] if text else []
            more = f" ({'; '.join(parts)})" if parts else ""
            say.info(f"still {self.what}: {now - self.t0:.0f} s{more}")
            moved = (cpu - mark[1] >= CPU_S or (got is not None and mark[2] is not None and got - mark[2] >= READ_B)
                     or back > mark[3])
            if moved:
                mark, warned = (now, cpu, got, back), False
            elif now - mark[0] >= self.still and not warned:
                warned = True
                say.warn(f"nothing has moved for {now - mark[0]:.0f} s while {self.what}: no bytes read, no CPU"
                         f"{', no more of the files on tape on disk' if text else ''}. To see where it waits: "
                         f"kill -USR1 {os.getpid()} (each thread's stack, here)")
