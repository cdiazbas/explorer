"""Q U V's noise levels (core.noise) and their +-sigma on the spectra (ui.spectra): sigma is CRISPEX's, the standard
deviation of S/I_c over the frame at the continuum tuning (crispex.pro L21033-21043), in % of I_c; read once per t,
nothing again for a t seen; none for Stokes I, nor for a cube without 4 Stokes or without a continuum tuning; drawn at
+-sigma in each plot's coordinates, as lines in the classic look and a band in modern and glass, never taking the
mouse."""
import json
import time

import numpy as np
import pytest
from astropy.io import fits

from explorer.data.stats import stokes_noise
from explorer.obs import summary
from explorer.testing import synth
from explorer.testing.driver import Driver

SIG = (0.1, 0.2, 0.3)       # Q U V's noise in % of I_c in the hand cube
SHAPE = (3, 4, 5, 64, 64)   # (t, s, lambda, y, x)
CONT = 4


def counters():
    return summary().get("counters", {})


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


def hand_cube(path, shape=SHAPE, cont=CONT, seed=3):
    """I uniform (2e-8, as SST intensities), Q U V Gaussian noise of SIG % of I at every lambda, a corner of NaN
    padding; the continuum tuning in the header as SSTRED writes it. Returns the data, numpy (t, s, lambda, y, x)."""
    nt, ns, nl, ny, nx = shape
    rng = np.random.default_rng(seed)
    a = np.empty(shape, np.float32)
    a[:, 0] = 2e-8
    for k in range(1, ns):
        a[:, k] = rng.standard_normal((nt, nl, ny, nx)) * SIG[k - 1] / 100 * 2e-8
    a[:, :, :, :6, :6] = np.nan
    h = fits.Header()
    for i, c in enumerate(("HPLN-TAB", "HPLT-TAB", "WAVE-TAB", "STOKES", "UTC--TAB"), 1):
        h[f"CTYPE{i}"] = c
    h["BUNIT"] = "W m^-2 Hz^-1 sr^-1"
    if cont is not None:
        h["PRSTEP1"] = "STOKES-CROSSTALK-CORRECTION"
        h["PRPARA1"] = json.dumps({"TUNING_SELECTION": [cont]})
    fits.PrimaryHDU(a.astype(">f4"), header=h).writeto(path)
    return a


def by_hand(a, t, cont=CONT):
    """sigma of S/I_c in %, per Q U V: sqrt(sum((r - mean)^2) / (n - 1)) over the finite pixels, as IDL's STDDEV."""
    out = {}
    for s in (1, 2, 3):
        r = 100.0 * a[t, s, cont].astype(np.float64) / a[t, 0, cont]
        r = r[np.isfinite(r)]
        out[s] = float(np.sqrt(((r - r.mean()) ** 2).sum() / (r.size - 1)))
    return out


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    path = tmp_path_factory.mktemp("noise") / "hand_im.fits"
    return path, hand_cube(path)


# ---------------------------------------------------------------- the value
def test_sigma_is_the_standard_deviation_of_s_over_ic_by_hand():
    rng = np.random.default_rng(0)
    ic = np.full((40, 50), 3.0)
    ic[0, :5] = np.nan                                  # padding
    ic[1, :5] = 0                                       # no I_c: left out, not infinite
    q = rng.standard_normal(ic.shape) * 0.006
    q[2, 0] = np.nan
    good = np.isfinite(ic) & (ic > 0) & np.isfinite(q)
    r = 100 * q[good] / ic[good]
    want = np.sqrt(((r - r.mean()) ** 2).sum() / (r.size - 1))
    got = stokes_noise(ic, {1: q, 2: np.full(ic.shape, np.nan), 3: np.zeros(ic.shape)})
    assert got.keys() == {1}                            # nothing finite, or no spread: no sigma
    assert got[1] == pytest.approx(want, rel=1e-6)      # its ratios in float32
    assert got[1] == pytest.approx(0.2, rel=0.05)       # 0.006 / 3 = 0.2 %
    mad = stokes_noise(ic, {1: q}, robust=True)[1]
    assert mad == pytest.approx(1.4826 * np.median(np.abs(r - np.median(r))), rel=1e-6)


def test_the_core_sends_crispexs_sigma_of_the_t_shown(cube):
    path, a = cube
    with Driver.open(path, noise=True) as d:
        assert d.shown.noise_t == 0
        want = by_hand(a, 0)
        assert d.shown.noise.keys() == {1, 2, 3}
        for s in (1, 2, 3):
            assert d.shown.noise[s] == pytest.approx(want[s], rel=1e-6)
            assert d.shown.noise[s] == pytest.approx(SIG[s - 1], rel=0.05)   # the noise put in
        d.step("t", 1)
        d.wait_idle()
        assert d.shown.noise_t == 1
        assert d.shown.noise == pytest.approx(by_hand(a, 1), rel=1e-6)


def test_a_t_seen_again_reads_nothing(cube):
    path, a = cube
    with Driver.open(path, noise=True) as d:
        d.step("t", 1)
        d.wait_idle()
        c = counters()
        jobs, frames = c.get("core.noise.jobs", 0), c.get("core.noise.frames_read", 0)
        d.step("t", -1)
        d.wait_idle()
        c = counters()
        assert (c.get("core.noise.jobs", 0), c.get("core.noise.frames_read", 0)) == (jobs, frames)
        assert d.shown.noise_t == 0 and d.shown.noise == pytest.approx(by_hand(a, 0), rel=1e-6)


def test_its_frames_come_from_the_cache_when_there_and_are_not_kept_when_read(cube):
    """At the continuum tuning, the image shown is one of the four frames: not read again. The others are read
    without entering the frame cache, so they never push out the frames read ahead."""
    from explorer.data.dataset import Dataset

    path, a = cube
    with Dataset.open(path) as ds:
        shown = ds.image((1, 0, CONT)).result()
        img, read = ds.read_frame((1, 0, CONT))
        assert img is shown and not read
        img, read = ds.read_frame((1, 2, CONT))
        assert read and ds.cache.peek((1, 2, CONT)) is None
        np.testing.assert_array_equal(img, a[1, 2, CONT])


def test_not_while_playing_but_at_the_pause(cube):
    path, a = cube
    with Driver.open(path, noise=True) as d:
        d.play(True)
        d.wait_idle()
        jobs = counters().get("core.noise.jobs", 0)
        d.step("t", 2)
        d.wait_idle()
        assert counters().get("core.noise.jobs", 0) == jobs and d.shown.noise_t == 0
        d.play(False)
        d.wait_idle()
        assert d.shown.noise_t == 2 and d.shown.noise == pytest.approx(by_hand(a, 2), rel=1e-6)


def test_none_without_four_stokes_or_a_continuum_or_when_not_asked(cube, tmp_path):
    one = synth.write_stokes_cube(tmp_path / "i_im.fits", shape=(2, 1, 5, 32, 32))
    hand_cube(tmp_path / "nocont_im.fits", cont=None)
    for p, kw in ((one, {"noise": True}), (tmp_path / "nocont_im.fits", {"noise": True}), (cube[0], {})):
        jobs = counters().get("core.noise.jobs", 0)
        with Driver.open(p, **kw) as d:
            d.step("t", 1)
            d.wait_idle()
            assert d.shown.noise is None and "noise" not in d.shown.counts, p
        assert counters().get("core.noise.jobs", 0) == jobs, p



# ---------------------------------------------------------------- the display
def panel(qapp, style):
    from explorer.ui.spectra import SpectraPanel

    sp = SpectraPanel(4, 5, None)
    sp.set_noise_style(style)
    sp.widget.resize(700, 500)
    sp.widget.show()
    for k in range(4):
        sp.set_range(k, (-1.0, 1.0))
    qapp.processEvents()
    return sp


def kinds(sp):
    """The +-sigma items on the plots, by kind."""
    import pyqtgraph as pg

    items = sp.noise_items()
    return (sum(isinstance(it, pg.InfiniteLine) for it in items), sum(isinstance(it, pg.LinearRegionItem)
                                                                      for it in items))


@pytest.mark.parametrize("style", ["lines", "band"])
def test_drawn_at_plus_minus_sigma_on_q_u_v_in_plot_coordinates(qapp, style):
    from PySide6 import QtCore

    sp = panel(qapp, style)
    sp.set_noise({1: 0.25, 2: 0.5, 3: 0.125})
    assert sp.noise_at(0) is None                       # never on Stokes I
    assert [sp.noise_at(k) for k in (1, 2, 3)] == [(-0.25, 0.25), (-0.5, 0.5), (-0.125, 0.125)]
    assert kinds(sp) == ((6, 0) if style == "lines" else (0, 3))
    p = sp.plots[2]
    items = sp._noise[2]
    sp.set_range(2, (-2.0, 3.0))                        # in data coordinates: they follow the y range
    qapp.processEvents()
    if style == "band":
        rect = items[0].mapRectToScene(items[0].boundingRect())
        top, bottom = rect.top(), rect.bottom()
    else:
        top = items[0].mapToScene(QtCore.QPointF(0, 0)).y()
        bottom = items[1].mapToScene(QtCore.QPointF(0, 0)).y()
    x = sum(p.vb.viewRange()[0]) / 2
    assert top == pytest.approx(p.vb.mapViewToScene(QtCore.QPointF(x, 0.5)).y(), abs=0.5)
    assert bottom == pytest.approx(p.vb.mapViewToScene(QtCore.QPointF(x, -0.5)).y(), abs=0.5)
    sp.set_noise({1: 0.25})                             # a Stokes without a sigma has none
    assert sp.noise_at(1) == (-0.25, 0.25) and sp.noise_at(2) is None and sp.noise_at(3) is None
    sp.widget.close()


def test_a_change_of_style_leaves_no_items_of_the_other(qapp):
    sp = panel(qapp, "lines")
    sp.set_noise({1: 0.25, 2: 0.5, 3: 0.125})
    for style, want in (("band", (0, 3)), ("lines", (6, 0)), ("band", (0, 3))):
        sp.set_noise_style(style)
        assert kinds(sp) == want, style                 # the sigma shown, drawn again in the new style
        assert [sp.noise_at(k) for k in (1, 2, 3)] == [(-0.25, 0.25), (-0.5, 0.5), (-0.125, 0.125)]
    with pytest.raises(ValueError):
        sp.set_noise_style("off")
    sp.widget.close()


def test_a_panel_without_four_stokes_draws_none(qapp):
    from explorer.ui.spectra import SpectraPanel

    one = SpectraPanel(1, 5, None)
    one.set_noise({1: 0.25})
    assert not one.noise_items() and one.noise_at(1) is None


def test_the_trial_switch_is_gone(cube, monkeypatch):
    """EXPLORER_TRY_SIGMA chose the style while it was tried; the look chooses it now, and the variable does
    nothing."""
    import explorer.ui.spectra as spectra

    assert not hasattr(spectra, "NOISE_VAR") and not hasattr(spectra, "noise_mode")
    monkeypatch.setenv("EXPLORER_TRY_SIGMA", "off")
    with Driver.open(cube[0], noise=True) as d:          # the window asks for the noise whatever it says
        assert d.shown.noise is not None


@pytest.mark.parametrize("look, style", [("classic", "lines"), ("modern", "band"), ("glass", "band")])
def test_each_look_draws_its_style_and_m_switches_it(qapp, cube, look, style):
    """Lines in classic, a band in modern and glass, with the core's sigma; changing the look (M) changes it, and
    nothing of the other stays. A press inside the band, or on a line, still picks lambda."""
    from PySide6 import QtCore
    from test_gestures import mouse

    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui.shell import Shell

    path, a = cube
    ds = Dataset.open(path)
    w = Shell(ds, look=get_look(look))
    try:
        w.resize(1400, 900)
        w.show()
        assert spin(qapp, lambda: w.first_image_s is not None and "spectra" in w.last)
        sp = w.spectra
        want = by_hand(a, 0)
        assert spin(qapp, lambda: sp.noise_at(3) is not None)
        assert sp.noise_style == style and kinds(sp) == ((6, 0) if style == "lines" else (0, 3))
        for k in (1, 2, 3):
            lo, hi = sp.noise_at(k)
            assert hi == pytest.approx(want[k], rel=1e-6) and lo == -hi
        assert sp.noise_at(0) is None
        p, B, E = sp.plots[1], QtCore.Qt.MouseButton, QtCore.QEvent.Type
        for lam, y in ((3, 0.0), (1, want[1])):         # inside the band; on the line at +sigma
            pt = p.vb.mapViewToScene(QtCore.QPointF(float(sp.xl[lam]), y))
            mouse(sp.w, pt, E.MouseButtonPress, B.LeftButton, B.LeftButton)
            mouse(sp.w, pt, E.MouseButtonRelease, B.LeftButton, B.NoButton)
            assert w.session.state.l == lam
        other = "modern" if look == "classic" else "classic"
        w.set_look(get_look(other))
        qapp.processEvents()
        assert sp.noise_style == ("band" if other == "modern" else "lines")
        assert kinds(sp) == ((0, 3) if other == "modern" else (6, 0))
        assert sp.noise_at(1)[1] == pytest.approx(want[1], rel=1e-6)
    finally:
        w.close()
        ds.close()
