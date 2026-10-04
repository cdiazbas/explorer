"""The colour key and the 2x2 view (ROADMAP E5.30), offscreen, in the modern and the glass look: the key describes
one Stokes' map and levels, and the four panels have each their own, so no key is shown while the 2x2 view is on,
whichever way it came (key 5, All in the Stokes control) and whatever happens in it (a click on a panel, C, M, T);
out of it (keys 1-4, a Stokes in the control, key 5 again) the key is back for the Stokes in the image, with its map
and its levels. C in the 2x2 view recolours the panel of the session's Stokes."""
import contextlib
import time

import numpy as np
import pytest

from explorer.data.axes import STOKES
from explorer.testing import synth

SHAPE = (3, 4, 5, 96, 80)


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("gridkey"), "c", shape=SHAPE, icube=False)["im"]


@contextlib.contextmanager
def made(qapp, cube, look):
    from PySide6 import QtGui, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui import style
    from explorer.ui.shell import Shell

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    ds = Dataset.open(cube)
    w = Shell(ds, title="c_im.fits", look=get_look(look, {}))
    w.setGeometry(60, 50, 1000, 700)
    w.show()
    try:
        assert spin(qapp, lambda: w.first_image_s is not None and "lambda_t" in w.last)
        yield w
    finally:
        w.close()
        ds.close()
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)
        qapp.setProperty("explorer_light", False)


@pytest.fixture(params=["modern", "glass"])
def shell(request, qapp, cube):
    with made(qapp, cube, request.param) as w:
        assert key_right(w), key_seen(w)                # the single view's key, as it starts
        yield w


def fire(w, seq):
    from PySide6 import QtGui

    ks = QtGui.QKeySequence(seq)
    hits = [sc for sc in w.findChildren(QtGui.QShortcut) if sc.key() == ks]
    assert len(hits) == 1, seq
    hits[0].activated.emit()


def click(view, y, x):
    """A left click at data pixel (y, x) on an ImageView's scene, as pyqtgraph hands it to sigMouseClicked."""
    from PySide6 import QtCore

    pos = view.vb.mapViewToScene(QtCore.QPointF(x + 0.5, y + 0.5))
    ev = type("Click", (), dict(scenePos=lambda self: pos, double=lambda self: False,
                                button=lambda self: QtCore.Qt.MouseButton.LeftButton))()
    view.widget.scene().sigMouseClicked.emit(ev)


def grid_on(w):
    return w.grid is not None and w.grid.isVisible()


def key_shown(w):
    return w.colour_key is not None and w.colour_key.isVisible()


def key_seen(w):
    """What the key and the image hold: for the message of an assertion that fails."""
    k = w.colour_key
    return dict(look=w.look.name, grid=grid_on(w), s=w.session.state.s, image=w.last.get("image"),
                maps=getattr(w.colours, "maps", None),
                key=None if k is None else dict(visible=k.isVisible(), state=k.state))


def key_right(w):
    """The key shown, for the Stokes in the image: its name, the levels the image was painted with, its map."""
    k, s = w.colour_key, w.session.state.s
    idx, levels = w.last.get("image", ((None, None), None))
    if not key_shown(w) or grid_on(w) or idx[1] != s:
        return False
    lut = w.colours.lut(s)
    same_lut = (k.lut is None and lut is None) or (k.lut is not None and lut is not None and np.array_equal(k.lut, lut))
    return same_lut and k.state == (STOKES[s], round(float(levels[0]), 12), round(float(levels[1]), 12),
                                    w.colours.maps[s])


def settle(qapp, w):
    for _ in range(5):
        qapp.processEvents()


def test_key_5_and_all_hide_the_key_and_one_stokes_brings_back_its_own(qapp, shell):
    w = shell
    fire(w, "5")
    assert grid_on(w) and not key_shown(w), key_seen(w)
    fire(w, "2")                                        # key 2: Q, the 2x2 view gives way
    assert spin(qapp, lambda: key_right(w)) and w.session.state.s == 1, key_seen(w)
    w.nav.stokes.setCurrentIndex(4)                     # All in the Stokes control (in glass, on its bar)
    assert grid_on(w) and not key_shown(w), key_seen(w)
    w.nav.stokes.setCurrentIndex(3)                     # V picked in the control
    assert spin(qapp, lambda: key_right(w)) and w.session.state.s == 3, key_seen(w)
    fire(w, "5")
    assert grid_on(w) and not key_shown(w), key_seen(w)
    fire(w, "5")                                        # key 5 again: the single view, V still
    assert spin(qapp, lambda: key_right(w)) and w.session.state.s == 3, key_seen(w)


def test_a_click_on_a_panel_keeps_the_key_hidden_and_out_its_stokes_is_the_key(qapp, shell):
    w = shell
    fire(w, "5")
    assert spin(qapp, lambda: all(v._full is not None for v in w.grid.views))
    click(w.grid.views[2], 20, 30)                      # U: the session's Stokes, its image read for the single view
    assert spin(qapp, lambda: w.session.state.s == 2 and w.last["image"][0][1] == 2), key_seen(w)
    settle(qapp, w)
    assert grid_on(w) and not key_shown(w), key_seen(w)
    fire(w, "5")
    assert spin(qapp, lambda: key_right(w)) and w.session.state.s == 2, key_seen(w)


def test_c_in_the_2x2_view_recolours_its_panel_and_the_key_stays_hidden(qapp, shell):
    w = shell
    fire(w, "5")
    assert spin(qapp, lambda: all(v._full is not None for v in w.grid.views))
    click(w.grid.views[3], 20, 30)                      # V the session's
    assert spin(qapp, lambda: w.session.state.s == 3 and w.last["image"][0][1] == 3), key_seen(w)
    before = w.colours.maps[3]
    fire(w, "C")
    settle(qapp, w)
    assert w.colours.maps[3] != before and not key_shown(w), key_seen(w)
    tab = w.colours.image_lut(3)
    assert tab is not None and np.array_equal(w.grid.views[3].img.lut, tab)    # the panel on its new map
    fire(w, "Shift+C")
    fire(w, "Shift+C")
    settle(qapp, w)
    assert not key_shown(w), key_seen(w)
    tab = w.colours.image_lut(3)
    lut = w.grid.views[3].img.lut
    assert (tab is None and lut is w.grid.views[3].base_lut) or np.array_equal(lut, tab)
    fire(w, "4")                                        # out: V's key, on the map C left it
    assert spin(qapp, lambda: key_right(w)), key_seen(w)
    assert w.colour_key.state[3] == w.colours.maps[3] != before


def test_m_through_the_looks_in_the_2x2_view_shows_no_key(qapp, shell):
    w = shell
    start = w.look.name
    fire(w, "5")
    assert grid_on(w) and not key_shown(w), key_seen(w)
    seen = []
    for _ in range(3):                                  # classic, modern and glass in turn, back to the first
        fire(w, "M")
        settle(qapp, w)
        seen.append(w.look.name)
        assert grid_on(w) and not key_shown(w), key_seen(w)
    assert seen[-1] == start and len(set(seen)) == 3
    fire(w, "5")
    assert spin(qapp, lambda: key_right(w)), key_seen(w)


def test_m_from_classic_in_the_2x2_view_brings_no_key(qapp, shell):
    """Into the 2x2 view in classic (no key), then M to a look with colour: the key stays hidden until it ends."""
    w = shell
    while w.look.name != "classic":
        fire(w, "M")
        settle(qapp, w)
    fire(w, "5")
    assert grid_on(w) and not key_shown(w), key_seen(w)
    fire(w, "M")                                        # modern
    settle(qapp, w)
    assert w.look.name == "modern" and grid_on(w) and not key_shown(w), key_seen(w)
    fire(w, "5")
    assert spin(qapp, lambda: key_right(w)), key_seen(w)


def test_started_in_classic_the_key_made_in_the_2x2_view_stays_hidden(qapp, cube):
    """The key is made the first time a look has colour: made while the 2x2 view is on, it is hidden all the same."""
    with made(qapp, cube, "classic") as w:
        assert w.colour_key is None
        fire(w, "5")
        fire(w, "M")                                    # modern: the key made now, over the panels
        settle(qapp, w)
        assert w.colour_key is not None and grid_on(w) and not key_shown(w), key_seen(w)
        fire(w, "5")
        assert spin(qapp, lambda: key_right(w)), key_seen(w)


def test_t_in_the_2x2_view_shows_no_key(qapp, shell):
    from explorer.ui import style

    w = shell
    fire(w, "5")
    fire(w, "T")
    settle(qapp, w)
    assert style.is_light() and grid_on(w) and not key_shown(w), key_seen(w)
    fire(w, "T")
    settle(qapp, w)
    assert not style.is_light() and grid_on(w) and not key_shown(w), key_seen(w)
    fire(w, "1")
    assert spin(qapp, lambda: key_right(w)) and w.session.state.s == 0, key_seen(w)


def test_in_glass_the_bar_stays_over_the_2x2_view_without_the_key(qapp, shell):
    from PySide6 import QtCore

    from explorer.ui import glass

    w = shell
    if w.glass is None:
        pytest.skip("the glass look's bar")
    w.nav.stokes.setCurrentIndex(4)
    assert grid_on(w) and not key_shown(w), key_seen(w)
    bar = w.glass.bar
    bar.show()
    hit = w.view.widget.childAt(bar.geometry().center())
    assert hit is bar or bar.isAncestorOf(hit)          # look_glass.py:935, the bar raised over the grid
    w.nav.stokes.setCurrentIndex(0)
    assert spin(qapp, lambda: key_right(w)), key_seen(w)
    assert w.colour_key.pos() == QtCore.QPoint(glass.MARGIN, glass.MARGIN)    # at glass's top left still
