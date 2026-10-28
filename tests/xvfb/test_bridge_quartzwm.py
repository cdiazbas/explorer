"""The bridge under a window manager that frames as quartz-wm does (fake_quartzwm.py, ROADMAP E6.4): the floating
panels unframed, where Qt has them, and still. Through XQuartz a panel declared a utility window got the manager's
16-px strip over its own title and crept down 16 px at every round trip; panels floated before their
window was shown came out the same way. Xvfb alone has no manager, so the other X tests could not see it.

    EXPLORER_TEST_XDISPLAY=:99 XAUTHORITY=<cookie> pytest tests/xvfb/test_bridge_quartzwm.py

It starts the manager itself, on a display that has none.
"""
import os
import subprocess
import sys
import time

import pytest
from test_bridge_xvfb import App, wait

XDISP = os.environ.get("EXPLORER_TEST_XDISPLAY")
pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")
HERE = os.path.dirname(os.path.abspath(__file__))
PANELS = ("Spectrum", "λ–t")


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    from explorer.testing import synth

    return synth.write_dataset(tmp_path_factory.mktemp("xbqwm"), "c", shape=(3, 4, 5, 96, 80), icube=False)["im"]


@pytest.fixture(scope="module")
def x():
    from Xlib import display

    d = display.Display(XDISP)
    yield d
    d.close()


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


def panels(x, app):
    """Each floating panel: where Qt has it, where X has it on the root, and whether the manager framed it."""
    root = x.screen().root
    out = {}
    for w in app("state")["windows"]:
        if w["title"] in PANELS and not w["popup"]:
            win = x.create_resource_object("window", w["xid"])
            at = root.translate_coords(win, 0, 0)
            out[w["title"]] = dict(qt=tuple(w["geometry"][:2]), x=(at.x, at.y),
                                   framed=win.query_tree().parent.id != root.id)
    return out


def still_and_unframed(x, app, wm):
    assert wait(lambda: len(panels(x, app)) == 2, 10), app("state")["windows"]
    time.sleep(0.5)                                     # placed
    first = panels(x, app)
    time.sleep(1.5)                                     # a creep is 16 px per round trip: seen in this time
    second = panels(x, app)
    seen = dict(first=first, second=second, manager_alive=wm.poll() is None)
    assert not any(p["framed"] for p in second.values()), seen
    assert first == second, seen
    assert all(p["qt"] == p["x"] for p in second.values()), seen


def test_glass_panels_are_unframed_and_still_under_a_quartz_like_manager(x, cube, wm):
    app = App(cube)
    try:
        app("look glass")
        still_and_unframed(x, app, wm)
    finally:
        app.close()


def test_panels_floated_before_their_window_too(x, cube, wm):
    app = App(cube, "800x600", "--float-first")
    try:
        still_and_unframed(x, app, wm)
    finally:
        app.close()
