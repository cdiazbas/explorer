"""Dataset: every read through the facade equals the FITS data; per-pixel files found, ignored when broken, or
calibrated; memory re-split; everything closed."""
import logging

import numpy as np
import pytest
from astropy.io import fits

from explorer.data.dataset import Dataset
from explorer.data.slits import frame_index, slit_path
from explorer.testing import synth

SHAPE = (3, 4, 5, 48, 40)


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("ds"), "c", shape=SHAPE)
    return d, fits.getdata(d["im"]).astype(np.float32)               # (t, s, l, y, x)


def test_reads_through_the_facade_equal_the_fits_data(dataset):
    d, data = dataset
    with Dataset.open(d["im"]) as ds:
        assert ds.pixel is not None and ds.pixel.kind == "sp.fits" and "sp.fits" in ds.describe()
        assert tuple(ds.roles[:3]) == (0, 1, 2) and ds.axes.line == "Fe I 617.3"
        np.testing.assert_array_equal(ds.image((1, 2, 3)).result(5), data[1, 2, 3])
        hit = ds.image((1, 2, 3))
        assert hit.done() and np.array_equal(hit.result(), data[1, 2, 3], equal_nan=True)        # cached: no thread hop
        ds.prefetch((2, 2, 3))
        np.testing.assert_array_equal(ds.image((2, 2, 3)).result(5), data[2, 2, 3])
        np.testing.assert_array_equal(ds.pixel_block(20, 15).result(5), data[:, :, :, 20, 15].transpose(1, 0, 2))
        nb = ds.pixel_block(20, 14)                                   # same strip as x = 15 (8 px locally): cached
        assert nb.done() and np.array_equal(nb.result(), data[:, :, :, 20, 14].transpose(1, 0, 2), equal_nan=True)
        np.testing.assert_array_equal(ds.series(20, 15, (0, 1, 0), [0, 2]).result(5), data[:, 1, :, 20, 15])
        iy, ix = ds.slit(slit_path([(5.5, 10.5), (20.5, 30.5), (32.5, 12.5)]))
        slab = ds.slab(iy, ix).result(5)
        np.testing.assert_array_equal(slab, data[:, :, :, iy, ix].transpose(3, 1, 0, 2))
        idxs = [frame_index(3, ds.roles, t=t, s=3, l=4) for t in range(SHAPE[0])]
        np.testing.assert_array_equal(ds.bands(idxs, iy, ix).result(5), data[:, 3, 4][:, iy, ix])
        b = ds.update_memory()
        assert b.images == ds.cache.max_bytes and b.pixel == ds.pixel.max_bytes and ds.nbytes() > 0


def test_without_a_per_pixel_file(dataset):
    d, data = dataset
    with Dataset.open(d["im"], no_sp=True) as ds:
        assert ds.pixel is None and "no per-pixel file" in ds.describe()
        with pytest.raises(LookupError):
            ds.pixel_block(0, 0)
        with pytest.raises(LookupError):
            ds.slab(np.array([0]), np.array([0]))
        np.testing.assert_array_equal(ds.series(3, 4, (0, 0, 0), [0, 1, 2]).result(5), data[:, :, :, 3, 4])


def test_a_broken_per_pixel_file_is_ignored_with_a_warning(dataset, tmp_path, caplog):
    d, data = dataset
    bad = tmp_path / "bad_sp.fits"
    fits.PrimaryHDU(np.zeros((2, 2), np.float32)).writeto(bad)
    with caplog.at_level(logging.WARNING, logger="explorer.data"), Dataset.open(d["im"], sp=bad) as ds:
        assert ds.pixel is None
        np.testing.assert_array_equal(ds.image((0, 0, 0)).result(5), data[0, 0, 0])
    assert any("per-pixel file ignored" in r.getMessage() for r in caplog.records)


def test_an_integer_per_pixel_file_is_calibrated(dataset):
    d, data = dataset
    with Dataset.open(d["im"], sp=d["icube"]) as ds:
        assert ds.pixel.kind == "sp.icube" and ds.calibration is not None and ds.calibration["scale"] > 0
        blk = ds.pixel_block(20, 15).result(5)
        np.testing.assert_allclose(blk, data[:, :, :, 20, 15].transpose(1, 0, 2), rtol=0,
                                   atol=2 * ds.calibration["scale"])                 # 2 counts, as test_pixel


def test_close_is_complete_and_repeatable(dataset):
    d, _ = dataset
    ds = Dataset.open(d["im"])
    fd = ds.frames.fd
    ds.close()
    ds.close()
    assert ds.frames.fd == -1 and ds.pixel is None and ds.executors is None and fd >= 0


def test_a_file_that_is_not_a_cube_raises(tmp_path):
    p = tmp_path / "x.fits"
    p.write_bytes(b"nothing here")
    with pytest.raises((OSError, ValueError)):
        Dataset.open(p)


def test_closing_with_reads_ahead_in_flight_raises_nothing(dataset, capfd):
    """Frames read ahead and still queued are cancelled on closing; their callbacks must not raise."""
    d, _ = dataset
    ds = Dataset.open(d["im"])
    for t in range(SHAPE[0]):
        for lam in range(SHAPE[2]):
            ds.prefetch((t, 0, lam))
    ds.close()
    assert "CancelledError" not in capfd.readouterr().err


def test_integer_lp_frames_beside_a_fits_per_pixel_file_take_its_units(tmp_path):
    # an LP image cube without its idlsave, and a FITS per-pixel file given by hand (--sp): the frames were in counts
    # and the spectra in physical units, 1e11 apart. The frames are calibrated against the FITS file: its scale, and
    # the count SSTRED puts where the FITS has NaN (the padding)
    from astropy.io import fits

    from explorer.data.dataset import Dataset

    shape = (2, 4, 3, 16, 12)
    d = synth.write_dataset(tmp_path, "c", shape=shape, icube=False)
    im = fits.getdata(d["im"]).astype(np.float64)
    counts = np.round(np.nan_to_num(im * synth.ICUBE_SCALE, nan=-1240)).astype("<i2")
    lp = tmp_path / "lp=0-1_im.icube"                                 # its scans in the name: (t, s, lambda)
    head = (f"stokes=[I,Q,U,V], ns=4 :  datatype=2 (integer), dims=3, nx={shape[4]}, ny={shape[3]}, "
            f"nt={shape[0] * shape[1] * shape[2]}, endian=l")
    lp.write_bytes(head.encode().ljust(512, b"\0") + counts.tobytes())
    with Dataset.open(lp, sp=d["sp"]) as ds:
        assert ds.pixel is not None and ds.pixel.kind == "sp.fits"
        for idx in [(0, 0, 1), (1, 3, 2)]:
            got, want = ds.image(idx).result(), im[idx]
            assert (np.isnan(got) == np.isnan(want)).all()
            # two counts: half a count of rounding, and the fit's error on 6 samples (2 t x 3 lambda), as SpLP's
            assert np.nanmax(np.abs(got - want)) <= 2.0 / synth.ICUBE_SCALE
        assert ds.frame_calibration["blank"] == -1240


def test_a_per_pixel_file_alone_reads_what_its_image_cube_holds(tmp_path):
    """io.PerPixelFrames: the images, rows, bands along a slit, series, points and row blocks of a per-pixel file
    alone (no image cube beside it) equal those of the image cube it was made from, the negative-I rule included (4
    Stokes); a whole image is one pass, timed; blocks of 2 rows, so that a pass is several reads."""
    from explorer.data.io import PerPixelFrames

    shape = (3, 4, 5, 9, 7)
    d = synth.write_dataset(tmp_path, "c", shape=shape, icube=False)
    alone = tmp_path / "alone"
    alone.mkdir()
    sp = synth.write_sp_fits(d["im"], alone / "c_sp.fits", wcs=True)
    with Dataset.open(sp) as a, Dataset.open(d["im"], no_sp=True) as b:
        assert isinstance(a.frames, PerPixelFrames) and a.layout.shape == b.layout.shape
        assert a.layout.axes == b.layout.axes and a.frames.stokes == b.frames.stokes == 1
        a.frames.block_rows = 2
        for idx in ((0, 0, 0), (2, 3, 4), (1, 2, 1)):
            assert np.array_equal(a.frames.read(idx), b.frames.read(idx), equal_nan=True)
            assert np.array_equal(a.frames.read_rows(idx, 3, 8), b.frames.read_rows(idx, 3, 8), equal_nan=True)
        assert len(a.frames.passes) >= 3
        at = np.array([0, 5, 13, 20])
        idxs = [(0, 1, 2), (2, 3, 0), (1, 0, 4)]
        assert np.array_equal(a.frames.band_values(idxs, 2, 5, at), b.frames.band_values(idxs, 2, 5, at),
                              equal_nan=True)
        for idx, free in (((0, 2, 0), [0, 2]), ((1, 0, 3), [1]), ((0, 0, 0), [0, 1, 2]), ((2, 3, 1), [2])):
            assert np.array_equal(a.frames.series(4, 3, idx, free), b.frames.series(4, 3, idx, free), equal_nan=True)
            assert np.array_equal(a.frames.row_band(idx, free, 1, 4), b.frames.row_band(idx, free, 1, 4),
                                  equal_nan=True)
        fn = np.array([[0, 7, 59], [20, 21, 3]])
        ys, xs = np.array([1, 8]), np.array([6, 0])
        assert np.array_equal(a.frames.points(ys, xs, fn), b.frames.points(ys, xs, fn), equal_nan=True)
        assert np.array_equal(a.pixel_block(4, 3).result().transpose(1, 0, 2),
                              a.frames.series(4, 3, (0, 0, 0), [0, 1, 2]), equal_nan=True)


def test_positions_outside_the_band_are_refused_with_or_without_a_per_pixel_file(tmp_path):
    """A band of 3 rows of 7 holds positions 0..20: -1 (numpy would take it from the band's end) and 21 are refused,
    by io.PerPixelFrames as by FrameReader."""
    from explorer.data.io import PerPixelFrames

    d = synth.write_dataset(tmp_path, "c", shape=(3, 4, 5, 9, 7), icube=False)
    alone = tmp_path / "alone"
    alone.mkdir()
    sp = synth.write_sp_fits(d["im"], alone / "c_sp.fits", wcs=True)
    with Dataset.open(sp) as a, Dataset.open(d["im"], no_sp=True) as b:
        assert isinstance(a.frames, PerPixelFrames)
        for r in (a.frames, b.frames):
            for at in ([-1], [0, 21]):
                with pytest.raises(IndexError, match="positions outside a band of 3 rows of 7"):
                    r.band_values([(0, 1, 2)], 2, 5, at)
