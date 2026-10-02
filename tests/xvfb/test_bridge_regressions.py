"""Fixes of the prototype's bridge, ported to explorer's and checked here against a real X server (ROADMAP E6.6, the
prototype's audit in its docs/AUDIT_COHERENCE.md): two floating panels drawn as Qt draws them (F29), a panel that
grows shown whole (F23a), Qt's cursor on the X windows (F20d), glass's rounded panels (F85), and the end when the
X display goes away (F32).

    EXPLORER_TEST_XDISPLAY=:99 XAUTHORITY=<cookie> pytest tests/xvfb/test_bridge_regressions.py

F32 starts an X server of its own (Xvfb on the PATH, or EXPLORER_TEST_XVFB), as it kills it. Minimising under
quartz-wm (F20h) is not reproduced: no manager here iconifies as it does.
"""
import os
import shutil
import signal
import subprocess
import sys
import time

import pytest
from test_bridge_xvfb import HERE, SHAPE, App, fake, main_window, same_as_qt, wait

from explorer.testing import synth

XDISP = os.environ.get("EXPLORER_TEST_XDISPLAY")
pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("xbreg"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture(scope="module")
def x():
    from Xlib import display

    d = display.Display(XDISP)
    yield d
    d.close()


@pytest.fixture
def app(cube):
    a = App(cube)
    yield a
    a.close()


def test_two_floating_panels_are_drawn_as_qt_draws_them(x, app):
    """F29: with two panels floating, the prototype's second panel lost requests in python-xlib's flush and showed
    stale pixels; explorer's client sends the whole buffer. Each panel's X pixels are Qt's."""
    docks = app("float")["docks"]
    assert app("idle")["idle"]
    wins = {w["title"]: w for w in app("state")["windows"]}
    seen = {}
    for name, title in (("spectrum", "Spectrum"), ("lambda_t", "λ–t")):
        assert title in wins, dict(want=title, windows=sorted(wins), docks=docks)
        bad, shape = same_as_qt(x, app, wins[title]["xid"], name)
        seen[name] = dict(differing=bad, shape=shape, geometry=wins[title]["geometry"])
    assert all(v["differing"] == 0 for v in seen.values()), seen


def test_a_panel_that_grows_is_shown_whole(x, app):
    """F23a: a shape the size of the window, published once, kept the window that size when it grew. Without a mask
    no shape is set, and one set before is taken off: the grown panel is shown whole, its pixels Qt's."""
    from Xlib.ext import shape

    app("panel")
    app("mask")                                         # an ellipse, then none again
    app("unmask")
    got = app("grow 400 300")
    assert app("idle")["idle"]
    pw = next(w for w in app("state")["windows"] if w["title"] == "panel λ–t")
    win = x.create_resource_object("window", pw["xid"])
    rects = [(r.x, r.y, r.width, r.height) for r in win.shape_get_rectangles(shape.SK.Bounding).rectangles]
    assert rects == [(0, 0, 400, 300)], dict(rectangles=rects, panel=got)
    bad, size = same_as_qt(x, app, pw["xid"], "panel")
    assert bad == 0, dict(differing=bad, size=size)


def test_qts_cursor_is_on_the_x_window(x, app):
    """F20d: Qt's cursor (its application override, else the widget's) is copied to the X windows as a cursor-font
    glyph; the prototype's showed the arrow whatever Qt set. A wait cursor of Qt's changes the one X shows, and
    taking it away brings the other back."""
    x.xfixes_query_version()
    mw = main_window(app)
    gx, gy, gw, gh = mw["geometry"]
    fake(x, None, xy=(gx + gw // 3, gy + gh // 2))      # over the image
    assert app("idle")["idle"]

    def cursor():
        c = x.xfixes_get_cursor_image(x.screen().root)
        return (c.width, c.height, c.xhot, c.yhot, hash(tuple(c.cursor_image)))
    before = cursor()
    app("override wait")
    waiting = wait(lambda: cursor() != before and cursor(), 3.0)
    app("override none")
    after = wait(lambda: cursor() == before and cursor(), 3.0)
    assert waiting and after, dict(before=before, with_wait=cursor() if not waiting else waiting, after=after)


def test_glass_panels_have_rounded_corners_on_the_x_server(x, app):
    """F85: glass's floating panels are rounded slabs; on X the shape (the bridge publishes the panel's region) leaves
    the corners out, so the desktop shows there and not a square of the panel's background."""
    from Xlib.ext import shape

    app("look glass")
    try:
        titles = ("Spectrum", "λ–t")
        assert wait(lambda: len([w for w in app("state")["windows"] if w["title"] in titles]) == 2, 10)
        assert app("idle")["idle"]
        seen = {}
        for w in (w for w in app("state")["windows"] if w["title"] in titles):
            win = x.create_resource_object("window", w["xid"])
            rects = [(r.x, r.y, r.width, r.height) for r in win.shape_get_rectangles(shape.SK.Bounding).rectangles]
            _x, _y, ww, wh = w["geometry"]
            corners = [(0, 0), (ww - 1, 0), (0, wh - 1), (ww - 1, wh - 1)]
            covered = [c for c in corners if any(rx <= c[0] < rx + rw and ry <= c[1] < ry + rh
                                                  for rx, ry, rw, rh in rects)]
            seen[w["title"]] = dict(rectangles=len(rects), corners_in_shape=covered, size=(ww, wh))
        assert all(v["rectangles"] > 1 and not v["corners_in_shape"] for v in seen.values()), seen
    finally:
        app("look classic")


def test_when_the_display_goes_away_it_says_so_and_exits_1(cube, tmp_path):
    """F32: the prototype went on at 79 % CPU, a traceback per tick, when XQuartz quit or ssh was cut. Explorer says
    so once, closes its windows and exits 1."""
    xvfb = os.environ.get("EXPLORER_TEST_XVFB") or shutil.which("Xvfb")
    if not xvfb:
        pytest.skip("no Xvfb to start and kill (EXPLORER_TEST_XVFB or on the PATH)")
    disp = ":" + str(70 + os.getpid() % 20)
    server = subprocess.Popen([xvfb, disp, "-screen", "0", "1280x800x24", "-nolisten", "tcp"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait(lambda: os.path.exists(f"/tmp/.X11-unix/X{disp[1:]}"), 10), f"no X server at {disp}"
        env = dict(os.environ, DISPLAY=disp)
        env.pop("QT_QPA_PLATFORM", None)
        env.pop("XAUTHORITY", None)                     # this server takes anyone local
        p = subprocess.Popen([sys.executable, os.path.join(HERE, "bridge_app.py"), str(cube)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
        hello = p.stdout.readline()
        assert '"ready": true' in hello, dict(hello=hello, exit=p.poll())
        server.send_signal(signal.SIGTERM)
        t0 = time.perf_counter()
        try:
            code = p.wait(15)
        except subprocess.TimeoutExpired:
            p.kill()
            code = None
        err = p.stderr.read()
        assert code == 1, dict(exit=code, after_s=round(time.perf_counter() - t0, 1), stderr=err[-2000:])
        assert err.count("the X display went away") == 1, err[-2000:]
    finally:
        if server.poll() is None:
            server.kill()
