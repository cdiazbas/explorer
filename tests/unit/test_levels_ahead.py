"""The image's levels off the UI thread (ROADMAP E5.21): computed on the thread that read the frame, the frames read
ahead too, the same as computed when shown; one computation per frame, waited for rather than repeated; nothing
for a read already stale; fixed levels still win."""
import concurrent.futures as cf
import dataclasses
import threading
import time

import numpy as np
import pytest
from astropy.io import fits
from test_scheduler import Recorder, SlowCube, settle

from explorer.core import levels as levels_mod
from explorer.core.levels import Levels
from explorer.core.loop import ManualLoop
from explorer.core.scheduler import Scheduler
from explorer.core.session import Session
from explorer.data.dataset import Dataset
from explorer.obs import summary
from explorer.testing import synth

SHAPE = (4, 4, 3, 48, 40)
real_levels = levels_mod.image_levels


def counters():
    return summary().get("counters", {})


@pytest.fixture
def spy(monkeypatch):
    """Every computation of an image's levels: (on the main thread, the image's mean, symmetric)."""
    calls: list = []

    def image_levels(img, symmetric):
        calls.append((threading.current_thread() is threading.main_thread(), float(np.nanmean(img)), symmetric))
        return real_levels(img, symmetric)

    monkeypatch.setattr(levels_mod, "image_levels", image_levels)
    return calls


def on_a_worker(fn):
    """Run fn on a thread of its own (done callbacks then run there, as on the thread that read a frame)."""
    th = threading.Thread(target=fn)
    th.start()
    th.join(5)


def wait_for(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > end:
            return False
        time.sleep(0.002)
    return True


# ---------------------------------------------------------------- Levels

def test_levels_ahead_are_the_levels_shown_computed_once():
    img = np.random.default_rng(3).normal(5, 1, (64, 64)).astype(np.float32)
    lv = Levels()
    on_a_worker(lambda: lv.ahead((1, 0, 2), False, img))
    before = counters().get("core.levels.computed", 0)
    assert lv.image((1, 0, 2), False, img) == real_levels(img, False)
    assert counters().get("core.levels.computed", 0) == before                     # served from the cache


def test_a_computation_in_progress_is_waited_for_not_repeated(monkeypatch):
    img = np.random.default_rng(4).normal(0, 1, (64, 64)).astype(np.float32)
    started, release, threads = threading.Event(), threading.Event(), []

    def slow(a, symmetric):
        threads.append(threading.current_thread().name)
        started.set()
        release.wait(5)
        return real_levels(a, symmetric)

    monkeypatch.setattr(levels_mod, "image_levels", slow)
    lv = Levels()
    worker = threading.Thread(target=lambda: lv.ahead((0, 1, 0), True, img), name="reader")
    worker.start()
    assert started.wait(5)
    threading.Timer(0.05, release.set).start()
    before = counters().get("core.levels.waited", 0)
    assert lv.image((0, 1, 0), True, img) == real_levels(img, True)                # waits for the reader's
    worker.join(5)
    assert threads == ["reader"] and counters()["core.levels.waited"] == before + 1


def test_levels_ahead_are_per_rule_and_a_failure_leaves_nothing_behind(spy, monkeypatch):
    rng = np.random.default_rng(5)
    b = rng.normal(9, 2, (32, 32))
    lv = Levels()
    lv.ahead((3, 0, 0), False, b, "minmax")
    spy.clear()
    assert lv.image((3, 0, 0), False, b) == real_levels(b, False)                  # its own rule, computed when shown
    assert len(spy) == 1

    def broken(img, symmetric):
        raise FloatingPointError("bad frame")

    monkeypatch.setattr(levels_mod, "image_levels", broken)
    with pytest.raises(FloatingPointError):
        lv.ahead((4, 0, 0), False, b)
    monkeypatch.setattr(levels_mod, "image_levels", real_levels)
    assert lv.image((4, 0, 0), False, b) == real_levels(b, False)                  # not left waiting


def test_a_read_ahead_gives_its_future_none_when_cached(tmp_path):
    d = synth.write_dataset(tmp_path, "c", shape=SHAPE, icube=False)
    with Dataset.open(d["im"], no_sp=True) as ds:
        gate = threading.Event()
        real_read = ds.frames.read
        ds.frames.read = lambda idx, chunks=None: (gate.wait(5), real_read(idx, chunks))[1]
        fut = ds.prefetch((1, 0, 0))
        assert isinstance(fut, cf.Future) and ds.prefetch((1, 0, 0)) is fut            # the one in flight
        assert ds.prefetch((99, 0, 0)) is None                                          # outside the cube
        gate.set()
        np.testing.assert_array_equal(fut.result(5), real_read((1, 0, 0)))
        assert wait_for(lambda: ds.cache.peek((1, 0, 0)) is not None)
        assert ds.prefetch((1, 0, 0)) is None                                           # cached


# ---------------------------------------------------------------- the scheduler

@pytest.fixture
def grid(tmp_path):
    """A scheduler on a synthetic cube whose reads ahead wait for gate."""
    d = synth.write_dataset(tmp_path, "c", shape=SHAPE, icube=False)
    data = fits.getdata(d["im"]).astype(np.float32)
    ds = Dataset.open(d["im"], no_sp=True)
    gate = threading.Event()
    real_read = ds.frames.read

    def read(idx, chunks=None):                         # chunks=1: a read ahead (FrameCache.prefetch)
        if chunks == 1:
            gate.wait(5)
        return real_read(idx, chunks)

    ds.frames.read = read
    sess = Session(ManualLoop(), ds)
    shown: list = []
    rec = Recorder()
    rec.image = lambda idx, img, levels: shown.append(("image", 0, idx, img, levels))
    rec.grid_image = lambda s, idx, img, levels: shown.append(("grid", s, idx, img, levels))
    sched = Scheduler(sess, rec)
    settle(sched)
    yield sess, sched, ds, data, gate, shown
    gate.set()
    sched.close()
    ds.close()


def keys_ahead(sess, sched, t, stokes):
    return [(tuple(sess.index(state=dataclasses.replace(sess.state, t=t, s=s))), s > 0) for s in stokes]


def test_a_step_in_the_grid_computes_no_levels_on_the_ui_thread(grid, spy):
    """The frames read ahead have their levels when the step shows them: before, the UI thread computed the four
    quadrants' at each step (~11 ms of a ~47 ms step, bellatrix)."""
    sess, sched, ds, data, gate, shown = grid
    assert sched.ds.probe.read_ahead >= 1
    sched.set_grid(True)
    settle(sched)
    sess.step("t", 1)                                   # reads t = 2.. ahead, for the four Stokes
    settle(sched)
    want = keys_ahead(sess, sched, 2, range(4))
    after = [threading.Event() for _ in want]
    for (idx, _), ev in zip(want, after, strict=True):    # the reads in flight; called after the scheduler's
        ds.cache._pending[idx].add_done_callback(lambda f, ev=ev: ev.set())
    gate.set()
    assert all(ev.wait(5) for ev in after)
    spy.clear()
    shown.clear()
    sess.step("t", 1)
    settle(sched)
    st = sess.state
    got = {c[1]: c for c in shown if c[0] == "grid"}
    assert sorted(got) == [0, 1, 2, 3] and st.t == 2
    for s, (_, _, _idx, img, lev) in got.items():
        np.testing.assert_array_equal(img, data[2, s, st.l])
        assert lev == real_levels(data[2, s, st.l], s > 0)                         # the same as when shown
    assert [c for c in spy if c[0]] == []                                           # none on the UI thread


def test_a_stale_read_computes_no_levels_and_the_shown_image_has_its_own(spy):
    cube_ = SlowCube()
    sess = Session(ManualLoop(), cube_)
    shown: list = []
    rec = Recorder()
    rec.image = lambda idx, img, levels: shown.append((idx, levels))
    sched = Scheduler(sess, rec)
    sess.set_index("t", 1)
    sess.store.loop.pump()
    sess.set_index("t", 2)
    sess.store.loop.pump()
    frames = {t_: np.arange(100, dtype=np.float32).reshape(10, 10) + 1000 * (t_ + 1) for t_ in range(3)}
    for t_ in (2, 1, 0):                                # the latest, then two reads already stale
        on_a_worker(lambda t_=t_: cube_.images[(t_, 0, 1)].set_result(frames[t_]))
    sess.store.loop.pump()
    assert spy == [(False, float(np.nanmean(frames[2])), False)]                        # the latest only, off the UI
    assert shown == [((2, 0, 1), real_levels(frames[2], False))]
    cube_.gates.setdefault((5, 5), threading.Event()).set()
    settle(sched)
    cube_.executors.close()


def test_fixed_levels_win_over_levels_read_ahead(grid, spy):
    sess, sched, ds, data, gate, shown = grid
    st = sess.state
    sched.fix_levels(True)
    fixed = real_levels(data[st.t, st.s, st.l], False)
    sess.step("t", 1)
    settle(sched)
    spy.clear()
    ahead = keys_ahead(sess, sched, 2, [0])[0]
    after = threading.Event()
    ds.prefetch(ahead[0]).add_done_callback(lambda f: after.set())                  # after the scheduler's
    gate.set()
    assert after.wait(5)
    assert spy == [] and ahead not in sched.levels._cache                         # nothing computed while fixed
    sess.step("t", 1)
    settle(sched)
    assert shown[-1][0] == "image" and shown[-1][2] == ahead[0] and shown[-1][4] == fixed
    sched.fix_levels(False)
    assert shown[-1][4] == real_levels(data[2, st.s, st.l], False)                 # its own once unfixed
