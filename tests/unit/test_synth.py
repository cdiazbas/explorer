"""The synthetic cubes are what the demo and the comparison with the prototype stand on: shape, byte order,
padding, determinism, the SOLARNET header, and the per-pixel files that must hold the same values."""
import hashlib
import json
import re

import numpy as np
from astropy.io import fits

from explorer.testing import synth

SHAPE = (3, 4, 5, 48, 40)                                  # (t, s, lambda, y, x): small, not square


def test_shape_dtype_and_axes(tmp_path):
    p = synth.write_stokes_cube(tmp_path / "c_im.fits", shape=SHAPE)
    with fits.open(p, memmap=False) as h:
        d, hdr = h[0].data, h[0].header
    assert d.shape == SHAPE and d.dtype == np.dtype(">f4")
    assert [hdr[f"CTYPE{i}"] for i in (5, 4, 3, 2, 1)] == ["UTC--TAB", "STOKES", "WAVE-TAB", "HPLT-TAB", "HPLN-TAB"]


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


def test_wcs_tab_as_sstred_writes_it(tmp_path):
    """The header the prototype's app/physics.py reads: WCS-TAB column (nt, nl, 2, 2, 4), indices, continuum."""
    nt, _, nl, ny, nx = SHAPE
    p = synth.write_stokes_cube(tmp_path / "c_im.fits", shape=SHAPE)
    with fits.open(p) as h:
        hdr, tab = h[0].header, h["WCS-TAB"].data
        col = tab[hdr["PS3_1"]][0]
        assert hdr["PS3_0"] == "WCS-TAB" and hdr["PS3_1"] == "HPLN+HPLT+WAVE+TIME"
        assert col.shape == (nt, nl, 2, 2, 4)
        assert list(tab["HPLN-INDEX"][0]) == [1, nx] and list(tab["HPLT-INDEX"][0]) == [1, ny]
        assert json.loads(hdr["PRPARA1"])["TUNING_SELECTION"] == [nl - 1]
        np.testing.assert_allclose(col[0, :, 0, 0, 2], synth.LINE_NM + synth.tunings_A(nl) / 10)
        assert (np.diff(col[:, 0, 0, 0, 3]) == synth.CADENCE_S).all()        # time per scan
        assert col[1, 0, 0, 0, 0] != col[0, 0, 0, 0, 0]                    # pointing drifts with t


def test_per_pixel_files_hold_the_same_values(tmp_path):
    paths = synth.write_dataset(tmp_path, "c", shape=SHAPE)
    im, sp = fits.getdata(paths["im"]), fits.getdata(paths["sp"])
    assert sp.shape == (SHAPE[3], SHAPE[4], SHAPE[1], SHAPE[0], SHAPE[2])    # (y, x, s, t, lambda)
    np.testing.assert_array_equal(sp, im.transpose(3, 4, 1, 0, 2))          # exactly the same values
    raw = open(paths["icube"], "rb").read()
    head = raw[:512].rstrip(b"\0").decode()
    kv = dict(re.findall(r"(\w+)=([^,:]+)", head))          # parsed as the prototype's SpLP does
    got = (kv["datatype"].split()[0], int(kv["nx"]), int(kv["ny"]), kv["endian"].strip())
    assert got == ("2", SHAPE[2], SHAPE[0], "l")
    assert int(kv["nt"]) == SHAPE[3] * SHAPE[4] * SHAPE[1] and int(kv["ns"]) == SHAPE[1]
    counts = np.frombuffer(raw[512:], "<i2").reshape(sp.shape)
    expect = np.round(np.nan_to_num(sp.astype(np.float64) * synth.ICUBE_SCALE)).astype("<i2")
    np.testing.assert_array_equal(counts, expect)
