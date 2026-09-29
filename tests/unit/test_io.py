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
