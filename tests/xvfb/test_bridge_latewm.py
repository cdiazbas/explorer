"""The bridge under the quartz-like manager (fake_quartzwm.py) telling each window's first geometry late, as quartz-wm
through ssh -Y to a Mac: the notice of a geometry the bridge asked for before its last request is an echo, not where
the window is (ROADMAP E6.14). A module of its own: one manager at a time, and test_bridge_quartzwm.py keeps its own
for the whole module.

    EXPLORER_TEST_XDISPLAY=:99 XAUTHORITY=<cookie> pytest tests/xvfb/test_bridge_latewm.py
"""
import os
import subprocess
import sys

import pytest
from test_bridge_quartzwm import HERE, XDISP

pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    from explorer.testing import synth

    return synth.write_dataset(tmp_path_factory.mktemp("xblate"), "c", shape=(3, 4, 5, 96, 80), icube=False)["im"]


def _manager(*args):
    env = dict(os.environ, DISPLAY=XDISP)
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "fake_quartzwm.py"), *args],
                         stdout=subprocess.PIPE, env=env, text=True)
    line = p.stdout.readline().strip()
    if line != "ready":
        p.wait(5)
        pytest.skip(f"the quartz-like manager did not start: {line!r} (exit {p.poll()})")
    return p


@pytest.fixture
def late_wm():
    """The manager with the notice of each window's first geometry 300 ms late, as through ssh -Y to a Mac."""
    p = _manager("--late", "300")
    yield p
    p.terminate()
    p.wait(5)


@pytest.fixture
def late_mixed_wm():
    """The same, the notice with the window's first place and the size it has by then."""
    p = _manager("--late", "300", "--mixed")
    yield p
    p.terminate()
    p.wait(5)


def _glass_switch(cube):
    import json

    env = {k: v for k, v in os.environ.items() if k not in ("QT_QPA_PLATFORM", "EXPLORER_X11")}
    env.update(DISPLAY=XDISP, EXPLORER_TERMINAL_KEYS="0")
    p = subprocess.run([sys.executable, os.path.join(HERE, "glass_switch_app.py"), str(cube)], env=env,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    r = json.loads(p.stdout.strip().splitlines()[-1])
    print("after classic -> glass:", r)
    return r


def test_glass_panels_stay_placed_when_the_manager_tells_their_first_place_late(cube, late_wm):
    """Seen from bellatrix through ssh -Y (2026-10-04, a geometry trace): M into glass, the panels placed beside the
    window, then 230 ms later quartz-wm's notice of the geometry a panel's X window was created with, and the bridge
    took it as new: the spectrum went back to where Qt had first floated it. A notice of a geometry the bridge asked
    for before its last request is an echo, the one it created the window with included."""
    from explorer.ui.glass import GAP

    r = _glass_switch(cube)
    assert r["spec_qt"] == r["spec_x"], r
    assert r["spec_qt"] == [r["main_right"] + GAP, r["main"][1]], r


def test_glass_panels_stay_placed_when_the_late_notice_has_their_first_place_and_new_size(cube, late_mixed_wm):
    """Seen from bellatrix through ssh -Y (2026-10-04, a geometry trace): the first M into glass, the panels placed
    beside the window, then 1.8 s later XQuartz's notice of the place each was first floated at with the size asked
    after it, a geometry never asked for as a whole: the bridge took it and the panels went back (the second time
    Qt had their place already). The glass look now makes a panel's window where it goes."""
    from explorer.ui.glass import GAP

    r = _glass_switch(cube)
    assert r["spec_qt"] == r["spec_x"], r
    assert r["spec_qt"] == [r["main_right"] + GAP, r["main"][1]], r
