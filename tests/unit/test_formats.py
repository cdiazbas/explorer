"""Formats: layouts from headers, scaling keywords, LP headers, detection by content, per-pixel companions."""
import numpy as np
import pytest
from astropy.io import fits

from explorer.data import formats
from explorer.data.io import FrameReader
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


def _lp_frames(path, frames, ns=None):
    """An LP cube written as SSTRED writes one without a per-pixel file: frames (n, ny, nx), a header with or without
    stokes=."""
    return synth.write_lp(path, frames, head=f"stokes=[I], ns={ns} :  " if ns else " :  ")


def test_an_lp_map_without_per_pixel_file_is_a_time_series(tmp_path):
    frames = np.arange(4 * 6 * 5, dtype=np.float32).reshape(4, 6, 5)
    lay = formats.open_layout(_lp_frames(tmp_path / "Blos_6173_x=0-3.fcube", frames))
    assert lay.shape == (4, 6, 5) and lay.axes == ("UTC", "HPLT", "HPLN")
    two = formats.open_layout(_lp_frames(tmp_path / "Vlos_x=0-1_y=0-1.fcube", frames))   # two series: 2 + 2 scans
    assert two.shape == (4, 6, 5)


def test_an_lp_cube_without_per_pixel_file_splits_by_the_scans_in_its_name(tmp_path):
    frames = np.arange(3 * 4 * 6 * 5, dtype=np.float32).reshape(12, 6, 5)       # 3 scans x 4 tunings, CRISPEX order
    lay = formats.open_layout(_lp_frames(tmp_path / "nb_8542_x_clipped=0-2.icube", frames, ns=1))
    assert lay.shape == (3, 1, 4, 6, 5) and lay.axes[:3] == ("UTC", "STOKES", "WAVE")
    from explorer.data.io import FrameReader

    with FrameReader(lay) as r:                                               # frame (t * ns + s) * nl + l
        np.testing.assert_array_equal(r.read((2, 0, 1)), frames[2 * 4 + 1])


def test_an_lp_cube_with_nothing_to_split_it_has_one_unknown_axis(tmp_path):
    from explorer.data.axes import roles

    frames = np.zeros((7, 6, 5), np.float32)
    lay = formats.open_layout(_lp_frames(tmp_path / "Bstr.6173_x.fcube", frames))
    assert lay.shape == (7, 6, 5) and roles(lay.axes, lay.shape).how == "unknown"


def test_companions_of_a_cube_with_a_tag_after_im(tmp_path):
    # <stem>_im.<tag>.icube (a cube aligned to another line's grid, as SSTRED names it) has <stem>_sp.<tag>.icube
    im = tmp_path / "c_im.aligned6173.icube"
    im.write_bytes(b"")
    (tmp_path / "c_sp.aligned6173.icube").write_bytes(b"")
    (tmp_path / "c_sp.icube").write_bytes(b"")                    # the unaligned one is not its companion
    assert [p.rsplit("/", 1)[1] for p in formats.companions(im)] == ["c_sp.aligned6173.icube"]


def _lp_pair(tmp_path, counts, ns=1):
    """An LP image cube <stem>_im.icube and its per-pixel file from counts (t, s, lambda, y, x) int16."""
    nt, _, nl, ny, nx = counts.shape
    head = f"stokes=[I], ns={ns} :  datatype=2 (integer), dims=3, nx={{}}, ny={{}}, nt={{}}, endian=l"
    im, sp = tmp_path / "c_im.icube", tmp_path / "c_sp.icube"
    frames = counts.astype("<i2").tobytes()
    im.write_bytes(head.format(nx, ny, nt * ns * nl).encode().ljust(512, b"\0") + frames)
    per_pixel = counts.transpose(3, 4, 1, 0, 2)                         # (y, x, s, t, lambda)
    sp.write_bytes(head.format(nl, nt, ny * nx * ns).encode().ljust(512, b"\0") + per_pixel.astype("<i2").tobytes())
    return im, sp


def test_an_lp_cube_takes_its_scaling_and_padding_from_the_idlsave_beside_it(tmp_path):
    counts = np.arange(2 * 1 * 3 * 4 * 5, dtype=np.int16).reshape(2, 1, 3, 4, 5) + 100
    counts[..., 0] = -1240                                              # padding, as SSTRED's nan_rplcmnt
    im, _ = _lp_pair(tmp_path, counts)
    assert formats.lp_sidecar(im) is None
    assert not formats.open_layout(im).scaled                           # without the file: counts
    synth.write_idlsave(tmp_path / "c_im_times+wvl.idlsave", {"fac": np.float32(1e11), "nan_rplcmnt": np.int16(-1240)})
    assert formats.lp_sidecar(im) == str(tmp_path / "c_im_times+wvl.idlsave")
    lay = formats.open_layout(im)
    assert lay.scale == pytest.approx(1e-11) and lay.blank == -1240
    with FrameReader(lay) as fr:
        f = fr.read((1, 0, 2))
    assert np.isnan(f[:, 0]).all()
    np.testing.assert_allclose(f[:, 1:], counts[1, 0, 2, :, 1:] * 1e-11, rtol=1e-6)


def test_an_aligned_lp_cube_and_a_float_padding_value(tmp_path):
    frames = np.full((2, 4, 5), 3e-9, np.float32)
    frames[:, :, 0] = np.float32(-1.7691475e-08)                        # an fcube's padding: its minimum, a float
    cube = _lp_frames(tmp_path / "c=0-1_im.aligned6173.fcube", frames)
    synth.write_idlsave(tmp_path / "c=0-1_im_times+wvl.idlsave", {"fac": np.float32(1.0),
                                                                    "nan_rplcmnt": np.float32(-1.7691475e-08)})
    lay = formats.open_layout(cube)                                     # the tag is not in the idlsave's name
    assert not lay.scaled and lay.blank is not None
    with FrameReader(lay) as fr:
        f = fr.read((1,))
    assert np.isnan(f[:, 0]).all() and (f[:, 1:] == np.float32(3e-9)).all()


def test_an_idlsave_that_cannot_be_read_leaves_the_counts(tmp_path):
    im, _ = _lp_pair(tmp_path, np.ones((2, 1, 3, 4, 5), np.int16))
    (tmp_path / "c_im_times+wvl.idlsave").write_bytes(b"SR\0\4" + b"\0" * 3)
    lay = formats.open_layout(im)
    assert not lay.scaled and lay.blank is None


def test_an_lp_cube_linked_alone_finds_the_idlsave_beside_the_file_it_points_to(tmp_path):
    # as data/lp/ links: the cube linked under another name into another folder, its idlsave not linked
    (tmp_path / "real").mkdir()
    (tmp_path / "links").mkdir()
    im, _ = _lp_pair(tmp_path / "real", np.ones((2, 1, 3, 4, 5), np.int16))
    synth.write_idlsave(tmp_path / "real" / "c_im_times+wvl.idlsave", {"fac": np.float32(1e11)})
    link = tmp_path / "links" / "generic_im.icube"
    link.symlink_to(im)
    assert formats.lp_sidecar(link) == str(tmp_path / "real" / "c_im_times+wvl.idlsave")
    assert formats.open_layout(link).scale == pytest.approx(1e-11)


def test_an_lp_cube_takes_its_idlsave_under_the_older_name(tmp_path):
    # SSTRED's 2019 cubes: <stem>_im_times_wvl.idlsave, an underscore for the plus
    im, _ = _lp_pair(tmp_path, np.ones((2, 1, 3, 4, 5), np.int16))
    synth.write_idlsave(tmp_path / "c_im_times_wvl.idlsave", {"fac": np.float32(1e9)})
    assert formats.lp_sidecar(im) == str(tmp_path / "c_im_times_wvl.idlsave")
    assert formats.open_layout(im).scale == pytest.approx(1e-9)


def test_of_two_idlsave_files_each_cube_takes_the_one_whose_scale_fits_its_values(tmp_path):
    # as SSTRED's 8542 Stokes cubes of 2019: the same times and lambda in both files, fac 1e9 in
    # _times_wvl for the integer cubes, fac 1 in _times+wvl for the float one
    im, _ = _lp_pair(tmp_path, np.ones((2, 1, 3, 4, 5), np.int16))
    fl = _lp_frames(tmp_path / "c_im.aligned6173.fcube", np.full((6, 4, 5), 1e-9, np.float32))
    synth.write_idlsave(tmp_path / "c_im_times+wvl.idlsave", {"fac": np.float32(1.0)})
    synth.write_idlsave(tmp_path / "c_im_times_wvl.idlsave", {"fac": np.float32(1e9)})
    assert formats.lp_sidecar(im) == str(tmp_path / "c_im_times_wvl.idlsave")
    assert formats.open_layout(im).scale == pytest.approx(1e-9)
    assert formats.lp_sidecar(fl) == str(tmp_path / "c_im_times+wvl.idlsave")
    assert not formats.open_layout(fl).scaled


def test_of_two_idlsave_files_that_both_fit_neither_is_taken(tmp_path, caplog):
    im, _ = _lp_pair(tmp_path, np.ones((2, 1, 3, 4, 5), np.int16))
    synth.write_idlsave(tmp_path / "c_im_times+wvl.idlsave", {"fac": np.float32(1e11)})
    synth.write_idlsave(tmp_path / "c_im_times_wvl.idlsave", {"fac": np.float32(1e9)})
    with caplog.at_level("WARNING"):
        assert formats.lp_sidecar(im) is None
    print(caplog.text)
    assert "c_im_times+wvl.idlsave" in caplog.text and "c_im_times_wvl.idlsave" in caplog.text


def test_an_aligned_cube_given_as_its_per_pixel_file_says_which_idlsave_it_took(tmp_path, caplog):
    # nb_6563_..._corrected_sp.aligned6173.icube: its image cube's idlsave is the unaligned cube's, the tag dropped
    (tmp_path / "w").mkdir()
    im0, sp0 = _lp_pair(tmp_path / "w", np.ones((2, 1, 3, 4, 5), np.int16))
    im, sp = tmp_path / "c_im.aligned6173.icube", tmp_path / "c_sp.aligned6173.icube"
    im0.rename(im)
    sp0.rename(sp)
    synth.write_idlsave(tmp_path / "c_im_times+wvl.idlsave", {"fac": np.float32(1e11)})
    o = formats.opening(sp)
    assert o.path == str(im)
    with caplog.at_level("WARNING"):
        assert formats.open_layout(o.path).scale == pytest.approx(1e-11)
    print(caplog.text)
    assert "c_im.aligned6173.icube" in caplog.text and "c_im_times+wvl.idlsave" in caplog.text


def test_an_integer_lp_cube_whose_idlsave_gives_no_scale_says_its_values_are_counts(tmp_path, caplog):
    # SSTRED's 6173 cmapcorr integer cube of 2019: the one idlsave there says fac 1, the float cube's
    im, _ = _lp_pair(tmp_path, np.ones((2, 1, 3, 4, 5), np.int16))
    synth.write_idlsave(tmp_path / "c_im_times+wvl.idlsave", {"fac": np.float32(1.0)})
    with caplog.at_level("WARNING"):
        assert not formats.open_layout(im).scaled
    print(caplog.text)
    assert "counts" in caplog.text and "c_im_times+wvl.idlsave" in caplog.text


def test_an_integer_lp_cube_without_its_idlsave_says_its_values_are_counts(tmp_path, caplog):
    im, _ = _lp_pair(tmp_path, np.ones((2, 1, 3, 4, 5), np.int16))
    with caplog.at_level("WARNING"):
        formats.open_layout(im)
    assert any("counts" in r.getMessage() and "times+wvl.idlsave" in r.getMessage() for r in caplog.records)
