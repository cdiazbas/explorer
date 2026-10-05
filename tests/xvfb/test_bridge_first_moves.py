"""The first moves of a window under a manager that validates frames as quartz-wm does (fake_quartzwm_frames.py
--validate, ROADMAP E6.14): a window asked for where no monitor is goes to the main monitor's corner, at the map and
at each move, and the bridge follows; once on a monitor, every move is where it was asked. Qt and X agree at every
step.

Through XQuartz (2026-10-03, three monitors in one X screen of 3067x1513) a window asked for at (200, 150) was put
at (1147, 22), and moves to (220, 160) and (240, 172) did not stick, the third one did: a 900-px window starting
left of x = 247 touched no monitor there. quartz-wm's validate_window_position (x-screen.m) moves such a frame onto
a monitor. The layout here is inferred from that screen's size and its laptop monitor's (1147x719), not read from it;
the second place XQuartz chose, (240, 790), this manager does not make.

    EXPLORER_TEST_XDISPLAY=:99 XAUTHORITY=<cookie> pytest tests/xvfb/test_bridge_first_moves.py
"""
import json
import os
import subprocess
import sys

import pytest
from test_bridge_quartzwm import HERE, XDISP
from xlinkenv import app_display

pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")
HEADS = [(1147, 0, 1920, 1080), (0, 794, 1147, 719)]    # the main monitor first; nothing at x < 1147, y < 794


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    from explorer.testing import synth

    return synth.write_dataset(tmp_path_factory.mktemp("xbfirst"), "c", shape=(3, 4, 5, 96, 80), icube=False)["im"]


@pytest.fixture
def wm():
    heads = ";".join(",".join(str(v) for v in h) for h in HEADS)
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "fake_quartzwm_frames.py"), "--validate", "--heads",
                          heads], stdout=subprocess.PIPE, env=dict(os.environ, DISPLAY=XDISP), text=True)
    line = p.stdout.readline().strip()
    if line != "ready":
        p.wait(5)
        pytest.skip(f"the quartz-like manager did not start: {line!r} (exit {p.poll()})")
    yield p
    p.terminate()
    p.wait(5)


def on_a_monitor(x, y, w=900, h=600) -> bool:
    return any(x < hx + hw and hx < x + w and y < hy + hh and hy < y + h for hx, hy, hw, hh in HEADS)


def test_a_window_on_no_monitor_goes_to_the_main_one_and_qt_follows(cube, wm):
    env = {k: v for k, v in os.environ.items() if k not in ("QT_QPA_PLATFORM", "EXPLORER_X11")}
    env.update(DISPLAY=app_display(XDISP), EXPLORER_TERMINAL_KEYS="0")
    p = subprocess.run([sys.executable, os.path.join(HERE, "first_moves_app.py"), str(cube), "200", "150", "20",
                        "12"], env=env, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-3000:]
    rows = json.loads(p.stdout.strip().splitlines()[-1])["rows"]
    print(json.dumps(rows))
    corner = list(HEADS[0][:2])
    want = [r["asked"] if on_a_monitor(*r["asked"]) else corner for r in rows]
    assert [r["x"] for r in rows] == want, rows
    assert [r["qt"] for r in rows] == want, rows
    assert [on_a_monitor(*r["asked"]) for r in rows] == [False, False, False, True, True, True, True], rows
