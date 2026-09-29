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
