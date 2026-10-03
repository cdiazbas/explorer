"""The IDL SAVE reader on files written by synth.write_idlsave: every kind of variable SSTRED's files hold, records
skipped, what it does not decode, and files it refuses. That it reads SSTRED's real files as scipy.io.readsav
does was measured on all of them (docs/journal.md)."""
import numpy as np
import pytest

from explorer.data.formats import idlsave
from explorer.testing import synth

TIMES = 58751.188 + np.arange(6, dtype=np.float64).reshape(2, 3)        # (scan, tuning) seconds of the day


@pytest.fixture
def save(tmp_path):
    return synth.write_idlsave(tmp_path / "c_im_times+wvl.idlsave", {
        "lambda": np.array([617.30, 617.33, 617.36]), "time": TIMES, "times": np.array(["16:19:11.188", "16:19:31"]),
        "fac": np.float32(1e11), "nan_rplcmnt": np.int16(-1240), "n": np.int32(-7), "mu": np.float64(0.83),
        "cube": np.arange(24, dtype=np.float32).reshape(2, 3, 4), "counts": np.array([-3, 0, 32767], np.int16),
        "label": "nb 6173", "empty": ""}, structures=["meta"])


def test_every_kind_of_variable_reads_back(save):
    v = idlsave.read(save)
    np.testing.assert_array_equal(v["lambda"], [617.30, 617.33, 617.36])
    np.testing.assert_array_equal(v["time"], TIMES)                      # numpy order: (scan, tuning)
    assert list(v["times"]) == ["16:19:11.188", "16:19:31"]
    assert v["fac"] == np.float32(1e11) and v["fac"].dtype == np.float32
    assert v["nan_rplcmnt"] == -1240 and v["nan_rplcmnt"].dtype == np.int16
    assert v["n"] == -7 and v["mu"] == 0.83
    np.testing.assert_array_equal(v["cube"], np.arange(24, dtype=np.float32).reshape(2, 3, 4))
    np.testing.assert_array_equal(v["counts"], [-3, 0, 32767])
    assert v["label"] == "nb 6173" and v["empty"] == ""
    assert v["time"].dtype.isnative and v["cube"].dtype.isnative


def test_a_structure_is_not_decoded_and_the_rest_still_reads(save):
    v = idlsave.read(save)
    assert isinstance(v["meta"], idlsave.Unread) and v["meta"].why == "structure"
    assert set(v) >= {"lambda", "fac", "meta"}


def test_only_the_names_asked_for(save):
    assert set(idlsave.read(save, names={"FAC", "lambda"})) == {"fac", "lambda"}
    assert idlsave.read(save, names={"absent"}) == {}


def test_files_it_refuses(tmp_path, save):
    raw = open(save, "rb").read()
    for name, content, why in (("fits", b"SIMPLE  =" + b" " * 80, "not an IDL SAVE"),
                               ("zipped", b"SR\0\6" + raw[4:], "compressed"),
                               ("short", raw[:len(raw) // 2], "short")):
        (tmp_path / name).write_bytes(content)
        with pytest.raises(ValueError, match=why):
            idlsave.read(tmp_path / name)
