"""What a cube's values and its axis other than t are called, offscreen: the Spectrum panel of an axis not known to be
lambda named as its lambda-t is, and its values as what the cube shows when it has no Stokes; the status bar's value
named I Q U V only with Stokes or along lambda, else by what the cube shows, as its curve's axis. Each test prints
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


def fits_cube(path, a, **cards):
    from astropy.io import fits

    h = fits.Header()
    for k, v in cards.items():
        h[k] = v
    fits.PrimaryHDU(np.asarray(a, ">f4"), h).writeto(path)
    return str(path)


@pytest.fixture(scope="module")
def cubes(tmp_path_factory):
    d = tmp_path_factory.mktemp("labels")
    spec = synth.write_dataset(d, "spec", shape=(NT, 4, 7, NY, NX), sp=False, icube=False)["im"]
    y, x = np.mgrid[0:NY, 0:NX]
    planes = np.stack([np.sin(x / 6 + k) * 300 + y * 5 + 40 * k for k in range(NT)])
    # one axis before the image, unnamed: "unknown", taken for lambda by default, not known to be
    unknown = fits_cube(d / "blos_planes.fits", planes, BTYPE="Blos", BUNIT="G")
    blos_t = fits_cube(d / "blos_t.fits", planes, CTYPE1="HPLN-TAN", CTYPE2="HPLT-TAN", CTYPE3="UTC", BTYPE="Blos",
                       BUNIT="G")
    plain_t = fits_cube(d / "aia_like.fits", planes + 500, CTYPE3="UTC")         # no BTYPE, no BUNIT, no map word
    # two unnamed axes before the image: "default (t, lambda)", its second not known to be lambda
    t_planes = fits_cube(d / "blos_t_planes.fits", np.stack([planes[:3] + 10 * t for t in range(NT)]), BTYPE="Blos",
                         BUNIT="G")
    return {"spec": spec, "unknown": unknown, "blos_t": blos_t, "plain_t": plain_t, "t_planes": t_planes}


def test_the_main_cube_names_an_axis_not_known_to_be_lambda_as_a_linked_one(qapp, cubes):
    """The main cube with an axis of several planes not known to be lambda (two unnamed axes: t and one taken for
    lambda by default) names it as a linked cube does (data.names.slice_names: "Blos–t", "Blos index"): its lambda-t's
    title and x axis, its Spectrum's x axis, its slit panel's spectral axis. Before: "λ–t" and "λ index"."""
    w, close = open_window(qapp, cubes["t_planes"])
    try:
        assert w.dataset.roles.how == "default (t, lambda)"
        got = {"title": w.lt_dock.windowTitle(),
               "lambda-t": w.lambda_t.w.getPlotItem().getAxis("bottom").labelText,
               "spectrum": w.main.spectra.plots[-1].getAxis("bottom").labelText,
               "slit": w.slit_panel.sl.getAxis("left").labelText}
        print(got)
        assert got == {"title": "Blos–t", "lambda-t": "Blos index", "spectrum": "Blos index", "slit": "Blos index"}
    finally:
        close()


def open_window(qapp, main, linked=(), size=(1200, 640)):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(main)
    lks = [Dataset.open(p, executors=ds.executors) for p in linked]
    w = Shell(ds, linked=lks)
    w.resize(*size)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and all(c.scheduler.img is not None for c in w.linked))
    qapp.processEvents()

    def close():
        w.close()
        for d in lks:
            d.close()
        ds.close()
    return w, close


def test_the_spectrum_of_an_axis_not_known_to_be_lambda_is_named_as_its_lambda_t(qapp, cubes):
    """A linked cube whose one axis before the image is unnamed: its Spectrum's x axis says what its lambda-t says
    ("Blos index", data.names.slice_names), not "λ index"; without Stokes its values are "Blos", not "I". The main
    cube, along lambda with I Q U V, keeps "Δλ [Å]" and I Q U V."""
    w, close = open_window(qapp, cubes["spec"], [cubes["unknown"]])
    try:
        lk = w.linked[0]
        assert lk.slices is not None and not lk.slices.spectral and lk.spectra is not None
        x = lk.spectra.plots[-1].getAxis("bottom").labelText
        y = lk.spectra.plots[0].getAxis("left").labelText
        mx = w.main.spectra.plots[-1].getAxis("bottom").labelText
        my = [p.getAxis("left").labelText for p in w.main.spectra.plots]
        print("linked x", repr(x), "y", repr(y), "lambda-t label", repr(lk.slices.label), "| main x", repr(mx),
              "y", my)
        assert x == lk.slices.label == "Blos index"
        assert y.startswith("Blos") and not y.startswith("I")
        assert mx == "λ − 6173.34\u00a0Å" and my[0].startswith("I [")
        assert all(t.startswith(s) for t, s in zip(my[1:], "QUV", strict=True))
    finally:
        close()


def test_every_axis_in_delta_lambda_says_the_line_centre_it_is_measured_from(qapp, cubes):
    """Spectrum, lambda-t and the slit's spectral slice: "λ − 6173.34 Å", λ₀ the laboratory centre of
    the header's line (WAVEBAND Fe I 6173: 617.3341 nm) to the readout's three decimals; the velocity axis over the
    Spectrum is measured from the same λ₀. A cube whose axis is not known to be lambda keeps its index label."""
    from explorer.data.axes import C_KMS

    w, close = open_window(qapp, cubes["spec"], [cubes["unknown"]])
    try:
        want = "λ − 6173.34\u00a0Å"
        got = {"spectrum": w.main.spectra.plots[-1].getAxis("bottom").labelText,
               "lambda-t": w.lambda_t.w.getPlotItem().getAxis("bottom").labelText,
               "slit": w.slit_panel.sl.getAxis("left").labelText}
        print("labels:", got, "| lam0_nm", w.dataset.axes.lam0_nm)
        assert all(v == want for v in got.values()), got
        top = w.main.spectra.plots[0].getAxis("top")
        assert top.k == pytest.approx(C_KMS / 6173.341)                    # v from the same λ₀
        assert w.linked[0].spectra.plots[-1].getAxis("bottom").labelText == "Blos index"
    finally:
        close()


@pytest.mark.parametrize("which, name", [("blos_t", "Blos"), ("plain_t", "Quantity"), ("spec", "I")])
def test_the_status_bar_names_the_value_by_what_the_cube_shows_without_stokes(qapp, cubes, which, name):
    """A cube without Stokes and without lambda: the status bar names its value as its curve's axis does (BTYPE, the
    map's word, ..., else "Quantity": data.names.quantity); with I Q U V along lambda: I, then Q."""
    w, close = open_window(qapp, cubes[which])
    try:
        w.session.hover(NY // 2, NX // 2)
        qapp.processEvents()
        last = w.status.text().split("   ·   ")[-1]
        curve = w.main.slices.value if w.main.slices is not None else None
        print(which, "status", repr(w.status.text()), "| curve's y", repr(curve))
        assert last.split(" ")[0] == name
        assert curve is None or curve.split(" [")[0] == name
        if which == "spec":
            w.session.set_index("s", 1)
            assert spin(qapp, lambda: w.status.text().split("   ·   ")[-1].startswith("Q"))
    finally:
        close()
