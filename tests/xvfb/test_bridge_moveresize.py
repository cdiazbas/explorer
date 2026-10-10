"""Moving and resizing by explorer's own title bar and edges, through the bridge, handed to the window manager when it
says it can (EWMH _NET_WM_MOVERESIZE in _NET_SUPPORTED), as Qt's xcb does with startSystemMove: GNOME and KDE then
also snap the window to the screen's edges and halves (ROADMAP E6.11). Where it cannot (XQuartz's quartz-wm, no
manager) the title bar and the edges move and resize the window themselves, as before.

The manager is fake_moveresize_wm.py, another client: it reports the message it gets and whether its grab of the
pointer was granted (the press's implicit grab must be released first). The pointer is X's own, through XTEST.

    EXPLORER_TEST_XDISPLAY=:99 XAUTHORITY=<cookie> pytest tests/xvfb/test_bridge_moveresize.py
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time

import pytest
from test_bridge_xvfb import fake
from xlinkenv import app_display

XDISP = os.environ.get("EXPLORER_TEST_XDISPLAY")
pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")
HERE = os.path.dirname(os.path.abspath(__file__))
MOVE, RIGHT = 8, 3                                      # EWMH directions


class Lines:
    """A process's JSON lines, read on a thread: next(timeout) or None when none came."""

    def __init__(self, p):
        self.p, self.q = p, queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            self.q.put(line.strip())

    def next(self, timeout=20.0):
        try:
            line = self.q.get(timeout=timeout)
        except queue.Empty:
            return None
        return json.loads(line) if line.startswith("{") else line


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    from explorer.testing import synth

    return synth.write_dataset(tmp_path_factory.mktemp("xbmr"), "c", shape=(3, 4, 5, 96, 80), icube=False)["im"]


@pytest.fixture
def x():
    from Xlib import display

    d = display.Display(XDISP)
    yield d
    d.close()


def manager(*args):
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "fake_moveresize_wm.py"), *args],
                         stdout=subprocess.PIPE, env=dict(os.environ, DISPLAY=XDISP), text=True)
    lines = Lines(p)
    first = lines.next(10)
    if first != "ready":
        p.kill()
        pytest.skip(f"the manager did not start: {first!r}")
    return p, lines


class TitleApp:
    def __init__(self, cube):
        env = {k: v for k, v in os.environ.items() if k not in ("QT_QPA_PLATFORM", "EXPLORER_X11")}
        env.update(DISPLAY=app_display(XDISP), EXPLORER_TERMINAL_KEYS="0")
        self.p = subprocess.Popen([sys.executable, os.path.join(HERE, "titlebar_app.py"), str(cube)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, text=True)
        self.lines = Lines(self.p)
        self.hello = self.lines.next(60)
        assert isinstance(self.hello, dict) and self.hello.get("ready"), self.hello

    def __call__(self, cmd):
        self.p.stdin.write(cmd + "\n")
        self.p.stdin.flush()
        return self.lines.next()

    def close(self):
        if self.p.poll() is None:
            try:
                self("quit")
            except OSError:
                pass
            try:
                self.p.wait(10)
            except subprocess.TimeoutExpired:
                self.p.kill()


def stop(p):
    p.terminate()
    try:
        p.wait(5)
    except subprocess.TimeoutExpired:
        p.kill()


def press_and_release(x, at, drag=(0, 0), between=None):
    """XTEST: the pointer to at, the left button pressed, moved by drag in steps, released. between(): called while the
    button is down."""
    from Xlib import X

    fake(x, None, xy=at)
    time.sleep(0.2)
    fake(x, X.ButtonPress, 1)
    time.sleep(0.3)
    if between is not None:
        between()
    for k in range(1, 5):
        fake(x, None, xy=(at[0] + drag[0] * k // 4, at[1] + drag[1] * k // 4))
        time.sleep(0.05)
    time.sleep(0.2)
    fake(x, X.ButtonRelease, 1)
    time.sleep(0.3)
    fake(x, None, xy=(at[0] + drag[0] + 5, at[1] + drag[1] + 5))         # a move after it, no button down
    time.sleep(0.3)


def test_the_title_bar_and_an_edge_hand_the_drag_to_a_manager_that_can(cube, x):
    wm, said = manager()
    app = None
    try:
        app = TitleApp(cube)
        h = app.hello
        assert h["bar_edges"] == 0 and h["edge_edges"] == 4, h        # the bar's middle, the right edge
        got: list = []
        press_and_release(x, h["bar"], (60, 40), between=lambda: got.append(said.next(5)))
        msg = got[0]
        assert msg is not None, "no _NET_WM_MOVERESIZE reached the manager"
        assert msg["window"] == h["xid"], msg
        assert msg["data"] == [*h["bar"], MOVE, 1, 1], msg               # root x, y, direction, button, source
        assert msg["grab"] == "Success", f"the manager could not take the pointer: {msg['grab']}"
        assert said.next(5) == {"released": 1, "root": [h["bar"][0] + 60, h["bar"][1] + 40]}
        st = app("state")
        # the manager here moves nothing: the bar did not move the window itself, and Qt holds no button
        assert st["geometry"] == h["geometry"], st
        assert st["buttons"] == 0 and not st["bar_drag"], st

        got.clear()
        press_and_release(x, h["edge"], (50, 0), between=lambda: got.append(said.next(5)))
        msg = got[0]
        assert msg is not None and msg["data"] == [*h["edge"], RIGHT, 1, 1] and msg["grab"] == "Success", msg
        assert said.next(5) == {"released": 1, "root": [h["edge"][0] + 50, h["edge"][1]]}
        st = app("state")
        assert st["geometry"] == h["geometry"] and st["buttons"] == 0 and not st["edge_drag"], st
    finally:
        if app is not None:
            app.close()
        stop(wm)


def test_without_the_manager_saying_so_the_title_bar_moves_the_window_itself(cube, x):
    wm, said = manager("--unsupported")
    app = None
    try:
        app = TitleApp(cube)
        h = app.hello
        press_and_release(x, h["bar"], (60, 40))
        assert said.next(1) is None, "a message went to a manager that does not offer _NET_WM_MOVERESIZE"
        gx, gy, gw, gh = h["geometry"]
        st = app("state")
        assert st["geometry"] == [gx + 60, gy + 40, gw, gh], st
        assert st["buttons"] == 0 and not st["bar_drag"], st
    finally:
        if app is not None:
            app.close()
        stop(wm)
