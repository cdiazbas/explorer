"""The outline the X server draws (ROADMAP E5.8), with a stand-in server: the latest size wins, what the server
cannot keep up with is skipped and never queued, and the ring is 2 px inside the window."""
import threading
import time

from explorer.platform import xoutline


class SlowServer:
    """Takes 30 ms per size, as a shaped window costs XQuartz 33 ms (bench/x_ops.py)."""

    def __init__(self):
        self.applied, self.closed = [], threading.Event()

    def apply(self, r):
        time.sleep(0.03)
        self.applied.append(r)

    def close(self):
        self.closed.set()


def test_the_latest_size_wins_and_nothing_queues():
    srv = SlowServer()
    o = xoutline.XOutline(0x2F6FDE, server=lambda: srv)
    for i in range(40):                                 # a drag of 1 s at 40 moves a second, asked at once
        o.show(100, 100, 600 + i, 400)
    time.sleep(0.2)
    o.close(wait=1.0)
    assert srv.closed.is_set()
    assert srv.applied[-1] == (100, 100, 639, 400)      # where the pointer ended
    assert len(srv.applied) <= 3                        # not 40: the ones in between were skipped


def test_the_server_never_waits_for_the_pointer():
    srv = SlowServer()
    o = xoutline.XOutline(0x2F6FDE, server=lambda: srv)
    t0 = time.perf_counter()
    for i in range(20):
        o.show(0, 0, 700 + 10 * i, 500)
        time.sleep(0.025)
    shown_by = time.perf_counter()
    end = shown_by + 1.0
    while (not srv.applied or srv.applied[-1] != (0, 0, 890, 500)) and time.perf_counter() < end:
        time.sleep(0.005)
    o.close(wait=1.0)
    assert srv.applied[-1] == (0, 0, 890, 500)
    assert time.perf_counter() - shown_by < 0.2         # one step behind at most, not the whole drag
    assert t0 < shown_by


def test_the_ring():
    assert xoutline.ring(100, 50) == [(0, 0, 100, 2), (0, 48, 100, 2), (0, 0, 2, 50), (98, 0, 2, 50)]


def test_no_x_server_no_outline_and_no_error():
    def fail():
        raise OSError("no display")
    o = xoutline.XOutline(0, server=fail)
    o.show(0, 0, 10, 10)
    o.close(wait=1.0)
