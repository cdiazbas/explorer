"""The temporal panels at most 100 t steps (ViewState.t_cap, data.tsample): lambda-t (and the value against t of a
cube without lambda) and the slit's time slice read and show only the t steps evenly spread over the cube's t; a cube
with nt <= the cap, or the cap off ("all"), as before; the number in their titles changes it; the current t's line
and a click stay in the cube's own t, a click picking the nearest t shown. Each test prints what it measured.

The behaviour tests use only what existed before the cap (the Driver, the Store, Dataset): on the code before it they
fail on their assertions, not on an import."""
import time

import numpy as np
import pytest
from astropy.io import fits

from explorer.data.dataset import Dataset
from explorer.data.io import SeriesReader
from explorer.testing import synth
from explorer.testing.driver import Driver

NT, NS, NL, NY, NX = 250, 4, 3, 24, 20
Y, X = 14, 8                                            # not the centre, where the cursor starts
SLIT = ((3.5, 6.5), (16.5, 18.5))


def steps(nt, cap):
    """The steps the panels must show, computed here: the centres of `cap` equal bins of [0, nt)."""
    return np.floor((np.arange(cap) + 0.5) * nt / cap).astype(int)


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("tcap"), "c", shape=(NT, NS, NL, NY, NX), icube=False)
    return d["im"], fits.getdata(d["im"]).astype(np.float32)


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("tcap_small"), "s", shape=(5, NS, NL, NY, NX), icube=False)
    return d["im"], fits.getdata(d["im"]).astype(np.float32)


@pytest.fixture(params=["per-pixel", "frames"])
def drv(request, cube):
    d = Driver.open(cube[0], no_sp=request.param == "frames")
    yield d
    d.close()


def frames_read(ds, monkeypatch):
    """The number of frames each series read of ds asks for (FrameReader.series_frames), in order."""
    got: list[int] = []
    orig = ds.frames.series_frames

    def spy(*a, **kw):
        sizes, fn = orig(*a, **kw)
        got.append(int(fn.size))
        return sizes, fn
    monkeypatch.setattr(ds.frames, "series_frames", spy)
    return got


# ---------------------------------------------------------------- the steps
def test_the_steps_are_bin_centres_and_every_t_within_the_cap():
    from explorer.data.tsample import nearest_sample, time_samples

    for nt, cap in ((250, 100), (300, 100), (3900, 100), (101, 100), (7, 3)):
        ts = time_samples(nt, cap)
        print(nt, cap, "->", ts[:4], "...", ts[-2:])
        assert len(ts) == cap and np.array_equal(ts, steps(nt, cap)) and (np.diff(ts) > 0).all()
        j = np.arange(cap)
        assert ((ts + 1 > j * nt / cap) & (ts < (j + 1) * nt / cap)).all()   # each row drawn over its t's cell
    for nt, cap in ((5, 100), (100, 100), (250, None)):
        assert np.array_equal(time_samples(nt, cap), np.arange(nt))
    ts = time_samples(250, 100)                                          # 1, 3, 6, 8, 11, ...
    assert nearest_sample(ts, 3.4) == 3 and nearest_sample(ts, 5.0) == 3 and nearest_sample(ts, 6.2) == 6
    assert nearest_sample(ts, 0.0) == 1 and nearest_sample(ts, 250.0) == ts[-1]


# ---------------------------------------------------------------- lambda-t
def test_lambda_t_reads_and_shows_100_of_250_t(drv, cube, monkeypatch):
    data = cube[1]
    reads = frames_read(drv.dataset, monkeypatch)
    drv.hover(Y, X)
    drv.wait_idle()
    lt, ts = drv.shown.lambda_t, steps(NT, 100)
    print("lambda-t", None if lt is None else lt.shape, "frames per series read", reads)
    assert lt is not None and lt.shape == (100, NL)
    assert np.allclose(lt, data[ts, 0, :, Y, X], rtol=1e-5, atol=0, equal_nan=True)
    if drv.dataset.pixel is None:                   # without a per-pixel file only the steps are read
        assert reads and max(reads) == 100 * NL


def test_the_cap_off_reads_every_t(drv, cube):
    drv.hover(Y, X)
    drv.wait_idle()
    drv.session.store.set(t_cap=None)               # "all"
    drv.wait_idle()
    lt = drv.shown.lambda_t
    print("cap off: lambda-t", lt.shape)
    assert lt.shape == (NT, NL) and np.allclose(lt, cube[1][:, 0, :, Y, X], rtol=1e-5, atol=0, equal_nan=True)
    drv.session.store.set(t_cap=50)
    drv.wait_idle()
    print("cap 50: lambda-t", drv.shown.lambda_t.shape)
    assert np.allclose(drv.shown.lambda_t, cube[1][steps(NT, 50), 0, :, Y, X], rtol=1e-5, atol=0, equal_nan=True)


@pytest.mark.parametrize("no_sp", [False, True])
def test_a_cube_within_the_cap_is_as_before(small, no_sp):
    """nt = 5: every t, the same arrays as before the cap (this one passes before and after)."""
    with Driver.open(small[0], no_sp=no_sp) as d:
        d.hover(Y, X)
        d.show("slit")
        d.set_slit(SLIT)
        d.wait_idle()
        iy, ix = d.shown.slit_pix
        print("nt 5: lambda-t", d.shown.lambda_t.shape, "time slice", d.shown.slit_ts.shape)
        assert np.allclose(d.shown.lambda_t, small[1][:, 0, :, Y, X], rtol=1e-5, atol=0, equal_nan=True)
        lam = d.state().l                               # the tuning the session starts at
        assert np.allclose(d.shown.slit_ts, small[1][:, 0, lam][:, iy, ix], rtol=1e-5, atol=0, equal_nan=True)


# ---------------------------------------------------------------- the slit's time slice
def test_the_slits_time_slice_reads_and_shows_100_of_250_t(drv, cube):
    drv.show("slit")
    drv.set_slit(SLIT)
    drv.wait_idle()
    iy, ix = drv.shown.slit_pix
    a, ts, lam = drv.shown.slit_ts, steps(NT, 100), drv.state().l
    frames = [r["frames"] for r in drv.scheduler.slit.reads if r.get("kind") == "ts"]
    print("time slice", a.shape, "frames read for it", frames)
    assert a.shape == (100, len(iy)) and np.allclose(a, cube[1][ts, 0, lam][:, iy, ix], rtol=1e-5, atol=0,
                                                               equal_nan=True)
    if drv.dataset.pixel is None:
        assert frames == [100]
    drv.session.store.set(t_cap=None)
    drv.wait_idle()
    assert drv.shown.slit_ts.shape == (NT, len(iy))


# ---------------------------------------------------------------- a file series: one file read per step
def test_a_series_reads_one_file_per_step_shown(tmp_path, monkeypatch):
    n, ny, nx = 150, 6, 5
    rng = np.random.default_rng(1)
    imgs = rng.integers(0, 3000, (n, ny, nx)).astype(np.int16)
    t0 = np.datetime64("2026-06-07T06:52:00.000", "ms")
    paths = []
    for k in range(n):
        h = fits.Header()
        h["T_OBS"] = str(t0 + np.timedelta64(12000 * k, "ms")) + "Z"
        h["WAVELNTH"], h["INSTRUME"], h["BUNIT"] = 171, "AIA_3", "DN"
        p = str(tmp_path / f"aia_{k:03d}.fits")
        fits.PrimaryHDU(imgs[k], h).writeto(p)
        paths.append(p)
    calls: list[int] = []
    orig = SeriesReader._pixel_raw

    def spy(self, t, y, x):
        calls.append(int(t))
        return orig(self, t, y, x)
    monkeypatch.setattr(SeriesReader, "_pixel_raw", spy)
    with Driver(Dataset.open(None, series=paths), own=True) as d:
        q = time.perf_counter()
        d.hover(3, 2)
        d.wait_idle()
        ts = steps(n, 100)
        print(f"series of {n}: files read {len(calls)}, curve {d.shown.lambda_t.shape}, "
              f"{(time.perf_counter() - q) * 1e3:.0f} ms")
        assert sorted(set(calls)) == ts.tolist() and len(calls) == 100
        assert np.array_equal(d.shown.lambda_t.reshape(-1), imgs[ts, 3, 2].astype(np.float32))


# ---------------------------------------------------------------- the panels: drawn in the cube's own t
def test_the_panels_draw_the_steps_at_their_t_and_a_click_picks_the_nearest(qapp):
    from PySide6 import QtCore

    from explorer.ui.lambda_t import LambdaTPanel, TimeCurve
    from explorer.ui.slitpanel import SlitPanel

    ts = steps(NT, 100)
    c = TimeCurve(NT, None)
    c.show(np.arange(100, dtype=np.float32)[:, None])
    print("curve x", np.asarray(c.curve.xData)[:4], "pick 5.0 ->", c.pick(QtCore.QPointF(5.0, 0)))
    assert np.allclose(c.curve.xData, ts + 0.5)
    assert c.pick(QtCore.QPointF(5.0, 0)) == {"t": 3} and c.pick(QtCore.QPointF(6.4, 0)) == {"t": 6}
    c.set_markers(4)
    assert c.t_line.value() == 4.5                   # the current t where it is, between the steps
    c.show(np.arange(NT, dtype=np.float32))          # every t: as before
    assert np.allclose(c.curve.xData, np.arange(NT) + 0.5) and c.pick(QtCore.QPointF(5.0, 0)) == {"t": 5}

    p = LambdaTPanel(NT, NL, None)
    p.show(np.ones((100, NL), np.float32), (0.0, 2.0))
    r = p.img.mapRectToParent(p.img.boundingRect())
    print("lambda-t image rect", r.height(), "pick y 5.0 ->", p.pick(QtCore.QPointF(1.5, 5.0)))
    assert r.height() == pytest.approx(NT) and p.pick(QtCore.QPointF(1.5, 5.0)) == {"l": 1, "t": 3}
    p.show(np.ones((NT, NL), np.float32), (0.0, 2.0))
    assert p.pick(QtCore.QPointF(1.5, 5.0)) == {"l": 1, "t": 5}

    s = SlitPanel(NT, NL, None)
    s.set_path((np.arange(8), np.arange(8)))
    s.show(np.ones((100, 8), np.float32), np.ones((NL, 8), np.float32), (0.0, 2.0), (0.0, 2.0))
    r = s.ts_img.mapRectToParent(s.ts_img.boundingRect())
    assert r.height() == pytest.approx(NT) and np.array_equal(s.steps, ts)
