"""The slit's panel in glass (ROADMAP E7.4, the prototype's F84), offscreen: a third floating panel with the glass
skin; the three stacked beside the window 40/30/30 (look_glass.py:572), none over another nor over the window; S
puts it below lambda-t when the monitor has room there (look_glass.py:607-618); I hides and shows it with the others,
the reset button places it again; the slit button on the glass bar (look_glass.py:729-731), back in the toolbar out
of glass.

The geometry runs in its own process, on a monitor with room beside the window (1920 x 1200; the tests'
application has an 800 x 800 one, where the panels overlap the window):

    python tests/unit/test_slit_glass.py <cube_im.fits> enter|draw|room   (one JSON line a step)
"""
import json
import os
import subprocess
import sys
import time

import pytest

SCREEN = (1920, 1200)
SHAPE = (3, 4, 5, 60, 48)                               # t, s, lambda, y, x
A = ((6.5, 8.5), (40.5, 50.5))


def spin(qapp, until=lambda: False, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    from explorer.testing import synth

    return synth.write_dataset(tmp_path_factory.mktemp("slitglass"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube):
    import pyqtgraph as pg
    from PySide6 import QtGui, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui import style
    from explorer.ui.shell import Shell

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    ds = Dataset.open(cube)
    w = Shell(ds, title="c_im.fits")
    w.setGeometry(60, 50, 1000, 700)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and "lambda_t" in w.last)
    w.set_look(get_look("glass"))
    assert spin(qapp, lambda: w.spec_dock.isFloating() and w.lt_dock.isFloating())
    yield w
    w.close()
    ds.close()
    qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
    qapp.setPalette(pal)
    qapp.setProperty("explorer_light", False)
    pg.setConfigOptions(background="k", foreground="d")


def make(qapp, w):
    w.set_slit_mode(True)
    for x, y in A:
        w.slit_tool.add(x, y)
    w.slit_tool.finish()
    assert spin(qapp, lambda: w.slit_dock.isFloating() and w.slit_dock.isVisible())


def overlaps(docks):
    return [(a.objectName(), b.objectName()) for i, a in enumerate(docks) for b in docks[i + 1:]
            if a.frameGeometry().intersects(b.frameGeometry())]


def test_the_slit_button_is_on_the_glass_bar_and_back_in_the_toolbar_out_of_it(qapp, shell):
    from explorer.look import get_look

    w = shell
    g, b = w.glass, w.nav.slit
    assert g.bar.isAncestorOf(b) and b.isVisible() and b in g._sheets            # flat on the glass, as its row's
    row = [g._rows[0].itemAt(i).widget() for i in range(g._rows[0].count())]
    assert row.index(b) == row.index(w.nav.panels) - 1                          # before Panels (look_glass.py:729)
    b.click()
    assert w.slit_tool.mode and b.isChecked()
    b.click()
    assert not w.slit_tool.mode
    w.set_look(get_look("classic"))
    spin(qapp, timeout=0.2)
    assert w.nav.tb.isAncestorOf(b) and b.isVisible() and b.styleSheet() == ""


def test_the_slit_panel_wears_the_glass_skin_and_three_panels_do_not_overlap(qapp, shell):
    from explorer.ui.glass import PanelTitle

    w = shell
    make(qapp, w)
    assert w.slit_dock in [s.d for s in w.glass.skins]
    assert isinstance(w.slit_dock.titleBarWidget(), PanelTitle)
    three = [w.spec_dock, w.lt_dock, w.slit_dock]
    assert all(d.isFloating() and d.isVisible() for d in three)
    assert not overlaps(three), [d.frameGeometry().getRect() for d in three]


def test_panels_hides_and_shows_the_slits_panel_as_the_others_and_reset_places_it_again(qapp, shell):
    w = shell
    make(qapp, w)
    three = [w.spec_dock, w.lt_dock, w.slit_dock]
    for d in three:                                     # Panels → each entry
        d.toggleViewAction().trigger()
    assert all(d.isHidden() for d in three)
    for d in three:
        d.toggleViewAction().trigger()
    assert not any(d.isHidden() for d in three)
    w.slit_dock.close()                                 # its own close button
    w.reset_panels()
    spin(qapp, timeout=0.2)
    assert all(d.isVisible() and d.isFloating() for d in three) and not overlaps(three)
    assert w.slit_dock.width() == w.lt_dock.width() and w.slit_dock.x() == w.lt_dock.x()


# ---------------------------------------------------------------- the geometry, on a monitor with room
def run(cube, case, tmp_path):
    conf = tmp_path / "screen.json"
    conf.write_text(json.dumps({"screens": [{"name": "wide", "x": 0, "y": 0, "width": SCREEN[0],
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


def meets(a, b) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


@pytest.mark.parametrize("case", ["enter", "draw"])
def test_three_panels_beside_the_window_40_30_30(cube, case, tmp_path):
    """enter: a slit drawn in classic, then glass; draw: drawn in glass, no room below lambda-t."""
    from explorer.ui.glass import FLOAT_W, GAP

    s = run(cube, case, tmp_path)["three"]
    print(case, json.dumps(s))
    win, d = s["window"], s["docks"]
    order = [d[k]["frame"] for k in ("spectrum", "lambda_t", "slit")]
    assert all(d[k]["floating"] and d[k]["visible"] and d[k]["skin"] for k in d), d
    avail = win[3] - 2 * GAP
    want = [int(avail * f) for f in (0.40, 0.30, 0.30)]
    assert [f[3] for f in order] == want, ([f[3] for f in order], want, win)
    x = win[0] + win[2] - 1 + GAP                                       # GAP right of the window's right edge
    assert all(f[0] == x and f[2] == FLOAT_W for f in order), (order, win)
    assert order[0][1] == win[1]
    assert [b[1] - (a[1] + a[3]) for a, b in zip(order, order[1:], strict=False)] == [GAP, GAP], order
    for f in order:
        assert not meets(f, win), (f, win)


def test_with_room_below_lambda_t_the_slits_panel_goes_there(cube, tmp_path):
    from explorer.ui.glass import FLOAT_W, GAP
    from explorer.ui.shell import SLIT_FLOAT_H

    s = run(cube, "room", tmp_path)["three"]
    print(json.dumps(s))
    lt, sl = s["docks"]["lambda_t"]["frame"], s["docks"]["slit"]["frame"]
    assert sl == [lt[0], lt[1] + lt[3] - 1 + GAP, FLOAT_W, SLIT_FLOAT_H], (lt, sl)
    assert sl[1] + sl[3] <= SCREEN[1]


# ---------------------------------------------------------------- the case, in its own process
def main() -> int:
    from PySide6 import QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.platform.screens import monitor_rect
    from explorer.ui.shell import Shell

    cube, case = sys.argv[1], sys.argv[2]
    app = QtWidgets.QApplication([])
    ds = Dataset.open(cube)
    w = Shell(ds, title="c_im.fits")
    # tall enough that 40 % of it is more than the spectra's least height (glass.FLOAT_MIN_H); "room": short enough
    # that the slit's panel fits below lambda-t
    w.setGeometry(40, 40, 1000, 640 if case == "room" else 1100)
    w.show()

    def wait(until=lambda: False, timeout=1.0):
        end = time.perf_counter() + timeout
        while not until() and time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.002)
        return until()

    def rect(r):
        return [r.x(), r.y(), r.width(), r.height()]

    def slit():
        w.set_slit_mode(True)
        for x, y in A:
            w.slit_tool.add(x, y)
        w.slit_tool.finish()

    three = (w.spec_dock, w.lt_dock, w.slit_dock)

    def step(name):
        skins = [s.d for s in w.glass.skins] if w.glass is not None else []
        print(json.dumps(dict(
            step=name, window=rect(w.frameGeometry()), monitor=rect(monitor_rect(app, w.frameGeometry().center())),
            docks={d.objectName(): dict(floating=d.isFloating(), visible=d.isVisible(), frame=rect(d.frameGeometry()),
                                        skin=d in skins) for d in three})), flush=True)

    assert wait(lambda: w.first_image_s is not None and "lambda_t" in w.last, timeout=20)
    if case == "enter":
        slit()
        assert wait(lambda: not w.slit_dock.isHidden(), timeout=5)
    w.set_look(get_look("glass"))
    assert wait(lambda: w.spec_dock.isFloating() and w.lt_dock.isFloating(), timeout=10)
    wait()
    if case != "enter":
        slit()
    assert wait(lambda: all(d.isFloating() and d.isVisible() for d in three), timeout=10)
    wait()
    step("three")
    w.close()
    ds.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
