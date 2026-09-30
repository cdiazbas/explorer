"""FrameReader: whole frames and row bands as native float32, exact reads, scaled integers, LP image cubes."""
import numpy as np
import pytest
from astropy.io import fits

from explorer.data import formats
from explorer.data.io import FrameReader, ShortRead
from explorer.testing import synth

SHAPE = (2, 4, 3, 16, 12)


@pytest.fixture
def dataset(tmp_path):
    return synth.write_dataset(tmp_path, "c", shape=SHAPE)


def test_frames_and_rows_equal_the_fits_data(dataset):
    data = fits.getdata(dataset["im"]).astype(np.float32)
    with FrameReader(formats.open_layout(dataset["im"])) as r:
        for idx in [(0, 0, 0), (1, 3, 2), (0, 2, 1)]:
            img = r.read(idx)
            assert img.dtype == np.float32 and img.dtype.byteorder in "=|"
            np.testing.assert_array_equal(img, data[idx])
            np.testing.assert_array_equal(r.read(idx, chunks=1), data[idx])
            np.testing.assert_array_equal(r.read_rows(idx, 3, 9), data[idx][3:9])


def test_index_outside_the_cube(dataset):
    with FrameReader(formats.open_layout(dataset["im"])) as r:
        for bad in [(2, 0, 0), (0, 4, 0), (0, 0, -1), (0, 0)]:
            with pytest.raises(IndexError):
                r.read(bad)
        with pytest.raises(IndexError):
            r.read_rows((0, 0, 0), 5, 20)


def test_a_short_read_is_an_error_not_garbage(dataset, tmp_path):
    cut = tmp_path / "cut_im.fits"
    lay = formats.fits_layout(dataset["im"])
    end = lay.offset + lay.nbytes - 2 * SHAPE[3] * SHAPE[4] * 4           # the last two frames missing (the
    cut.write_bytes(open(dataset["im"], "rb").read()[:end])                # WCS-TAB extension follows the data)
    with FrameReader(formats.fits_layout(cut)) as r, pytest.raises(ShortRead):
        r.read((1, 3, 2))


def test_scaled_integers_become_physical_values(tmp_path):
    p = tmp_path / "int_im.fits"
    data = np.arange(2 * 3 * 4, dtype=">i2").reshape(2, 3, 4)
    data[1, 2, 3] = -32768                                             # BLANK
    hdr = fits.Header()
    for k, v in (("SIMPLE", True), ("BITPIX", 16), ("NAXIS", 3), ("NAXIS1", 4), ("NAXIS2", 3), ("NAXIS3", 2),
                 ("BSCALE", 0.5), ("BZERO", 10.0), ("BLANK", -32768)):
        hdr[k] = v
    body = data.tobytes()
    p.write_bytes(hdr.tostring().encode() + body + b"\0" * (-len(body) % 2880))
    with FrameReader(formats.fits_layout(p)) as r:
        img = r.read((1,))
    expect = data[1].astype(np.float32) * np.float32(0.5) + np.float32(10.0)
    expect[2, 3] = np.nan
    np.testing.assert_array_equal(img, expect)


def test_lp_image_cube_in_crispex_frame_order(dataset, tmp_path):
    im = fits.getdata(dataset["im"])
    counts = np.round(np.nan_to_num(im.astype(np.float64) * synth.ICUBE_SCALE)).astype("<i2")
    lp_im = tmp_path / "c_im.icube"
    head = f"stokes=[I,Q,U,V], ns=4 :  datatype=2 (integer), dims=3, nx={SHAPE[4]}, ny={SHAPE[3]}, " \
           f"nt={SHAPE[0] * SHAPE[1] * SHAPE[2]}, endian=l"
    lp_im.write_bytes(head.encode().ljust(512, b"\0") + counts.tobytes())
    layout, _ = formats.lp_pair_layouts(lp_im, dataset["icube"])
    with FrameReader(layout) as r:
        np.testing.assert_array_equal(r.read((1, 2, 0)), counts[1, 2, 0].astype(np.float32))


def test_series_along_any_free_axes(dataset):
    data = fits.getdata(dataset["im"]).astype(np.float32)             # (t, s, l, y, x)
    y, x = 9, 5
    with FrameReader(formats.open_layout(dataset["im"])) as r:
        np.testing.assert_array_equal(r.series(y, x, (1, 2, 0), [2]), data[1, 2, :, y, x])            # profile
        np.testing.assert_array_equal(r.series(y, x, (0, 3, 0), [0, 2]), data[:, 3, :, y, x])         # lambda-t
        np.testing.assert_array_equal(r.series(y, x, (0, 0, 0), [2, 0, 1]), data[:, :, :, y, x])      # everything
        with pytest.raises(IndexError):
            r.series(SHAPE[3], 0, (0, 0, 0), [2])


def test_series_short_read(dataset, tmp_path):
    cut = tmp_path / "cut_im.fits"
    lay = formats.fits_layout(dataset["im"])
    cut.write_bytes(open(dataset["im"], "rb").read()[: lay.offset + lay.nbytes // 2])
    with FrameReader(formats.fits_layout(cut)) as r, pytest.raises(ShortRead):
        r.series(9, 5, (0, 0, 0), [0, 1, 2])


def test_numba_cache_goes_to_the_user_cache(monkeypatch, tmp_path):
    import subprocess
    import sys

    env = {k: v for k, v in __import__("os").environ.items() if k != "NUMBA_CACHE_DIR"}
    env["XDG_CACHE_HOME"] = str(tmp_path)
    code = "import numba; from explorer.data import gather; print(numba.config.CACHE_DIR)"
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True).stdout
    assert out.strip() == str(tmp_path / "explorer" / "numba")


def test_band_values_at_flat_positions(dataset, tmp_path):
    data = fits.getdata(dataset["im"]).astype(np.float32)             # (t, s, l, y, x)
    lay = formats.open_layout(dataset["im"])
    rows, cols = np.array([3, 4, 8]), np.array([1, 11, 0])
    at = (rows - 3) * SHAPE[4] + cols
    idxs = [(t, 2, 1) for t in range(SHAPE[0])]
    with FrameReader(lay) as r:
        got = r.band_values(idxs, 3, 9, at, threads=2)
        assert got.dtype == np.float32
        np.testing.assert_array_equal(got, data[:, 2, 1][:, rows, cols])
        with pytest.raises(IndexError):
            r.band_values(idxs, 3, 9, [6 * SHAPE[4]])
    cut = tmp_path / "cut_im.fits"                                     # the last two frames missing
    cut.write_bytes(open(dataset["im"], "rb").read()[:lay.offset + lay.nbytes - 2 * SHAPE[3] * SHAPE[4] * 4])
    with FrameReader(formats.fits_layout(cut)) as r, pytest.raises(ShortRead):
        r.band_values([(1, 3, 2)], 0, 4, [0])


def test_scattered_reads_use_at_most_one_thread_per_request(dataset):
    """With a limit set, a read of n requests runs on min(n, limit, pool) numba threads; the values do not change."""
    import numba

    data = fits.getdata(dataset["im"]).astype(np.float32)
    with FrameReader(formats.open_layout(dataset["im"])) as r:
        r.gather_threads = 3
        np.testing.assert_array_equal(r.series(9, 5, (0, 1, 0), [2]), data[0, 1, :, 9, 5])     # 3 requests
        assert numba.get_num_threads() == min(3, numba.config.NUMBA_NUM_THREADS)
        np.testing.assert_array_equal(r.series(9, 5, (0, 1, 0), [0]), data[:, 1, 0, 9, 5])     # 2 requests
        assert numba.get_num_threads() == min(2, numba.config.NUMBA_NUM_THREADS)


def test_numba_pool_holds_the_threads_scattered_reads_may_use():
    """numba's pool is sized at import: at least 128 threads unless NUMBA_NUM_THREADS says otherwise."""
    import os
    import subprocess
    import sys

    code = "import explorer.data.gather, numba; print(numba.config.NUMBA_NUM_THREADS)"
    env = {k: v for k, v in os.environ.items() if k != "NUMBA_NUM_THREADS"}
    got = int(subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                             check=True).stdout)
    assert got >= 128
    env["NUMBA_NUM_THREADS"] = "3"
    assert subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                          check=True).stdout.strip() == "3"
