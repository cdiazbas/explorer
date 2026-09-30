"""testing.Driver end to end on the synthetic cube, with and without a per-pixel file: what would be drawn equals
the data; a burst of moves reads once; padding, the lock and hidden panels read nothing; the y-range sample and
padlock work through the public API."""
import numpy as np
import pytest
from astropy.io import fits

from explorer.core.scheduler import SAMPLE_AFTER_S
from explorer.data.axes import plot_units
from explorer.obs import summary
from explorer.testing import synth
from explorer.testing.driver import Driver

SHAPE = (3, 4, 5, 48, 40)


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("drv"), "c", shape=SHAPE, icube=False)
    return d["im"], fits.getdata(d["im"]).astype(np.float32)


@pytest.fixture(params=["sp", "nosp"])
def drv(request, cube):
    with Driver.open(cube[0], no_sp=request.param == "nosp") as d:
        yield d, cube[1]


def reads():
    return summary().get("counters", {}).get("core.cursor.reads", 0)


def test_what_is_drawn_is_the_data(drv):
    d, data = drv
    st = d.state()
    assert d.shown.image_idx == (0, 0, 2) and np.array_equal(d.shown.image, data[0, 0, 2], equal_nan=True)
    d.hover(20, 15)
    d.set_stokes(3)
    d.wait_idle()
    y, x = 20, 15
    np.testing.assert_array_equal(d.shown.lambda_t, data[:, 3, :, y, x])
    want = plot_units(data[st.t, :, :, y, x], d.dataset.axes.cont, d.shown.iscale)
    np.testing.assert_allclose(d.shown.spectra, want, rtol=1e-6)
    assert d.shown.spectra_at == ((20, 15), 0) and d.shown.lambda_t_at == ((20, 15), 3)


def test_a_burst_of_moves_reads_once(drv):
    d, _ = drv
    before = reads()
    for x in range(10, 20):
        d.hover(24, x)
    d.wait_idle()
    assert reads() == before + 1 and d.shown.spectra_at[0] == (24, 19)


def test_padding_lock_and_hidden_panels_read_nothing(drv):
    d, _ = drv
    before = reads()
    d.hover(1, 1)                                           # padding
    d.wait_idle()
    assert d.shown.cleared_at == (1, 1) and d.shown.spectra is None and reads() == before
    d.hover(24, 20)
    d.wait_idle()
    d.lock()
    d.hover(30, 30)
    d.wait_idle()
    assert d.state().cursor == (24, 20)
    d.lock(False)
    d.show("spectra", False)
    d.show("lambda_t", False)
    d.wait_idle()
    before = reads()
    d.hover(30, 30)
    d.wait_idle()
    assert reads() == before


def test_a_t_step_redraws_the_spectra_only(drv):
    d, data = drv
    d.hover(22, 18)
    d.wait_idle()
    n = dict(d.shown.counts)
    d.step("t", 1)
    d.wait_idle()
    assert d.shown.counts["spectra"] == n["spectra"] + 1 and d.shown.counts.get("lambda_t") == n.get("lambda_t")
    assert d.shown.image_idx == (1, 0, 2)


def test_y_range_sample_and_padlock(drv):
    d, _ = drv
    d.advance(SAMPLE_AFTER_S)
    d.wait_idle()
    d.set_y_fixed(True)
    d.wait_idle()
    sample = d.y_sample()
    assert sample is not None and d.shown.y_ranges[0] == sample[0]
    assert all(d.shown.y_ranges[k] == sample[k] for k in (1, 2, 3))         # Q U V from whole frames in
