"""Cubes whose header says nothing about their axes: 4-D is taken as (t, lambda, y, x), 3-D as an unknown profile
axis, 5-D in SOLARNET order; --axes says otherwise. Steps, spectra and lambda-t work in indices."""
import concurrent.futures as cf

import numpy as np
import pytest
from astropy.io import fits

from explorer.core.loop import ManualLoop
from explorer.core.scheduler import Scheduler
from explorer.core.session import Session
from explorer.data.dataset import Dataset


class Recorder:
    def __init__(self):
        self.calls = []

    def image(self, idx, img, levels):
        self.calls.append(("image", idx, img.shape))

    def spectra(self, spec, pixel, t):
        self.calls.append(("spectra", spec.shape))

    def lambda_t(self, lt, pixel, s, levels):
        self.calls.append(("lambda_t", lt.shape))

    def cleared(self, pixel):
        self.calls.append(("cleared",))

    def y_range(self, k, r):
        pass

    def units(self, iscale):
        pass


def settle(sched):
    for _ in range(100):
        cf.wait(sched.in_flight(), timeout=5)
        if sched.loop.pump() == 0 and not sched.in_flight():
            return


def bare(tmp_path, shape):
    p = tmp_path / f"bare{len(shape)}.fits"
    fits.PrimaryHDU(np.random.default_rng(1).uniform(1, 2, size=shape).astype(np.float32)).writeto(p)
    return p


@pytest.mark.parametrize("shape, axes, how, want", [
    ((5, 7, 16, 12), None, "default (t, lambda)", [("spectra", (1, 7)), ("lambda_t", (5, 7))]),
    ((4, 7, 16, 12), "s,l", "--axes", [("spectra", (4, 7))]),                      # (s, lambda): no t, no lambda-t
    ((7, 16, 12), None, "unknown", [("spectra", (1, 7))]),                          # a profile, in indices
    ((7, 16, 12), "t", "--axes", []),                                               # a time series: image only
    ((5, 4, 7, 16, 12), None, "SOLARNET order", [("spectra", (4, 7)), ("lambda_t", (5, 7))]),
])
def test_cubes_without_a_header(tmp_path, shape, axes, how, want):
    with Dataset.open(bare(tmp_path, shape), no_sp=True, axes=axes) as ds:
        assert ds.roles.how == how and ds.axes.lam_nm is None and ds.axes.t_sec is None
        sess = Session(ManualLoop(), ds)
        rec = Recorder()
        sched = Scheduler(sess, rec)
        settle(sched)
        assert rec.calls[0][0] == "image" and rec.calls[1:] == want
        axis = "t" if ds.roles.t is not None else "l" if ds.roles.l is not None else None
        if axis:                                                                    # stepping works on what there is
            rec.calls.clear()
            sess.step(axis, 1)
            sess.store.loop.pump()
            settle(sched)
            assert rec.calls and rec.calls[0][0] == "image"
        sched.close()


class Values(Recorder):
    def spectra(self, spec, pixel, t):
        self.calls.append(("spectra", np.array(spec), pixel))

    def lambda_t(self, lt, pixel, s, levels):
        self.calls.append(("lambda_t", np.array(lt), pixel))


@pytest.mark.parametrize("shape, axes", [((7, 5, 16, 12), "l,t"), ((7, 4, 16, 12), "l,s")])
def test_lambda_before_t_or_stokes_still_reaches_the_panels_as_t_lambda_and_s_lambda(tmp_path, shape, axes):
    """The panels take the spectra as (Stokes, lambda) and lambda-t as (t, lambda), whatever order the cube keeps
    them in: read along the cube's order, a (lambda, t) cube's lambda-t came transposed and a (lambda, s) cube's
    spectra scrambled."""
    p = bare(tmp_path, shape)
    data = fits.getdata(p)
    with Dataset.open(p, no_sp=True, axes=axes) as ds:
        sess = Session(ManualLoop(), ds)
        rec = Values()
        sched = Scheduler(sess, rec)
        settle(sched)
        y, x = sess.state.cursor
        got = {c[0]: c[1] for c in rec.calls if c[0] in ("spectra", "lambda_t")}
        if axes == "l,t":
            assert np.allclose(got["lambda_t"], data[:, :, y, x].T)                 # (t, lambda)
            assert np.allclose(got["spectra"], data[:, sess.state.t, y, x][None])
        else:
            assert "lambda_t" not in got
            assert np.allclose(got["spectra"], data[:, :, y, x].T)                   # (s, lambda)
        sched.close()
