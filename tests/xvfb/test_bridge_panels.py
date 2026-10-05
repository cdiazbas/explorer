"""The glass look's floating panels under a manager that keeps quartz-wm's record of the frame
(fake_quartzwm_frames.py): placed beside the window, the slit's panel below them, and one dragged by its title; at
every step each window is on the X server where Qt has it, and the dragged one ends where the drag left it. The old
manager (fake_quartzwm.py) answers every move with a notice of it; this one answers a move at once with its record of
before, and a move asked while one is on its way with nothing until X confirms it.

    EXPLORER_TEST_XDISPLAY=:99 XAUTHORITY=<cookie> pytest tests/xvfb/test_bridge_panels.py
"""
import json
import os
import subprocess
import sys

import pytest
from test_bridge_quartzwm import HERE, XDISP
from xlinkenv import app_display

pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    from explorer.testing import synth

    return synth.write_dataset(tmp_path_factory.mktemp("xbpanels"), "c", shape=(3, 4, 5, 96, 80), icube=False)["im"]


@pytest.fixture
def wm():
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "fake_quartzwm_frames.py")], stdout=subprocess.PIPE,
                         env=dict(os.environ, DISPLAY=XDISP), text=True)
    line = p.stdout.readline().strip()
    if line != "ready":
        p.wait(5)
        pytest.skip(f"the quartz-like manager did not start: {line!r} (exit {p.poll()})")
    yield p
    p.terminate()
    p.wait(5)


def test_glass_panels_placed_shown_and_dragged_are_on_x_where_qt_has_them(cube, wm):
    env = {k: v for k, v in os.environ.items() if k not in ("QT_QPA_PLATFORM", "EXPLORER_X11")}
    env.update(DISPLAY=app_display(XDISP), EXPLORER_TERMINAL_KEYS="0")
    p = subprocess.run([sys.executable, os.path.join(HERE, "panel_app.py"), str(cube)], env=env, capture_output=True,
                       text=True, timeout=120)
    steps = {s["step"]: s for s in (json.loads(x) for x in p.stdout.splitlines() if x.startswith("{"))}
    assert p.returncode == 0 and len(steps) == 4, f"exit {p.returncode}\n{p.stdout}\n{p.stderr[-3000:]}"
    print(json.dumps(steps))
    apart = {(name, n): (w["qt"], w["x"]) for name, s in steps.items() for n, w in s["windows"].items()
             if w["qt"] != w["x"]}
    assert not apart, apart
    assert {"spectrum", "lambda_t", "slit"} <= set(steps["slit"]["windows"]), steps["slit"]["windows"]
    before, after = steps["slit"]["windows"]["spectrum"]["qt"], steps["dragged"]["windows"]["spectrum"]["qt"]
    assert after == [before[0] + 8 * 30, before[1] + 3 * 30, *before[2:]], (before, after)
