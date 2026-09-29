"""The synthetic cube is what the demo and the comparison tests stand on: shape, byte order, padding, determinism."""
import hashlib

import numpy as np
from astropy.io import fits

from explorer.testing import synth

SHAPE = (2, 4, 3, 48, 40)                                  # (t, s, lambda, y, x): small, not square


def test_shape_dtype_and_axes(tmp_path):
    p = synth.write_stokes_cube(tmp_path / "c_im.fits", shape=SHAPE)
    with fits.open(p, memmap=False) as h:
        d, hdr = h[0].data, h[0].header
    assert d.shape == SHAPE and d.dtype == np.dtype(">f4")
    assert [hdr[f"CTYPE{i}"] for i in (5, 4, 3)] == ["UTC", "STOKES", "WAVE"]


def test_padding_is_nan_and_the_field_is_finite(tmp_path):
    p = synth.write_stokes_cube(tmp_path / "c_im.fits", shape=SHAPE)
    d = fits.getdata(p)
    inside = synth.fov_mask(*SHAPE[-2:])
    assert 0.05 < (~inside).mean() < 0.6                   # some padding, most of the image is data
    assert np.isnan(d[..., ~inside]).all() and np.isfinite(d[..., inside]).all()
    assert (d[:, 0][..., inside] > 0).all()                # Stokes I is positive where there is data


def test_deterministic(tmp_path):
    a = synth.write_stokes_cube(tmp_path / "a_im.fits", shape=SHAPE, seed=3)
    b = synth.write_stokes_cube(tmp_path / "b_im.fits", shape=SHAPE, seed=3)
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()   # noqa: E731
    assert digest(a) == digest(b)
