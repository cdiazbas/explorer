"""The outline the X server draws (ROADMAP E5.8), with a stand-in server: the latest size wins, what the server
cannot keep up with is skipped and never queued, and the look's colours reach it before the next size."""
import threading
import time

from explorer.platform import xoutline


class SlowServer:
    """Takes 30 ms per size, as a shaped window costs XQuartz 33 ms (bench/x_ops.py)."""

    def __init__(self):
        self.applied, self.at, self.closed = [], [], threading.Event()

    def apply(self, r):
        time.sleep(0.03)
        self.applied.append(r)
        self.at.append(time.perf_counter())

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
    """The outline is one size behind the pointer at most, not the whole drag: after the last move the server applies
    the size it was on and the last one, never the ones in between. Counted, not timed: a GitHub runner slept 120 ms
    for each 25-ms sleep and a bound of 0.2 s failed with nothing queued. Moves every 10 ms against 30 ms a size: a
    queue would leave 13-14 sizes to apply after the last move (measured with a queued stand-in, also 5x slower),
    the outline 1-2."""
    srv = SlowServer()
    o = xoutline.XOutline(0x2F6FDE, server=lambda: srv)
    for i in range(20):
        o.show(0, 0, 700 + 10 * i, 500)
        time.sleep(0.01)
    shown_by = time.perf_counter()
    end = shown_by + 5.0
    while (not srv.applied or srv.applied[-1] != (0, 0, 890, 500)) and time.perf_counter() < end:
        time.sleep(0.005)
    o.close(wait=1.0)
    assert srv.applied[-1] == (0, 0, 890, 500)
    assert sum(t > shown_by for t in srv.at) <= 2       # the one in flight and the last


class PaintingServer(SlowServer):
    def __init__(self):
        super().__init__()
        self.painted = []

    def paint(self, border, inside, ink):
        self.painted.append(((border, inside, ink), len(self.applied)))


def test_the_colours_reach_the_server_before_the_next_size():
    """The look may change between two drags: the colours asked go to the server before the size after them."""
    srv = PaintingServer()
    o = xoutline.XOutline(0x0A84FF, server=lambda: srv)
    o.show(0, 0, 300, 200)
    time.sleep(0.1)
    o.colours(0xFF9230, 0x101013, 0xEBEBF0)
    o.show(0, 0, 320, 210)
    time.sleep(0.1)
    o.close(wait=1.0)
    assert srv.painted == [((0xFF9230, 0x101013, 0xEBEBF0), 1)]   # after the first size, before the second
