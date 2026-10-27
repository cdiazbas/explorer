"""Bifrost simulation cubes, as helita's writefits writes them (SI; z the vertical axis, positive up, the last index of
its three; a 1-D extension ' z-coordinate' with the non-uniform heights in Mm; BUNIT = T, a FITS logical, for the
field in tesla; BTYPE 'lg(x)' for log10 of x), offscreen. The header is the real files' (en024048_hion, snapshot 385)
on a small cube. Each test prints what it measured."""
import time

import numpy as np
import pytest
from astropy.io import fits

NZ, NY, NX = 30, 20, 24
ZTAU51 = 0.0613866
Z = (-2.444008 + (14.36705 + 2.444008) * (np.linspace(0, 1, NZ) ** 1.6)).astype(np.float32)   # non-uniform, up


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


def bifrost(path, btype="lg(tg)", bunit="K", data=None, instrume="Bifrost ", ext=True):
    """A snapshot variable [z, y, x] with the real files' cards; data: its values (default: log10 T rising with
    height, a little structure in x and y)."""
    z, y, x = np.mgrid[0:NZ, 0:NY, 0:NX]
    a = data if data is not None else 3.6 + 2.5 * z / NZ + 0.05 * np.sin(x / 3.0) * np.cos(y / 4.0)
    h = fits.Header()
    for k, v in (("INSTRUME", instrume), ("OBJECT", "en024048_hion"), ("ORIGIN", " ITA/Oslo"), ("BTYPE", btype),
                 ("BUNIT", bunit), ("CTYPE1", "x"), ("CTYPE2", "y"), ("CTYPE3", "z"), ("CUNIT1", "Mm"),
                 ("CUNIT2", "Mm"), ("CUNIT3", "Mm"), ("CDELT1", 0.0476190), ("CDELT2", 0.0476190),
                 ("CDELT3", 0.0971498), ("CRVAL1", 0.0), ("CRVAL2", 0.0), ("CRVAL3", -2.44401), ("CRPIX1", 1),
                 ("CRPIX2", 1), ("CRPIX3", 1), ("ELAPSED", 3850.0), ("ZTAU51", ZTAU51), ("DATA_LEV", 2)):
        if v is not None:
            h[k] = v
    hdus = [fits.PrimaryHDU(np.asarray(a, ">f4"), h)]
    if ext:
        e = fits.ImageHDU(Z.astype(">f4"))
        e.header["EXTNAME"] = " z-coordinate"
        hdus.append(e)
    fits.HDUList(hdus).writeto(path)
    return str(path)


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    d = tmp_path_factory.mktemp("bifrost")
    z, y, x = np.mgrid[0:NZ, 0:NY, 0:NX]
    return {"lgtg": bifrost(d / "BIFROST_en024048_hion_lgtg_385.fits"),
            "bz": bifrost(d / "BIFROST_en024048_hion_bz_385.fits", "bz", True,
                          0.25 * np.sin(x / 4.0) * np.exp(-z / 10.0)),
            "bz_other": bifrost(d / "other_bz.fits", "bz", True, 0.25 * np.sin(x / 4.0), instrume="MURaM"),
            "linear": bifrost(d / "BIFROST_noext_lgtg_385.fits", ext=False)}


def open_window(qapp, path=None, series=None):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(None, series=series) if series else Dataset.open(path)
    w = Shell(ds)
    w.resize(1100, 600)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    qapp.processEvents()

    def close():
        w.close()
        ds.close()
    return w, close


def test_an_axis_s_own_coordinates_from_its_extension_else_its_linear_wcs(files):
    """Point 1: the ' z-coordinate' extension (NAXIS3 values) is z in CUNIT3, non-uniform; without it the linear WCS
    (CRVAL3 + (i + 1 - CRPIX3) CDELT3); x and y by theirs. A cube's own lambda, t, Stokes or solar axes are not
    read so. Before: no coordinates."""
    from explorer.data import axes

    ax = axes.from_fits(files["lgtg"])
    z, u = ax.lead_coord(0)
    print("z", z[:3], "...", z[-1], u, "| x", ax.coord(1)[0][:3], ax.coord(1)[1])
    np.testing.assert_allclose(z, Z, rtol=1e-6)
    assert u == "Mm" and np.diff(np.diff(z)).std() > 0              # the extension's, non-uniform
    np.testing.assert_allclose(ax.coord(1)[0], np.arange(NX) * 0.0476190, rtol=1e-6)
    lin = axes.from_fits(files["linear"]).lead_coord(0)[0]
    np.testing.assert_allclose(lin, -2.44401 + np.arange(NZ) * 0.0971498, rtol=1e-6)


def test_a_bifrost_field_s_logical_bunit_is_tesla_and_a_log_says_so(files):
    """Points 2 and 3: BUNIT = T (a logical) in a Bifrost file is tesla ("bz [T]"), elsewhere no unit, as before;
    BTYPE lg(tg) reads "log₁₀(tg) [K]". Before: "bz", "lg(tg) [K]"."""
    from explorer.data import axes
    from explorer.data.names import short_name, slice_names

    got = {}
    for key in ("bz", "bz_other", "lgtg"):
        lay_ax = axes.from_fits(files[key])
        r = axes.Roles(None, None, 0, 1, 1, NZ, "unknown")
        got[key] = (slice_names(r, lay_ax, files[key]).value, short_name(files[key], lay_ax))
    print(got)
    assert got["bz"][0] == "bz [T]" and got["bz_other"][0] == "bz"
    assert got["lgtg"] == ("log₁₀(tg) [K]", "log₁₀(tg)")


def test_a_bifrost_cube_in_the_window_reads_in_mm(qapp, files):
    """Points 1, 3, 4, 5 and 8 in the window: the profile panel ("Profile", not "Spectrum") along z in Mm, its
    points at the extension's heights, a quiet line at ZTAU51 labelled "τ₅₀₀=1", its y axis "log₁₀(tg) [K]" with no
    10⁰; the slider "z" with the height, "1.23 Mm"; the status line x and y in Mm, z in Mm and the value with its
    unit and no × 10⁰. Before: "Spectrum", "z index", "z 15/29", "x 12  y 10", "λ 15", "lg(tg) 4.85 × 10⁰ K"."""
    w, close = open_window(qapp, files["lgtg"])
    try:
        w.session.hover(10, 12)
        w.session.set_index("l", 15)
        qapp.processEvents()
        assert spin(qapp, lambda: w.spectra is not None and w.spectra.curves[0].xData is not None)
        sp = w.spectra
        p = sp.plots[0]
        refs = [(ln.value(), ln.label.toPlainText()) for ln in getattr(sp, "refs", [])]
        got = {"dock": w.spec_dock.windowTitle(), "x": p.getAxis("bottom").labelText,
               "y": p.getAxis("left").labelText, "slider": [w.nav.l_name, w.nav.labels["l"].text()],
               "status": w.status.text().split("   ·   "), "refs": refs}
        print(got)
        assert got["dock"] == "Profile" and got["x"] == "z [Mm]" and got["y"] == "log₁₀(tg) [K]"
        np.testing.assert_allclose(sp.curves[0].xData, Z, rtol=1e-6)
        assert refs and abs(refs[0][0] - ZTAU51) < 1e-9 and refs[0][1] == "τ₅₀₀=1"
        from explorer.data.axes import coord_text

        z15 = coord_text((Z, "Mm"), 15)
        assert got["slider"] == ["z", z15]
        st = got["status"]
        assert st[0] == f"x {coord_text((np.arange(NX) * 0.047619, 'Mm'), 12, 1)}  y " \
                        f"{coord_text((np.arange(NY) * 0.047619, 'Mm'), 10, 1)}"
        assert st[1] == f"z {z15}" and st[2].startswith("log₁₀(tg) ") and st[2].endswith("K") and "10⁰" not in st[2]
    finally:
        close()


def test_a_lambda_cube_keeps_its_spectrum_and_its_index_forms(qapp, tmp_path):
    """λ cubes as before: "Spectrum", "Δλ" axes, the slider's λ₀ offset."""
    from explorer.testing import synth

    spec = synth.write_dataset(tmp_path, "spec", shape=(3, 4, 7, 24, 20), sp=False, icube=False)["im"]
    w, close = open_window(qapp, spec)
    try:
        got = (w.spec_dock.windowTitle(), w.nav.l_name, w.nav.labels["l"].text(), getattr(w.main, "l_coords", None),
               getattr(w.spectra, "refs", []))
        print(got)
        assert got[0] == "Spectrum" and got[1] == "λ" and got[2].startswith("λ₀") and got[3] is None and not got[4]
    finally:
        close()


def test_snapshots_without_a_date_are_timed_by_elapsed(qapp, tmp_path):
    """Point 6: a --series of snapshot images with ELAPSED and no T_OBS or DATE-*: t is the simulation's seconds, in
    ELAPSED order, said "s", not UT; the slider "3860 s", the status line, the time curve's "t [s]". Before: t an
    index in name order."""
    from explorer.data.formats import series_layout

    paths = []
    for k, el in enumerate((3870.0, 3850.0, 3860.0)):                       # named against their times
        h = fits.Header()
        for c, v in (("INSTRUME", "Bifrost "), ("BTYPE", "lg(tg)"), ("BUNIT", "K"), ("ELAPSED", el)):
            h[c] = v
        p = tmp_path / f"slice_{k}.fits"
        fits.PrimaryHDU((4 + 0.1 * k + np.zeros((NY, NX))).astype(">f4"), h).writeto(p)
        paths.append(str(p))
    lay = series_layout(paths)
    print(lay.time_key, lay.t_sec, lay.notes)
    assert lay.time_key == "ELAPSED" and lay.t_sec == (3850.0, 3860.0, 3870.0)
    w, close = open_window(qapp, series=paths)
    try:
        w.session.set_index("t", 1)
        w.session.hover(5, 5)
        qapp.processEvents()
        got = (w.nav.labels["t"].text(), w.status.text().split("   ·   ")[1],
               w.lambda_t.w.getPlotItem().getAxis("bottom").labelText)
        print(got)
        assert got[0].startswith("3860&nbsp;s&nbsp;") and got[1] == "3860 s" and got[2] == "t [s]"
    finally:
        close()
