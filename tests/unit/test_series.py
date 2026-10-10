"""A file series (--series): FITS images, one per file, read as the t axis of one cube, in header time order; the
files refused when they are not one series; every read equal to the images stacked; compressed as plain."""
import os

import numpy as np
import pytest
from astropy.io import fits

from explorer.data import axes as _axes
from explorer.data.dataset import Dataset
from explorer.data.formats import series_layout
from explorer.data.formats.series import parse_time

NY, NX = 12, 16
T0 = np.datetime64("2026-06-07T06:52:00.000", "ms")


def images(n=5, seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(-500, 3000, (n, NY, NX)).astype(np.int16)


def write(d, name, img, i=None, compressed=False, **cards):
    """One AIA-like file: its image, T_OBS at mid-exposure (12 s cadence, from T0) unless i is None."""
    hdr = fits.Header()
    hdr["CTYPE1"], hdr["CTYPE2"] = "HPLN-TAN", "HPLT-TAN"
    hdr["WAVELNTH"], hdr["INSTRUME"], hdr["BUNIT"] = 171, "AIA_3", "DN"
    if i is not None:
        hdr["DATE-OBS"] = str(T0 + np.timedelta64(12000 * i, "ms"))
        hdr["T_OBS"] = str(T0 + np.timedelta64(12000 * i + 1000, "ms")) + "Z"
    scaling = {k: cards.pop(k) for k in ("BSCALE", "BZERO", "BLANK") if k in cards}
    for k, v in cards.items():
        hdr[k.replace("_", "-") if k == "DATE_OBS" else k] = v
    if "BLANK" in scaling:                                          # one pixel without data in every file
        img = img.copy()
        img[1, 2] = scaling["BLANK"]
    path = os.path.join(d, name)
    if compressed:
        hdu = fits.CompImageHDU(img, hdr, compression_type="RICE_1")
    else:
        hdu = fits.PrimaryHDU(img, hdr)
    for k, v in scaling.items():                                    # the stored integers, with their meaning
        hdu.header[k] = v
    hdus = [fits.PrimaryHDU(), hdu] if compressed else [hdu]
    fits.HDUList(hdus).writeto(path)
    with fits.open(path, do_not_scale_image_data=True) as h:       # written as given
        h.verify("exception")
        assert np.array_equal(h[-1].data, img) and all(h[-1].header.get(k) == v for k, v in scaling.items())
    return path


def series(d, n=5, compressed=False, order=None, **cards):
    """n files whose names run against their times when order is given (file k holds time order[k])."""
    imgs = images(n)
    order = list(range(n)) if order is None else order
    paths = [write(d, f"aia_{k:02d}.fits", imgs[order[k]], order[k], compressed, **cards) for k in range(n)]
    return paths, imgs


def stacked(paths_in_t_order):
    return np.stack([fits.getdata(p).astype(np.float32) for p in paths_in_t_order])


def test_order_is_the_header_times_not_the_names(tmp_path):
    paths, imgs = series(tmp_path, order=[3, 0, 4, 1, 2])
    lay = series_layout(paths)
    assert lay.shape == (5, NY, NX) and lay.axes == ("UTC", "HPLT", "HPLN") and lay.time_key == "T_OBS"
    assert [os.path.basename(p) for p in lay.paths] == ["aia_01.fits", "aia_03.fits", "aia_04.fits", "aia_00.fits",
                                                        "aia_02.fits"]
    assert lay.t_sec == (0.0, 12.0, 24.0, 36.0, 48.0) and lay.dateref == "2026-06-07T06:52:01.000"
    assert any("not the files' name order" in n for n in lay.notes)
    in_name_order = series_layout(sorted(paths, reverse=True))
    assert in_name_order.paths == lay.paths                       # the order given does not matter


def test_mid_exposure_first_then_the_start(tmp_path):
    """T_OBS (mid-exposure) where every file has it; DATE-OBS (the start) only when it is the one left."""
    (tmp_path / "both").mkdir()
    paths, _ = series(tmp_path / "both")
    assert series_layout(paths).time_key == "T_OBS"
    d = tmp_path / "start"
    d.mkdir()
    p = [write(d, f"f{k}.fits", images(2)[k], None, DATE_OBS=f"2026-06-07T06:52:{10 * k:02d}.5") for k in range(2)]
    lay = series_layout(p)
    assert lay.time_key == "DATE-OBS" and lay.t_sec == (0.0, 10.0)


def test_times_as_jsoc_writes_them():
    assert parse_time("2011.06.07_06:52:01.07_TAI") == np.datetime64("2011-06-07T06:52:01.070", "us")
    assert parse_time("2011-06-07T06:52:01.07Z") == np.datetime64("2011-06-07T06:52:01.070", "us")
    assert parse_time("yesterday") is None and parse_time(None) is None


def test_without_times_the_names_order_and_t_is_an_index(tmp_path):
    imgs = images(3)
    paths = [write(tmp_path, f"x{k}.fits", imgs[k]) for k in (2, 0, 1)]
    lay = series_layout(paths)
    assert [os.path.basename(p) for p in lay.paths] == ["x0.fits", "x1.fits", "x2.fits"]
    assert lay.t_sec is None and any("an index" in n for n in lay.notes)
    with Dataset.open(None, series=paths) as ds:
        assert ds.roles.t == 0 and ds.roles.nt == 3 and ds.roles.l is None and ds.axes.t_sec is None


def test_two_files_at_the_same_time_are_refused_by_name(tmp_path):
    imgs = images(3)
    paths = [write(tmp_path, f"x{k}.fits", imgs[k], min(k, 1)) for k in range(3)]
    with pytest.raises(ValueError, match="same time") as e:
        series_layout(paths)
    assert "x1.fits" in str(e.value) and "x2.fits" in str(e.value)


@pytest.mark.parametrize("card, values", [("WAVELNTH", (171, 193)), ("INSTRUME", ("AIA_3", "AIA_4")),
                                          ("BUNIT", ("DN", "DN/s"))])
def test_files_of_another_channel_are_refused_with_the_groups(tmp_path, card, values):
    imgs = images(4)
    paths = [write(tmp_path, f"x{k}.fits", imgs[k], k, **{card: values[k // 3]}) for k in range(4)]
    with pytest.raises(ValueError, match=f"{card} differs") as e:
        series_layout(paths)
    assert "(3 files: x0.fits, x1.fits, x2.fits)" in str(e.value) and "(1 file: x3.fits)" in str(e.value)


def test_another_shape_is_refused(tmp_path):
    paths, _ = series(tmp_path, n=2)
    paths.append(write(tmp_path, "big.fits", np.zeros((NY + 1, NX), np.int16), 9))
    with pytest.raises(ValueError, match="shape differs"):
        series_layout(paths)


def test_every_read_equals_the_images_stacked(tmp_path):
    """Frames, a pixel along t, rows along t, points and slit bands: BSCALE, BZERO and BLANK applied as for a cube."""
    paths, _ = series(tmp_path, order=[1, 0, 2, 4, 3], BSCALE=0.5, BZERO=100.0, BLANK=-500)
    with Dataset.open(None, series=paths) as ds:
        data = stacked(ds.layout.paths)
        assert np.isnan(data).any()                                 # a BLANK pixel, NaN in both
        assert ds.roles[:3] == (0, None, None) and ds.roles.nt == 5 and ds.pixel is None
        np.testing.assert_allclose(ds.axes.t_sec, np.arange(5) * 12.0)
        assert ds.axes.utc_str(1) == "06:52:13" and ds.axes.bunit == "DN"
        for t in range(5):
            np.testing.assert_array_equal(ds.image((t,)).result(5), data[t])
        np.testing.assert_array_equal(ds.read_series(7, 9, (0,), [0]), data[:, 7, 9])
        np.testing.assert_array_equal(ds.frames.row_band((0,), [0], 3, 6).astype(np.float32) * 0.5 + 100,
                                      np.where(np.isnan(data[:, 3:6]), -500 * 0.5 + 100, data[:, 3:6]))
        pts = ds.frames.points(np.array([1, 2]), np.array([3, 4]), np.array([[0, 4], [2, 1]]))
        np.testing.assert_array_equal(pts, [[data[0, 1, 3], data[4, 1, 3]], [data[2, 2, 4], data[1, 2, 4]]])
        iy, ix = np.array([2, 3, 3, 4]), np.array([5, 5, 6, 7])
        np.testing.assert_array_equal(ds.read_bands([(t,) for t in range(5)], iy, ix), data[:, iy, ix])


def test_compressed_equals_plain(tmp_path):
    (tmp_path / "plain").mkdir()
    (tmp_path / "rice").mkdir()
    plain, _ = series(tmp_path / "plain", order=[2, 0, 1, 4, 3], BLANK=-500)
    rice, _ = series(tmp_path / "rice", compressed=True, order=[2, 0, 1, 4, 3], BLANK=-500)
    with Dataset.open(None, series=plain) as a, Dataset.open(None, series=rice) as b:
        assert b.layout.compressed and not a.layout.compressed
        assert a.layout.t_sec == b.layout.t_sec
        for t in range(5):
            np.testing.assert_array_equal(b.image((t,)).result(5), a.image((t,)).result(5))
        np.testing.assert_array_equal(b.read_series(7, 9, (0,), [0]), a.read_series(7, 9, (0,), [0]))
        iy, ix = np.array([2, 3, 3]), np.array([5, 5, 6])
        np.testing.assert_array_equal(b.read_bands([(t,) for t in range(5)], iy, ix),
                                      a.read_bands([(t,) for t in range(5)], iy, ix))


def test_axes_read_names_t_and_no_lambda(tmp_path):
    paths, _ = series(tmp_path)
    lay = series_layout(paths)
    r, ax = _axes.read(lay.path, lay)
    assert (r.t, r.s, r.l, r.nt, r.how) == (0, None, None, 5, "header")
    assert ax.lam_nm is None and str(ax.utc(4))[:19] == "2026-06-07T06:52:49"

