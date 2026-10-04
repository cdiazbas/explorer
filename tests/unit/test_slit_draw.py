"""Drawing the slit (ROADMAP E7.1, the prototype's variant D), offscreen: S or the toolbar's button turns the mode on,
shown by the button, a pencil and a hint over the image; a click adds a point on the pixel's centre, a double click
finishes the slit, a right click removes the last point and with none left ends the mode, Esc or S cancel the slit
being drawn and keep a finished one, ⌫ or Delete remove it; the finished slit is the session's path. The keys are in
the one table (A and D left free); the slit takes the look's colour and the theme; it is drawn and drawn on in the
2x2 view, and in glass its hint goes below the colour key."""
import time

import numpy as np
import pytest

from explorer.testing import synth

SHAPE = (3, 4, 5, 60, 48)


def spin(qapp, until=lambda: False, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("slit"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube):
    from PySide6 import QtGui, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.ui import style
    from explorer.ui.shell import Shell

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    ds = Dataset.open(cube)
    w = Shell(ds, title="c_im.fits")
    w.setGeometry(60, 50, 1000, 700)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    for _ in range(10):
        qapp.processEvents()
    yield w
    w.close()
    ds.close()
    qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
    qapp.setPalette(pal)
    qapp.setProperty("explorer_light", False)
    import pyqtgraph as pg

    pg.setConfigOptions(background="k", foreground="d")


def mouse(view, x, y, kind, button=None, buttons=None):
    """A mouse event on an ImageView's viewport at data point (x, y), as the platform delivers it."""
    from PySide6 import QtCore, QtGui, QtWidgets

    B = QtCore.Qt.MouseButton
    gv, vp = view.widget, view.widget.viewport()
    p = QtCore.QPointF(gv.mapFromScene(view.vb.mapViewToScene(QtCore.QPointF(x, y))))
    ev = QtGui.QMouseEvent(kind, p, vp.mapToGlobal(p), button if button is not None else B.NoButton,
                           buttons if buttons is not None else B.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(vp, ev)


def click(view, x, y, button=None, double=False):
    """Press and release (a double click: the second press as Qt's double-click event) at data point (x, y). At a
    pixel's centre when the pixel matters: the point goes through whole screen pixels, and at a pixel's edge it can
    land in the one beside."""
    from PySide6 import QtCore

    B, E = QtCore.Qt.MouseButton, QtCore.QEvent.Type
    b = button or B.LeftButton
    mouse(view, x, y, E.MouseButtonDblClick if double else E.MouseButtonPress, b, b)
    mouse(view, x, y, E.MouseButtonRelease, b, B.NoButton)


def scene_click(view, x, y, button=None, double=False):
    """A click at data point (x, y) as pyqtgraph hands it to sigMouseClicked (the 2x2 view's panels)."""
    from PySide6 import QtCore

    pos = view.vb.mapViewToScene(QtCore.QPointF(x, y))
    ev = type("Click", (), dict(scenePos=lambda self: pos, double=lambda self: double,
                                button=lambda self: button or QtCore.Qt.MouseButton.LeftButton))()
    view.widget.scene().sigMouseClicked.emit(ev)


def key(w, k):
    from PySide6.QtTest import QTest

    QTest.keyClick(w, k)


def line_xy(item):
    x, y = item.getData()
    return np.column_stack([x, y]) if x is not None else np.zeros((0, 2))


def dots_xy(item):
    return np.array([(p.x(), p.y()) for p in (s.pos() for s in item.points())]).reshape(-1, 2)


def test_s_and_the_button_turn_the_mode_on_and_off_and_say_so(qapp, shell):
    from PySide6 import QtCore

    w, K, C = shell, QtCore.Qt.Key, QtCore.Qt.CursorShape
    vp = w.view.widget.viewport()
    assert not w.slit_tool.mode and not w.slit_hint.isVisible() and vp.cursor().shape() == C.CrossCursor
    key(w, K.Key_S)
    assert w.slit_tool.mode and w.nav.slit.isChecked()
    assert vp.cursor().shape() == C.BitmapCursor                    # the pencil
    assert w.slit_hint.isVisible() and "click adds a point" in w.slit_hint.text
    key(w, K.Key_S)
    assert not w.slit_tool.mode and not w.nav.slit.isChecked()
    assert vp.cursor().shape() == C.CrossCursor and not w.slit_hint.isVisible()
    w.nav.slit.click()                                              # the toolbar's button, the same mode
    assert w.slit_tool.mode and vp.cursor().shape() == C.BitmapCursor
    w.nav.slit.click()
    assert not w.slit_tool.mode


def test_the_pencil_has_its_tip_on_the_hot_spot_at_the_screens_ratio(qapp, shell):
    """The prototype's F69a: a 2x pixmap under xcb came out 48 x 48 with the hot spot mid-edge."""
    from explorer.ui.slit import pencil_cursor

    c = pencil_cursor(shell.view.widget)
    pm = c.pixmap()
    dpr = shell.view.widget.screen().devicePixelRatio()
    assert (c.hotSpot().x(), c.hotSpot().y()) == (1, 23)
    assert pm.width() == int(24 * max(1.0, dpr)) and pm.devicePixelRatio() == max(1.0, dpr)


def test_clicks_add_points_and_a_double_click_finishes_the_slit_into_the_session(qapp, shell):
    from PySide6 import QtCore

    w, C = shell, QtCore.Qt.CursorShape
    st0 = w.session.state
    w.set_slit_mode(True)
    click(w.view, 12.3, 10.7)
    assert w.slit_tool.pts == [(12.5, 10.5)]                       # on the pixel's centre
    assert w.view.widget.viewport().cursor().shape() == C.BitmapCursor     # still the pencil after the click
    click(w.view, 25.7, 30.3)
    assert w.slit_tool.pts == [(12.5, 10.5), (25.5, 30.5)] and "2 points" in w.slit_hint.text
    assert len(line_xy(w.slit_tool.marks[0].band)) > 2              # the slit being drawn, dashed
    click(w.view, 25.7, 30.3, double=True)
    st = w.session.state
    assert st.path == ((12.5, 10.5), (25.5, 30.5)) and not w.slit_tool.mode and not w.nav.slit.isChecked()
    assert st.locked == st0.locked                                  # the clicks were the slit's, not the cursor's
    m = w.slit_tool.marks[0]
    xy = line_xy(m.line)
    assert np.allclose(xy[0], (12.5, 10.5)) and np.allclose(xy[-1], (25.5, 30.5)) and len(xy) > 20
    assert len(line_xy(m.band)) == 0 and np.allclose(dots_xy(m.dots), [(12.5, 10.5), (25.5, 30.5)])
    assert w.slit_hint.isVisible() and "S new slit" in w.slit_hint.text
    assert w.view.widget.viewport().cursor().shape() == C.CrossCursor


def test_three_points_a_curve_through_every_one(qapp, shell):
    w = shell
    w.set_slit_mode(True)
    pts = [(5.5, 5.5), (20.5, 40.5), (40.5, 10.5)]
    for x, y in pts:
        click(w.view, x, y)
    click(w.view, *pts[-1], double=True)
    assert w.session.state.path == tuple(pts)
    xy = line_xy(w.slit_tool.marks[0].line)
    for p in pts:                                                   # Catmull-Rom: through every point clicked,
        assert np.hypot(*(xy - p).T).min() < 0.6                    # the middle one 30 px off the ends' line
    assert np.allclose(xy[0], pts[0]) and np.allclose(xy[-1], pts[-1])


def test_a_right_click_removes_the_last_point_and_with_none_ends_the_mode(qapp, shell):
    from PySide6 import QtCore

    w, R = shell, QtCore.Qt.MouseButton.RightButton
    w.session.lock(True)
    w.set_slit_mode(True)
    click(w.view, 10.5, 10.5)
    click(w.view, 20.5, 20.5)
    click(w.view, 20.5, 20.5, button=R)
    assert w.slit_tool.pts == [(10.5, 10.5)] and w.slit_tool.mode
    click(w.view, 20.5, 20.5, button=R)
    assert w.slit_tool.pts == [] and w.slit_tool.mode
    click(w.view, 20.5, 20.5, button=R)
    assert not w.slit_tool.mode and not w.nav.slit.isChecked()
    spin(qapp, timeout=0.05)
    assert w.session.state.locked                                   # not the cursor's release


def test_one_point_is_no_slit(qapp, shell):
    w = shell
    w.set_slit_mode(True)
    click(w.view, 10.5, 10.5)
    click(w.view, 10.5, 10.5, double=True)
    assert w.slit_tool.mode and w.session.state.path is None and "two points at least" in w.slit_hint.text


def test_esc_and_s_cancel_the_slit_being_drawn_and_keep_the_finished_one(qapp, shell):
    from PySide6 import QtCore

    w, K = shell, QtCore.Qt.Key
    w.set_slit_mode(True)
    click(w.view, 5.5, 5.5)
    click(w.view, 30.5, 40.5)
    click(w.view, 30.5, 40.5, double=True)
    kept = w.session.state.path
    for leave in (K.Key_Escape, K.Key_S):
        key(w, K.Key_S)
        click(w.view, 15.5, 15.5)
        assert w.slit_tool.pts == [(15.5, 15.5)]
        key(w, leave)
        m = w.slit_tool.marks[0]
        assert not w.slit_tool.mode and w.slit_tool.pts == [] and w.session.state.path == kept
        assert len(line_xy(m.band)) == 0 and np.allclose(dots_xy(m.dots), kept) and len(line_xy(m.line)) > 2
    w.session.lock(True)
    key(w, K.Key_Escape)                                            # out of the mode: Esc releases the cursor again
    assert spin(qapp, lambda: not w.session.state.locked)


@pytest.mark.parametrize("which", ["Key_Backspace", "Key_Delete"])
def test_backspace_or_delete_removes_the_finished_slit(qapp, shell, which):
    from PySide6 import QtCore

    w = shell
    w.session.set_path(((5.5, 5.5), (30.5, 40.5)))
    assert spin(qapp, lambda: len(line_xy(w.slit_tool.marks[0].line)) > 2)   # the state's path, drawn
    assert w.slit_hint.isVisible()
    key(w, getattr(QtCore.Qt.Key, which))
    m = w.slit_tool.marks[0]
    assert w.session.state.path is None and len(line_xy(m.line)) == 0 and len(dots_xy(m.dots)) == 0
    assert not w.slit_hint.isVisible()


def test_the_slit_being_drawn_reaches_to_the_pointer(qapp, shell):
    from PySide6 import QtCore

    w = shell
    w.set_slit_mode(True)
    click(w.view, 10.5, 10.5)
    w.view._moved(w.view.vb.mapViewToScene(QtCore.QPointF(33.2, 41.7)))
    xy = line_xy(w.slit_tool.marks[0].band)
    assert np.allclose(xy[0], (10.5, 10.5)) and np.allclose(xy[-1], (33.2, 41.7), atol=1e-6)


def test_the_session_path_two_points_at_least_clipped_to_the_image(qapp, shell):
    s = shell.session
    with pytest.raises(ValueError):
        s.set_path(((1.5, 1.5),))
    s.set_path([(-3, 2.5), (100.0, 70.0)])
    assert s.state.path == ((0.0, 2.5), (float(SHAPE[-1]), float(SHAPE[-2])))
    s.set_path(None)
    assert s.state.path is None


def test_the_keys_are_in_the_one_table_and_a_d_are_left_free(qapp, shell):
    from PySide6 import QtCore, QtGui

    w, K = shell, QtCore.Qt.Key
    rows = {k: what for k, what, _b in w.key_table()}
    assert "S" in rows and "⌫" in rows and "slit" in rows["Esc"]
    seqs = [QtGui.QKeySequence(seq) for seq, _fn in w.action_registry.binds()]
    for k in (K.Key_S, K.Key_Backspace, K.Key_Delete):
        assert QtGui.QKeySequence(k) in seqs
    for k in (K.Key_A, K.Key_D):                                    # walking along the slit, later (F75)
        assert QtGui.QKeySequence(k) not in seqs
    html = w.action_registry.sheet_html(w.palette())
    assert "draw a slit" in html and "remove the slit" in html and "S, then click on the image" in html


def test_the_slit_takes_the_looks_colour_and_the_theme(qapp, shell):
    from PySide6 import QtGui

    from explorer.look import get_look
    from explorer.ui import style
    from explorer.ui.imageview import CURSOR_PEN

    w = shell
    w.session.set_path(((5.5, 5.5), (30.5, 40.5)))
    spin(qapp, lambda: w.slit_hint.isVisible())
    m = w.slit_tool.marks[0]
    assert m.colour() == CURSOR_PEN.color()                         # classic: the cursor's red
    w.set_look(get_look("modern"))
    assert m.colour() == style.accent() and m.dots.opts["pen"].color() == style.accent()
    dark = w.slit_hint.grab().toImage().pixelColor(3, w.slit_hint.height() // 2)
    w.set_theme("light")
    assert style.is_light() and w.slit_hint.light and m.colour() == style.accent()
    light = w.slit_hint.grab().toImage().pixelColor(3, w.slit_hint.height() // 2)
    assert QtGui.QColor(light).lightness() > QtGui.QColor(dark).lightness() + 100
    w.set_theme("dark")
    assert not w.slit_hint.light


def test_in_the_2x2_view_the_slit_is_on_the_four_and_drawn_on_any(qapp, shell):
    from PySide6 import QtCore

    w, C = shell, QtCore.Qt.CursorShape
    w.session.set_path(((5.5, 5.5), (30.5, 40.5)))
    spin(qapp, lambda: len(line_xy(w.slit_tool.marks[0].line)) > 2)
    w.set_grid(True)
    assert w.grid is not None and w.grid.isVisible() and len(w.slit_tool.marks) == 5
    main = line_xy(w.slit_tool.marks[0].line)
    assert all(np.array_equal(line_xy(m.line), main) for m in w.slit_tool.marks[1:])
    assert w.slit_hint.isVisible() and w.slit_hint.y() >= 30         # below the panel's Stokes label
    s0, locked0 = w.session.state.s, w.session.state.locked
    w.set_slit_mode(True)
    assert all(v.widget.viewport().cursor().shape() == C.BitmapCursor for v in w.grid.views)
    q = w.grid.views[2]
    scene_click(q, 10.2, 12.7)
    scene_click(q, 40.1, 50.9)
    scene_click(q, 40.1, 50.9, double=True)
    st = w.session.state
    assert st.path == ((10.5, 12.5), (40.5, 50.5)) and not w.slit_tool.mode
    assert st.s == s0 and st.locked == locked0                      # the panel's click was the slit's
    assert all(np.allclose(line_xy(m.line)[-1], (40.5, 50.5)) for m in w.slit_tool.marks)
    assert all(v.widget.viewport().cursor().shape() == C.CrossCursor for v in w.grid.views)


def test_in_glass_the_accent_and_the_hint_below_the_colour_key(qapp, shell):
    from PySide6 import QtCore

    from explorer.look import get_look
    from explorer.ui import glass

    w = shell
    w.set_look(get_look("glass"))
    for _ in range(5):
        qapp.processEvents()
    assert w.slit_tool.marks[0].colour() == glass.accent()
    key(w, QtCore.Qt.Key.Key_S)
    assert w.slit_tool.mode and w.slit_hint.isVisible()
    k = w.colour_key
    assert w.slit_hint.x() == glass.MARGIN and w.slit_hint.y() >= k.y() + k.height()
    click(w.view, 8.5, 8.5)
    click(w.view, 30.5, 30.5)
    click(w.view, 30.5, 30.5, double=True)
    assert w.session.state.path == ((8.5, 8.5), (30.5, 30.5))
    w.set_look(get_look("classic"))
    assert w.slit_hint.pos() == QtCore.QPoint(8, 8) and w.slit_tool.marks[0].colour() != glass.accent()
