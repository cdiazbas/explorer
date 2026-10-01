"""The looks (ROADMAP E5.5), offscreen: which parts each has; the colour tables (grey exact, padding at level 0,
one map per Stokes, cycling); classic: the sliders in the cursor's red, the crosshair in its locked colour, rounded
panels, no colour keys; modern: the reticle instead of two lines, the Stokes segments in step with the state, C
recolouring image, lambda-t and key, the zero lines and the cards."""
import sys
import time

import numpy as np
import pytest

from explorer.testing import synth

SHAPE = (6, 4, 21, 48, 40)


def spin(qapp, until, timeout=5.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


def test_the_looks_and_their_parts():
    from explorer.look import PARTS, get_look

    assert get_look().name == "classic" and not get_look().parts
    assert get_look("modern", {}).parts == frozenset(PARTS)
    off = get_look("modern", {"EXPLORER_LOOK_OFF": "reticle, cards"})
    assert not off.has("reticle") and not off.has("cards") and off.has("colour")
    assert not get_look("modern", {"EXPLORER_LOOK_OFF": "colour"}).has("cmap")   # C needs the tables
    with pytest.raises(ValueError):
        get_look("baroque")


def test_the_colour_tables():
    from explorer.look import colormaps as cm

    assert cm.table("gray") is None
    lut = cm.table("CET-L1")
    assert lut.shape == (256, 3) and (lut[:, 0] == lut[:, 1]).all() and (lut[:, 1] == lut[:, 2]).all()
    had = "matplotlib" in sys.modules
    rd = cm.table("RdBu_r")                              # built here, matplotlib not needed
    assert tuple(rd[0]) != tuple(rd[255]) and (had or "matplotlib" not in sys.modules)
    t = cm.image_table(cm.table("CET-D4"), light=False)
    assert tuple(t[0]) == (0, 0, 0) and tuple(t[1]) == tuple(cm.table("CET-D4")[0])
    assert cm.image_table(None, light=False) is None and tuple(cm.image_table(None, light=True)[0]) == (255, 255, 255)
    reg = cm.ColormapRegistry(4)
    assert reg.maps == ["gray", "gray", "gray", "gray"]  # Q U V start in grey, the same scale as I
    assert reg.cycle(3, 1) == "CET-D4" and reg.maps[1] == "gray"       # one map per Stokes
    assert reg.cycle(0, -1) == cm.SEQUENTIAL[-1]
    n = len(reg.names_for(3))
    for _ in range(n - 1):
        reg.cycle(3, 1)
    assert reg.maps[3] == "gray"                         # round the list


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("look"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def themed(qapp):
    """The dark style on the application (the sliders' fill is its attribute), as it was after."""
    import pyqtgraph as pg
    from PySide6 import QtGui, QtWidgets

    from explorer.ui import style

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    yield qapp
    qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
    qapp.setPalette(pal)
    qapp.setProperty("explorer_light", False)
    pg.setConfigOptions(background="k", foreground="d")


def make(qapp, cube, name):
    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds, look=get_look(name, {}))
    w.resize(900, 600)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and "lambda_t" in w.last)
    return w, ds


def test_classic(themed, cube):
    from explorer.ui.imageview import CURSOR_PEN, LOCK_PEN

    w, ds = make(themed, cube, "classic")
    try:
        assert themed.style().SLIDER == CURSOR_PEN.color()            # the sliders in the markers' red
        assert w.view.reticle is None and w.view.hl.isVisible()
        w.session.lock(True)
        themed.processEvents()
        assert w.view.hl.pen.color() == LOCK_PEN.color()
        w.session.lock(False)
        themed.processEvents()
        assert w.view.hl.pen.color() == CURSOR_PEN.color()
        assert w.colours is None and w.colour_key is None and w.nav.segments is None
        assert len(w._rounders) == 3                                    # image, spectra, lambda-t
        assert all("colours" not in what for _k, what, _b in w.actions.rows)
    finally:
        w.close()
        ds.close()


def test_modern(themed, cube):
    from PySide6 import QtGui

    from explorer.look import colormaps as cm

    w, ds = make(themed, cube, "modern")
    try:
        assert themed.style().SLIDER is None                           # the accent
        assert w.view.reticle is not None and not w.view.hl.isVisible()
        w.session.lock(True)
        themed.processEvents()
        assert w.view.reticle.locked
        seg = w.nav.segments
        assert seg is not None and seg.isVisible() and not w.nav.stokes.isVisible()   # the combo stays, hidden
        seg.group.button(3).click()
        assert spin(themed, lambda: w.session.state.s == 3 and w.nav.stokes.currentIndex() == 3)
        w.session.set_index("s", 1)
        themed.processEvents()
        assert seg.group.checkedId() == 1
        w.session.set_index("s", 3)
        assert spin(themed, lambda: w.last.get("image", (None,))[0] is not None and w.last["image"][0][1] == 3)
        assert spin(themed, lambda: w.last.get("lambda_t", (0, 0, -1))[2] == 3)
        before = w.view.img.lut
        w.cycle_colours(1)
        assert w.colours.maps[3] == "CET-D4" and w.colour_key.note == "CET-D4"
        assert w.view.img.lut is not None and before is None
        assert np.array_equal(w.lambda_t.img.lut, cm.table("CET-D4"))
        assert w.colour_key.state[0] == "V" and w.colour_key.state[3] == "CET-D4"
        w.cycle_colours(-1)
        assert w.colours.maps[3] == "gray" and w.view.img.lut is None
        assert QtGui.QColor(w.spectra.w.backgroundBrush().color()).name() == "#141416"     # the cards
        assert len([i for i in w.spectra.plots[1].items if type(i).__name__ == "InfiniteLine"]) >= 2   # zero line
        assert any("colours" in what for _k, what, _b in w.actions.rows)
    finally:
        w.close()
        ds.close()


def test_parts_can_be_left_out(themed, cube, monkeypatch):
    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui.shell import Shell

    with Dataset.open(cube) as ds:
        w = Shell(ds, look=get_look("modern", {"EXPLORER_LOOK_OFF": "reticle,stokes,colour"}))
        assert w.view.reticle is None and w.nav.segments is None and w.colours is None
        assert all("colours" not in what for _k, what, _b in w.actions.rows)
        w.close()
