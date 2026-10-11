"""The image's limits and gamma on the image itself, offscreen (ui.scalekey): min, max and the limit rule per (cube,
Stokes) in the session next to gamma; the key of every image dragged, wheeled and double-clicked; its menu; the card;
the layout keeping them; the G keys on the sheet."""
import time

import pytest
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtTest import QTest

from explorer.core.levels import rule_levels
from explorer.testing import synth

SHAPE = (3, 4, 5, 90, 80)


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cubes(tmp_path_factory):
    d = tmp_path_factory.mktemp("scale")
    main = synth.write_dataset(d, "main", shape=SHAPE, icube=False)["im"]
    other = synth.write_dataset(d, "other", shape=(SHAPE[0], SHAPE[1], 7, SHAPE[3], SHAPE[4]), seed=4, icube=False,
                                sp=False)["im"]
    return main, other


def open_window(qapp, cubes, look=None):
    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui.shell import Shell

    ds = Dataset.open(cubes[0])
    linked = [Dataset.open(cubes[1], executors=ds.executors)]
    w = Shell(ds, linked=linked, look=get_look(look) if look else None)
    w.resize(1400, 600)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and all(c.scheduler.img is not None for c in w.linked))
    qapp.processEvents()
    return w, [ds, *linked]


@pytest.fixture
def window(qapp, cubes):
    w, dss = open_window(qapp, cubes)
    yield w, qapp
    w.close()
    for d in reversed(dss):
        d.close()


def drawn(qapp, cube, s=None):
    """The levels cube's image was drawn with, once the image of its Stokes s is there."""
    qapp.processEvents()
    return tuple(cube.view._lim)


# ---------------------------------------------------------------------------------------------- the state
def test_min_max_and_rule_are_per_cube_and_stokes_and_q_u_v_stay_symmetric(window):
    w, qapp = window
    sess = w.session
    sess.set_scale(0, 1, "fixed", -2.0, 3.0)
    sess.set_scale(1, 0, "minmax")
    assert sess.scale(0, 1) == ("fixed", -3.0, 3.0)                     # Q: symmetric about 0
    assert sess.scale(0, 0) == sess.scale(0, 2) == sess.scale(1, 1) == ("p1", 0.0, 0.0)
    assert sess.scale(1, 0) == ("minmax", 0.0, 0.0)
    sess.set_scale(0, 0, "fixed", 5.0, 7.0)
    assert sess.scale(0, 0) == ("fixed", 5.0, 7.0) and sess.scale(0, 1) == ("fixed", -3.0, 3.0)
    for bad in (("fixed", 7.0, 5.0), ("nope", 0.0, 1.0)):
        with pytest.raises(ValueError):
            sess.set_scale(0, 0, *bad)
    sess.set_scale(0, 1, "p1")
    assert sess.scale(0, 1) == ("p1", 0.0, 0.0) and len(sess.state.scale) == 2


def test_the_image_follows_its_rule_and_the_padlock_its_stokes(window):
    w, qapp = window
    sess, sch = w.session, w.main.scheduler
    auto = drawn(qapp, w.main)
    assert auto == rule_levels(sch.img, False, "p1")                    # at start: today's automatic levels
    sess.set_scale(0, 0, "minmax")
    assert spin(qapp, lambda: drawn(qapp, w.main) == rule_levels(sch.img, False, "minmax"))
    sess.set_scale(0, 0, "fixed", 1.0, 2.0)
    assert spin(qapp, lambda: drawn(qapp, w.main) == (1.0, 2.0)) and w.image_lock.isChecked()
    sess.set_index("s", 1)                                              # Q: its own, automatic
    assert spin(qapp, lambda: sch.img_idx[1] == 1 and drawn(qapp, w.main) == rule_levels(sch.img, True, "p1"))
    assert not w.image_lock.isChecked()
    w.image_lock.click()                                                # the padlock fixes Q's, not I's
    qapp.processEvents()
    assert sess.scale(0, 1)[0] == "fixed" and sess.scale(0, 0) == ("fixed", 1.0, 2.0)
    w.image_lock.click()
    qapp.processEvents()
    assert sess.scale(0, 1)[0] == "p1" and sess.scale(0, 0) == ("fixed", 1.0, 2.0)


# ---------------------------------------------------------------------------------------------- the key
def hot(qapp, key):
    key.set_hot(True)
    qapp.processEvents()
    assert key.hot and key.height() == key.H_HOT


def test_every_image_has_a_key_in_classic_too_and_it_takes_a_narrow_panel_s_width(qapp, cubes):
    w, dss = open_window(qapp, cubes, look="classic")
    try:
        assert all(c.key.isVisible() for c in w.cubes)
        assert w.colour_key is w.main.key and w.main.key.state is not None
        assert spin(qapp, lambda: w.linked[0].key.state is not None)
        assert w.linked[0].key.state[0].startswith(w.linked[0].name)
        view = w.linked[0].view.widget
        view.resize(200, view.height())
        qapp.processEvents()
        assert w.linked[0].key.width() == max(w.linked[0].key.MIN_W, 200 - 24)
    finally:
        w.close()
        for d in reversed(dss):
            d.close()


def test_dragging_a_handle_sets_that_limit_and_closes_the_padlock(window):
    w, qapp = window
    key, sess = w.main.key, w.session
    hot(qapp, key)
    lo, hi = key.levels()
    y = int(key._bar().center().y())
    QTest.mousePress(key, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier,
                     QtCore.QPoint(int(round(key.x_of(hi))), y))
    assert key.drag == "hi"
    to = int(round(key.x_of(hi))) - 25
    QTest.mouseMove(key, QtCore.QPoint(to, y))
    QTest.mouseRelease(key, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier,
                       QtCore.QPoint(to, y))
    rule, lo2, hi2 = sess.scale(0, 0)
    assert rule == "fixed" and lo2 == pytest.approx(lo) and hi2 < hi
    assert spin(qapp, lambda: drawn(qapp, w.main) == (lo2, hi2)) and w.image_lock.isChecked()
    assert sess.scale(0, 1) == sess.scale(1, 0) == ("p1", 0.0, 0.0)    # nothing else moved


def test_on_q_one_handle_moves_both_ends(window):
    w, qapp = window
    sess, key = w.session, w.linked[0].key
    sess.set_index("s", 2)
    assert spin(qapp, lambda: w.linked[0].scheduler.img_idx is not None and w.linked[0].scheduler.img_idx[1] == 2)
    hot(qapp, key)
    lo, hi = key.levels()
    assert lo == -hi
    key.drag = "lo"
    key._axis = key.axis()
    key.drag_to(lo / 2)
    assert sess.scale(1, 2) == ("fixed", -hi / 2, hi / 2) and sess.scale(0, 2)[0] == "p1"


def test_the_wheel_steps_gamma_and_a_double_click_gives_automatic_levels(window):
    w, qapp = window
    key, sess = w.main.key, w.session
    hot(qapp, key)
    at = QtCore.QPointF(20, 30)

    def wheel(dy):
        ev = QtGui.QWheelEvent(at, key.mapToGlobal(at), QtCore.QPoint(0, 0), QtCore.QPoint(0, dy),
                               QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier,
                               QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        QtWidgets.QApplication.sendEvent(key, ev)
    wheel(-120)
    assert sess.gamma(0, 0) == pytest.approx(10 ** -0.1)               # the G keys' step
    wheel(120)
    wheel(120)
    assert sess.gamma(0, 0) == pytest.approx(10 ** 0.1) and sess.gamma(1, 0) == 1.0
    sess.set_scale(0, 0, "fixed", 1.0, 2.0)
    qapp.processEvents()
    QTest.mouseDClick(key, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier,
                      QtCore.QPoint(20, 6))
    qapp.processEvents()
    assert sess.scale(0, 0) == ("p1", 0.0, 0.0) and not w.image_lock.isChecked()
    assert sess.gamma(0, 0) == pytest.approx(10 ** 0.1)                # the limits only


def test_a_right_click_on_the_key_opens_its_menu_not_a_release(window):
    w, qapp = window
    w.session.lock(True)
    qapp.processEvents()
    QTest.mousePress(w.main.key, QtCore.Qt.MouseButton.RightButton, QtCore.Qt.KeyboardModifier.NoModifier,
                     QtCore.QPoint(20, 6))
    qapp.processEvents()
    QTest.mouseRelease(w.main.key, QtCore.Qt.MouseButton.RightButton, QtCore.Qt.KeyboardModifier.NoModifier,
                       QtCore.QPoint(20, 6))                     # no button left held for the tests after
    menus = [m for m in w.findChildren(QtWidgets.QMenu) if m.isVisible()]
    assert menus and w.session.state.locked
    for m in menus:
        m.close()


# ---------------------------------------------------------------------------------------------- menu and card
def entries(menu):
    return {a.data(): a for a in menu.actions() if a.data() is not None}


def test_the_menu_holds_the_rules_the_gamma_presets_the_card_and_a_reset(window):
    from explorer.ui.scalekey import scale_menu

    w, qapp = window
    sess = w.session
    m = scale_menu(w, 0, 3)
    got = entries(m)
    assert set(got) == {("rule", r) for r in ("p1", "p05", "minmax", "fixed")} | \
        {("gamma", g) for g in (1.0, 0.7, 0.5, 0.3)} | {("card", None), ("reset", None)}
    assert got[("rule", "p1")].isChecked() and got[("gamma", 1.0)].isChecked()
    got[("rule", "p05")].trigger()
    assert sess.scale(0, 3) == ("p05", 0.0, 0.0)
    got[("gamma", 0.5)].trigger()
    assert sess.gamma(0, 3) == 0.5 and sess.gamma(0, 0) == 1.0
    sess.set_index("s", 3)
    assert spin(qapp, lambda: w.main.scheduler.img_idx[1] == 3 and drawn(qapp, w.main)
                == rule_levels(w.main.scheduler.img, True, "p05"))
    entries(scale_menu(w, 0, 3))[("rule", "fixed")].trigger()          # frozen at the levels shown
    assert sess.scale(0, 3) == ("fixed", *drawn(qapp, w.main))
    entries(scale_menu(w, 0, 3))[("reset", None)].trigger()
    assert sess.scale(0, 3) == ("p1", 0.0, 0.0) and sess.gamma(0, 3) == 1.0
    entries(scale_menu(w, 0, 3))[("card", None)].trigger()
    assert w.scale_card is not None and w.scale_card.isVisible()
    card = w.scale_card
    w.close()                                                           # closed with the window, its filter too
    assert w.scale_card is None and not card.isVisible()


def test_the_card_types_min_max_slides_gamma_picks_the_rule_and_closes(window):
    from explorer.ui.scalekey import gamma_of_slider

    w, qapp = window
    sess = w.session
    card = w.open_scale_card(1, 0)
    qapp.processEvents()
    lo, hi = w.scale_levels(1, 0)
    assert float(card.lo.text()) == pytest.approx(lo, rel=1e-5) and card.slider.value() == 500
    card.hi.setText(f"{hi * 0.5:.6g}")
    card.hi.editingFinished.emit()
    assert sess.scale(1, 0)[0] == "fixed" and sess.scale(1, 0)[2] == pytest.approx(hi * 0.5, rel=1e-5)
    card.slider.setValue(250)
    assert sess.gamma(1, 0) == pytest.approx(gamma_of_slider(250)) == pytest.approx(10 ** -0.5)
    card.rule.activated.emit(card.rule.findData("minmax"))
    assert sess.scale(1, 0) == ("minmax", 0.0, 0.0) and sess.scale(0, 0)[0] == "p1"
    card.reset.click()
    assert sess.scale(1, 0) == ("p1", 0.0, 0.0) and sess.gamma(1, 0) == 1.0
    QTest.keyClick(card, QtCore.Qt.Key.Key_Escape)
    qapp.processEvents()
    assert w.scale_card is None
    card = w.open_scale_card(0, 0)
    qapp.processEvents()
    QTest.mousePress(w.view.widget.viewport(), QtCore.Qt.MouseButton.LeftButton,
                     QtCore.Qt.KeyboardModifier.NoModifier, QtCore.QPoint(300, 300))
    qapp.processEvents()
    QTest.mouseRelease(w.view.widget.viewport(), QtCore.Qt.MouseButton.LeftButton,
                       QtCore.Qt.KeyboardModifier.NoModifier, QtCore.QPoint(300, 300))
    assert w.scale_card is None                                          # a click outside


# ---------------------------------------------------------------------------------------------- kept
def test_the_layout_keeps_limits_rule_and_gamma_by_cube_and_stokes(qapp, cubes, tmp_path):
    from explorer.ui.layout import LayoutStore

    path = str(tmp_path / "layout.ini")
    w, dss = open_window(qapp, cubes)
    try:
        w.session.set_scale(0, 1, "fixed", -2.0, 2.0)
        w.session.set_gamma(0, 1, 0.5)
        w.session.set_scale(1, 0, "p05")
        w.session.set_gamma(1, 3, 2.0)
        kept = w.scale_settings()
        LayoutStore("x11", path, linked=True).save_scale(kept)
    finally:
        w.close()
        for d in reversed(dss):
            d.close()
    back = LayoutStore("bridge", path).scale()                           # any way of displaying
    assert back == kept and len(back) == 3
    w, dss = open_window(qapp, cubes)
    try:
        assert w.session.state.scale == () and w.session.state.gamma == ()
        w.restore_scale(back)
        s = w.session
        assert s.scale(0, 1) == ("fixed", -2.0, 2.0) and s.gamma(0, 1) == 0.5
        assert s.scale(1, 0) == ("p05", 0.0, 0.0) and s.gamma(1, 3) == 2.0 and s.scale(0, 0)[0] == "p1"
    finally:
        w.close()
        for d in reversed(dss):
            d.close()


def test_the_g_keys_are_on_the_sheet(window):
    from explorer.ui.actions import mod_key

    w, _ = window
    html = w.action_registry.sheet_html(w.palette())
    assert "G" in html and "⇧G" in html and f"{mod_key()}G" in html and "γ" in html
