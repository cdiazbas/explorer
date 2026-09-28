"""`explorer doctor` runs headless, reads a cube's header, and reports a failed check with exit code 1."""
import json
import os

import numpy as np
import pytest

from explorer import doctor


@pytest.fixture
def headless(monkeypatch, tmp_path):
    # never open windows on the user's screen from a test (the X11 bridge would); cache in tmp
    monkeypatch.delenv("DISPLAY", raising=False)
    # a shell's LD_LIBRARY_PATH can point at another environment's Qt (bellatrix: the conda env of .bashrc),
    # which breaks PySide6; that is doctor's finding to report, not what this test is about
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path


def _tiny_cube(path):
    from astropy.io import fits

    data = np.arange(3 * 2 * 64 * 64, dtype=">f4").reshape(3, 2, 64, 64)       # (t, lambda, y, x)
    hdr = fits.Header()
    for i, c in enumerate(("HPLN-TAB", "HPLT-TAB", "WAVE-TAB", "UTC--TAB"), start=1):
        hdr[f"CTYPE{i}"] = c
    fits.PrimaryHDU(data, hdr).writeto(path)


def test_doctor_headless_with_cube(headless, capsys):
    cube = headless / "x_im.fits"
    _tiny_cube(cube)
    out = headless / "r.json"
    code = doctor.main([str(cube), "--out", str(out)])
    rep = json.loads(out.read_text())
    status = {c["name"]: c["status"] for c in rep["checks"]}
    assert status["Qt"] == "ok" and rep["qt"]["platform"] == "offscreen"
    assert status["numba"] == "ok" and status["files"] == "ok"
    assert rep["cube"]["shape"] == [3, 2, 64, 64] and rep["cube"]["axes"][0] == "UTC--TAB"
    assert code == (1 if "FAIL" in status.values() else 0)


def test_failed_check_gives_exit_1(headless, monkeypatch):
    monkeypatch.setattr(doctor, "c_numba", lambda rep: (doctor.FAIL, "forced"))
    assert doctor.main(["--out", os.devnull]) == 1


def test_own_qtlibs_on_library_path_is_not_a_warning(monkeypatch):
    monkeypatch.setattr(doctor.sys, "platform", "linux")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/some/where/explorer/.qtlibs/only")
    assert doctor.c_environment(doctor.Report())[0] == doctor.OK
    monkeypatch.setenv("LD_LIBRARY_PATH", "/other/env/lib:/some/where/explorer/.qtlibs/only")
    status, info = doctor.c_environment(doctor.Report())
    assert status == doctor.WARN and "/other/env/lib" in info
