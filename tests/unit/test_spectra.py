"""The spectra panel (ROADMAP E4.3), offscreen: its layout, axes and titles; what it draws is the core's spectrum in
plot units, with the core's y ranges and the cursor's lambda; a cube without lambda has no panel."""
import time

import numpy as np
import pytest

from explorer.testing import synth

SHAPE = (3, 4, 21, 48, 40)


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


def test_ticks_with_a_typographic_minus_and_a_plus_for_offsets(qapp):
    from explorer.ui.spectra import SignedAxis, decimals

    assert (decimals(1), decimals(0.5), decimals(0.05), decimals(0)) == (0, 1, 2, 2)
    assert SignedAxis("left").tickStrings([-0.5, 0.0, 0.5], 1, 0.5) == ["−0.5", "0.0", "0.5"]
    assert SignedAxis("bottom", plus=True).tickStrings([-0.2, 0.0, 0.2], 1, 0.2) == ["−0.2", "0", "+0.2"]


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("spectra"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    w.resize(1400, 900)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and "spectra" in w.last)
    yield w
    w.close()
    ds.close()


def test_four_stokes_as_two_by_two_with_physical_axes_and_units(qapp, shell):
    sp = shell.spectra
    assert sp is not None and len(sp.plots) == 4 and sp.physical
    rows_cols = [(sp.w.ci.getItem(r, c) is not None) for r in range(2) for c in range(2)]
    assert all(rows_cols)                                                   # I Q / U V
    assert all(p.vb.linkedView(p.vb.XAxis) is sp.plots[0].vb for p in sp.plots[1:])
    assert sp.plots[0].getAxis("top").isVisible()                          # v [km/s] over delta-lambda
    assert spin(qapp, lambda: sp.iscale is not None)
    labels = [p.getAxis("left").labelText for p in sp.plots]
    assert labels[0].startswith("I [10") and all("/I<sub>c</sub> [%]" in t for t in labels[1:])


def test_stokes_i_has_its_power_of_ten_from_the_start(qapp, cube):
    """With a per-pixel file, I's power of ten from the cursor's block read as the window is built (the prototype's
    first spectrum): the title never shows without it, and never widens its axis once the spectrum comes."""
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    with Dataset.open(cube) as ds:
        assert ds.pixel is not None
        w = Shell(ds)                                   # no event processed yet
        try:
            assert w.spectra.iscale is not None
            assert w.spectra.plots[0].getAxis("left").labelText.startswith("I [10")
            assert ds.peek_block(*w.session.state.cursor) is not None      # the first spectrum: no second read
        finally:
            w.close()


def test_it_draws_the_cores_spectrum_with_the_cores_ranges_and_lambda(qapp, shell):
    sp, s = shell.spectra, shell.session
    s.hover(20, 15)
    assert spin(qapp, lambda: shell.last["spectra"][1] == (20, 15))
    spec = shell.last["spectra"][0]                                        # plot units, from the core
    for k in range(4):
        x, y = sp.curves[k].getData()
        assert np.array_equal(x, sp.xl) and np.allclose(y, spec[k], equal_nan=True)
    yr = shell.scheduler.yrange
    assert spin(qapp, lambda: all(yr.r[k] is None or np.allclose(sp.plots[k].vb.viewRange()[1], yr.r[k])
                                  for k in range(4)))
    s.step("l", 3)
    assert spin(qapp, lambda: all(ln.value() == sp.xl[s.state.l] for ln in sp.lines))


def test_padding_leaves_the_plots_empty(qapp, shell):
    sp = shell.spectra
    sp.show(np.full((4, SHAPE[2]), np.nan))
    assert all(len(c.getData()[0] or []) == 0 for c in sp.curves)


def test_one_stokes_is_one_column_and_a_cube_without_lambda_has_no_panel(qapp, tmp_path):
    from astropy.io import fits

    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell
    from explorer.ui.spectra import SpectraPanel

    one = SpectraPanel(1, 7, None)
    assert len(one.plots) == 1 and not one.physical and one.plots[0].getAxis("left").labelText == "I"
    p = tmp_path / "t_y_x.fits"                                             # (t, y, x): no lambda at all
    fits.PrimaryHDU(np.random.default_rng(1).uniform(1, 2, size=(5, 24, 20)).astype(np.float32)).writeto(p)
    ds = Dataset.open(p, axes="t")
    assert ds.roles.l is None
    w = Shell(ds)
    try:
        w.show()
        assert spin(qapp, lambda: w.first_image_s is not None)
        assert w.spectra is None and w.spec_dock.isHidden()
    finally:
        w.close()
        ds.close()
