"""The glass look on a zoomed window (ROADMAP E5.27), offscreen: maximised (as a Mac's green button leaves it, Qt's
maximised state), full screen, or zoomed by our title bar (a geometry). In glass the window leaves its zoom and keeps
the monitor's height at its left edge, the panels in their column on its right, nothing overlapping, all inside the
monitor; out of glass it is zoomed again, and the zoom's undo gives back the size it had before the zoom. On a Mac
the window kept the screen's width and the panels landed on it.

Zoomed in glass (a Mac's green button pressed there; full screen), the zoom stays across looks: out of glass the
window is zoomed, back in glass narrowed as above, out again zoomed, and the zoom's undo gives back the size from
before glass. Before, a zoom taken in glass was left on the way out: the window came back at its size from before
glass, and back in glass it kept that size.

Each case runs in its own process: a monitor of the Mac's size (1352 x 878 points), which Qt's offscreen platform
takes from a configuration file of its own (the tests' application has an 800 x 800 one, with no room beside it).

    python tests/unit/test_glass_zoomed.py <cube_im.fits> CASE   (one JSON line a step)
    CASE: maximised|fullscreen|titlebar (zoomed in classic), glass_maximised|glass_fullscreen (zoomed in glass)
"""
import json
import os
import subprocess
import sys
import time

import pytest

SCREEN = (1352, 878)                                    # the user's Mac, in points
START = (139, 87, 1073, 671)                            # the window's geometry before the zoom, from the user's trace


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    from explorer.testing import synth

    return synth.write_dataset(tmp_path_factory.mktemp("zoomed"), "c", shape=(4, 4, 11, 96, 80), icube=False)["im"]


def run(cube, case, tmp_path):
    conf = tmp_path / "screen.json"
    conf.write_text(json.dumps({"screens": [{"name": "mac", "x": 0, "y": 0, "width": SCREEN[0],
                                             "height": SCREEN[1], "logicalDpi": 96, "logicalBaseDpi": 96,
                                             "dpr": 1}]}))
    env = dict(os.environ, QT_QPA_PLATFORM=f"offscreen:configfile={conf}", EXPLORER_TERMINAL_KEYS="0",
               XDG_CONFIG_HOME=str(tmp_path))
    env.pop("DISPLAY", None)
    p = subprocess.run([sys.executable, os.path.abspath(__file__), str(cube), case], capture_output=True, text=True,
                       env=env, timeout=120)
    steps = {s["step"]: s for s in (json.loads(x) for x in p.stdout.splitlines() if x.startswith("{"))}
    assert p.returncode == 0 and steps, f"exit {p.returncode}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr[-4000:]}"
    return steps


def inside(r, m) -> bool:
    x, y, w, h = r
    mx, my, mw, mh = m
    return x >= mx and y >= my and x + w <= mx + mw and y + h <= my + mh


def meets(a, b) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


@pytest.mark.parametrize("case", ["maximised", "fullscreen", "titlebar"])
def test_a_zoomed_window_in_glass_leaves_room_for_the_panels_and_is_zoomed_again_out_of_it(cube, case, tmp_path):
    from explorer.ui.glass import FLOAT_W

    s = run(cube, case, tmp_path)
    zoomed, g, back, undone = s["zoomed"], s["glass"], s["classic"], s["undone"]
    print(case, json.dumps(s))
    m = g["monitor"]
    assert zoomed["frame"][2] >= m[2] - 2, f"not zoomed to begin with: {zoomed}"
    # in glass: out of the zoom, the window at the monitor's left edge and height, the panels beside it
    assert not g["zoomed"] and g["unzoomed"] is None, g
    assert inside(g["frame"], m), f"the window {g['frame']} is off its monitor {m}"
    fx, fy, fw, fh = g["frame"]
    assert (fx, fy) == (m[0], m[1]) and abs(fh - m[3]) <= 1, f"the window {g['frame']} on the monitor {m}"
    assert fw <= m[2] - FLOAT_W, g
    for name, d in g["docks"].items():
        assert d["floating"] and d["visible"], (name, d)
        assert not meets(d["frame"], g["frame"]), f"{name} {d['frame']} on the window {g['frame']}"
        assert d["frame"][0] >= fx + fw and d["frame"][0] + d["frame"][2] <= m[0] + m[2], (name, d, m)
    # out of glass: zoomed again, as it was
    assert back["state"] == zoomed["state"] and back["frame"] == zoomed["frame"], dict(back=back, zoomed=zoomed)
    assert back["unzoomed"] == zoomed["unzoomed"], dict(back=back, zoomed=zoomed)
    # and the zoom's undo gives back the window from before the zoom
    assert undone["geometry"] == list(START) and not undone["zoomed"], undone


@pytest.mark.parametrize("case", ["glass_maximised", "glass_fullscreen", "glass_started_maximised"])
def test_a_zoom_taken_in_glass_stays_out_of_it_and_back_in_it(cube, case, tmp_path):
    """glass_started: the window shown in glass (the last session closed in it), so that the other look starts
    afresh at the first window's size (docks.first_geometry, no saved layout here): the zoom's undo gives that."""
    from explorer.ui.glass import FLOAT_W

    s = run(cube, case, tmp_path)
    zoomed, out, g, back, undone = s["zoomed"], s["classic"], s["glass"], s["classic2"], s["undone"]
    print(case, json.dumps(s))
    m = zoomed["monitor"]
    assert zoomed["zoomed"] and zoomed["frame"][2] >= m[2] - 2, f"not zoomed in glass to begin with: {zoomed}"
    # out of glass: zoomed as it was in glass
    assert out["zoomed"] and out["state"] == zoomed["state"], dict(out=out, zoomed=zoomed)
    assert out["frame"][2] >= m[2] - 2 and out["frame"][3] >= m[3] - 2, out
    # back in glass: narrowed beside the panels, as a window zoomed in another look
    assert not g["zoomed"] and g["unzoomed"] is None, g
    fx, fy, fw, fh = g["frame"]
    assert inside(g["frame"], m) and (fx, fy) == (m[0], m[1]) and abs(fh - m[3]) <= 1, (g["frame"], m)
    assert fw <= m[2] - FLOAT_W, g
    for name, d in g["docks"].items():
        assert d["floating"] and d["visible"] and not meets(d["frame"], g["frame"]), (name, d, g["frame"])
    # out again: zoomed as the first time
    assert back["state"] == out["state"] and back["frame"] == out["frame"], dict(back=back, out=out)
    # and the zoom's undo gives back the window from before glass, or the other look's first one
    assert undone["geometry"] == undone["before"] and not undone["zoomed"], undone


# ---------------------------------------------------------------- the case, in its own process
def main() -> int:
    from PySide6 import QtCore, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.platform.display import Display
    from explorer.platform.plan import DisplayPlan
    from explorer.platform.screens import monitor_rect
    from explorer.ui import docks
    from explorer.ui.shell import Shell

    zoom = QtCore.Qt.WindowState.WindowMaximized | QtCore.Qt.WindowState.WindowFullScreen

    cube, case = sys.argv[1], sys.argv[2]
    app = QtWidgets.QApplication([])
    ds = Dataset.open(cube)
    w = Shell(ds, title="c_im.fits")
    disp = Display(DisplayPlan("offscreen"))
    w.window_ops = ops = disp.ops(w)
    if case == "titlebar":                              # our title bar and edges, as ui.app.start puts them on
        from explorer.ui import app as appmod
        from explorer.ui import titlebar

        titlebar.wanted = lambda *a, **k: True          # a local Mac keeps its own
        appmod.chrome(app, w, ops, disp.ops, bridge=False)
    w.setGeometry(*START)
    if case.startswith("glass_started"):               # glass worn before the window is shown (the last session
        w.set_look(get_look("glass"))                   # closed in glass): out of it, the other look starts afresh
    w.show()

    def spin(until=lambda: False, timeout=1.0):
        end = time.perf_counter() + timeout
        while not until() and time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.002)
        return until()

    def rect(r):
        return [r.x(), r.y(), r.width(), r.height()]

    # the window's size under the zoom: START, or out of a glass worn before the window was shown, the other look's
    # first one (no saved layout here)
    started = case.startswith("glass_started")
    before = rect(docks.first_geometry(app, getattr(w, "images", 1))) if started else list(START)

    def step(name):
        print(json.dumps(dict(
            step=name, before=before, state=int(w.windowState().value), zoomed=bool(w.windowState() & zoom),
            frame=rect(w.frameGeometry()), geometry=rect(w.geometry()), normal=rect(w.normalGeometry()),
            monitor=rect(monitor_rect(app, w.frameGeometry().center())),
            unzoomed=rect(ops.unzoomed) if ops.unzoomed is not None else None,
            docks={d.objectName(): dict(floating=d.isFloating(), visible=d.isVisible(), frame=rect(d.frameGeometry()))
                   for d in (w.spec_dock, w.lt_dock)})), flush=True)

    assert spin(lambda: w.first_image_s is not None and "lambda_t" in w.last, timeout=20)
    if case.startswith("glass_"):                       # zoomed in glass; then classic, glass, classic
        if w.glass is None:
            w.set_look(get_look("glass"))
        assert spin(lambda: all(d.isFloating() and d.isVisible() for d in (w.spec_dock, w.lt_dock)), timeout=10)
        spin()
        (w.showFullScreen if case.endswith("fullscreen") else w.showMaximized)()
        spin()
        step("zoomed")
        for name, look in (("classic", "classic"), ("glass", "glass"), ("classic2", "classic")):
            w.set_look(get_look(look))
            if look == "glass":
                assert spin(lambda: all(d.isFloating() and d.isVisible() for d in (w.spec_dock, w.lt_dock)),
                            timeout=10)
            spin()
            step(name)
        w.showNormal()
        spin()
        step("undone")
        w.close()
        ds.close()
        return 0
    {"maximised": w.showMaximized, "fullscreen": w.showFullScreen, "titlebar": ops.zoom}[case]()
    spin()
    step("zoomed")
    w.set_look(get_look("glass"))
    assert spin(lambda: all(d.isFloating() and d.isVisible() for d in (w.spec_dock, w.lt_dock)), timeout=10)
    spin()
    step("glass")
    w.set_look(get_look("classic"))
    spin()
    step("classic")
    {"maximised": w.showNormal, "fullscreen": w.showNormal, "titlebar": ops.zoom}[case]()
    spin()
    step("undone")
    w.close()
    ds.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
