"""Cubes without lambda, or with a single tuning, main or linked, offscreen: no Spectrum panel without lambda (absent
after reset_panels and a saved layout's restore too, and not in the Panels menu); lambda-t, one cell wide, a curve of
the cursor's value against t, named by what the cube shows, its unit on the y axis, the current t marked and a click
on it setting t; the slit's one-row spectral slice left out, for the main cube as for a linked one; a single
tuning's Spectrum only from the Panels menu. A cube with lambda keeps its panels as they were. Each test prints
what it measured."""
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


@pytest.mark.parametrize("which", ["blos", "one"])
def test_the_slit_of_a_main_cube_with_one_plane_or_none_shows_its_time_slice_alone(qapp, cubes, which):
    """The slit panel of a main cube with a single tuning, or none, leaves out the one-row spectral slice, as a
    linked map's does."""
    w, close = open_window(qapp, cubes[which])
    try:
        print(which, "spectral slice shown:", w.slit_panel.spectral, "label", w.slit_panel.label)
        assert not w.slit_panel.spectral
    finally:
        close()


def test_a_single_tuning_has_its_spectra_and_a_curve_for_lambda_t(qapp, cubes):
    from explorer.ui.lambda_t import TimeCurve

    w, close = open_window(qapp, cubes["one"])
    try:
        print("spectra", type(w.spectra).__name__, "lambda-t", type(w.lambda_t).__name__, w.lt_dock.windowTitle())
        assert w.spectra is not None
        assert isinstance(w.lambda_t, TimeCurve) and w.lt_dock.windowTitle() == "Fe I 617.3–t"
    finally:
        close()


@pytest.mark.parametrize("look", ["classic", "glass"])
def test_a_single_tuning_s_spectrum_opens_only_from_panels(qapp, cubes, tmp_path, look):
    """One lambda point: its Spectrum (one point per Stokes) is not shown at start, after reset_panels or a saved
    layout's restore, in classic or glass; it is offered in the Panels menu and opens from there, until the next
    reset. Linked to a cube with several points, it is shown as ever."""
    from explorer.look import get_look
    from explorer.ui.layout import LayoutStore

    w, close = open_window(qapp, cubes["one"], look=get_look(look))
    try:
        spin(qapp, lambda: False, timeout=0.3)
        at_start = w.spec_dock.isHidden()
        offered = w.spec_dock.toggleViewAction().isVisible() and w.spec_dock.toggleViewAction().isEnabled()
        w.reset_panels()
        spin(qapp, lambda: False, timeout=0.3)
        after_reset = w.spec_dock.isHidden()
        store = LayoutStore("onel", path=str(tmp_path / "layout.ini"))
        store.save(w)
        store.restore(w, qapp)
        qapp.processEvents()
        after_restore = w.spec_dock.isHidden()
        w.spec_dock.toggleViewAction().trigger()        # Panels → Spectrum
        spin(qapp, lambda: False, timeout=0.3)
        asked = not w.spec_dock.isHidden()
        w.reset_panels()
        spin(qapp, lambda: False, timeout=0.3)
        reset_again = w.spec_dock.isHidden()
        print(look, "Spectrum hidden at start", at_start, "after reset", after_reset, "after restore", after_restore,
              "in the menu", offered, "shown from it", asked, "hidden after the next reset", reset_again)
        assert at_start and after_reset and after_restore and offered and asked and reset_again
    finally:
        close()
    w, close = open_window(qapp, cubes["one"], linked=[cubes["spec"]], look=get_look(look))
    try:
        spin(qapp, lambda: False, timeout=0.3)
        print(look, "linked to 7 points: Spectrum hidden", w.spec_dock.isHidden())
        assert not w.spec_dock.isHidden()
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


def test_a_2d_map_s_slit_is_a_curve_along_it(qapp, cubes, tmp_path):
    """A map with neither t nor lambda: no Spectrum, no lambda-t, and its slit's one row drawn as a curve of its
    values along the slit (the file's, pixel by pixel), "Blos [G]" up."""
    from astropy.io import fits

    p = tmp_path / "blos_2d.fits"
    h = fits.Header()
    h["CTYPE1"], h["CTYPE2"], h["BTYPE"], h["BUNIT"] = "HPLN-TAN", "HPLT-TAN", "Blos", "G"
    img = cubes["values"][0]
    fits.PrimaryHDU(img.astype(">f4"), h).writeto(p)
    w, close = open_window(qapp, str(p))
    try:
        assert w.spec_dock.isHidden() and w.lt_dock.isHidden()
        assert not w.spec_dock.toggleViewAction().isVisible() and not w.lt_dock.toggleViewAction().isVisible()
        w.session.set_path([(4.5, 10.5), (30.5, 30.5)], cube=0)
        w._slit_shown(True)
        sp = w.slit_panel
        assert spin(qapp, lambda: sp.pix is not None and sp.curve.yData is not None and len(sp.curve.yData) == sp.n
                    and np.isfinite(sp.curve.yData).all())
        iy, ix = sp.pix
        got, want = np.asarray(sp.curve.yData), img[iy, ix]
        print("flat", sp.flat, "label", sp.ts.getAxis("left").labelText, "points", sp.n, "max |diff|",
              float(np.abs(got - want).max()))
        assert sp.flat and not sp.spectral and sp.ts.getAxis("left").labelText == "Blos [G]"
        assert np.allclose(got, want)
    finally:
        close()


def test_a_single_tuning_linked_cube_in_its_own_window_opens_its_spectrum_only_from_panels(qapp, cubes):
    """A linked cube with one lambda point, in a window of its own: its Spectrum is not shown there (as the main
    window's, E8.7), it is offered in Panels and opens from there; a cube with several points keeps its own."""
    w, close = open_window(qapp, cubes["spec"], linked=[cubes["one"]])
    try:
        w.detach_action.setChecked(True)
        spin(qapp, lambda: False, timeout=0.6)
        c = w.linked[0]
        pane = c.panes["spectra:1"]
        at_start = pane.isHidden()
        menu = w.nav.panels.menu()
        menu.aboutToShow.emit()
        entry = [a for a in menu.actions() if a.text() == f"{c.name} · Spectrum"]
        entry[0].trigger()                              # Panels → its Spectrum
        spin(qapp, lambda: False, timeout=0.3)
        asked = not pane.isHidden()
        print("its own window: Spectrum hidden at start", at_start, "in the menu", len(entry), "shown from it", asked,
              "main Spectrum shown", not w.spec_dock.isHidden())
        assert at_start and len(entry) == 1 and asked and not w.spec_dock.isHidden()
        w.detach_action.setChecked(False)
        spin(qapp, lambda: False, timeout=0.3)
    finally:
        close()


def test_glass_s_panels_brings_back_a_single_tuning_s_spectrum_closed_by_its_mark(qapp, cubes):
    """One lambda point in glass: its Spectrum, opened from Panels and closed by its close mark, comes back from
    Panels (I is not bound); a reset still forgets it."""
    from PySide6 import QtWidgets

    from explorer.look import get_look

    w, close = open_window(qapp, cubes["one"], look=get_look("glass"))
    try:
        spin(qapp, lambda: False, timeout=0.3)
        w.spec_dock.toggleViewAction().trigger()        # Panels → Spectrum
        spin(qapp, lambda: False, timeout=0.3)
        asked = not w.spec_dock.isHidden()
        for d in (w.spec_dock, w.lt_dock):              # each closed by its close mark
            d.titleBarWidget().findChild(QtWidgets.QAbstractButton, "qt_dockwidget_closebutton").click()
        spin(qapp, lambda: False, timeout=0.3)
        closed = (w.spec_dock.isHidden(), w.lt_dock.isHidden())
        for d in (w.spec_dock, w.lt_dock):              # Panels → each entry again
            d.toggleViewAction().trigger()
        spin(qapp, lambda: False, timeout=0.3)
        back = (not w.spec_dock.isHidden(), not w.lt_dock.isHidden())
        w.reset_panels()
        spin(qapp, lambda: False, timeout=0.3)
        print("glass: shown from Panels", asked, "closed", closed, "back from Panels", back, "hidden after a reset",
              w.spec_dock.isHidden())
        assert asked and closed == (True, True) and back == (True, True) and w.spec_dock.isHidden()
    finally:
        close()
