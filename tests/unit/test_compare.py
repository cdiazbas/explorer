"""tools/golden/compare.py decides whether explorer matches the prototype: it must see every kind of difference."""
import importlib.util
import json
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location("compare", Path(__file__).parents[2] / "tools" / "golden" / "compare.py")
compare = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare)


def _ref(**arrays):
    return {"meta": np.array(json.dumps({"host": "a", "axes": {"cont": 4, "lam0_nm": 617.3341}})), **arrays}


def _status(rows):
    return {r.key: r.status for r in rows}


def test_identical_including_nan():
    a = np.array([1.0, np.nan, 3.0], np.float32)
    assert _status(compare.compare(_ref(x=a), _ref(x=a.copy()), meta=True)) == {"x": "same"}


def test_every_kind_of_difference():
    ref = _ref(a=np.array([1.0, 2.0]), b=np.array([1.0, np.nan]), c=np.zeros(3), d=np.array([1, 2], np.uint8),
               gone=np.zeros(1))
    got = _ref(a=np.array([1.0, 2.5]), b=np.array([1.0, 2.0]), c=np.zeros(4), d=np.array([1, 3], np.uint8),
               new=np.zeros(1))
    assert _status(compare.compare(ref, got)) == {"a": "DIFF", "b": "DIFF", "c": "DIFF", "d": "DIFF",
                                                 "gone": "MISSING", "new": "EXTRA"}


def test_tolerance_turns_small_differences_into_close():
    ref, got = _ref(a=np.array([1.0, 2.0])), _ref(a=np.array([1.0, 2.0 + 1e-9]))
    assert _status(compare.compare(ref, got)) == {"a": "DIFF"}
    assert _status(compare.compare(ref, got, rtol=1e-6)) == {"a": "close"}


def test_meta_numbers_compared_and_run_details_ignored():
    ref = _ref()
    got = {"meta": np.array(json.dumps({"host": "b", "axes": {"cont": 5, "lam0_nm": 617.3341}}))}
    assert _status(compare.compare(ref, got, meta=True)) == {"meta.axes.cont": "DIFF"}


def test_large_inputs_are_fingerprinted_not_read_through(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("export", Path(__file__).parents[2] / "tools" / "golden" /
                                                  "export_prototype.py")
    export = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(export)
    monkeypatch.setattr(export, "FULL_HASH_MAX", 1000)
    monkeypatch.setattr(export, "EDGE", 100)
    small, big = tmp_path / "small", tmp_path / "big"
    small.write_bytes(b"x" * 500)
    big.write_bytes(bytes(range(256)) * 20)
    assert len(export.fingerprint(small)) == 64                      # whole-file sha256
    size, mtime, digest = export.fingerprint(big).split(":")
    assert int(size) == 5120 and len(digest) == 64
    data = bytearray(big.read_bytes())
    data[2500] ^= 1                                                  # a change in the middle is not seen:
    big.write_bytes(bytes(data))                                     # the fingerprint trusts size, mtime, edges
    assert export.fingerprint(big).split(":")[2] == digest
