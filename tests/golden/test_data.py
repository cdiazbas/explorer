"""Level 1 of the comparison with the prototype (docs/plan.md §7.1): explorer.data against the references that
tools/golden/export_prototype.py wrote with the prototype's own functions. The synthetic case always runs; the
real one only where its reference exists (bellatrix), with -m golden_real or by default when present."""
import json
import tomllib
from pathlib import Path

import numpy as np
import pytest

from explorer.data import formats

ROOT = Path(__file__).resolve().parents[2]
CASES = tomllib.loads((ROOT / "tests" / "golden" / "cases.toml").read_text())["case"]


def _cases():
    for c in CASES:
        ref = ROOT / c["reference"]
        marks = [pytest.mark.golden_real] if c["source"] == "path" else []
        if not ref.exists():
            marks.append(pytest.mark.skip(reason=f"no reference here: {c['reference']}"))
        yield pytest.param(c, id=c["name"], marks=marks)


def _inputs(case):
    if case["source"] == "synthetic":
        d = ROOT / "tests" / "golden" / "data" / case["name"]
        return d / f"{case['name']}_im.fits"
    return (ROOT / case["path"]).resolve()


@pytest.fixture(params=list(_cases()))
def golden(request):
    case = request.param
    ref = np.load(ROOT / case["reference"])
    return case, ref, json.loads(str(ref["meta"])), _inputs(case)


def test_layout_matches_the_prototype(golden):
    case, ref, meta, im = golden
    lay = formats.open_layout(im)
    assert list(lay.shape) == meta["shape"]
    assert list(lay.axes) == meta["axes_names"]


def test_frames_identical_to_the_prototype(golden):
    from explorer.data.io import FrameReader

    case, ref, meta, im = golden
    with FrameReader(formats.open_layout(im)) as r:
        for i, idx in enumerate(case["frames"]):
            got, want = r.read(tuple(idx)), ref[f"frame.{i}"]
            assert got.dtype == want.dtype and got.shape == want.shape
            assert np.array_equal(got, want, equal_nan=True), f"frame {idx} differs"


def test_series_identical_to_the_prototype(golden):
    from explorer.data.io import FrameReader

    case, ref, meta, im = golden
    free = sorted(a for a in meta["axis_positions"] if a is not None)
    with FrameReader(formats.open_layout(im)) as r:
        for j, (y, x) in enumerate(case["pixels"]):
            got, want = r.series(y, x, (0,) * len(r.shape[:-2]), free), ref[f"series.{j}"]
            assert got.shape == want.shape and np.array_equal(got, want, equal_nan=True), f"pixel {(y, x)} differs"


def test_per_pixel_files_identical_to_the_prototype(golden):
    from explorer.data.io import FrameReader
    from explorer.data.pixel import SpLP, lp_pixel_layout, open_pixel

    case, ref, meta, im = golden
    with FrameReader(formats.open_layout(im)) as fr:
        sp = open_pixel(im, fr)
        if any(k.startswith("sp_fits.") for k in ref.files):
            assert sp is not None and sp.kind == "sp.fits"
            for j, (y, x) in enumerate(case["pixels"]):
                assert np.array_equal(sp.block(y, x), ref[f"sp_fits.{j}"], equal_nan=True), f"sp.fits {(y, x)}"
        if "icube_calibration" in meta:
            icube = str(im).replace("_im.fits", "_sp.icube")
            lp = SpLP(lp_pixel_layout(icube, fr.ny, fr.nx))
            cal, want = lp.calibrate(fr), meta["icube_calibration"]
            # np.polyfit differs between machines in the last digits (docs/journal.md): 1e-12 relative
            for k in ("scale", "zero", "max_resid"):
                assert cal[k] == pytest.approx(want[k], rel=1e-12, abs=1e-24), k
            for j, (y, x) in enumerate(case["pixels"]):
                assert np.array_equal(lp.block(y, x), ref[f"icube.{j}"], equal_nan=True), f"icube {(y, x)}"
            lp.close()
        if sp is not None:
            sp.close()


def test_axes_identical_to_the_prototype(golden):
    from explorer.data import axes

    case, ref, meta, im = golden
    lay = formats.open_layout(im)
    assert list(axes.roles(lay.axes, lay.shape)[:3]) == meta["axis_positions"]
    ax = axes.from_fits(im)
    for k in ("lam_nm", "t_sec", "corners", "dlam_A", "vel_kms"):
        v = getattr(ax, k)
        got = v() if callable(v) else v
        assert (got is None) == (f"axes.{k}" not in ref.files), k
        if got is not None:
            assert np.array_equal(got, ref[f"axes.{k}"]), f"axes.{k} differs"
    want = meta["axes"]
    t = axes.roles(lay.axes, lay.shape).t
    assert dict(line=ax.line, lam0_nm=ax.lam0_nm, cont=ax.cont, bunit=ax.bunit,
                corner_px=[list(c) for c in ax.corner_px] if ax.corner_px else None,
                dateref=None if ax.dateref is None else str(ax.dateref), source=ax.source,
                utc=[ax.utc_str(i) for i in range(lay.shape[t])] if t is not None else None) == want


def test_power_of_ten_of_stokes_i_as_the_prototype(golden):
    """The viewer's power of ten for I, from the first spectrum it showed (the image centre at its start index)."""
    from explorer.data import axes
    from explorer.data.io import FrameReader

    case, ref, meta, im = golden
    if "viewer" not in meta:
        pytest.skip("no viewer-level reference for this case")
    v = meta["viewer"]
    lay = formats.open_layout(im)
    r = axes.roles(lay.axes, lay.shape)
    with FrameReader(lay) as fr:
        spec = fr.series(fr.ny // 2, fr.nx // 2, tuple(v["idx"]), [r.s, r.l])
    assert axes.power_of_ten(spec[0]) == v["iscale"]
    assert axes.from_fits(im).cont == v["cont"]


def test_limits_and_reduction_identical_to_the_prototype(golden):
    from explorer.data.io import FrameReader
    from explorer.data.kernels import reduce_u8_serial
    from explorer.data.stats import limits

    case, ref, meta, im = golden
    with FrameReader(formats.open_layout(im)) as r:
        imgs = [r.read(tuple(idx)) for idx in case["frames"]]
    # np.percentile on float32 rounds its interpolation differently from one numpy to another: 2.3.5 (the Intel
    # Mac's pin) and 2.5.3 give limits 1 float32 ulp apart on the same values, on the same machine. Bit for bit with
    # the numpy the reference was exported with; within 1 ulp with another
    same_numpy = meta.get("numpy") == np.__version__
    for i, (img, idx) in enumerate(zip(imgs, case["frames"], strict=True)):
        got, want = np.asarray(limits(img, symmetric=idx[1] > 0)), ref[f"limits.{i}"]
        if same_numpy:
            assert np.array_equal(got, want), f"limits.{i}"
        else:
            np.testing.assert_array_max_ulp(got.astype(np.float32), want.astype(np.float32), maxulp=1)
    for k, c in enumerate(case["reduce"]):
        lo, hi = ref[f"limits.{c['frame']}"]
        out = np.empty((c["h"], c["w"]), np.uint8)
        reduce_u8_serial(imgs[c["frame"]], c["y0"], c["x0"], c["f"], float(lo), float(hi), out)
        assert np.array_equal(out, ref[f"reduce.{k}"]), f"reduce.{k}"


def _same(a, b):
    """Equal numbers, NaN equal to NaN, through nested lists, tuples and dicts."""
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return isinstance(b, (list, tuple)) and len(a) == len(b) and all(map(_same, a, b))
    return a == b or (a != a and b != b)


def test_quv_ranges_identical_to_the_prototype(golden):
    from explorer.data import axes
    from explorer.data.io import FrameReader
    from explorer.data.stats import quv_amplitude_ranges

    case, ref, meta, im = golden
    if "quv" not in meta:
        pytest.skip("no Q U V in this case")
    lay = formats.open_layout(im)
    roles, cont = axes.roles(lay.axes, lay.shape), axes.from_fits(im).cont
    with FrameReader(lay) as r:
        for t, want in meta["quv"].items():
            half, info, _, _ = quv_amplitude_ranges(r, roles, cont, int(t))
            got = dict(half={str(k): v for k, v in half.items()}, info={str(k): list(v) for k, v in info.items()})
            assert _same(got, want), f"Q U V at t={t}: {got} != {want}"


def test_sampled_y_ranges_identical_to_the_prototype(golden):
    """The running viewer's spectra ranges: the random sample from its first image, with Q U V then replaced by the
    whole-frame ranges at its start t, and the first image's contrast limits."""
    from explorer.data import axes
    from explorer.data.executors import Executors
    from explorer.data.io import FrameReader
    from explorer.data.pixel import open_pixel
    from explorer.data.stats import (
        limits,
        quv_amplitude_ranges,
        quv_plot_ranges,
        sample_pixels,
        sample_profiles,
        sample_ranges,
    )

    case, ref, meta, im = golden
    if "viewer" not in meta:
        pytest.skip("no viewer-level reference for this case")
    v = meta["viewer"]
    lay = formats.open_layout(im)
    roles, cont = axes.roles(lay.axes, lay.shape), axes.from_fits(im).cont
    idx = tuple(v["idx"])
    ex = Executors(gather_threads=16)
    try:
        with FrameReader(lay) as fr:
            img = fr.read(idx)
            assert list(limits(img, symmetric=idx[roles.s] > 0)) == v["limits"]
            sp = open_pixel(im, fr)
            assert getattr(sp, "kind", None) == v["sp_kind"]
            ys, xs, ts = sample_pixels(img, im, roles.nt)
            prof = ex.numba.submit(sample_profiles, ys, xs, ts, fr, roles, sp).result()
            ranges, iscale, _ = sample_ranges(prof, cont, v["iscale"])
            t = idx[roles.t] if roles.t is not None else 0
            half = quv_amplitude_ranges(fr, roles, cont, t)[0]
            yquv = quv_plot_ranges(half, cont, iscale)
            if sp is not None:
                sp.close()
    finally:
        ex.close()
    assert _same({str(k): list(r) for k, r in yquv.items()}, v["yquv"])
    for k, r in yquv.items():
        ranges[k] = r
    assert _same([list(r) for r in ranges], v["ysample"])


def test_slits_identical_to_the_prototype(golden):
    """Path (1e-12 relative: its float64 differs in the last digit between machines, docs/journal.md), pixels,
    the slab from the per-pixel file and the bands from the frames."""
    from explorer.data.io import FrameReader
    from explorer.data.pixel import open_pixel
    from explorer.data.slits import read_slit_bands, read_slit_slab, slit_path, slit_pixels

    case, ref, meta, im = golden
    with FrameReader(formats.open_layout(im)) as fr:
        sp = open_pixel(im, fr)
        for m, pts in enumerate(case["slits"]):
            path = slit_path(pts)
            np.testing.assert_allclose(path, ref[f"slit_path.{m}"], rtol=1e-12, atol=0)
            iy, ix = slit_pixels(ref[f"slit_path.{m}"], fr.ny, fr.nx)
            assert np.array_equal(iy, ref[f"slit_iy.{m}"]) and np.array_equal(ix, ref[f"slit_ix.{m}"])
            assert np.array_equal(slit_pixels(path, fr.ny, fr.nx)[0], iy), "pixels from our own path"
            if f"slit_slab.{m}" in ref.files:
                slab, _ = read_slit_slab(sp, iy, ix)
                assert slab.dtype == np.float32 and np.array_equal(slab, ref[f"slit_slab.{m}"], equal_nan=True)
            bands = read_slit_bands(fr, [tuple(f) for f in case["frames"]], iy, ix)
            assert np.array_equal(bands, ref[f"slit_bands.{m}"], equal_nan=True), f"slit_bands.{m}"
        if sp is not None:
            sp.close()
