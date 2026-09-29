"""Per-pixel readers: blocks equal the image cube's values, strips, the LRU budget, calibration of integer files."""
import numpy as np
import pytest
from astropy.io import fits

from explorer.data import formats
from explorer.data.io import FrameReader
from explorer.data.pixel import SpFits, SpLP, lp_pixel_layout, open_pixel
from explorer.testing import synth

SHAPE = (2, 4, 3, 16, 12)                                   # (t, s, l, y, x)


@pytest.fixture
def dataset(tmp_path):
    return synth.write_dataset(tmp_path, "c", shape=SHAPE)


def test_block_is_the_cube_at_that_pixel(dataset):
    im = fits.getdata(dataset["im"]).astype(np.float32)
    with FrameReader(formats.open_layout(dataset["im"])) as fr:
        r = open_pixel(dataset["im"], fr, strip=5)
        assert r.kind == "sp.fits"
        for y, x in [(8, 6), (0, 0), (15, 11), (7, 10)]:           # (15, 11): the last strip of a row is shorter
            np.testing.assert_array_equal(r.block(y, x), im[:, :, :, y, x].transpose(1, 0, 2))
        r.close()


def test_the_cache_keeps_to_its_budget(dataset):
    with FrameReader(formats.open_layout(dataset["im"])) as fr:
        r = open_pixel(dataset["im"], fr, strip=4)
        one = r.pix * 4 // 4 * 4                              # bytes of one float32 block (s, t, l)
        r.set_budget(10 * SHAPE[1] * SHAPE[0] * SHAPE[2] * 4)
        for x in range(SHAPE[4]):
            r.block(3, x)
        assert r.nbytes() <= r.max_bytes and one > 0
        r.close()


def test_shapes_must_match_the_image_cube(dataset):
    with pytest.raises(ValueError):
        SpFits(dataset["sp"], (4, 2, 99))


def test_icube_is_calibrated_against_the_cube(dataset):
    im = fits.getdata(dataset["im"]).astype(np.float32)
    with FrameReader(formats.open_layout(dataset["im"])) as fr:
        r = open_pixel(dataset["im"], fr, sp_path=dataset["icube"])
        assert isinstance(r, SpLP) and r.kind == "sp.icube"
        assert abs(float(r.scale) - 1 / synth.ICUBE_SCALE) < 1e-3 / synth.ICUBE_SCALE
        b, want = r.block(8, 6), im[:, :, :, 8, 6].transpose(1, 0, 2)
        # within two counts: the fit uses one pixel's lambda-t, here only 6 samples (2 t x 3 lambda), so scale and
        # zero carry an error of about a count on top of the rounding; that explorer calibrates exactly as the
        # prototype does is checked against its references (tests/golden/test_data.py)
        assert np.nanmax(np.abs(b - want)) <= 2.0 / synth.ICUBE_SCALE
        r.close()


def test_calibration_skips_padding_and_fails_without_data(dataset):
    with FrameReader(formats.open_layout(dataset["im"])) as fr:
        r = SpLP(lp_pixel_layout(dataset["icube"], fr.ny, fr.nx))
        cal = r.calibrate(fr, pixels=[(0, 0), (8, 6)])          # (0, 0) is padding
        assert cal["pixel"] == (8, 6)
        with pytest.raises(ValueError):
            r.calibrate(fr, pixels=[(0, 0), (15, 0)])
        r.close()
