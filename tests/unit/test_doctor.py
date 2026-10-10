"""`explorer doctor` runs headless, reads a cube's header, and reports a failed check with exit code 1."""
import json
import os
import sys

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


def test_started_by_run_sh_the_numba_pool_is_the_one_the_viewer_sizes(headless):
    """The scattered reads use one numba thread per request up to the storage probe's 128 on network storage
    (data/_numba.py: a cold lambda-t 0.42 s with 128 threads against 0.56 s with 64). run.sh exported
    NUMBA_NUM_THREADS=64, a default older than that measurement, which capped them at 64 for everyone it starts;
    and doctor imported numba before explorer sized its pool, so it reported the cores' count instead of the
    viewer's pool (ROADMAP E0.16)."""
    import subprocess

    from explorer.data._numba import GATHER_MAX

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env = {k: v for k, v in os.environ.items() if k != "NUMBA_NUM_THREADS"}
    # the environment running these tests: a worktree or a copy in /tmp has none of its own next to the code, and
    # run.sh leaves another tree's as it is (ROADMAP X.6)
    env["EXPLORER_VENV"] = sys.prefix
    out = headless / "r.json"
    subprocess.run([os.path.join(root, "scripts", "run.sh"), "doctor", "--out", str(out)], env=env,
                   capture_output=True, text=True, timeout=300)
    assert json.loads(out.read_text())["numba"]["threads"] >= GATHER_MAX
