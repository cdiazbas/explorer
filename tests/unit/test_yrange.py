"""The spectra's y ranges: grow while moving, refit at rest, the padlock's sample ranges and Q U V from whole
frames, fit and reset, the units; then wired into the scheduler on the synthetic cube."""
import concurrent.futures as cf

import numpy as np

from explorer.core.loop import ManualLoop
from explorer.core.yrange import REST_S, YRange
from explorer.data.stats import nice_range


def make(ns=2, cont=None):
    loop, applied, units, quv = ManualLoop(), [], [], []
    yr = YRange(loop, ns, cont, lambda k, r: applied.append((k, r)), units.append, lambda: quv.append(1))
    return loop, yr, applied, units, quv


def spec(i_vals, q_vals):
    return np.array([i_vals, q_vals], dtype=np.float64)


def test_ranges_grow_while_moving_and_fit_at_rest():
    loop, yr, applied, units, _ = make()
    yr.spectrum(spec([2e-9, 4e-9], [1e-9, 2e-9]))
    assert units == [1e-9] and yr.r[0] == nice_range(2, 4)
    yr.spectrum(spec([2.5e-9, 3e-9], [1e-9, 2e-9]))        # smaller: the range stays
    assert yr.r[0] == nice_range(2, 4)
    yr.spectrum(spec([1e-9, 8e-9], [1e-9, 2e-9]))          # larger: it grows over both
    grown = yr.r[0]
    assert grown == nice_range(1, 8)
    yr.spectrum(spec([2.5e-9, 3e-9], [1e-9, 2e-9]))        # smaller again: a refit waits for rest
    loop.advance(REST_S / 2)
    yr.spectrum(spec([2.5e-9, 3.1e-9], [1e-9, 2e-9]))      # still moving: the rest timer starts over
    loop.advance(REST_S / 2 + 1e-9)
    loop.pump()
    assert yr.r[0] == grown                                 # the first timer was stale
    loop.advance(REST_S)
    loop.pump()
    assert yr.r[0] == nice_range(2.5, 3.1)                  # at rest: this profile's own range


def test_quv_in_percent_of_the_continuum_when_it_is_known():
    _, yr, _, _, _ = make(cont=1)
    out = yr.spectrum(spec([2e-9, 4e-9], [2e-11, -4e-11]))
    np.testing.assert_allclose(out, [[2, 4], [0.5, -1.0]])


def test_padlock_takes_the_sample_and_quv_from_whole_frames():
    loop, yr, applied, _, quv = make(cont=1)
    yr.spectrum(spec([2e-9, 4e-9], [2e-11, -4e-11]))
    yr.set_fixed(True)                                      # before the sample came
    assert quv == [1] and yr.fixed
    prof = np.stack([spec([2e-9 + i * 1e-11, 4e-9], [1e-11 * np.sin(i), -1e-11]) for i in range(30)])
    yr.sample_ready(prof)
    assert yr.r[0] == yr.sample[0] and yr.r[1] != yr.sample[1]      # Q waits for the whole frames
    yr.quv_ready({1: 3.2})
    assert yr.r[1] == nice_range(-3.2, 3.2) == yr.sample[1]
    yr.spectrum(spec([1e-9, 9e-9], [5e-10, -5e-10]))        # fixed: nothing moves
    assert yr.r[0] == yr.sample[0]
    yr.set_fixed(True)
    assert quv == [1]                                       # asked for once


def test_fit_fixes_to_the_profile_and_reset_goes_back():
    loop, yr, applied, _, _ = make()
    yr.spectrum(spec([2e-9, 4e-9], [1e-9, 2e-9]))
    yr.spectrum(spec([2.5e-9, 3e-9], [1e-9, 2e-9]))
    yr.fit()
    assert yr.fixed and yr.r[0] == nice_range(2.5, 3)
    yr.sample = [(0.0, 10.0), (-5.0, 5.0)]
    q_before = yr.r[1]
    yr.reset()                                              # I to the sample; Q U V wait for the whole frames
    assert yr.r == [(0.0, 10.0), q_before] and yr.quv_pending
    yr.quv_ready({1: 5e-9})                                 # data units: no continuum, Q over I's 1e-9
    assert yr.r[1] == yr.sample[1] == nice_range(-5.0, 5.0)
    yr.set_fixed(False)
    yr.reset()
    assert yr.r[0] == nice_range(2.5, 3) and not yr.fixed


def test_the_scheduler_reads_the_sample_and_quv(tmp_path):
    from explorer.core.scheduler import SAMPLE_AFTER_S, Scheduler
    from explorer.core.session import Session
    from explorer.data.dataset import Dataset
    from explorer.data.stats import quv_amplitude_ranges, quv_plot_ranges, sample_pixels, sample_profiles, sample_ranges
    from explorer.testing import synth

    class Sink:
        def __init__(self):
            self.ranges = {}

        def image(self, *a): pass
        def spectra(self, *a): pass
        def lambda_t(self, *a): pass
        def cleared(self, *a): pass
        def units(self, *a): pass

        def y_range(self, k, r):
            self.ranges[k] = r

    def settle(sched):
        for _ in range(200):
            cf.wait(sched.in_flight(), timeout=10)
            if sched.loop.pump() == 0 and not sched.in_flight():
                return

    d = synth.write_dataset(tmp_path, "c", shape=(3, 4, 5, 48, 40), icube=False)
    with Dataset.open(d["im"]) as ds:
        sess, sink = Session(ManualLoop(), ds), Sink()
        sched = Scheduler(sess, sink)
        settle(sched)
        assert sched.yrange.sample is None
        sess.store.loop.advance(SAMPLE_AFTER_S)
        settle(sched)
        img = ds.image(sess.index()).result()
        ys, xs, ts = sample_pixels(img, ds.path, ds.roles.nt)
        prof = sample_profiles(ys, xs, ts, ds.frames, ds.roles, ds.pixel)
        want, _, _ = sample_ranges(prof, ds.axes.cont, sched.yrange.iscale)
        assert sched.yrange.sample == want
        sched.set_y_fixed(True)
        settle(sched)
        half = quv_amplitude_ranges(ds.frames, ds.roles, ds.axes.cont, 0)[0]
        quv = quv_plot_ranges(half, ds.axes.cont, sched.yrange.iscale)
        assert {k: sink.ranges[k] for k in quv} == quv and sink.ranges[0] == want[0]
        sched.close()
