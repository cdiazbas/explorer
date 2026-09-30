"""Scheduler: what each change reads and shows, with and without a per-pixel file; padding and hidden panels read
nothing; the order tests: stale work is skipped before it reads, and an old result never replaces a newer one."""
import concurrent.futures as cf
import threading
import types

import numpy as np
import pytest
from astropy.io import fits

from explorer.core.loop import ManualLoop
from explorer.core.scheduler import Scheduler
from explorer.core.session import Session
from explorer.data.axes import roles
from explorer.data.dataset import Dataset
from explorer.data.executors import Executors
from explorer.obs import summary
from explorer.testing import synth

SHAPE = (3, 4, 5, 48, 40)


class Recorder:
    def __init__(self):
        self.calls = []

    def image(self, idx, img, levels):
        self.calls.append(("image", idx))

    def spectra(self, spec, pixel, t):
        self.calls.append(("spectra", pixel, t, spec.shape))

    def lambda_t(self, lt, pixel, s, levels):
        self.calls.append(("lambda_t", pixel, s, lt.shape))

    def cleared(self, pixel):
        self.calls.append(("cleared", pixel))

    def kinds(self):
        return [c[0] for c in self.calls]


def settle(sched, rounds=200):
    """Run the loop until no read is in flight and nothing is pending."""
    for _ in range(rounds):
        cf.wait(sched.in_flight(), timeout=5)
        if sched.loop.pump() == 0 and not sched.in_flight():
            return
    raise AssertionError("the scheduler did not settle")


def counters():
    return summary().get("counters", {})


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("sched"), "c", shape=SHAPE, icube=False)
    return d, fits.getdata(d["im"]).astype(np.float32)


@pytest.fixture(params=["sp", "nosp"])
def setup(request, cube):
    d, data = cube
    ds = Dataset.open(d["im"], no_sp=request.param == "nosp")
    sess = Session(ManualLoop(), ds)
    rec = Recorder()
    sched = Scheduler(sess, rec)
    settle(sched)
    yield sess, sched, rec, data
    sched.close()
    ds.close()


def test_start_shows_the_image_and_both_panels(setup):
    sess, sched, rec, data = setup
    assert rec.kinds() == ["image", "spectra", "lambda_t"]
    assert rec.calls[1] == ("spectra", (24, 20), 0, (4, 5)) and rec.calls[2] == ("lambda_t", (24, 20), 0, (3, 5))
    np.testing.assert_array_equal(sched.img, data[0, 0, 2])


def test_each_change_reads_what_it_needs(setup):
    sess, sched, rec, _ = setup
    for axis, v, want in [("t", 1, ["image", "spectra"]), ("s", 2, ["image", "lambda_t"]), ("l", 4, ["image"])]:
        rec.calls.clear()
        sess.set_index(axis, v)
        sess.store.loop.pump()
        settle(sched)
        assert rec.kinds() == want, axis
    rec.calls.clear()
    sess.hover(20, 15)
    sess.store.loop.pump()
    settle(sched)
    assert rec.kinds() == ["spectra", "lambda_t"] and rec.calls[0][1] == (20, 15)


def test_hidden_panels_read_nothing_and_come_back_when_shown(setup):
    sess, sched, rec, _ = setup
    sess.show("lambda_t", False)
    sess.hover(22, 18)
    sess.store.loop.pump()
    settle(sched)
    rec.calls.clear()
    sess.show("spectra", False)
    before = counters().get("core.cursor.skipped_hidden", 0)
    sess.hover(23, 18)
    sess.store.loop.pump()
    settle(sched)
    assert rec.calls == [] and counters()["core.cursor.skipped_hidden"] == before + 1
    sess.show("lambda_t")
    sess.store.loop.pump()
    settle(sched)
    assert rec.kinds() == ["lambda_t"]


def test_padding_clears_once_reads_nothing_and_the_next_valid_pixel_fills_both(setup):
    sess, sched, rec, _ = setup
    rec.calls.clear()
    before = counters().get("core.cursor.reads", 0)
    for x in (1, 2):                                    # corner pixels: padding in the synthetic cube
        sess.hover(1, x)
        sess.store.loop.pump()
        settle(sched)
    assert rec.kinds() == ["cleared"] and counters().get("core.cursor.reads", 0) == before
    rec.calls.clear()
    sess.hover(24, 20)
    sess.set_index("t", 1)                              # a t change and a move in one burst
    sess.store.loop.pump()
    settle(sched)
    assert rec.kinds() == ["image", "spectra", "lambda_t"]


# ---------------------------------------------------------------- order, with reads the test releases

class SlowCube:
    """A Dataset stand-in: images and series complete when the test says so."""

    def __init__(self):
        self.shape = (4, 1, 3, 10, 10)
        self.roles = roles(("UTC", "STOKES", "WAVE", "HPLT", "HPLN"), self.shape)
        self.ny = self.nx = 10
        self.pixel = None
        self.executors = Executors(gather_threads=1, io_threads=1, strips=1)
        self.images: dict = {}
        self.gates: dict = {}
        self.reads: list = []
        self.probe = types.SimpleNamespace(read_ahead=0)

    def image(self, idx):
        return self.images.setdefault(tuple(idx), cf.Future())

    def prefetch(self, idx):
        pass

    def peek_series(self, *a):
        return None

    def read_series(self, y, x, idx, free):
        self.gates.setdefault((y, x), threading.Event()).wait(5)
        self.reads.append(((y, x), tuple(free)))
        n = [self.shape[a] for a in free]
        return np.full(n, 10 * y + x, np.float32)


def test_stale_cursor_work_is_skipped_before_it_reads():
    cube_ = SlowCube()
    sess = Session(ManualLoop(), cube_)
    rec = Recorder()
    sched = Scheduler(sess, rec)
    cube_.images[(0, 0, 1)].set_result(np.ones((10, 10), np.float32))
    sess.store.loop.pump()                              # the first image: reads for the centre (5, 5) start
    for p in [(1, 1), (2, 2), (3, 3)]:                  # three moves while the first read blocks
        sess.hover(*p)
        sess.store.loop.pump()
    for p in [(5, 5), (1, 1), (2, 2), (3, 3)]:
        cube_.gates.setdefault(p, threading.Event()).set()
    settle(sched)
    read_pixels = [p for p, _ in cube_.reads]
    assert (1, 1) not in read_pixels and (2, 2) not in read_pixels     # overtaken before they started
    assert read_pixels[-2:] == [(3, 3), (3, 3)]                          # the last: spectrum, then lambda-t
    shown = [c[1] for c in rec.calls if c[0] in ("spectra", "lambda_t")]
    assert shown[-2:] == [(3, 3), (3, 3)] and (1, 1) not in shown
    cube_.executors.close()


def test_an_old_image_never_replaces_a_newer_one():
    cube_ = SlowCube()
    sess = Session(ManualLoop(), cube_)
    rec = Recorder()
    sched = Scheduler(sess, rec)
    sess.set_index("t", 1)
    sess.store.loop.pump()
    sess.set_index("t", 2)
    sess.store.loop.pump()
    cube_.images[(2, 0, 1)].set_result(np.ones((10, 10), np.float32))    # the newest first
    sess.store.loop.pump()
    cube_.images[(1, 0, 1)].set_result(np.ones((10, 10), np.float32))
    cube_.images[(0, 0, 1)].set_result(np.ones((10, 10), np.float32))
    sess.store.loop.pump()
    assert [c for c in rec.calls if c[0] == "image"] == [("image", (2, 0, 1))]
    cube_.gates.setdefault((5, 5), threading.Event()).set()
    settle(sched)
    cube_.executors.close()


def test_a_burst_of_steps_reads_one_image():
    cube_ = SlowCube()
    sess = Session(ManualLoop(), cube_)
    Scheduler(sess, Recorder())
    for _ in range(3):
        sess.step("t", 1)
    sess.store.loop.pump()
    assert set(cube_.images) == {(0, 0, 1), (3, 0, 1)}  # the start and the end of the burst, nothing between
    cube_.executors.close()


def test_a_step_back_from_padding_fills_both_panels_without_a_per_pixel_file():
    """The prototype refilled both panels after padding only with a per-pixel file: without one, a t step from padding
    to data read the spectra alone and left the lambda-t empty."""
    cube_ = SlowCube()
    for p in [(5, 5)]:
        cube_.gates.setdefault(p, threading.Event()).set()
    sess = Session(ManualLoop(), cube_)
    rec = Recorder()
    sched = Scheduler(sess, rec)
    padded = np.ones((10, 10), np.float32)
    padded[5, 5] = np.nan                               # the cursor starts on padding at t = 0
    cube_.images[(0, 0, 1)].set_result(padded)
    settle(sched)
    assert rec.kinds() == ["image", "cleared"]
    rec.calls.clear()
    sess.set_index("t", 1)
    sess.store.loop.pump()
    cube_.images[(1, 0, 1)].set_result(np.ones((10, 10), np.float32))      # data at t = 1
    settle(sched)
    assert rec.kinds() == ["image", "spectra", "lambda_t"]
    cube_.executors.close()
