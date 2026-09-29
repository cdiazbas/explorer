"""Formats: layouts from headers, scaling keywords, LP headers, detection by content, per-pixel companions."""
import numpy as np
import pytest
from astropy.io import fits

from explorer.data import formats
from explorer.testing import synth

SHAPE = (2, 4, 3, 16, 12)


@pytest.fixture
def dataset(tmp_path):
    return synth.write_dataset(tmp_path, "c", shape=SHAPE)


def test_fits_layout_points_at_the_samples(dataset):
    lay = formats.fits_layout(dataset["im"])
    assert lay.shape == SHAPE and lay.dtype == np.dtype(">f4")
    assert lay.axes == ("UTC", "STOKES", "WAVE", "HPLT", "HPLN")
    with open(dataset["im"], "rb") as f:
        f.seek(lay.offset)
        raw = np.frombuffer(f.read(lay.nbytes), lay.dtype).reshape(lay.shape)
    np.testing.assert_array_equal(raw, fits.getdata(dataset["im"]))


def test_fits_scaling_keywords(tmp_path):
    p = tmp_path / "int_im.fits"
    data = np.arange(2 * 3 * 4, dtype=">i2").reshape(2, 3, 4)
    hdr = fits.Header()                                  # written by hand: the raw integers stay as they are
    for k, v in (("SIMPLE", True), ("BITPIX", 16), ("NAXIS", 3), ("NAXIS1", 4), ("NAXIS2", 3), ("NAXIS3", 2),
                 ("BSCALE", 0.5), ("BZERO", 10.0), ("BLANK", -32768)):
        hdr[k] = v
    body = data.tobytes()
    p.write_bytes(hdr.tostring().encode() + body + b"\0" * (-len(body) % 2880))
    lay = formats.fits_layout(p)
    assert (lay.dtype, lay.scale, lay.zero, lay.blank, lay.scaled) == (np.dtype(">i2"), 0.5, 10.0, -32768, True)


def test_lp_pair_layouts(dataset, tmp_path):
    # an LP image cube written from the same values: frames in CRISPEX order (lambda, then Stokes, then t)
    im = fits.getdata(dataset["im"])
    lp_im = tmp_path / "c_im.icube"
    head = f"stokes=[I,Q,U,V], ns=4 :  datatype=2 (integer), dims=3, nx={SHAPE[4]}, ny={SHAPE[3]}, " \
           f"nt={SHAPE[0] * SHAPE[1] * SHAPE[2]}, endian=l"
    counts = np.round(np.nan_to_num(im.astype(np.float64) * synth.ICUBE_SCALE)).astype("<i2")
    lp_im.write_bytes(head.encode().ljust(512, b"\0") + counts.tobytes())
    image, per_pixel = formats.lp_pair_layouts(lp_im, dataset["icube"])
    assert image.shape == SHAPE and image.dtype == np.dtype("<i2") and image.offset == 512
    assert per_pixel.shape == (SHAPE[3], SHAPE[4], SHAPE[1], SHAPE[0], SHAPE[2])
    assert formats.open_layout(lp_im) == image                       # found through its companion


def test_lp_header_like_sstred_writes_it(tmp_path):
    p = tmp_path / "x_sp.icube"
    p.write_bytes(b"stokes=[I], ns=1 :  datatype=2 (integer), dims=3, nx=21, ny=66, nt=4068240, endian=l".ljust(
        512, b"\0"))
    h = formats.lp_header(p)
    assert (h.dtype, h.nx, h.ny, h.nt, h.ns) == (np.dtype("<i2"), 21, 66, 4068240, 1)


def test_detection_is_by_content_not_name(dataset, tmp_path):
    misnamed = tmp_path / "cube.dat"
    misnamed.write_bytes(open(dataset["im"], "rb").read())
    assert formats.detect(misnamed) == "fits"
    assert formats.detect(dataset["icube"]) == "lp"
    junk = tmp_path / "junk_im.fits"
    junk.write_bytes(b"\x00\x01binary" * 100)
    with pytest.raises(ValueError):
        formats.detect(junk)


def test_companions_best_first_and_through_links(dataset, tmp_path):
    names = [p.rsplit("/", 1)[1] for p in formats.companions(dataset["im"])]
    assert names == ["c_sp.fits", "c_sp.icube"]
    link_dir = tmp_path / "links"
    link_dir.mkdir()
    (link_dir / "c_im.fits").symlink_to(dataset["im"])               # a cube linked into data/, as on bellatrix
    assert [p.rsplit("/", 1)[1] for p in formats.companions(link_dir / "c_im.fits")] == names
