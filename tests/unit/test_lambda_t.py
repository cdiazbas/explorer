"""The lambda-t panel (ROADMAP E4.4), offscreen: its axes (ticks at cell centres, round delta-lambda between the
tunings), what it draws (the core's lambda-t with the core's levels, on the index grid), its markers, no zoom, and
no panel without t or lambda."""
import time

import numpy as np
import pytest

from explorer.testing import synth

SHAPE = (6, 4, 21, 48, 40)


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


def test_index_ticks_at_cell_centres_each_cell_once(qapp):
    from explorer.ui.lambda_t import IndexAxis

    ax = IndexAxis("bottom", str, 10)
    (step, vals), = ax.tickValues(0, 10, 2000)          # room for every label
    assert step == 1 and vals == [i + 0.5 for i in range(10)]
    assert ax.tickStrings(vals, 1, 1) == [str(i) for i in range(10)]
    (step, vals), = ax.tickValues(0, 10, 60)            # little room: every 5th cell
    assert step == 5 and vals == [0.5, 5.5]


def test_tuning_ticks_are_round_delta_lambda_between_the_tunings(qapp):
    from explorer.ui.lambda_t import TuningAxis

    xl = np.array([-0.33, -0.17, -0.09, -0.01, 0.07, 0.15, 0.4])   # uneven, as a line scan and its continuum
    ax = TuningAxis("bottom", xl)
    ticks = [v for _sp, vs in ax.tickValues(0, len(xl), 600) for v in vs]
    labels = ax.tickStrings(ticks, 1, 0.1)
    assert labels and all(abs(float(s.replace("−", "-")) * 10 - round(float(s.replace("−", "-")) * 10))
                          < 1e-9 for s in labels)          # round tenths, not the tunings' own values
    assert all(0 <= v <= len(xl) for v in ticks)          # placed on the index grid


def test_tuning_labels_never_overlap_across_tick_levels(qapp):
    """The 6173 cube's tunings, from -0.34 to the continuum at +0.68 Å: on the wide-spaced continuum side a minor
    +0.3 landed on a major +0.4 when the room was checked per level."""
    from PySide6 import QtGui

    from explorer.ui.lambda_t import TuningAxis

    xl = np.array([-0.34, -0.24, -0.17, -0.12, -0.08, -0.05, -0.02, 0.01, 0.04, 0.08, 0.12, 0.2, 0.32, 0.68])
    ax = TuningAxis("bottom", xl)
    size = 600
    room = QtGui.QFontMetrics(QtGui.QFont()).horizontalAdvance("\u22120.00") + 10
    px = sorted(v / len(xl) * size for _sp, vs in ax.tickValues(0, len(xl), size) for v in vs)
    assert px and all(b - a >= room - 1e-6 for a, b in zip(px, px[1:], strict=False))


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("lambda_t"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    w.resize(1400, 900)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and "lambda_t" in w.last)
    yield w
    w.close()
    ds.close()


def test_it_draws_the_cores_lambda_t_on_the_index_grid_with_the_markers(qapp, shell):
    lt_panel, s = shell.lambda_t, shell.session
    s.hover(20, 15)
    s.set_index("s", 3)                                 # Stokes V: levels symmetric about 0
    assert spin(qapp, lambda: shell.last["lambda_t"][1] == (20, 15) and shell.last["lambda_t"][2] == 3)
    lt, _pixel, _s, levels = shell.last["lambda_t"]
    assert lt.shape == (SHAPE[0], SHAPE[2])
    assert np.allclose(lt_panel.img.image, lt, equal_nan=True)
    assert tuple(lt_panel.img.levels) == pytest.approx(tuple(levels)) and levels[0] == pytest.approx(-levels[1])
    r = lt_panel.img.mapRectToParent(lt_panel.img.boundingRect())
    assert (r.x(), r.y(), r.width(), r.height()) == (0, 0, SHAPE[2], SHAPE[0])    # one cell per (t, lambda)
    s.step("t", 2)
    s.step("l", -3)
    assert spin(qapp, lambda: lt_panel.t_line.value() == s.state.t + 0.5 and lt_panel.l_line.value() == s.state.l + 0.5)


def test_no_zoom_no_pan_and_nothing_finite_draws_an_empty_grid(qapp, shell):
    lt_panel = shell.lambda_t
    vb = lt_panel.w.getPlotItem().vb
    assert vb.state["mouseEnabled"] == [False, False]
    lt_panel.show(np.full((SHAPE[0], SHAPE[2]), np.nan), (0.0, 1.0))
    assert not np.isnan(lt_panel.img.image).any()


def test_no_lambda_t_without_t(qapp, tmp_path):
    from astropy.io import fits

    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    p = tmp_path / "s_l_y_x.fits"
    fits.PrimaryHDU(np.random.default_rng(1).uniform(1, 2, size=(4, 7, 24, 20)).astype(np.float32)).writeto(p)
    ds = Dataset.open(p, axes="s,l")
    w = Shell(ds)
    try:
        w.show()
        assert spin(qapp, lambda: w.first_image_s is not None)
        assert w.lambda_t is None and w.lt_dock.isHidden() and w.spectra is not None
    finally:
        w.close()
        ds.close()
