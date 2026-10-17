"""A cube of 4 Stokes whose header gives no continuum tuning (an LP icube) takes the quietest tuning in Q U V of the
y-range sample as its continuum (stats.quietest_tuning, core.scheduler _choose_cont): Q U V go to % of I_c, their
ranges are fitted again, the noise levels come, and it is said once. The header's continuum wins; a cube of one
Stokes or one tuning gets none."""
import json
import time

import numpy as np
import pytest
from astropy.io import fits

from explorer.core.scheduler import SAMPLE_AFTER_S
from explorer.data.stats import CONT_SAMPLE_N, SAMPLE_N, quietest_tuning
from explorer.testing import synth
from explorer.testing.driver import Driver

SIG = (0.5, 0.4, 0.3, 0.05, 0.4)    # Q U V's noise in % of I at each tuning: tuning 3 the quietest


def cube_without_cont(path, sig=SIG, ns=4, nt=3, ny=96, nx=100, cont=None, seed=5):
    """I uniform (2e-8), Q U V Gaussian noise of sig[k] % of I at tuning k; no continuum in the header unless cont."""
    nl = len(sig)
    rng = np.random.default_rng(seed)
    a = np.empty((nt, ns, nl, ny, nx), np.float32)
    a[:, 0] = 2e-8
    for s in range(1, ns):
        for k in range(nl):
            a[:, s, k] = rng.standard_normal((nt, ny, nx)) * sig[k] / 100 * 2e-8
    h = fits.Header()
    for i, c in enumerate(("HPLN-TAB", "HPLT-TAB", "WAVE-TAB", "STOKES", "UTC--TAB"), 1):
        h[f"CTYPE{i}"] = c
    if cont is not None:
        h["PRSTEP1"] = "STOKES-CROSSTALK-CORRECTION"
        h["PRPARA1"] = json.dumps({"TUNING_SELECTION": [cont]})
    fits.PrimaryHDU(a.astype(">f4"), header=h).writeto(path)
    return a


def sampled(d):
    """The sample, and the first image's pixel and spectrum (as read) at the cursor."""
    d.advance(SAMPLE_AFTER_S)
    d.wait_idle()


def counting(monkeypatch):
    """How many profiles the scheduler's samples read."""
    import explorer.core.scheduler as sch

    n = [0]
    real = sch.sample_profiles

    def count(ys, *a, **kw):
        n[0] += len(ys)
        return real(ys, *a, **kw)
    monkeypatch.setattr(sch, "sample_profiles", count)
    return n


# ---------------------------------------------------------------- the choice
def test_the_quietest_tuning_of_hand_made_profiles():
    rng = np.random.default_rng(0)
    n, nl = 300, 5
    prof = np.empty((n, 4, nl))
    prof[:, 0] = 3.0
    for k, s in enumerate(SIG):
        prof[:, 1:, k] = rng.standard_normal((n, 3)) * s / 100 * 3.0
    assert quietest_tuning(prof) == 3
    noisy = prof.copy()
    noisy[:5, 2, 1] = 1e3                               # a profile's U wild at tuning 1...
    noisy[:5, 0, 1] = -1.0                              # ...where its I is negative (padding): not counted
    noisy[5:9, 3, 4] = np.nan                           # NaN counts nowhere
    noisy[:, :, 0] = np.nan                             # a tuning with nothing finite: never chosen
    assert quietest_tuning(noisy) == 3
    lone = prof.copy()
    lone[:, 1:, 2] = 0                                  # tuning 2 without any polarisation...
    lone[1:, 0, 2] = 0                                  # ...in the one profile whose I_c is there: no spread to tell
    assert quietest_tuning(lone) == 3
    assert quietest_tuning(prof[:, :1]) is None         # one Stokes
    assert quietest_tuning(prof[:, :, :1]) is None      # one tuning
    assert quietest_tuning(np.full((10, 4, 3), np.nan)) is None


# ---------------------------------------------------------------- in the core
def test_a_cube_without_a_continuum_takes_the_quietest_tuning(tmp_path, monkeypatch):
    path = tmp_path / "icube_like_im.fits"
    a = cube_without_cont(path)
    n = counting(monkeypatch)
    with Driver.open(path, noise=True) as d:
        assert d.dataset.axes.cont is None and d.shown.noise is None
        (y, x), t = d.shown.spectra_at
        iscale = d.shown.iscale
        np.testing.assert_allclose(d.shown.spectra[1], a[t, 1, :, y, x] / iscale, rtol=1e-5)     # I's units
        sampled(d)
        assert n[0] == CONT_SAMPLE_N
        assert d.dataset.axes.cont == 3
        k, text = d.shown.continuum
        assert k == 3 and text.startswith("continuum: tuning 3") and f"of {CONT_SAMPLE_N} profiles" in text
        assert d.shown.counts["continuum"] == 1
        # the spectrum shown drawn again in % of this pixel's I_c, and Q U V's ranges fitted to it
        ic = a[t, 0, 3, y, x]
        for s in (1, 2, 3):
            got = d.shown.spectra[s]
            np.testing.assert_allclose(got, 100 * a[t, s, :, y, x] / ic, rtol=1e-5)
            lo, hi = d.shown.y_ranges[s]
            assert lo <= got.min() and got.max() <= hi and hi - lo < 50 * (got.max() - got.min() + 1e-9)
        assert d.shown.noise_t == t                     # the noise levels, at the tuning chosen
        for s in (1, 2, 3):
            assert d.shown.noise[s] == pytest.approx(SIG[3], rel=0.1)
        d.step("t", 1)                                  # and from now on, as with the header's
        d.wait_idle()
        (y, x), t = d.shown.spectra_at
        np.testing.assert_allclose(d.shown.spectra[2], 100 * a[t, 2, :, y, x] / a[t, 0, 3, y, x], rtol=1e-5)
        assert d.shown.noise_t == t and d.shown.counts["continuum"] == 1


def test_the_headers_continuum_wins(tmp_path, monkeypatch):
    path = tmp_path / "with_cont_im.fits"
    cube_without_cont(path, cont=0)                     # tuning 0 the noisiest, but the header says it
    n = counting(monkeypatch)
    with Driver.open(path, noise=True) as d:
        sampled(d)
        assert d.dataset.axes.cont == 0 and d.shown.continuum is None and "continuum" not in d.shown.counts
        assert n[0] == SAMPLE_N                         # the y-range sample only


@pytest.mark.parametrize("shape", ["one_stokes", "one_tuning"])
def test_none_for_one_stokes_or_one_tuning(tmp_path, monkeypatch, shape):
    path = tmp_path / f"{shape}_im.fits"
    if shape == "one_stokes":
        cube_without_cont(path, ns=1)
    else:
        cube_without_cont(path, sig=(0.3,))
    n = counting(monkeypatch)
    with Driver.open(path, noise=True) as d:
        sampled(d)
        assert d.dataset.axes.cont is None and d.shown.continuum is None and d.shown.noise is None
        assert n[0] in (0, SAMPLE_N)                    # one tuning: a spectrum of one point, sampled as before


# ---------------------------------------------------------------- in the window
def spin(qapp, until, timeout=15.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


def test_the_window_says_it_once_and_shows_q_u_v_in_percent_with_sigma(qapp, tmp_path, capsys):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    path = synth.write_stokes_cube(tmp_path / "even_im.fits", shape=(3, 4, 9, 48, 40), continuum=False)
    ds = Dataset.open(path)
    w = Shell(ds)
    try:
        assert ds.axes.cont is None
        w.resize(1400, 900)
        w.show()
        sp = w.spectra
        assert spin(qapp, lambda: "spectra" in w.last)
        assert "/I<sub>c</sub>" not in sp.plots[1].getAxis("left").labelText
        assert spin(qapp, lambda: ds.axes.cont is not None and sp.noise_at(1) is not None)
        k = ds.axes.cont
        assert all("/I<sub>c</sub> [%]" in p.getAxis("left").labelText for p in sp.plots[1:])
        assert w.statusBar().currentMessage().startswith(f"continuum: tuning {k} (λ₀ ")
        assert "(cont.)" in w.nav.labels["l"].text() or w.session.state.l != k
        err = capsys.readouterr().err
        assert err.count("continuum: tuning") == 1
    finally:
        w.close()
        ds.close()
