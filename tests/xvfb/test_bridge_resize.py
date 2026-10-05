"""An edge resize through the bridge under a manager that answers as quartz-wm does (fake_quartzwm_frames.py): one
resize is one size change in Qt, one request to X, one whole window sent, and the window ends where it was asked.

Through XQuartz (2026-10-05, a geometry and a bridge trace) every edge resize of the main window went back and forth
between the new size and the old one 2-4 times in 30-160 ms, sent whole at each size (5.7 MB for one resize to
1748x1013), and the window kept its old place: the bridge asked the move and the size apart, quartz-wm answered the
move with its record of the frame (the old place and size), the bridge took that and, resizing Qt before moving it,
asked X for the old size again. A module of its own: one manager at a time.

    EXPLORER_TEST_XDISPLAY=:99 XAUTHORITY=<cookie> pytest tests/xvfb/test_bridge_resize.py
"""
import json
import os
import subprocess
import sys
import threading

import pytest
from test_bridge_quartzwm import HERE, XDISP
from xlinkenv import app_display

pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    from explorer.testing import synth

    return synth.write_dataset(tmp_path_factory.mktemp("xbresize"), "c", shape=(3, 4, 5, 96, 80), icube=False)["im"]


@pytest.fixture
def wm():
    env = dict(os.environ, DISPLAY=XDISP)
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "fake_quartzwm_frames.py")], stdout=subprocess.PIPE,
                         env=env, text=True)
    line = p.stdout.readline().strip()
    if line != "ready":
        p.wait(5)
        pytest.skip(f"the quartz-like manager did not start: {line!r} (exit {p.poll()})")
    yield p
    p.terminate()
    p.wait(5)


class ResizeApp:
    def __init__(self, cube):
        env = {k: v for k, v in os.environ.items() if k not in ("QT_QPA_PLATFORM", "EXPLORER_X11")}
        env.update(DISPLAY=app_display(XDISP), EXPLORER_TERMINAL_KEYS="0")
        self.p = subprocess.Popen([sys.executable, os.path.join(HERE, "resize_app.py"), str(cube)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                                  text=True)

    def read(self, timeout=60):
        box: list = []
        th = threading.Thread(target=lambda: box.append(self.p.stdout.readline()), daemon=True)
        th.start()
        th.join(timeout)
        if not box or not box[0]:
            self.p.kill()
            raise AssertionError(f"no answer from resize_app (exit {self.p.poll()}): {self.p.stderr.read()[-3000:]}")
        return json.loads(box[0])

    def say(self, line):
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()

    def close(self):
        if self.p.poll() is None:
            self.p.kill()
        self.p.wait(10)


def on_x(xid):
    from Xlib import display

    d = display.Display(XDISP)
    try:
        win = d.create_resource_object("window", xid)
        t, g = win.translate_coords(d.screen().root, 0, 0), win.get_geometry()
        return [-t.x, -t.y, g.width, g.height]
    finally:
        d.close()


def test_an_edge_resize_is_one_size_change_and_one_whole_window(cube, wm):
    import time

    app = ResizeApp(cube)
    try:
        hello = app.read()
        assert hello.get("ready"), hello
        app.say("go 200 100")                           # the first resize: the second met the bridge's own mess
        first = app.read()["released"]
        time.sleep(1.5)
        app.say("go 150 100")
        asked = app.read()["released"]
        time.sleep(1.5)
        x = on_x(hello["xid"])
        app.say("report")
        r = app.read()
    finally:
        app.close()
    print("first", first, "asked", asked, "on X", x, json.dumps(r))
    seen = dict(sizes=[s[1:] for s in r["sizes"]], whole=[f[1:] for f in r["fresh"]], qt=r["final"], x=x,
                requests=r["delta"]["configures"])
    want = dict(sizes=[asked[2:]], whole=[asked[2:]], qt=asked, x=asked, requests=1)
    assert seen == want, seen
