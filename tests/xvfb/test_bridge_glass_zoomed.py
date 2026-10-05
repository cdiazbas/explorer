"""The glass look on a zoomed window through the bridge, under the quartz-like manager (fake_quartzwm.py, ROADMAP
E5.27): in glass the window leaves its zoom and keeps the monitor's height at its left edge, the panels beside it,
nothing overlapping, all inside the monitor, on the X server as in Qt; out of glass it is zoomed again. Maximised (a
window manager's maximise, which the bridge follows; a Mac's green button gives Qt the same state), the window kept
the monitor's width in glass and the panels landed on it. A module of its own: one manager at a time.

    EXPLORER_TEST_XDISPLAY=:99 XAUTHORITY=<cookie> pytest tests/xvfb/test_bridge_glass_zoomed.py
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

    return synth.write_dataset(tmp_path_factory.mktemp("xbzoom"), "c", shape=(3, 4, 5, 96, 80), icube=False)["im"]


@pytest.fixture(scope="module")
def wm():
    env = dict(os.environ, DISPLAY=XDISP)
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "fake_quartzwm.py")], stdout=subprocess.PIPE,
                         env=env, text=True)
    line = p.stdout.readline().strip()
    if line != "ready":
        p.wait(5)
        pytest.skip(f"the quartz-like manager did not start: {line!r} (exit {p.poll()})")
    yield p
    p.terminate()
    p.wait(5)


def run(cube, case):
    env = {k: v for k, v in os.environ.items() if k not in ("QT_QPA_PLATFORM", "EXPLORER_X11")}
    env.update(DISPLAY=app_display(XDISP), EXPLORER_TERMINAL_KEYS="0")
    p = subprocess.run([sys.executable, os.path.join(HERE, "glass_zoom_app.py"), str(cube), case], env=env,
                       capture_output=True, text=True, timeout=120)
    steps = {s["step"]: s for s in (json.loads(x) for x in p.stdout.splitlines() if x.startswith("{"))}
    assert p.returncode == 0 and len(steps) == 3, f"exit {p.returncode}\n{p.stdout}\n{p.stderr[-3000:]}"
    print(case, json.dumps(steps))
    return steps


def inside(r, m) -> bool:
    return r[0] >= m[0] and r[1] >= m[1] and r[0] + r[2] <= m[0] + m[2] and r[1] + r[3] <= m[1] + m[3]


def meets(a, b) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


@pytest.mark.parametrize("case", ["maximised", "titlebar"])
def test_a_zoomed_window_in_glass_leaves_room_for_the_panels_on_x_too(cube, wm, case):
    s = run(cube, case)
    zoomed, g, back = s["zoomed"], s["glass"], s["classic"]
    m = g["monitor"]
    assert zoomed["x"][2] >= m[2] - 2, f"not zoomed to begin with: {zoomed}"
    assert not g["zoomed"] and g["unzoomed"] is None, g
    assert g["x"] == g["frame"], f"X has the window at {g['x']}, Qt at {g['frame']}"
    assert inside(g["x"], m) and g["x"][:2] == m[:2] and abs(g["x"][3] - m[3]) <= 1, (g["x"], m)
    for name, d in g["docks"].items():
        assert d["floating"] and d["visible"] and d["x"] is not None, (name, d)
        assert d["x"][:2] == d["frame"][:2], (name, d)
        assert not meets(d["x"], g["x"]), f"{name} {d['x']} on the window {g['x']}"
        assert inside(d["x"], [m[0], m[1], m[2], 10 ** 5]), (name, d["x"], m)   # below a short monitor they go on
    assert back["zoomed"] == zoomed["zoomed"] and back["x"] == zoomed["x"], dict(back=back, zoomed=zoomed)
    assert back["unzoomed"] == zoomed["unzoomed"], dict(back=back, zoomed=zoomed)
