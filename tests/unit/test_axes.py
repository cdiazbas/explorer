"""Physical axes from SOLARNET headers, the roles of the leading axes, and the units the spectra are shown in."""
import numpy as np
import pytest
from astropy.io import fits

from explorer.data import axes
from explorer.testing import synth

SHAPE = (3, 4, 5, 16, 12)


@pytest.fixture
def cube(tmp_path):
    return synth.write_stokes_cube(tmp_path / "c_im.fits", shape=SHAPE)


def _rewrite(src, dst, edit):
    with fits.open(src) as h:
        hd = h[0].header.copy()
        edit(hd)
        fits.HDUList([fits.PrimaryHDU(h[0].data, hd)] + [x.copy() for x in h[1:]]).writeto(dst)
    return dst


def test_axes_of_a_synthetic_sstred_header(cube):
    ax = axes.from_fits(cube)
    nt, ns, nl = SHAPE[:3]
    assert ax.line == "Fe I 617.3" and ax.lam0_nm == 617.3341
    assert ax.cont == nl - 1 and "PRPARA1" in ax.source[1]
    assert ax.lam_nm.shape == (nl,) and ax.t_sec.shape == (nt,) and ax.corners.shape == (nt, 2, 2, 2)
    np.testing.assert_allclose(ax.dlam_A(), synth.tunings_A(nl), atol=1e-9)
    assert ax.dlam_A(0) == pytest.approx(ax.dlam_A()[0])
    assert ax.vel_kms(0) == pytest.approx(ax.dlam_A(0) / (ax.lam0_nm * 10) * axes.C_KMS)
    assert ax.utc_str(0) is not None and ax.utc(1) > ax.utc(0)
    (x0, x1), (y0, y1) = ax.corner_px
    assert (x0, x1, y0, y1) == (0, SHAPE[4] - 1, 0, SHAPE[3] - 1)
    assert ax.arcsec(y0, x0, 0) == pytest.approx(tuple(ax.corners[0, 0, 0]))
    assert ax.arcsec(y1, x1, 0) == pytest.approx(tuple(ax.corners[0, 1, 1]))
    assert ax.distortion is None


def test_continuum_from_an_isolated_tuning_without_prpara(cube, tmp_path):
    ax = axes.from_fits(_rewrite(cube, tmp_path / "n.fits", lambda h: h.remove("PRPARA1")))
    assert ax.cont is None                          # 5 tunings: the last is 2x the median step away, not > 4x
    wide = synth.write_stokes_cube(tmp_path / "w_im.fits", shape=(2, 1, 12, 8, 8))
    ax = axes.from_fits(_rewrite(wide, tmp_path / "w.fits", lambda h: h.remove("PRPARA1")))
    assert ax.cont == 11 and ax.source[-1] == "continuum: isolated red tuning"


def test_unknown_line_and_a_distortion_are_reported(cube, tmp_path):
    def edit(h):
        h["WAVEBAND"] = "Xx 1234"
        h["CWDIS3"] = "Lookup"

    ax = axes.from_fits(_rewrite(cube, tmp_path / "d.fits", edit))
    assert ax.line is None and ax.dlam_A() is None and ax.vel_kms(0) is None and ax.lam_A(0) is not None
    assert ax.distortion == "WCSDVARR CWDIS3 = Lookup"


def test_a_header_without_wcs_table_or_a_bad_file_gives_indices(tmp_path):
    p = tmp_path / "plain.fits"
    fits.PrimaryHDU(np.zeros((2, 3, 4), np.float32)).writeto(p)
    ax = axes.from_fits(p)
    assert ax.lam_nm is None and ax.t_sec is None and ax.arcsec(0, 0, 0) is None and ax.utc_str(0) is None
    bad = tmp_path / "bad.fits"
    bad.write_bytes(b"not a fits file")
    ax = axes.from_fits(bad)
    assert ax.lam_nm is None and ax.source and ax.source[0].startswith("header not read")


@pytest.mark.parametrize("names, shape, want", [
    (("UTC", "STOKES", "WAVE", "HPLT", "HPLN"), (3, 4, 5, 8, 8), (0, 1, 2, 3, 4, 5, "header")),
    (("WAVE", "UTC", "HPLT", "HPLN"), (7, 3, 8, 8), (1, None, 0, 3, 1, 7, "header")),
    (("A", "B", "C", "Y", "X"), (3, 4, 5, 8, 8), (0, 1, 2, 3, 4, 5, "SOLARNET order")),
    (("A", "B", "Y", "X"), (3, 4, 8, 8), (0, None, 1, 3, 1, 4, "default (t, lambda)")),   # (t, lambda, y, x)
    (("A", "Y", "X"), (7, 8, 8), (None, None, 0, 1, 1, 7, "unknown")),                  # t or lambda: a profile
    (("WAVE", "Y", "X"), (7, 8, 8), (None, None, 0, 1, 1, 7, "header")),
])
def test_roles_by_name_else_by_how_many_axes(names, shape, want):
    assert tuple(axes.roles(names, shape)) == want


@pytest.mark.parametrize("spec, want", [("s,l", (None, 0, 1, 1, 3, 4, "--axes")),
                                        ("l, t", (1, None, 0, 4, 1, 3, "--axes"))])
def test_axes_given_by_the_user_win(spec, want):
    assert tuple(axes.roles(("UTC", "WAVE", "Y", "X"), (3, 4, 8, 8), spec)) == want


@pytest.mark.parametrize("spec", ["t", "t,t", "t,x", "t,s,l"])
def test_axes_given_wrong_are_refused(spec):
    with pytest.raises(ValueError):
        axes.roles(("A", "B", "Y", "X"), (3, 4, 8, 8), spec)


def test_units_of_the_spectra():
    spec = np.array([[2e-9, 3e-9, 4e-9], [2e-11, -3e-11, 0.0]])        # I, Q; continuum at tuning 2
    assert axes.power_of_ten(spec[0]) == 1e-9
    assert axes.power_of_ten([np.nan, 0.0]) is None
    np.testing.assert_allclose(axes.plot_units(spec, 2, 1e-9), [[2, 3, 4], [0.5, -0.75, 0]])
    np.testing.assert_allclose(axes.plot_units(spec, None, 1e-9), [[2, 3, 4], [0.02, -0.03, 0]])
    padded = spec.copy()
    padded[0, 2] = np.nan
    np.testing.assert_array_equal(axes.plot_units(padded, 2, 1e-9)[1], spec[1])          # Q U V as read
    assert axes.unit_text("W m^-2 Hz^-1 sr^-1") == "W m⁻² Hz⁻¹ sr⁻¹"
    assert (axes.fmt_signed(1.25), axes.fmt_signed(-1.25), axes.fmt_signed(-0.01)) == ("+1.2", "−1.2", "0.0")


def _lp_cube_with_save(tmp_path, nt=2, nl=3, **save):
    """An LP image cube (t, 1, lambda, 4, 5) of float frames and, when save is given, its idlsave."""
    head = f"stokes=[I], ns=1 :  datatype=4 (float), dims=3, nx=5, ny=4, nt={nt * nl}, endian=l"
    im = tmp_path / f"c=0-{nt - 1}_im.fcube"
    im.write_bytes(head.encode().ljust(512, b"\0") + np.ones((nt * nl, 4, 5), "<f4").tobytes())
    if save:
        synth.write_idlsave(tmp_path / f"c=0-{nt - 1}_im_times+wvl.idlsave", save)
    return im


def test_lp_axes_from_the_idlsave_beside_the_cube(tmp_path):
    from explorer.data import formats

    tod = 58751.188 + np.array([[0.0, 0.5, 1.0], [20.0, 20.5, 21.0]])  # (scan, tuning) seconds of the day, UT
    im = _lp_cube_with_save(tmp_path, **{"lambda": np.array([617.30, 617.33, 617.36]), "time": tod,
                                                       "times": np.array(["16:19:11", "16:19:31"])})
    lay = formats.open_layout(im)
    ax = axes.from_lp(im, axes.roles(lay.axes, lay.shape))
    np.testing.assert_allclose(ax.lam_nm, [617.30, 617.33, 617.36])
    np.testing.assert_allclose(ax.t_sec, tod.mean(axis=1))              # the mean over tunings, as from_fits
    assert ax.line == "Fe I 617.3" and ax.lam0_nm == 617.3341           # the one line inside the tuned range
    assert ax.dlam_A(1) == pytest.approx((617.33 - 617.3341) * 10)
    assert ax.dateref is None and ax.utc_str(0) == "16:19:11" and ax.utc_str(1, seconds=False) == "16:19"


def test_lp_axes_whatever_the_name_of_the_seconds(tmp_path):
    # SSTRED names the (scan, tuning) seconds "time" in some files and "times" in others: the float one is taken
    from explorer.data import formats

    im = _lp_cube_with_save(tmp_path, **{"lambda": np.array([656.2, 656.3, 656.4]),
                                         "time": np.array(["09:19:23", "09:19:43"]),
                                         "times": 33563.0 + np.zeros((2, 3))})
    lay = formats.open_layout(im)
    ax = axes.from_lp(im, axes.roles(lay.axes, lay.shape))
    assert ax.utc_str(1) == "09:19:23" and ax.line == "Hα"


def test_lp_axes_that_do_not_match_the_cube_stay_unknown(tmp_path):
    from explorer.data import formats

    im = _lp_cube_with_save(tmp_path, **{"lambda": np.array([617.3, 617.4]), "time": np.zeros((5, 3))})
    lay = formats.open_layout(im)
    ax = axes.from_lp(im, axes.roles(lay.axes, lay.shape))
    assert ax.lam_nm is None and ax.t_sec is None and ax.utc_str(0) is None
    assert any("does not match" in s for s in ax.source)
    (tmp_path / "bare").mkdir()
    bare = _lp_cube_with_save(tmp_path / "bare")                        # no file: nothing, and no error
    assert axes.from_lp(bare, axes.roles(lay.axes, lay.shape)).lam_nm is None
