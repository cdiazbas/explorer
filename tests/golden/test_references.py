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
