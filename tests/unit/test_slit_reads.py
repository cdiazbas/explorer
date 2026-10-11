"""The slit panel's reads (ROADMAP E7.3, core.slitreads), without a display: the slices along a slit are the cube's
values at its pixels, through the per-pixel file's blocks and through rows read per frame without it; t, lambda and
Stokes give the slices at them; nothing is read while the panel is behind, nor on the UI thread; a result made for
another slit is never shown; the slit being drawn is read live (only its new pixels with the per-pixel file, after
the pointer rests without it); the blocks kept are bounded, and count in the Dataset's memory; without the per-pixel
file the spectral slice waits out playback."""
import concurrent.futures as cf
import threading

import numpy as np
import pytest
from astropy.io import fits

from explorer.core import slitreads
from explorer.core.loop import ManualLoop
from explorer.core.scheduler import Scheduler
from explorer.core.session import Session
from explorer.data import dataset as dataset_mod
from explorer.data.dataset import Dataset
from explorer.data.slits import slit_path, slit_pixels
from explorer.obs import summary
from explorer.testing import synth
from explorer.testing.driver import Driver

SHAPE = (3, 4, 5, 48, 40)                               # t, s, lambda, y, x
A = ((5.5, 10.5), (30.5, 35.5))                         # (x, y) points clicked
B = ((8.5, 40.5), (20.5, 12.5), (34.5, 20.5))


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("slitreads"), "c", shape=SHAPE, icube=False)
    return d["im"], fits.getdata(d["im"]).astype(np.float32)


def pixels(pts, ny=SHAPE[3], nx=SHAPE[4]):
    return slit_pixels(slit_path(np.asarray(pts, float)), ny, nx)


def want(data, pts, t, s, l):  # noqa: E741
    """The slices straight from the cube read by astropy: (nt, n) at (s, l) and (nl, n) at (t, s)."""
    iy, ix = pixels(pts)
    return data[:, s, l, iy, ix], data[t, s, :, iy, ix].T


@pytest.fixture(params=["per-pixel", "frames"])
def drv(request, cube):
    d = Driver.open(cube[0], no_sp=request.param == "frames")
    yield d
    d.close()


def show_slit(d, pts):
    d.show("slit")
    d.set_slit(pts)
    d.wait_idle()


def test_the_slices_are_the_cubes_values_at_the_slits_pixels(drv, cube):
    data = cube[1]
    show_slit(drv, A)
    st = drv.state()
    ts, sl = want(data, A, st.t, st.s, st.l)
    iy, ix = pixels(A)
    assert np.array_equal(drv.shown.slit_pix[0], iy) and np.array_equal(drv.shown.slit_pix[1], ix)
    assert drv.shown.slit_ts.shape == (SHAPE[0], len(iy)) and drv.shown.slit_sl.shape == (SHAPE[2], len(iy))
    np.testing.assert_array_equal(drv.shown.slit_ts, ts)
    np.testing.assert_array_equal(drv.shown.slit_sl, sl)


def test_t_lambda_and_stokes_give_the_slices_at_them(drv, cube):
    data = cube[1]
    show_slit(drv, B)
    drv.set_index("l", 1)
    drv.set_index("t", 2)
    drv.set_stokes(3)
    drv.wait_idle()
    ts, sl = want(data, B, 2, 3, 1)
    np.testing.assert_array_equal(drv.shown.slit_ts, ts)
    np.testing.assert_array_equal(drv.shown.slit_sl, sl)
    assert drv.shown.slit_s == 3


def test_removing_the_slit_empties_the_panel(drv):
    show_slit(drv, A)
    drv.set_slit(None)
    drv.wait_idle()
    assert drv.shown.slit_pix is None and drv.shown.slit_ts is None and drv.shown.slit_sl is None


def test_behind_the_panel_only_a_finished_slits_blocks_are_read_then_it_fills(drv, cube):
    """A slit being drawn is not read while the panel is behind; a finished one, with the per-pixel file, has its
    blocks read at once (its tab comes in front with it), and its slices are made only once the panel is in front."""
    drv.draw_slit(B)
    drv.wait_idle()
    assert drv.shown.slit_pix is not None and drv.scheduler.slit.reads == []
    drv.draw_slit(None)
    drv.set_slit(A)
    drv.wait_idle()
    assert drv.shown.slit_pix is not None                # its pixels are known: the markers can follow
    assert drv.shown.counts.get("slit", 0) == 0
    per_pixel = drv.session.main.pixel is not None
    iy, ix = pixels(A)
    assert [r["pixels"] for r in drv.scheduler.slit.reads] == (
        [len(set(zip(iy.tolist(), ix.tolist(), strict=True)))] if per_pixel else [])
    drv.show("slit")
    drv.wait_idle()
    st = drv.state()
    np.testing.assert_array_equal(drv.shown.slit_ts, want(cube[1], A, st.t, st.s, st.l)[0])
    assert len(drv.scheduler.slit.reads) == (1 if per_pixel else 2)     # nothing read again for the blocks


def test_nothing_is_read_on_the_ui_thread(drv, monkeypatch):
    from explorer.data.io import FrameReader
    from explorer.data.pixel import SpFits

    on_main = []
    for cls, name in ((SpFits, "strip_read"), (FrameReader, "band_values")):
        orig = getattr(cls, name)

        def spy(self, *a, _o=orig, **k):
            on_main.append(threading.current_thread() is threading.main_thread())
            return _o(self, *a, **k)
        monkeypatch.setattr(cls, name, spy)
    show_slit(drv, B)
    drv.step("t")
    drv.step("l")
    drv.wait_idle()
    assert on_main and not any(on_main)


class Recorder:
    def __init__(self):
        self.calls = []

    def image(self, idx, img, levels):
        pass

    def spectra(self, spec, pixel, t):
        pass

    def lambda_t(self, lt, pixel, s, levels):
        pass

    def cleared(self, pixel):
        pass

    def grid_image(self, s, idx, img, levels):
        pass

    def y_range(self, k, r):
        pass

    def units(self, iscale):
        pass

    def slit_path(self, pix):
        self.calls.append(("path", None if pix is None else len(pix[0])))

    def slit(self, ts, sl, s, ts_levels, sl_levels):
        self.calls.append(("slit", None if ts is None else ts.shape, None if sl is None else sl.shape))


def settle(sched, rounds=500):
    for _ in range(rounds):
        cf.wait(sched.in_flight(), timeout=10)
        if sched.loop.pump() == 0 and not sched.in_flight():
            return
    raise AssertionError("the scheduler did not settle")


@pytest.fixture
def frames_only(cube):
    ds = Dataset.open(cube[0], no_sp=True)
    yield ds
    ds.close()


def test_a_result_made_for_another_slit_is_never_shown(frames_only, monkeypatch):
    """The first slit's read is held until the second slit is set: its slices come after, and are dropped."""
    ds = frames_only
    gate, started = threading.Event(), threading.Event()
    orig = ds.read_bands

    def held(idxs, iy, ix, threads=None):
        if len(iy) == len(pixels(A)[0]):
            started.set()
            assert gate.wait(10)
        return orig(idxs, iy, ix, threads)
    monkeypatch.setattr(ds, "read_bands", held)
    rec, loop = Recorder(), ManualLoop()
    session = Session(loop, ds)
    sched = Scheduler(session, rec)
    settle(sched)
    dropped = summary()["counters"].get("core.slit.dropped_other_slit", 0)
    session.show("slit")
    session.set_path(A)
    loop.pump()
    assert started.wait(10)                             # A's read is on the slit thread now
    session.set_path(B)
    loop.pump()
    gate.set()
    settle(sched)
    nA, nB = len(pixels(A)[0]), len(pixels(B)[0])
    shown = [i for i, c in enumerate(rec.calls) if c[0] == "slit"]
    assert shown and all(rec.calls[i][1] in (None, (SHAPE[0], nB)) and rec.calls[i][2] in (None, (SHAPE[2], nB))
                         for i in shown), rec.calls
    assert rec.calls.index(("path", nA)) < rec.calls.index(("path", nB)) < shown[0]
    assert summary()["counters"].get("core.slit.dropped_other_slit", 0) > dropped
    sched.close()


def test_the_slit_being_drawn_is_read_live_its_new_pixels_only(cube):
    with Driver.open(cube[0]) as d:
        d.show("slit")
        d.draw_slit(A[:1])                              # one point: nothing to show yet
        d.wait_idle()
        assert d.shown.slit_pix is None
        d.draw_slit(A)                                  # the point and the pointer's pixel
        d.wait_idle()
        first = d.scheduler.slit.reads[-1]["pixels"]
        np.testing.assert_array_equal(d.shown.slit_ts, want(cube[1], A, 0, 0, d.state().l)[0])
        moved = (A[0], (A[1][0] + 1, A[1][1]))         # the pointer one pixel on
        d.draw_slit(moved)
        d.wait_idle()
        iy0, ix0 = pixels(A)
        iy1, ix1 = pixels(moved)
        new = set(zip(iy1.tolist(), ix1.tolist(), strict=True)) - set(zip(iy0.tolist(), ix0.tolist(), strict=True))
        assert first == len(set(zip(iy0.tolist(), ix0.tolist(), strict=True)))
        assert d.scheduler.slit.reads[-1]["pixels"] == len(new) < first
        np.testing.assert_array_equal(d.shown.slit_sl, want(cube[1], moved, 0, 0, d.state().l)[1])
        n = len(d.scheduler.slit.reads)
        d.set_slit(moved)                               # finished where it was drawn: nothing more to read
        d.draw_slit(None)
        d.wait_idle()
        assert len(d.scheduler.slit.reads) == n and np.array_equal(d.shown.slit_pix[0], iy1)


def test_without_the_per_pixel_file_the_slit_being_drawn_waits_for_the_pointer_to_rest(cube):
    with Driver.open(cube[0], no_sp=True) as d:
        d.show("slit")
        d.draw_slit(A)
        d.wait_idle()
        assert d.shown.slit_pix is not None and d.scheduler.slit.reads == []
        d.advance(slitreads.REST_S * 0.6)
        d.wait_idle()
        d.draw_slit(B)                                  # moved before the rest: A's timer, due next, does nothing
        d.wait_idle()
        d.advance(slitreads.REST_S * 0.6)
        d.wait_idle()
        assert d.scheduler.slit.reads == []
        d.advance(slitreads.REST_S * 0.6)
        d.wait_idle()
        assert len(d.scheduler.slit.reads) == 2         # the time slice, then the spectral slice
        np.testing.assert_array_equal(d.shown.slit_ts, want(cube[1], B, 0, 0, d.state().l)[0])


def test_without_the_per_pixel_file_the_spectral_slice_waits_out_playback(cube):
    with Driver.open(cube[0], no_sp=True) as d:
        show_slit(d, A)
        kinds = [r["kind"] for r in d.scheduler.slit.reads]
        d.play(True)
        d.step("t", 1, wrap=True)
        d.wait_idle()
        assert [r["kind"] for r in d.scheduler.slit.reads] == kinds      # the time slice is kept; no reads
        d.play(False)
        d.wait_idle()
        assert [r["kind"] for r in d.scheduler.slit.reads] == kinds + ["sl"]
        np.testing.assert_array_equal(d.shown.slit_sl, want(cube[1], A, 1, 0, d.state().l)[1])


def test_one_block_read_at_a_time_the_latest_slit_next(cube, monkeypatch):
    ds = Dataset.open(cube[0])
    try:
        gate, calls, active, most = threading.Event(), [], [0], [0]
        orig = ds.slit_blocks
        lock = threading.Lock()

        def slow(pix):
            calls.append(set(pix))
            fut = orig(pix)
            out: cf.Future = cf.Future()

            def later():
                with lock:
                    active[0] += 1
                    most[0] = max(most[0], active[0])
                gate.wait(10)
                with lock:
                    active[0] -= 1
                out.set_result(fut.result())
            threading.Thread(target=later, daemon=True).start()
            return out
        monkeypatch.setattr(ds, "slit_blocks", slow)
        rec, loop = Recorder(), ManualLoop()
        session = Session(loop, ds)
        sched = Scheduler(session, rec)
        settle(sched)
        session.show("slit")
        for pts in (A, B, ((2.5, 2.5), (20.5, 3.5))):   # three slits while the first read is held
            session.set_draft(pts)
            loop.pump()
        gate.set()
        settle(sched)
        last = pixels(((2.5, 2.5), (20.5, 3.5)))
        assert most[0] == 1 and len(calls) == 2         # A's, then the latest's: B was never read
        assert set(zip(last[0].tolist(), last[1].tolist(), strict=True)) <= calls[1] | calls[0]
        assert not (calls[1] & calls[0])                # only what A's read did not bring
        sched.close()
    finally:
        ds.close()


def test_the_blocks_kept_are_bounded_and_the_shown_slits_stay(cube):
    with Driver.open(cube[0]) as d:
        d.session.main.slit_cache.max_blocks = 40
        show_slit(d, A)
        d.set_slit(B)
        d.wait_idle()
        iy, ix = pixels(B)
        assert set(d.scheduler.slit.blocks.keys()) == set(zip(iy.tolist(), ix.tolist(), strict=True))
        st = d.state()
        np.testing.assert_array_equal(d.shown.slit_ts, want(cube[1], B, st.t, st.s, st.l)[0])


def test_the_blocks_kept_count_in_the_datasets_memory_and_its_budget_bounds_them(cube):
    """The blocks along slits are the Dataset's (slit_cache): in nbytes(), and over their share of the memory budget
    only the shown slit's stay, copied out of the runs they were read in, so that the memory of the others is freed."""
    with Driver.open(cube[0]) as d:
        ds = d.session.main
        before = ds.nbytes()
        show_slit(d, A)
        block = SHAPE[1] * SHAPE[0] * SHAPE[2] * 4
        nA = len(set(zip(*(a.tolist() for a in pixels(A)), strict=True)))
        assert ds.slit_cache.nbytes() == nA * block and ds.nbytes() == before + nA * block
        d.set_slit(B)
        d.wait_idle()
        keyB = set(zip(*(a.tolist() for a in pixels(B)), strict=True))
        assert len(ds.slit_cache) > len(keyB)            # A's are still kept
        ds.guard.budget = int(len(keyB) * block / dataset_mod.SLIT_SHARE)       # B's alone fit
        ds.guard.update = lambda: ds.guard.budget                               # whatever the machine has free
        ds.update_memory()
        assert set(ds.slit_cache.keys()) == keyB and ds.slit_cache.nbytes() == len(keyB) * block
        assert all(ds.slit_cache.get(p).base is None for p in keyB)            # no longer views of the runs read
        st = d.state()
        d.set_index("t", 1)
        d.wait_idle()
        np.testing.assert_array_equal(d.shown.slit_ts, want(cube[1], B, 1, st.s, st.l)[0])


def test_while_drawn_a_late_result_for_its_previous_stage_is_shown_once_drawn_not(cube, monkeypatch):
    """The pointer gives a new slit every pixel: a result for the stage before, arriving after the next stage was
    asked for, is still shown while drawing (newer than what is shown); once the slit is finished elsewhere, not."""
    from explorer.core.slitreads import SlitReads

    ds = Dataset.open(cube[0])
    try:
        gate, started, hold = threading.Event(), threading.Event(), [True]
        orig = SlitReads._from_blocks

        def held(self, *a):
            if hold[0]:
                hold[0] = False
                started.set()
                assert gate.wait(10)
            return orig(self, *a)
        monkeypatch.setattr(SlitReads, "_from_blocks", held)
        rec, loop = Recorder(), ManualLoop()
        session = Session(loop, ds)
        sched = Scheduler(session, rec)
        settle(sched)
        session.show("slit")
        moved = (A[0], (A[1][0] + 3, A[1][1]))
        nA, nM = len(pixels(A)[0]), len(pixels(moved)[0])
        assert nA != nM
        session.set_draft(A)
        loop.pump()
        assert started.wait(10)                         # A's slices are being made
        session.set_draft(moved)
        loop.pump()
        gate.set()
        settle(sched)
        shapes = [c[1][1] for c in rec.calls if c[0] == "slit"]
        assert shapes[0] == nA and shapes[-1] == nM     # A's came late and was shown, then the pointer's

        rec.calls.clear()
        gate.clear()
        started.clear()
        hold[0] = True
        session.set_draft(B)
        loop.pump()
        assert started.wait(10)
        session.set_path(A)                             # finished on another slit before B's slices came
        session.set_draft(None)
        loop.pump()
        gate.set()
        settle(sched)
        shapes = [c[1][1] for c in rec.calls if c[0] == "slit"]
        assert shapes and all(n == nA for n in shapes), rec.calls
        sched.close()
    finally:
        ds.close()


@pytest.mark.parametrize("linked_file", ["per-pixel", "frames"])
def test_a_slit_drawn_on_a_linked_cube_reads_that_cube_at_its_own_lambda(cube, tmp_path, linked_file):
    """With linked cubes (ROADMAP E8.1) the slices are those of the cube the slit was drawn on (ViewState.path_cube):
    its values at the same pixels, at its own lambda, through its per-pixel file or its frames; back on the main
    cube, the main cube's."""
    d = synth.write_dataset(tmp_path, "other", shape=(SHAPE[0], SHAPE[1], 7, SHAPE[3], SHAPE[4]), seed=4,
                            icube=False)
    other = fits.getdata(d["im"]).astype(np.float32)
    drv = Driver.open(cube[0])
    ds = Dataset.open(d["im"], no_sp=linked_file == "frames", executors=drv.dataset.executors)
    try:
        k = drv.session.add(ds)
        drv.show("slit")
        drv.session.set_path(A, k)
        drv.wait_idle()
        st = drv.session.member_state(k)
        print("linked cube", k, "per-pixel" if ds.pixel is not None else "frames", "lambda", st.l, "Stokes", st.s)
        ts, sl = want(other, A, st.t, st.s, st.l)
        np.testing.assert_array_equal(drv.shown.slit_ts, ts)
        np.testing.assert_array_equal(drv.shown.slit_sl, sl)
        drv.session.set_member_index(k, "l", 5)             # its own lambda: the time slice there
        drv.wait_idle()
        np.testing.assert_array_equal(drv.shown.slit_ts, want(other, A, st.t, st.s, 5)[0])
        drv.session.set_path(A, 0)
        drv.wait_idle()
        main = drv.state()
        ts, sl = want(cube[1], A, main.t, main.s, main.l)
        np.testing.assert_array_equal(drv.shown.slit_ts, ts)
        np.testing.assert_array_equal(drv.shown.slit_sl, sl)
    finally:
        ds.close()
        drv.close()


class SliceRec(Recorder):
    """The slit's pixels and the last slices given (a linked cube's sink: its slit tab)."""

    def __init__(self):
        super().__init__()
        self.pix = self.ts = self.sl = None

    def slit_path(self, pix):
        super().slit_path(pix)
        self.pix = pix
        if pix is None:
            self.ts = self.sl = None

    def slit(self, ts, sl, s, ts_levels, sl_levels):
        super().slit(ts, sl, s, ts_levels, sl_levels)
        self.ts = ts if ts is not None else self.ts
        self.sl = sl if sl is not None else self.sl


def idle(drv, *scheds):
    """The driver's scheduler and these idle: nothing pending, nothing in flight."""
    every = (drv.scheduler, *scheds)
    for _ in range(1000):
        futs = [f for s in every for f in s.in_flight()]
        if futs:
            cf.wait(futs, timeout=30)
        if drv.loop.pump() == 0 and not any(s.in_flight() for s in every):
            return
    raise AssertionError("not idle")


@pytest.mark.parametrize("linked_file", ["per-pixel", "frames"])
def test_a_slit_tab_per_cube_reads_each_cube_along_the_same_slit(cube, tmp_path, linked_file):
    """With a slit tab per cube (ViewState.slit_tabs) each cube's scheduler reads its own cube's slices along the
    slit, whichever image it was drawn on: the main cube's tab the main cube's, the linked cube's its own, at its own
    lambda. A tab behind reads nothing until it comes in front (the drawn-on cube's blocks excepted: its tab comes in
    front with the slit). Off, one tab as before: the main cube's reads follow the cube the slit was drawn on, and
    the linked cube's read nothing."""
    d = synth.write_dataset(tmp_path, "other", shape=(SHAPE[0], SHAPE[1], 7, SHAPE[3], SHAPE[4]), seed=4,
                            icube=False)
    other = fits.getdata(d["im"]).astype(np.float32)
    drv = Driver.open(cube[0])
    ds = Dataset.open(d["im"], no_sp=linked_file == "frames", executors=drv.dataset.executors)
    rec = SliceRec()
    sched = None
    try:
        k = drv.session.add(ds)
        sched = Scheduler(drv.session, rec, member=k)
        drv.session.set_slit_tabs(True)
        drv.show("slit")                                # the main cube's tab in front, the linked cube's behind
        drv.session.set_path(B, 0)                      # drawn on the main image
        idle(drv, sched)
        behind = list(sched.slit.reads)
        drv.session.set_path(A, k)                      # drawn on the linked cube's image
        idle(drv, sched)
        main = drv.state()
        ts, sl = want(cube[1], A, main.t, main.s, main.l)
        print(linked_file, "behind, a slit drawn on the main image: reads", behind, "; drawn on its own: reads",
              len(sched.slit.reads), "slices shown", rec.ts is not None)
        np.testing.assert_array_equal(drv.shown.slit_ts, ts)        # the main tab: the main cube's
        np.testing.assert_array_equal(drv.shown.slit_sl, sl)
        assert behind == [] and rec.pix is not None and rec.ts is None
        assert len(sched.slit.reads) == (0 if linked_file == "frames" else 1)
        drv.session.show(f"slit:{k}")                   # its tab in front: its own cube's slices
        idle(drv, sched)
        mine = drv.session.member_state(k)
        ts, sl = want(other, A, mine.t, mine.s, mine.l)
        np.testing.assert_array_equal(rec.ts, ts)
        np.testing.assert_array_equal(rec.sl, sl)
        drv.session.set_member_index(k, "l", 5)
        idle(drv, sched)
        np.testing.assert_array_equal(rec.ts, want(other, A, mine.t, mine.s, 5)[0])
        drv.session.set_slit_tabs(False)                # one tab: the cube the slit was drawn on, in the main one
        idle(drv, sched)
        assert rec.pix is None and rec.ts is None
        np.testing.assert_array_equal(drv.shown.slit_ts, want(other, A, mine.t, mine.s, 5)[0])
        drv.session.set_slit_tabs(True)
        idle(drv, sched)
        np.testing.assert_array_equal(drv.shown.slit_ts, want(cube[1], A, main.t, main.s, main.l)[0])
        np.testing.assert_array_equal(rec.ts, want(other, A, mine.t, mine.s, 5)[0])
    finally:
        if sched is not None:
            sched.close()
        ds.close()
        drv.close()
