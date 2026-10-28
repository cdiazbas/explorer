"""`explorer doctor` runs headless, reads a cube's header, and reports a failed check with exit code 1."""
import json
import os
import subprocess
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


def test_the_pythons_doctor_accepts_are_the_ones_pyproject_allows(monkeypatch):
    """doctor.PYTHONS and requires-python say the same: 3.12 and 3.13 pass the check, 3.11 and 3.14 do not."""
    import tomllib
    import types

    from packaging.specifiers import SpecifierSet

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(root, "pyproject.toml"), "rb") as f:
        allowed = SpecifierSet(tomllib.load(f)["project"]["requires-python"])
    assert {(3, m) for m in range(8, 20) if f"3.{m}.0" in allowed} == set(doctor.PYTHONS)
    for m, want in ((11, doctor.FAIL), (12, doctor.OK), (13, doctor.OK), (14, doctor.FAIL)):
        monkeypatch.setattr(doctor.sys, "version_info", types.SimpleNamespace(major=3, minor=m))
        status, msg = doctor.c_python(doctor.Report())
        assert status in (want, doctor.WARN if want == doctor.OK else want), (m, msg)   # WARN: not in a venv
        assert (status == doctor.FAIL) is (want == doctor.FAIL), (m, msg)


@pytest.mark.parametrize("extra, want", [
    ({}, doctor.WARN),                                              # auto: the bridge stands in, Qt offscreen
    ({"QT_QPA_PLATFORM": "xcb"}, doctor.FAIL),                      # Qt's own X11 asked for: it cannot start
    ({"EXPLORER_X11": "native"}, doctor.FAIL),
])
def test_without_libxcb_cursor_the_bridge_is_a_warning_not_a_failure(headless, monkeypatch, extra, want):
    """A Linux X display without libxcb-cursor: explorer starts through the X11 bridge (platform.plan), so doctor
    checks the Qt the bridge runs and warns; it fails only when Qt's own X11 was asked for."""
    monkeypatch.delenv("QT_QPA_PLATFORM")
    monkeypatch.delenv("EXPLORER_X11", raising=False)
    monkeypatch.setenv("DISPLAY", ":187")                           # never reached: the child runs offscreen
    for k, v in extra.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(doctor.sys, "platform", "linux")
    monkeypatch.setattr(doctor, "find_xcb_cursor", lambda env: None)
    status, msg = doctor.c_qt(doctor.Report(), False)
    assert status == want, msg
    assert "libxcb-cursor.so.0 not found" in msg
    if want == doctor.WARN:
        assert "on 'offscreen'" in msg and "X11 bridge" in msg


SSH = {"SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"}


@pytest.mark.parametrize("env, platform, cursor, want", [
    ({"DISPLAY": "localhost:10.0", **SSH}, "linux", True, ("offscreen", doctor.OK)),     # ssh -Y: the bridge
    ({"DISPLAY": "localhost:10.0", **SSH}, "darwin", True, ("offscreen", doctor.OK)),
    ({"DISPLAY": ":0", **SSH}, "linux", True, ("xcb", doctor.OK)),                       # its own display
    ({"DISPLAY": ":0"}, "linux", True, ("xcb", doctor.OK)),
    ({"DISPLAY": ":0"}, "linux", False, ("offscreen", doctor.WARN)),                     # the bridge stands in
    ({}, "linux", True, ("offscreen", doctor.OK)),                                       # no display
    ({**SSH}, "darwin", True, ("offscreen", doctor.OK)),                                 # no window server
    ({}, "darwin", True, (None, doctor.OK)),                                             # cocoa, Qt's default
    ({"QT_QPA_PLATFORM": "offscreen", "DISPLAY": "localhost:10.0", **SSH}, "linux", True, ("offscreen", doctor.OK)),
])
def test_qt_is_checked_on_the_platform_explorer_would_use(monkeypatch, env, platform, cursor, want):
    """doctor asks explorer's display plan (platform.plan): over ssh -Y explorer draws through the X11 bridge with Qt
    offscreen, and that is the Qt checked, not Qt's own X11 through the link. The child is not started: its
    environment is what is checked."""
    for k in ("DISPLAY", "WAYLAND_DISPLAY", "QT_QPA_PLATFORM", "SSH_CONNECTION", "EXPLORER_X11"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(doctor.sys, "platform", platform)
    monkeypatch.setattr(doctor, "find_xcb_cursor", lambda e: "/x/libxcb-cursor.so.0" if cursor else None)
    seen, real, rep = {}, subprocess.run, doctor.Report()

    def run(cmd, *a, env=None, **kw):
        if cmd[:2] != [sys.executable, "-c"]:                         # platform's own commands
            return real(cmd, *a, env=env, **kw)
        seen["qpa"] = env.get("QT_QPA_PLATFORM")
        d = dict(platform=env.get("QT_QPA_PLATFORM") or "default", qt="6", screens=[])
        return subprocess.CompletedProcess(cmd, 0, stdout="QTJSON" + json.dumps(d), stderr="")
    monkeypatch.setattr(doctor.subprocess, "run", run)
    status, msg = doctor.c_qt(rep, False)
    print(env, platform, cursor, seen, status, msg)
    assert (seen["qpa"], status) == want, msg


def test_doctor_leaves_explorer_s_kernels_compiled_for_the_first_start(tmp_path):
    """doctor's "kernels" check compiles explorer's own kernels into the cache a start then reads: in a fresh cache,
    a process after it finds every kernel the image, the reads and the bridge's warm-up need already compiled (none
    compiled again: their signatures are loaded, numba counts no compile). In processes of their own, as a person
    runs doctor and then explorer. Before: no such check; the first start compiled them."""
    import subprocess
    import sys

    env = dict(os.environ, NUMBA_CACHE_DIR=str(tmp_path / "numba"), QT_QPA_PLATFORM="offscreen")
    env.pop("DISPLAY", None)
    first = subprocess.run([sys.executable, "-c", "from explorer import doctor; doctor.c_kernels(doctor.Report())"],
                           env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr[-2000:]
    code = """
import time
from numba.core import event
n = []
event.register("numba:compile", event.Listener() if False else type("L", (event.Listener,), {
    "on_start": lambda self, e: n.append(e.data["dispatcher"].py_func.__name__), "on_end": lambda self, e: None})())
from explorer.data import gather, kernels
from explorer.platform.xbridge import kernels as xk
t = time.perf_counter()
kernels.warm_up(); gather.warm_up(); xk.warm_up()
print("SECONDS", round(time.perf_counter() - t, 3), "COMPILED", sorted(set(n)))
"""
    second = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    print(second.stdout.strip(), second.stderr[-1500:])
    assert second.returncode == 0 and "COMPILED []" in second.stdout
