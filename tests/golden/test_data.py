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
