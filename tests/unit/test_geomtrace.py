"""The geometry trace (ROADMAP E6.7, ui/geomtrace.py): off unless EXPLORER_GEOMETRY_TRACE is set, and then wrapping
nothing; on, a line for every move and resize of the window and its panels, for each one explorer's code asked for
with the frames that asked, and for each look worn; stopped, everything back as it was. A start through ui.app.run
with the variable writes the file."""
import inspect
import os
import subprocess
import sys
import time

import pytest

from explorer.testing import synth

SHAPE = (4, 4, 11, 96, 80)


def spin(qapp, until, timeout=8.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.005)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("trace"), "c", shape=SHAPE, icube=False)["im"]


def wrapped(QtWidgets, geomtrace) -> list[str]:
    """The watched methods that are Python functions (the tracer's) instead of Qt's own."""
    return [f"{c.__name__}.{n}" for c in (QtWidgets.QDockWidget, QtWidgets.QMainWindow)
            for n in geomtrace.WATCHED + ("setFloating",)
            if hasattr(c, n) and inspect.isfunction(getattr(c, n))]


def test_off_unless_asked_and_then_nothing_is_wrapped(qapp):
    from PySide6 import QtWidgets

    from explorer.ui import geomtrace

    assert geomtrace.ENV == "EXPLORER_GEOMETRY_TRACE"    # EXPLORER_TRACE is the spans' Perfetto file (obs.trace)
    assert geomtrace.wanted({geomtrace.ENV: "1"}) and geomtrace.wanted({geomtrace.ENV: "yes"})
    assert not geomtrace.wanted({}) and not geomtrace.wanted({geomtrace.ENV: "0"})
    assert not geomtrace.wanted({"EXPLORER_TRACE": "t.json"})
    assert geomtrace.install_from_env({}) is None
    assert not wrapped(QtWidgets, geomtrace), wrapped(QtWidgets, geomtrace)


def test_on_it_says_who_moved_what(qapp, cube, tmp_path):
    from PySide6 import QtCore, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui import geomtrace
    from explorer.ui.shell import Shell

    t = geomtrace.Tracer(tmp_path / "geometry.log")
    ds = Dataset.open(cube)
    w = Shell(ds)
    try:
        w.resize(1000, 700)
        w.show()
        assert spin(qapp, lambda: "lambda_t" in w.last)
        d = w.spec_dock
        d.setFloating(True)
        d.setGeometry(QtCore.QRect(1100, 80, 420, 300))
        w.set_look(get_look("glass"))                   # glass places its panels itself: glass.py asks
        spin(qapp, lambda: False, 1.0)
    finally:
        w.close()
        ds.close()
        t.stop()
    lines = (tmp_path / "geometry.log").read_text().splitlines()
    text = "\n".join(lines)
    assert lines[0].split()[1] == "START", text[:2000]
    want = [
        ("CALL spectrum  setFloating True", "test_geomtrace.py"),
        ("CALL spectrum  setGeometry (1100, 80, 420, 300)", "test_geomtrace.py"),
        ("EVT  spectrum  Move", ""),
        ("LOOK glass", ""),
        ("CALL spectrum  setGeometry", "glass.py"),
    ]
    for head, origin in want:
        hits = [ln for ln in lines if head in ln and origin in ln]
        assert hits, f"no line with {head!r} from {origin!r} in:\n{text[-4000:]}"
    assert not wrapped(QtWidgets, geomtrace), f"stop() left {wrapped(QtWidgets, geomtrace)} wrapped"
    assert "set_look" not in vars(Shell) or Shell.set_look.__qualname__ == "Shell.set_look", Shell.set_look


def test_a_start_with_the_variable_writes_the_trace(cube, tmp_path):
    env = dict(os.environ, EXPLORER_GEOMETRY_TRACE="1", XDG_CACHE_HOME=str(tmp_path / "cache"),
               EXPLORER_LAYOUT=str(tmp_path / "layout.ini"), QT_QPA_PLATFORM="offscreen", EXPLORER_TERMINAL_KEYS="0")
    env.pop("DISPLAY", None)
    env.pop("EXPLORER_TRACE", None)
    p = subprocess.run([sys.executable, "-m", "explorer", str(cube), "--look", "glass", "--quit-after", "0.5"],
                       capture_output=True, text=True, env=env, timeout=120, cwd=tmp_path)
    logs = list((tmp_path / "cache").rglob("geometry-*.log"))
    assert p.returncode == 0 and len(logs) == 1, dict(exit=p.returncode, logs=logs, stderr=p.stderr[-3000:])
    text = logs[0].read_text()
    assert "[geometry] tracing" in p.stderr, p.stderr[-2000:]
    assert "LOOK glass" in text and "EVT  main" in text, text[-3000:]
    assert not (tmp_path / "geometry").exists() and not list(tmp_path.glob("*.json")), "a spans trace was written"
