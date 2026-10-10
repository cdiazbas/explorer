"""Cubes without lambda, or with a single tuning, main or linked, offscreen: no Spectrum panel without lambda (absent
after reset_panels and a saved layout's restore too, and not in the Panels menu); lambda-t, one cell wide, a curve of
the cursor's value against t, named by what the cube shows, its unit on the y axis, the current t marked and a click
on it setting t; the slit's one-row spectral slice left out, for the main cube as for a linked one. A cube with
lambda keeps its panels as they were. Each test prints what it measured."""
import time

import numpy as np
import pytest

from explorer.testing import synth

NT, NY, NX = 5, 48, 40


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


def t_map(path, btype="Blos", bunit="G"):
    from astropy.io import fits

    y, x = np.mgrid[0:NY, 0:NX]
    a = np.stack([np.sin(x / 6 + t) * 300 + y * 5 + 40 * t for t in range(NT)]).astype(">f4")
    h = fits.Header()
    h["CTYPE1"], h["CTYPE2"], h["CTYPE3"] = "HPLN-TAN", "HPLT-TAN", "UTC"
    h["BTYPE"], h["BUNIT"] = btype, bunit
    fits.PrimaryHDU(a, h).writeto(path)
    return path, a.astype(np.float32)


@pytest.fixture(scope="module")
def cubes(tmp_path_factory):
    d = tmp_path_factory.mktemp("nolambda")
    spec = synth.write_dataset(d, "spec", shape=(NT, 4, 7, NY, NX), sp=False, icube=False)["im"]
    one = synth.write_dataset(d, "onel", shape=(NT, 4, 1, NY, NX), seed=3, sp=False, icube=False)["im"]
    blos, values = t_map(d / "blos_t.fits")
    return {"spec": spec, "one": one, "blos": str(blos), "values": values}


def open_window(qapp, main, linked=(), **kw):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(main)
    lks = [Dataset.open(p, executors=ds.executors) for p in linked]
    w = Shell(ds, linked=lks, **kw)
    w.resize(1200, 640)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    qapp.processEvents()

    def close():
        w.close()
        for d in lks:
            d.close()
        ds.close()
    return w, close


def test_a_single_tuning_or_none_is_named_by_what_the_cube_shows():
    """One plane along lambda, or no lambda: mapped, its lambda-t named by the cube's line or quantity, its values by
    BTYPE (else the map's word, else "value") with BUNIT; more than one tuning known to be lambda: as always."""
    from explorer.data.axes import Roles
    from explorer.data.names import slice_names

    class Ax:
        def __init__(self, btype=None, bunit=None, line=None, dl=None):
            self.btype, self.bunit, self.line, self._dl = btype, bunit, line, dl

        def dlam_A(self):
            return self._dl

    cases = [
        (Roles(0, 1, 2, 5, 4, 7), Ax(line="Fe I 617.3", dl=list(range(7))), "x_im.fits",
         ("λ–t", "λ index", True, False)),
        (Roles(0, 1, 2, 5, 4, 1), Ax(line="Fe I 617.3", dl=[0.0], bunit="W"), "x_im.fits",
         ("Fe I 617.3–t", "Fe I 617.3 index", True, True, "value [W]")),
        (Roles(0, None, None, 5, 1, 1), Ax(btype="Blos", bunit="G"), "m.fits", ("Blos–t", "Blos index", False, True,
                                                                               "Blos [G]")),
        (Roles(0, None, None, 5, 1, 1), Ax(), "Vlos.6173_map.fcube", ("Vlos–t", "Vlos index", False, True, "Vlos")),
    ]
    for r, ax, path, want in cases:
        got = slice_names(r, ax, path)
        print(path, r.nl, "->", tuple(got))
        assert tuple(got)[:len(want)] == want


def test_a_map_main_cube_has_no_spectrum_panel_anywhere(qapp, cubes, tmp_path):
    """No Spectrum for a cube without lambda: hidden at start, and kept so by reset_panels and by a saved layout's
    restore (which shows every hidden panel), and not offered in the Panels menu."""
    from explorer.ui.layout import LayoutStore

    w, close = open_window(qapp, cubes["blos"])
    try:
        assert w.spectra is None and w.spec_dock.isHidden()
        w.reset_panels()
        qapp.processEvents()
        after_reset = w.spec_dock.isHidden()
        store = LayoutStore("nolambda", path=str(tmp_path / "layout.ini"))
        store.save(w)
        store.restore(w, qapp)
        qapp.processEvents()
        after_restore = w.spec_dock.isHidden()
        offered = w.spec_dock.toggleViewAction().isVisible()
        print("Spectrum hidden after reset", after_reset, "after restore", after_restore, "in the menu", offered)
        assert after_reset and after_restore and not offered
    finally:
        close()


def test_a_map_s_lambda_t_is_its_value_against_t_and_a_click_sets_t(qapp, cubes):
    """The map's lambda-t is a curve (TimeCurve): the cursor's values over t, as the file has them, named "Blos–t",
    "Blos [G]" up; the current t marked; a click on it at t = 3 sets t = 3."""
    from PySide6 import QtCore

    from explorer.ui.lambda_t import TimeCurve

    w, close = open_window(qapp, cubes["blos"])
    try:
        lt = w.lambda_t
        assert isinstance(lt, TimeCurve), type(lt)
        y, x = 20, 13
        w.session.hover(y, x)
        w.session.lock(True)
        want = cubes["values"][:, y, x]
        spin(qapp, lambda: lt.curve.yData is not None and np.allclose(lt.curve.yData, want))
        got = np.asarray(lt.curve.yData)
        print("dock", w.lt_dock.windowTitle(), "y label", lt.w.getAxis("left").labelText, "curve", got, "file", want)
        assert w.lt_dock.windowTitle() == "Blos–t" and lt.w.getAxis("left").labelText == "Blos [G]"
        assert np.allclose(got, want) and not w.lt_dock.isHidden()
        assert lt.t_line.value() == pytest.approx(w.session.state.t + 0.5)
        vb = lt.w.getPlotItem().vb
        pos = vb.mapViewToScene(QtCore.QPointF(3.5, float(np.mean(want))))
        w.main.lt_pick(pos)
        qapp.processEvents()
        print("t after a click at 3.5:", w.session.state.t, "marker", lt.t_line.value())
        assert w.session.state.t == 3 and lt.t_line.value() == pytest.approx(3.5)
    finally:
        close()


def test_a_single_tuning_keeps_its_spectra_and_has_a_curve_for_lambda_t(qapp, cubes):
    from explorer.ui.lambda_t import TimeCurve

    w, close = open_window(qapp, cubes["one"])
    try:
        print("spectra", type(w.spectra).__name__, "lambda-t", type(w.lambda_t).__name__, w.lt_dock.windowTitle())
        assert w.spectra is not None and not w.spec_dock.isHidden()
        assert isinstance(w.lambda_t, TimeCurve) and w.lt_dock.windowTitle() == "Fe I 617.3–t"
    finally:
        close()


def test_a_linked_map_has_a_curve_tab_and_no_spectra_tab(qapp, cubes):
    """Linked to a cube with lambda, the map has no Spectrum tab and a lambda-t tab with its curve."""
    from explorer.ui.lambda_t import LambdaTPanel, TimeCurve

    w, close = open_window(qapp, cubes["spec"], linked=[cubes["blos"]])
    try:
        c = w.linked[0]
        tabs = {k: [t.tabText(i) for i in range(t.count())] for k, t in (("spectra", w.spec_tabs),
                                                                          ("lambda_t", w.lt_tabs)) if t is not None}
        print("tabs", tabs, "main", type(w.lambda_t).__name__, "linked", type(c.lambda_t).__name__)
        assert c.spectra is None and isinstance(c.lambda_t, TimeCurve) and isinstance(w.lambda_t, LambdaTPanel)
        assert w.spec_tabs is None and w.lt_tabs is not None and w.lt_tabs.count() == 2
    finally:
        close()


def test_a_main_cube_with_lambda_keeps_its_panels(qapp, cubes):
    from explorer.ui.lambda_t import LambdaTPanel

    w, close = open_window(qapp, cubes["spec"])
    try:
        print("lambda-t", type(w.lambda_t).__name__, w.lt_dock.windowTitle(), "slices", w.main.slices,
              "slit spectral", w.slit_panel.spectral)
        assert isinstance(w.lambda_t, LambdaTPanel) and w.lt_dock.windowTitle() == "λ–t" and w.main.slices is None
        assert w.slit_panel.spectral and not w.spec_dock.isHidden()
        assert w.spec_dock.toggleViewAction().isVisible() and w.lt_dock.toggleViewAction().isVisible()
    finally:
        close()
