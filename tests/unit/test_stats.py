"""Kernels in strips against one serial call, the profile sample's two read paths, and what the prototype's
references do not cover (scaled integer cubes, dropped profiles)."""
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from astropy.io import fits

from explorer.data import axes, formats
from explorer.data.executors import Executors
from explorer.data.io import FrameReader
from explorer.data.kernels import absmax_into, reduce_u8, reduce_u8_serial
from explorer.data.pixel import open_pixel
from explorer.data.stats import (
    limits,
    nice_range,
    quv_amplitude_ranges,
    quv_threads,
    sample_pixels,
    sample_profiles,
    sample_ranges,
)
from explorer.testing import synth

SHAPE = (3, 4, 5, 48, 40)


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("stats"), "c", shape=SHAPE)


def test_reduction_in_strips_equals_one_serial_call():
    rng = np.random.default_rng(1)
    img = rng.normal(size=(1300, 1100)).astype(np.float32)
    img[:40, :] = np.nan                                               # padding: level 0
    serial, strips = np.empty((650, 550), np.uint8), np.empty((650, 550), np.uint8)
    reduce_u8_serial(img, 0, 0, 2, -1.0, 1.0, serial)
    with ThreadPoolExecutor(8) as pool:
        reduce_u8(img, 0, 0, 2, -1.0, 1.0, strips, pool, 8)
    assert np.array_equal(serial, strips) and serial[:20].max() == 0 and serial[20:].min() >= 1


@pytest.mark.parametrize("dtype", [">f4", "<f4"])
def test_absmax_equals_numpy_serial_and_in_strips(dtype):
    rng = np.random.default_rng(2)
    frames = [rng.normal(size=300_000).astype(dtype) for _ in range(3)]
    frames[1][:10] = np.nan
    scale = rng.uniform(0.5, 2, size=300_000).astype(np.float32)
    want = np.max([np.nan_to_num(np.abs(f.astype(np.float32) * scale)) for f in frames], axis=0)
    a, b = np.zeros(300_000, np.float32), np.zeros(300_000, np.float32)
    with ThreadPoolExecutor(4) as pool:
        for f in frames:
            absmax_into(a, f.tobytes(), f.dtype, scale)
            absmax_into(b, f.tobytes(), f.dtype, scale, pool, 4)
    assert np.array_equal(a, want) and np.array_equal(b, want)


def test_limits_and_nice_range():
    assert limits(np.full((16, 16), np.nan, np.float32)) == (0.0, 1.0)
    assert limits(np.full((16, 16), 3.0, np.float32)) == (3.0, 4.0)
    assert limits(np.zeros((16, 16), np.float32), symmetric=True) == (0.0, 1.0)
    assert nice_range(0.13, 0.87) == (0.0, 1.0)
    assert nice_range(-3.2, 3.2) == (-4.0, 4.0)
    assert nice_range(5.0, 5.0) == (4.0, 6.0)                         # span |hi| = 5: step 2


def test_sample_is_the_same_from_the_cube_and_from_the_per_pixel_file(dataset):
    data = fits.getdata(dataset["im"]).astype(np.float64)              # (t, s, l, y, x)
    lay = formats.open_layout(dataset["im"])
    roles = axes.roles(lay.axes, lay.shape)
    ex = Executors(gather_threads=4, io_threads=1, strips=1)
    with FrameReader(lay) as fr:
        img = fr.read((0, 0, 2))
        ys, xs, ts = sample_pixels(img, dataset["im"], roles.nt)
        again = sample_pixels(img, "/elsewhere/" + os.path.basename(dataset["im"]), roles.nt)
        assert all(np.array_equal(a, b) for a, b in zip((ys, xs, ts), again, strict=True))   # seed from the name
        assert np.isfinite(img[ys, xs]).all() and (img[ys, xs] != 0).all()
        from_cube = ex.numba.submit(sample_profiles, ys, xs, ts, fr, roles).result()
        with open_pixel(dataset["im"], fr) as sp:
            from_sp = sample_profiles(ys, xs, ts, fr, roles, sp)
    ex.close()
    want = np.stack([data[t, :, :, y, x] for y, x, t in zip(ys, xs, ts, strict=True)])
    assert np.array_equal(from_cube, want) and np.array_equal(from_sp, want)
    assert sample_pixels(np.full((8, 8), np.nan, np.float32), "x", 3) is None


def test_sample_ranges_drop_padding_and_keep_intensity_non_negative():
    rng = np.random.default_rng(3)
    prof = np.empty((50, 4, 6))
    prof[:, 0] = rng.normal(2e-9, 1.5e-9, size=(50, 6)).clip(1e-12)   # wide: median - 2 sigma < 0
    prof[:, 1:] = rng.normal(0, 1e-11, size=(50, 3, 6))
    prof[3, 2, 1] = np.nan                                             # padding at its t
    ranges, iscale, kept = sample_ranges(prof, cont=5)
    assert kept == 49 and iscale == 1e-9 and ranges[0][0] == 0.0
    assert all(r[0] == -r[1] for r in ranges[1:])
    assert sample_ranges(np.full((3, 4, 6), np.nan), cont=5) == (None, None, 0)


def test_quv_ranges_of_a_scaled_integer_cube_are_those_of_its_values(tmp_path):
    """The prototype read Q U V frames as raw floats; BSCALE/BZERO integers are converted first here."""
    rng = np.random.default_rng(4)
    nt, ns, nl, ny, nx = 2, 4, 5, 64, 64
    raw = rng.integers(-3000, 3000, size=(nt, ns, nl, ny, nx)).astype(">i2")
    raw[:, 0] = rng.integers(20000, 30000, size=(nt, nl, ny, nx))     # Stokes I, positive
    raw[:, :, :, :4, :] = -32768                                       # BLANK rows
    hdr = fits.Header()
    for k, v in (("SIMPLE", True), ("BITPIX", 16), ("NAXIS", 5), ("NAXIS1", nx), ("NAXIS2", ny), ("NAXIS3", nl),
                 ("NAXIS4", ns), ("NAXIS5", nt), ("BSCALE", 1e-12), ("BZERO", 0.0), ("BLANK", -32768)):
        hdr[k] = v
    body = raw.tobytes()
    p = tmp_path / "int_im.fits"
    p.write_bytes(hdr.tostring().encode() + body + b"\0" * (-len(body) % 2880))
    phys = raw.astype(np.float32) * np.float32(1e-12) + np.float32(0.0)
    phys[raw == -32768] = np.nan
    q = tmp_path / "float_im.fits"
    fits.PrimaryHDU(phys).writeto(q)
    got, want = [], []
    for path, out in ((p, got), (q, want)):
        lay = formats.open_layout(path)
        with FrameReader(lay) as fr:
            out.append(quv_amplitude_ranges(fr, axes.roles(lay.axes, lay.shape), 4, 1, min_px=10)[:2])
    assert repr(got) == repr(want) and set(got[0][0]) == {1, 2, 3}      # repr: NaN percentiles compare equal


def test_quv_threads_within_the_batch_memory():
    assert quv_threads(4096 * 4096 * 4, 64) == 4                     # 64 MB frames: 256 MB
    assert quv_threads(2048 * 2048 * 4, 64) == 16
    assert quv_threads(2048 * 2048 * 4, 8) == 8
