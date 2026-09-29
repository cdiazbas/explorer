"""The prototype's references (tools/golden/export_prototype.py) stand on exactly these inputs: if an input file
changed, the reference no longer describes it. The comparisons of explorer against them are added with each
layer that produces the same quantities (ROADMAP E1 onwards)."""
import hashlib
import json
import tomllib
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
CASES = tomllib.loads((ROOT / "tests" / "golden" / "cases.toml").read_text())["case"]
SYNTHETIC = [c for c in CASES if c["source"] == "synthetic"]


def _meta(ref):
    return json.loads(str(ref["meta"]))


@pytest.mark.parametrize("case", SYNTHETIC, ids=lambda c: c["name"])
def test_reference_matches_its_versioned_inputs(case):
    ref = np.load(ROOT / case["reference"])
    inputs = _meta(ref)["inputs"]
    d = ROOT / "tests" / "golden" / "data" / case["name"]
    assert inputs, "the reference records no inputs"
    for name, digest in inputs.items():
        assert hashlib.sha256((d / name).read_bytes()).hexdigest() == digest, f"{name} changed since the export"


@pytest.mark.parametrize("case", SYNTHETIC, ids=lambda c: c["name"])
def test_reference_covers_the_case(case):
    ref = np.load(ROOT / case["reference"])
    keys, m = set(ref.files), _meta(ref)
    assert {f"frame.{i}" for i in range(len(case["frames"]))} <= keys
    assert {f"series.{j}" for j in range(len(case["pixels"]))} <= keys
    assert {f"reduce.{k}" for k in range(len(case["reduce"]))} <= keys
    assert {f"slit_slab.{k}" for k in range(len(case["slits"]))} <= keys
    assert m["prototype_code_md5"] and m["case"]["name"] == case["name"]
    assert m["viewer"]["ysample"] is not None                   # the running viewer's ranges were captured


# the result types test_data.py compares; a reference with any other one fails until its comparison is written
COMPARED = {"axes", "frame", "icube", "limits", "reduce", "series", "slit_bands", "slit_ix", "slit_iy", "slit_path",
            "slit_slab", "sp_fits"}


def _references():
    for c in CASES:
        p = ROOT / c["reference"]
        yield pytest.param(c, id=c["name"],
                           marks=[] if p.exists() else [pytest.mark.skip(reason=f"no reference here: {p}")])


@pytest.mark.parametrize("case", list(_references()))
def test_every_exported_result_is_compared(case):
    ref = np.load(ROOT / case["reference"])
    exported = {k.split(".")[0] for k in ref.files if k != "meta"}
    assert exported <= COMPARED, f"exported but never compared: {sorted(exported - COMPARED)}"


def _prototype_md5(proto: Path) -> str:
    """The fingerprint of the prototype's code, as tools/golden/export_prototype.py records it."""
    files = sorted(list((proto / "app").glob("*.py")) + list((proto / "viewer").glob("*.py")))
    code = {str(f.relative_to(proto)): hashlib.md5(f.read_bytes()).hexdigest() for f in files}
    return hashlib.md5(json.dumps(code, sort_keys=True).encode()).hexdigest()


@pytest.mark.parametrize("case", list(_references()))
def test_reference_was_exported_from_the_prototype_as_it_is(case):
    """A reference exported before the prototype's code changed no longer says what the prototype computes."""
    proto = ROOT.parent / "prototype"
    if not (proto / "app" / "viewer.py").exists():
        pytest.skip("no prototype next to explorer here")
    recorded = _meta(np.load(ROOT / case["reference"]))["prototype_code_md5"]
    assert _prototype_md5(proto) == recorded, (
        f"the prototype's code changed since {case['reference']} was exported: re-export it "
        "(tools/golden/export_prototype.py) and look at what changed with tools/golden/compare.py")
