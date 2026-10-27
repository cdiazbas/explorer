"""The scale in the 2x2 view (ROADMAP E5.33), offscreen, in classic, modern and glass: each panel has its own padlock
and its own colour key, both for that panel's Stokes, as the single image has one for the Stokes it shows.
- The padlock over a panel fixes or releases that panel's Stokes, a right click on it fixes the levels to that
  panel's frame, and it shows whether that Stokes is fixed; the single image's padlock is not over the panels.
- The key of a panel names its Stokes and holds that panel's levels and map; under the pointer it grows within its
  panel, a drag fixes that Stokes's limit, the wheel steps that Stokes's gamma, a double click gives that Stokes its
  automatic levels and gamma 1 again. A right click on it opens no menu; the one on the panel's Stokes label stays.
- G over a panel says the new gamma on that panel's key, and C the map's name on the key of the panel it recolours."""
import contextlib
import time

import numpy as np
import pytest

from explorer.core.levels import rule_levels
from explorer.data.axes import STOKES
from explorer.testing import synth

SHAPE = (3, 4, 5, 96, 80)


def spin(qapp, until=lambda: False, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("gridscale"), "c", shape=SHAPE, icube=False)["im"]


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
    w.setGeometry(60, 50, 1100, 760)
    w.show()
    try:
        assert spin(qapp, lambda: w.first_image_s is not None and "lambda_t" in w.last)
        w.set_grid(True)
        assert spin(qapp, lambda: all(v._full is not None for v in w.grid.views))
        spin(qapp, timeout=0.2)
        yield w
    finally:
        for m in w.findChildren(QtWidgets.QMenu):
            m.close()
        w.close()
        ds.close()
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)
        qapp.setProperty("explorer_light", False)


@pytest.fixture(params=["classic", "modern", "glass"])
def grid(request, qapp, cube):
    with made(qapp, cube, request.param) as w:
        yield w, qapp


def global_rect(widget):
    from PySide6 import QtCore

    return QtCore.QRect(widget.mapToGlobal(QtCore.QPoint(0, 0)), widget.size())


def lock_over(w, s):
    """The padlock shown over panel s of the 2x2 view (its centre on that panel), or None."""
    from explorer.ui.padlock import PanelLock

    panel = global_rect(w.grid.views[s].widget)
    over = [p for p in w.findChildren(PanelLock) if p.isVisible() and panel.contains(global_rect(p).center())]
    assert len(over) <= 1, over
    return over[0] if over else None


def key_of(w, s):
    """The colour key shown on panel s of the 2x2 view, or None."""
    from explorer.ui.scalekey import ScaleKey

    keys = [k for k in w.grid.views[s].widget.findChildren(ScaleKey) if k.isVisible()]
    assert len(keys) <= 1, keys
    return keys[0] if keys else None


def panel_drawn(qapp, w, s):
    qapp.processEvents()
    return tuple(w.grid.views[s]._lim)


# ---------------------------------------------------------------------------------------------- the padlocks
def test_the_padlock_over_each_panel_fixes_that_panel_s_stokes(grid):
    w, qapp = grid
    sess = w.session
    assert sess.state.s == 0
    for s in range(4):
        lock = lock_over(w, s)
        assert lock is not None and not lock.isChecked(), (s, lock)
    lock_over(w, 1).click()                             # Q's, while the session's Stokes is I
    qapp.processEvents()
    want = rule_levels(w.grid.views[1]._full, True, "p1")
    assert sess.scale(0, 1) == ("fixed", *want), sess.state.scale
    assert all(sess.scale(0, s)[0] == "p1" for s in (0, 2, 3)), sess.state.scale
    assert spin(qapp, lambda: panel_drawn(qapp, w, 1) == want)
    assert lock_over(w, 1).isChecked() and not any(lock_over(w, s).isChecked() for s in (0, 2, 3))
    lock_over(w, 1).click()                             # open: Q automatic again, the others untouched
    qapp.processEvents()
    assert all(sess.scale(0, s)[0] == "p1" for s in range(4)) and not lock_over(w, 1).isChecked()


def test_each_panel_s_padlock_shows_its_stokes_and_its_right_click_fits_its_frame(grid):
    w, qapp = grid
    sess = w.session
    sess.set_scale(0, 2, "fixed", 0.1, 0.5)             # U fixed by anything else (the menu, the layout)
    qapp.processEvents()
    assert [lock_over(w, s).isChecked() for s in range(4)] == [False, False, True, False]
    lock_over(w, 3).refit.emit()                        # V's right click: fixed to V's frame now
    qapp.processEvents()
    assert sess.scale(0, 3) == ("fixed", *rule_levels(w.grid.views[3]._full, True, "p1"))
    assert lock_over(w, 3).isChecked() and sess.scale(0, 2) == ("fixed", -0.5, 0.5)
    assert sess.scale(0, 0)[0] == "p1"
    w.set_grid(False)                                   # the single image: its own padlock, for its Stokes (I)
    qapp.processEvents()
    assert w.image_lock.isVisible() and not w.image_lock.isChecked()
    w.set_grid(True)
    qapp.processEvents()
    assert not w.image_lock.isVisible()
    assert [lock_over(w, s).isChecked() for s in range(4)] == [False, False, True, True]


# ---------------------------------------------------------------------------------------------- the keys
def test_each_panel_has_a_key_for_its_stokes_with_its_levels_and_map(grid):
    w, qapp = grid
    assert not w.colour_key.isVisible()                 # the single image's key: not over the four
    for s, v in enumerate(w.grid.views):
        key = key_of(w, s)
        assert key is not None, s
        assert key.target() == (0, s)
        cols = w.maps_for(s)                            # its map; without one (classic) the panel's grey
        assert key.state == (f"Stokes {STOKES[s]}", round(v._lim[0], 12), round(v._lim[1], 12),
                             cols.maps[s] if cols is not None else v.base_lut is None), (s, key.state)
        assert key.lut is (cols.lut(s) if cols is not None else v.base_lut)
        assert key.frame() is v._full and key.levels() == v._lim
        label = v.widget.mapFromScene(v.stokes.sceneBoundingRect()).boundingRect()
        assert v.widget.rect().contains(key.geometry()) and not key.geometry().intersects(label), \
            (s, key.geometry(), label)
    w.session.step("t", 1)                              # a step in t: each key with its panel's new levels
    assert spin(qapp, lambda: all(key_of(w, s).state[1:3] == tuple(round(x, 12) for x in v._lim)
                                  and v._full is not None for s, v in enumerate(w.grid.views)))


def enter(key):
    from PySide6 import QtCore, QtGui, QtWidgets

    p = QtCore.QPointF(6, 6)
    QtWidgets.QApplication.sendEvent(key, QtGui.QEnterEvent(p, p, QtCore.QPointF(key.mapToGlobal(p.toPoint()))))


def leave(key):
    from PySide6 import QtCore, QtWidgets

    QtWidgets.QApplication.sendEvent(key, QtCore.QEvent(QtCore.QEvent.Type.Leave))


def test_a_panel_s_key_grows_under_the_pointer_within_its_panel(grid):
    w, qapp = grid
    for s in range(4):
        key = key_of(w, s)
        assert key is not None, s
        enter(key)
        qapp.processEvents()
        assert key.hot and key.height() == key.H_HOT, s
        assert w.grid.views[s].widget.rect().contains(key.geometry()), (s, key.geometry())
        assert not any(key_of(w, o).hot for o in range(4) if o != s)
        leave(key)
        qapp.processEvents()
        assert not key.hot and key.height() == key.H


def test_dragging_a_panel_s_handle_fixes_that_stokes_and_closes_its_padlock(grid):
    from PySide6 import QtCore
    from PySide6.QtTest import QTest

    w, qapp = grid
    sess, key = w.session, key_of(w, 2)                 # U, while the session's Stokes is I
    assert key is not None
    enter(key)
    qapp.processEvents()
    lo, hi = key.levels()
    y = int(key._bar().center().y())
    at = int(round(key.x_of(hi)))
    QTest.mousePress(key, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier,
                     QtCore.QPoint(at, y))
    assert key.drag == "hi"
    QTest.mouseMove(key, QtCore.QPoint(at - 25, y))
    QTest.mouseRelease(key, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier,
                       QtCore.QPoint(at - 25, y))
    rule, lo2, hi2 = sess.scale(0, 2)
    assert rule == "fixed" and lo2 == -hi2 and hi2 < hi     # Q U V: symmetric, one handle moves both ends
    assert all(sess.scale(0, s)[0] == "p1" for s in (0, 1, 3))
    assert spin(qapp, lambda: panel_drawn(qapp, w, 2) == (lo2, hi2))
    assert lock_over(w, 2).isChecked() and not lock_over(w, 0).isChecked()
    leave(key)


def test_the_wheel_on_a_panel_s_key_steps_that_stokes_gamma_and_a_double_click_resets_it(grid):
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtTest import QTest

    w, qapp = grid
    sess, key = w.session, key_of(w, 3)                 # V
    assert key is not None
    enter(key)
    qapp.processEvents()
    at = QtCore.QPointF(20, 30)
    ev = QtGui.QWheelEvent(at, key.mapToGlobal(at), QtCore.QPoint(0, 0), QtCore.QPoint(0, -120),
                           QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier,
                           QtCore.Qt.ScrollPhase.NoScrollPhase, False)
    QtWidgets.QApplication.sendEvent(key, ev)
    qapp.processEvents()
    assert sess.gamma(0, 3) == pytest.approx(10 ** -0.1) and all(sess.gamma(0, s) == 1.0 for s in range(3))
    assert w.grid.views[3]._gamma == pytest.approx(10 ** -0.1) and w.grid.views[0]._gamma == 1.0
    sess.set_scale(0, 3, "fixed", -0.2, 0.2)
    sess.set_scale(0, 0, "fixed", 0.1, 0.9)
    qapp.processEvents()
    QTest.mouseDClick(key, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier,
                      QtCore.QPoint(20, 6))
    qapp.processEvents()
    assert sess.scale(0, 3) == ("p1", 0.0, 0.0) and sess.gamma(0, 3) == 1.0
    assert sess.scale(0, 0) == ("fixed", 0.1, 0.9)      # I's own, untouched
    assert not lock_over(w, 3).isChecked() and lock_over(w, 0).isChecked()
    leave(key)


def visible_menus(w):
    from PySide6 import QtWidgets

    return [m for m in w.findChildren(QtWidgets.QMenu) if m.isVisible()]


def test_a_right_click_on_a_panel_s_key_opens_no_menu_and_its_label_s_menu_stays(grid):
    from PySide6 import QtCore
    from PySide6.QtTest import QTest

    w, qapp = grid
    key = key_of(w, 1)
    assert key is not None
    QTest.mousePress(key, QtCore.Qt.MouseButton.RightButton, QtCore.Qt.KeyboardModifier.NoModifier,
                     QtCore.QPoint(20, 6))
    qapp.processEvents()
    QTest.mouseRelease(key, QtCore.Qt.MouseButton.RightButton, QtCore.Qt.KeyboardModifier.NoModifier,
                       QtCore.QPoint(20, 6))
    assert not visible_menus(w)
    v = w.grid.views[2]                                 # a right click on U's label: U's scale menu
    pos = v.stokes.sceneBoundingRect().center()
    ev = type("Click", (), dict(scenePos=lambda self: pos, double=lambda self: False,
                                button=lambda self: QtCore.Qt.MouseButton.RightButton))()
    v.widget.scene().sigMouseClicked.emit(ev)
    qapp.processEvents()
    menus = visible_menus(w)
    assert len(menus) == 1 and menus[0].actions()[0].text() == "Stokes U"
    card = next(a for a in menus[0].actions() if a.data() == ("card", None))
    menus[0].close()
    card.trigger()                                      # "Scale...": the card by U's panel's key
    qapp.processEvents()
    key = key_of(w, 2)
    assert w.scale_card is not None and w.scale_card.isVisible() and (w.scale_card.k, w.scale_card.s) == (0, 2)
    assert w.scale_card.x() == key.parentWidget().mapTo(w, key.geometry().topLeft()).x()
    w.scale_card.close()


def test_g_over_a_panel_says_the_gamma_on_that_panel_s_key(grid):
    from PySide6 import QtGui

    w, qapp = grid
    w.grid._hovered(3, 20, 20)                          # the mouse over the V panel
    hits = [sc for sc in w.findChildren(QtGui.QShortcut) if sc.key() == QtGui.QKeySequence("G")]
    assert len(hits) == 1
    hits[0].activated.emit()
    qapp.processEvents()
    assert w.session.gamma(0, 3) == pytest.approx(10 ** -0.1)
    assert key_of(w, 3).note == "γ = 0.79" and not any(key_of(w, s).note for s in range(3))


def test_c_in_the_2x2_view_names_the_map_on_its_panel_s_key(grid):
    """C recolours the panel of the session's Stokes (test_grid_colour_key); the map's name goes on that panel's key,
    where the single image's key says it."""
    from PySide6 import QtGui

    w, qapp = grid
    w.session.set_index("s", 3)
    qapp.processEvents()
    hits = [sc for sc in w.findChildren(QtGui.QShortcut) if sc.key() == QtGui.QKeySequence("C")]
    assert len(hits) == 1
    hits[0].activated.emit()
    qapp.processEvents()
    assert key_of(w, 3).note == w.colours.maps[3] and not any(key_of(w, s).note for s in range(3))
    assert key_of(w, 3).state[3] == w.colours.maps[3]   # and its bar on the new map


def test_the_keys_follow_a_look_and_a_theme_switch_in_the_2x2_view(grid):
    from explorer.look import get_look
    from explorer.ui import style

    w, qapp = grid
    start = w.look.name
    for look in ("classic", "modern", "glass", start):
        w.set_look(get_look(look, {}))
        spin(qapp, timeout=0.2)
        assert all(key_of(w, s) is not None for s in range(4)) and not w.colour_key.isVisible(), look
        for s, v in enumerate(w.grid.views):
            label = v.widget.mapFromScene(v.stokes.sceneBoundingRect()).boundingRect()
            assert not key_of(w, s).geometry().intersects(label), (look, s)
    w.set_theme("light")
    qapp.processEvents()
    assert style.is_light() and all(key_of(w, s) is not None for s in range(4))
    w.set_theme("dark")
    qapp.processEvents()
    w.set_grid(False)
    qapp.processEvents()
    assert w.colour_key.isVisible() and w.image_lock.isVisible()
    assert not any(k.isVisible() for k in w.grid.findChildren(type(w.colour_key)))
    assert np.isfinite(w.colour_key.state[1])
