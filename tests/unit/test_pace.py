"""core.pace: the cursor's panels are shown at once while the screen keeps up, as without a pace; held, the latest
winning, while the panels drawn before have not reached the screen; and the last state is always shown, when the
screen confirms or after HOLD_S."""
import concurrent.futures as cf

import pytest

from explorer.core.loop import ManualLoop
from explorer.core.pace import HOLD_S, Pace
from explorer.core.scheduler import Scheduler
from explorer.core.session import Session
from explorer.data.dataset import Dataset
from explorer.testing import synth

SHAPE = (3, 4, 5, 48, 40)


class Screen:
    """A display as the bridge is one: panels drawn make a frame, which is on its way once grabbed (grab()) and shown
    once confirmed (confirm(); at once when fast, a link that keeps up)."""

    def __init__(self, fast=False):
        self.fast, self.frame, self.waiting = fast, None, []

    def behind(self):
        return self.frame == "sent"

    def drawn(self):
        if self.frame is None:
            self.frame = "drawn"

    def when_shown(self, fn):
        self.waiting.append(fn)

    def grab(self):
        if self.frame == "drawn":
            self.frame = "sent"
            if self.fast:
                self.confirm()

    def confirm(self):
        if self.frame != "sent":
            return
        self.frame = None
        fns, self.waiting = self.waiting, []
        for fn in fns:
            fn()


def test_no_screen_shows_at_once():
    p, out = Pace(ManualLoop()), []
    for i in range(5):
        p.show(("c", "spectra"), lambda i=i: out.append(i))
    assert out == [0, 1, 2, 3, 4]


def test_a_screen_that_keeps_up_shows_every_one_at_once():
    loop = ManualLoop()
    p, out, scr = Pace(loop), [], Screen(fast=True)
    p.screen = scr
    for i in range(5):
        p.show(("c", "spectra"), lambda i=i: out.append(("sp", i)))
        p.show(("c", "lambda_t"), lambda i=i: out.append(("lt", i)))
        scr.grab()
    assert out == [(k, i) for i in range(5) for k in ("sp", "lt")]
    assert scr.waiting == [] and loop.timers() == 0


def test_behind_holds_the_latest_and_shows_it_when_the_screen_catches_up():
    loop = ManualLoop()
    p, out, scr = Pace(loop), [], Screen()
    p.screen = scr
    p.show(("c", "spectra"), lambda: out.append(("sp", 0)))     # the screen idle: at once
    p.show(("c", "lambda_t"), lambda: out.append(("lt", 0)))    # the same frame, not yet grabbed: at once
    scr.grab()                                                  # on its way
    assert out == [("sp", 0), ("lt", 0)] and scr.behind()
    for i in range(1, 6):                                       # behind: held, the latest per panel
        p.show(("c", "spectra"), lambda i=i: out.append(("sp", i)))
        p.show(("c", "lambda_t"), lambda i=i: out.append(("lt", i)))
    assert out == [("sp", 0), ("lt", 0)]
    scr.confirm()                                               # the frame reached the screen: the last state
    assert out[2:] == [("sp", 5), ("lt", 5)]
    scr.grab()
    assert scr.behind()                                         # and that one is on its way now
    scr.confirm()
    p.show(("c", "spectra"), lambda: out.append(("sp", 6)))
    assert out[-1] == ("sp", 6)


def test_a_frame_never_confirmed_holds_no_longer_than_hold_s():
    loop = ManualLoop()
    p, out, scr = Pace(loop), [], Screen()
    p.screen = scr
    p.show("k", lambda: out.append(0))
    scr.grab()
    p.show("k", lambda: out.append(1))
    loop.advance(HOLD_S * 0.9)
    loop.pump()
    assert out == [0]
    loop.advance(HOLD_S * 0.2)
    loop.pump()
    assert out == [0, 1]
    scr.confirm()                                               # a late confirmation shows nothing twice
    loop.advance(HOLD_S * 2)
    loop.pump()
    assert out == [0, 1]


def test_dropped_keys_are_not_shown():
    loop = ManualLoop()
    p, out, scr = Pace(loop), [], Screen()
    p.screen = scr
    p.show("a", lambda: out.append("a0"))
    scr.grab()
    p.show("a", lambda: out.append("a1"))
    p.show("b", lambda: out.append("b1"))
    p.drop(["a"])
    scr.confirm()
    assert out == ["a0", "b1"]


class Recorder:
    def __init__(self):
        self.calls = []

    def image(self, idx, img, levels):
        self.calls.append(("image", idx))

    def spectra(self, spec, pixel, t):
        self.calls.append(("spectra", pixel))

    def lambda_t(self, lt, pixel, s, levels):
        self.calls.append(("lambda_t", pixel))

    def cleared(self, pixel):
        self.calls.append(("cleared", pixel))

    def grid_image(self, s, idx, img, levels):
        pass

    def y_range(self, k, r):
        pass

    def units(self, iscale):
        pass

    def panels(self):
        return [c for c in self.calls if c[0] in ("spectra", "lambda_t")]


def settle(sched, rounds=200):
    for _ in range(rounds):
        cf.wait(sched.in_flight(), timeout=5)
        if sched.loop.pump() == 0 and not sched.in_flight():
            return
    raise AssertionError("the scheduler did not settle")


@pytest.fixture(params=["sp", "nosp"])
def setup(request, tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("pace"), "c", shape=SHAPE, icube=False)
    ds = Dataset.open(d["im"], no_sp=request.param == "nosp")
    sess = Session(ManualLoop(), ds)
    rec = Recorder()
    sched = Scheduler(sess, rec)
    settle(sched)
    yield sess, sched, rec
    sched.close()
    ds.close()


@pytest.mark.parametrize("fast", [True, False])
def test_cursor_sweep_through_the_scheduler(setup, fast):
    """A fast screen: every cursor position's panels, as without a pace. A slow one: the panels of the first
    position, then, once the screen confirms, those of the last; never one in between."""
    sess, sched, rec = setup
    scr = Screen(fast=fast)
    sess.pace.screen = scr
    rec.calls.clear()
    path = [(18 + i, 14 + i) for i in range(6)]       # inside the field of view
    for y, x in path:
        sess.hover(y, x)
        settle(sched)
        scr.grab()                                              # the bridge's grab after the paint
    if fast:
        assert rec.panels() == [(k, p) for p in path for k in ("spectra", "lambda_t")]
        return
    assert rec.panels() == [("spectra", path[0]), ("lambda_t", path[0])]
    scr.confirm()
    assert rec.panels()[2:] == [("spectra", path[-1]), ("lambda_t", path[-1])]


@pytest.mark.parametrize("mbps, held", [(10.0, True), (19.9, True), (20.0, False), (30.0, False)])
def test_the_hold_only_on_a_link_slower_than_below_mbps(mbps, held):
    """The display offers its screen; the link probe's measure decides: below BELOW_MBPS the panels wait for it, at
    or above every result is shown at once (no gain measured at 20 and 30 MB/s, the panels drawn half as often)."""
    from explorer.core.pace import BELOW_MBPS

    p, out, scr = Pace(ManualLoop()), [], Screen()
    p.offer = scr
    p.show(("c", "spectra"), lambda: out.append(0))             # before the probe: at once, never held
    scr.grab()
    p.show(("c", "spectra"), lambda: out.append(1))
    assert out == [0, 1] and BELOW_MBPS == 20.0
    scr.confirm()
    assert p.link(mbps) is held
    p.show(("c", "spectra"), lambda: out.append(2))             # the screen idle: at once either way
    scr.grab()
    p.show(("c", "spectra"), lambda: out.append(3))             # the frame of 2 not confirmed yet
    assert out == ([0, 1, 2] if held else [0, 1, 2, 3])
    p.offer = None
    assert p.link(5.0) is False                                 # no screen offered (Qt's own displays): never held
