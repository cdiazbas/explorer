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
