"""The slit panel (ROADMAP E7.2), offscreen: no Slit tab until the first S; S brings it as lambda-t's tab, in front,
and Esc without a slit takes it away; a finished slit puts it in front with its time and spectral slices, the cube's
values; the t and lambda markers, and the cursor's where it lies on the slit; a click picks t or lambda and the
point of the slit, locked; a right click releases; ⌫ removes it and reset does not bring it back; no pyqtgraph menu;
its slices live while the slit is drawn; the theme, the looks' markers and colour maps, the 2x2 view and glass."""
import time

import numpy as np
import pytest
from astropy.io import fits

from explorer.data.slits import slit_path, slit_pixels
from explorer.testing import synth

SHAPE = (3, 4, 5, 60, 48)                               # t, s, lambda, y, x


def spin(qapp, until=lambda: False, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("slitpanel"), "c", shape=SHAPE, icube=False)
    return d["im"], fits.getdata(d["im"]).astype(np.float32)


@pytest.fixture(params=["per-pixel", "frames"])
def shell(request, qapp, cube):
    from PySide6 import QtGui, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.ui import style
    from explorer.ui.shell import Shell

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    ds = Dataset.open(cube[0], no_sp=request.param == "frames")
    w = Shell(ds, title="c_im.fits")
    w.setGeometry(60, 50, 1100, 700)
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


def pixels(pts):
    return slit_pixels(slit_path(np.asarray(pts, float)), SHAPE[3], SHAPE[4])


def want(data, pts, t, s, l):  # noqa: E741
    iy, ix = pixels(pts)
    return data[:, s, l, iy, ix], data[t, s, :, iy, ix].T


def key(w, k):
    from PySide6.QtTest import QTest

    QTest.keyClick(w, k)


def front(w):
    """The Slit tab in front: the core reads for it (a tab behind is moved off screen, not hidden)."""
    return "slit" in w.session.state.panels


def complete(qapp, w, pts, data):
    """Until the slices shown are the slit's, whole: every pixel's block read."""
    p = w.slit_panel

    def done():
        st = w.session.state
        ts, sl = want(data, pts, st.t, st.s, st.l)
        a, b = p.ts_img.image, p.sl_img.image
        return (a is not None and b is not None and np.array_equal(a, ts, equal_nan=True)
                and np.array_equal(b, sl, equal_nan=True))
    return spin(qapp, done)


def make(qapp, w, pts, data):
    w.set_slit_mode(True)
    for x, y in pts:
        w.slit_tool.add(x, y)
    w.slit_tool.finish()
    assert complete(qapp, w, pts, data)


A = ((6.5, 8.5), (40.5, 50.5))
B = ((5.5, 40.5), (24.5, 10.5), (44.5, 30.5))


def test_no_tab_until_s_then_lambda_ts_tab_in_front_and_esc_without_a_slit_takes_it(qapp, shell):
    from PySide6 import QtCore

    w, K = shell, QtCore.Qt.Key
    assert w.slit_dock.isHidden() and not w.slit_dock.toggleViewAction().isEnabled() and not front(w)
    key(w, K.Key_S)
    assert spin(qapp, lambda: front(w))
    assert not w.slit_dock.isHidden() and w.slit_dock in w.tabifiedDockWidgets(w.lt_dock)
    assert w.slit_dock.toggleViewAction().isEnabled()
    assert spin(qapp, lambda: "lambda_t" not in w.session.state.panels)    # lambda-t behind: not read
    key(w, K.Key_Escape)
    assert spin(qapp, lambda: w.slit_dock.isHidden())
    assert not w.slit_dock.toggleViewAction().isEnabled() and not front(w)
    assert spin(qapp, lambda: "lambda_t" in w.session.state.panels)        # lambda-t back in front


def test_a_finished_slit_shows_its_slices_the_cubes_values(qapp, shell, cube):
    w = shell
    make(qapp, w, B, cube[1])
    assert front(w)
    st = w.session.state
    ts, sl = want(cube[1], B, st.t, st.s, st.l)
    np.testing.assert_array_equal(w.slit_panel.ts_img.image, ts)
    np.testing.assert_array_equal(w.slit_panel.sl_img.image, sl)
    n = len(pixels(B)[0])
    assert w.slit_panel.ts.vb.viewRange()[0] == [0, n] and w.slit_panel.sl.vb.viewRange()[0] == [0, n]
    assert w.slit_panel.ts.getAxis("bottom").labelText == "along the slit [px]"


def test_t_lambda_and_stokes_change_the_slices_and_move_the_markers(qapp, shell, cube):
    from PySide6 import QtCore

    w, K = shell, QtCore.Qt.Key
    make(qapp, w, A, cube[1])
    key(w, K.Key_Up)                                                # t + 1
    key(w, K.Key_Left)                                              # lambda - 1
    key(w, K.Key_4)                                                 # Stokes V
    st = w.session.state
    ts, sl = want(cube[1], A, st.t, st.s, st.l)
    p = w.slit_panel
    assert spin(qapp, lambda: p.ts_img.image is not None and np.array_equal(p.ts_img.image, ts, equal_nan=True)
                and np.array_equal(p.sl_img.image, sl, equal_nan=True))
    assert p.t_line.value() == st.t + 0.5 and p.l_line.value() == st.l + 0.5
    lo, hi = p.ts_img.levels                                        # Q U V symmetric about 0, as lambda-t's
    assert lo == -hi


def test_the_cursors_line_where_it_lies_on_the_slit(qapp, shell, cube):
    w = shell
    make(qapp, w, A, cube[1])
    iy, ix = pixels(A)
    w.session.lock(False)
    w.session.hover(int(iy[7]), int(ix[7]))
    first = min(i for i in range(len(iy)) if (iy[i], ix[i]) == (iy[7], ix[7]))
    assert spin(qapp, lambda: all(ln.isVisible() and ln.value() == first + 0.5 for ln in w.slit_panel.cur_lines))
    w.session.hover(int(iy[7]), int(ix[7]) + 9)                    # off the slit
    assert spin(qapp, lambda: not any(ln.isVisible() for ln in w.slit_panel.cur_lines))


def press(w, plot, x, y, button=None):
    from PySide6 import QtCore
    from PySide6.QtTest import QTest

    vp = w.slit_panel.w.viewport()
    pt = w.slit_panel.w.mapFromScene(plot.vb.mapViewToScene(QtCore.QPointF(x, y)))
    QTest.mouseClick(vp, button or QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier, pt)


def test_a_click_picks_t_or_lambda_and_puts_the_cursor_on_the_slit_locked(qapp, shell, cube):
    from PySide6 import QtCore

    w = shell
    make(qapp, w, A, cube[1])
    iy, ix = pixels(A)
    p = w.slit_panel
    w.session.lock(False)
    i = len(iy) // 3
    press(w, p.ts, i + 0.5, 2.5)
    assert spin(qapp, lambda: w.session.state.t == 2 and w.session.state.locked)
    y, x = w.session.state.cursor
    j = p.on.get((y, x))
    assert j is not None and abs(j - i) <= 1
    press(w, p.sl, i + 0.5, 1.5)
    assert spin(qapp, lambda: w.session.state.l == 1)
    press(w, p.sl, i + 0.5, 1.5, QtCore.Qt.MouseButton.RightButton)     # releases from this panel too
    assert spin(qapp, lambda: not w.session.state.locked)


def test_backspace_removes_it_and_reset_does_not_bring_it_back(qapp, shell, cube):
    from PySide6 import QtCore

    w = shell
    make(qapp, w, A, cube[1])
    key(w, QtCore.Qt.Key.Key_Backspace)
    assert spin(qapp, lambda: w.slit_dock.isHidden())
    assert not w.slit_dock.toggleViewAction().isEnabled() and w.slit_panel.ts_img.image is None
    w.reset_panels()
    spin(qapp, timeout=0.2)
    assert w.slit_dock.isHidden() and not w.lt_dock.isHidden()


def test_no_pyqtgraph_menu_and_no_zoom(qapp, shell):
    p = shell.slit_panel
    for pl in (p.ts, p.sl):
        assert not pl.menuEnabled() and not pl.vb.menuEnabled()
        assert pl.vb.state["mouseEnabled"] == [False, False]


def test_its_slices_live_while_the_slit_is_drawn(qapp, shell, cube):
    from PySide6 import QtCore

    w = shell
    w.set_slit_mode(True)
    w.slit_tool.add(*A[0])
    w.view._moved(w.view.vb.mapViewToScene(QtCore.QPointF(*A[1])))     # the pointer at the other end
    assert w.session.state.path is None and spin(qapp, lambda: front(w))
    assert complete(qapp, w, A, cube[1])                            # before the double click
    st = w.session.state
    np.testing.assert_array_equal(w.slit_panel.sl_img.image, want(cube[1], A, st.t, st.s, st.l)[1])
    w.set_slit_mode(False)                                          # Esc: no slit, its tab gone
    assert spin(qapp, lambda: w.slit_dock.isHidden() and w.slit_panel.ts_img.image is None)


def test_the_theme_the_looks_markers_and_colour_maps(qapp, shell, cube):
    from explorer.look import get_look
    from explorer.ui import style
    from explorer.ui.imageview import CURSOR_PEN

    w = shell
    make(qapp, w, A, cube[1])
    p = w.slit_panel
    assert p.t_line.pen.color() == CURSOR_PEN.color() and p.ts_img.lut is None          # classic: red, grey
    s = w.session.state.s
    w.cycle_colours(1)                                              # C in classic: the slices on the map too
    lut = w.colours.lut(s)
    assert lut is not None and p.ts_img.lut is lut and p.sl_img.lut is lut
    w.cycle_colours(-1)
    assert p.ts_img.lut is None and p.sl_img.lut is None            # grey again, as it started
    w.set_look(get_look("modern"))
    assert p.t_line.pen.color() == style.accent() and p.cur_lines[0].pen.color() == style.accent()
    assert p.ts_img.lut is w.colours.lut(s) and p.sl_img.lut is w.colours.lut(s)    # grey until C
    w.cycle_colours(1)                                              # C: the next map, the slices with it
    lut = w.colours.lut(s)
    assert lut is not None and p.ts_img.lut is lut and p.sl_img.lut is lut
    w.set_theme("light")
    ink = p.ts.getAxis("left").pen().color()
    assert style.is_light() and ink.lightness() < 128
    w.set_theme("dark")
    assert p.ts.getAxis("left").pen().color().lightness() > 128
    w.set_look(get_look("classic"))
    assert p.t_line.pen.color() == CURSOR_PEN.color() and p.ts_img.lut is lut      # the map chosen stays


def test_a_slit_drawn_in_the_2x2_view_has_its_panel(qapp, shell, cube):
    w = shell
    w.set_grid(True)
    assert w.grid is not None and w.grid.isVisible()
    make(qapp, w, B, cube[1])
    assert front(w)
    st = w.session.state
    np.testing.assert_array_equal(w.slit_panel.ts_img.image, want(cube[1], B, st.t, st.s, st.l)[0])


def test_in_glass_it_floats_over_lambda_ts_place(qapp, shell, cube):
    from explorer.look import get_look

    w = shell
    w.set_look(get_look("glass"))
    spin(qapp, timeout=0.3)
    make(qapp, w, A, cube[1])
    assert not w.slit_dock.isHidden() and front(w)
    assert w.slit_dock.isFloating() == w.lt_dock.isFloating()      # docked, it would narrow the image
    w.set_look(get_look("classic"))
    spin(qapp, timeout=0.2)
    assert not w.slit_dock.isFloating() and not w.slit_dock.isHidden()


@pytest.mark.parametrize("look", ["classic", "modern", "glass"])
def test_through_the_start_up_a_slit_drawn_with_the_mouse_opens_its_panel_with_its_slices(qapp, monkeypatch, look):
    """As `explorer demo` shows the window (ui.app.start, the demo's synthetic cube): S, a click, the pointer moved
    and a double click on the image; the Slit panel is on screen, in front, with both slices, the cube's values."""
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtTest import QTest

    from explorer import demo
    from explorer.ui.app import start

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    cube = demo.synthetic_cube()
    s = start(cube, look=look, theme="dark", saved_layout=False)
    assert s is not None
    w = s.shell
    try:
        w.resize(1300, 850)
        assert spin(qapp, lambda: w.first_image_s is not None)
        spin(qapp, timeout=0.3)
        assert w.slit_dock.isHidden()
        B, E = QtCore.Qt.MouseButton, QtCore.QEvent.Type
        vp, vb = w.view.widget.viewport(), w.view.vb

        def send(kind, x, y, button=B.NoButton, buttons=B.NoButton):
            p = QtCore.QPointF(w.view.widget.mapFromScene(vb.mapViewToScene(QtCore.QPointF(x, y))))
            QtWidgets.QApplication.sendEvent(vp, QtGui.QMouseEvent(kind, p, vp.mapToGlobal(p), button, buttons,
                                                                    QtCore.Qt.KeyboardModifier.NoModifier))
            qapp.processEvents()

        QTest.keyClick(w, QtCore.Qt.Key.Key_S)
        assert w.slit_tool.mode
        p0, p1 = (60.5, 70.5), (190.5, 170.5)
        send(E.MouseButtonPress, *p0, B.LeftButton, B.LeftButton)
        send(E.MouseButtonRelease, *p0, B.LeftButton)
        for f in np.linspace(0.1, 1, 10):                           # the pointer to the far end: live slices
            send(E.MouseMove, p0[0] + f * (p1[0] - p0[0]), p0[1] + f * (p1[1] - p0[1]))
        send(E.MouseButtonPress, *p1, B.LeftButton, B.LeftButton)
        send(E.MouseButtonRelease, *p1, B.LeftButton)
        send(E.MouseButtonDblClick, *p1, B.LeftButton, B.LeftButton)
        send(E.MouseButtonRelease, *p1, B.LeftButton)
        path = w.session.state.path
        assert path is not None and not w.slit_tool.mode
        data = fits.getdata(cube).astype(np.float32)
        iy, ix = slit_pixels(slit_path(np.asarray(path, float)), w.dataset.ny, w.dataset.nx)
        p = w.slit_panel

        def shown():
            st = w.session.state
            a, b = p.ts_img.image, p.sl_img.image
            return (a is not None and b is not None and np.array_equal(a, data[:, st.s, st.l, iy, ix], equal_nan=True)
                    and np.array_equal(b, data[st.t, st.s, :, iy, ix].T, equal_nan=True))
        assert spin(qapp, shown)
        assert w.slit_dock.isVisible() and not w.slit_dock.visibleRegion().isEmpty() and front(w)
        assert np.isfinite(p.ts_img.image).any() and np.isfinite(p.sl_img.image).any()
        assert p.w.isVisible() and p.w.width() > 100 and p.w.height() > 100
    finally:
        w.close()
        s.close()
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)
        qapp.setProperty("explorer_light", False)
        import pyqtgraph as pg

        pg.setConfigOptions(background="k", foreground="d")


def test_a_layout_saved_with_the_slit_open_starts_without_its_panel(qapp, monkeypatch, tmp_path, cube):
    """The saved layout's restore shows every hidden panel; the slit's stays hidden without a slit (the prototype's
    F70a), and comes as lambda-t's tab with the next one."""
    from PySide6 import QtGui, QtWidgets

    from explorer.ui.app import start

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("EXPLORER_LAYOUT", str(tmp_path / "layout.ini"))
    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    try:
        s = start(cube[0], look="classic", theme="dark")
        w = s.shell
        assert spin(qapp, lambda: w.first_image_s is not None)
        make(qapp, w, A, cube[1])
        assert not w.slit_dock.isHidden()
        w.close()                                       # the layout saved with the slit's tab open
        s.close()
        s = start(cube[0], look="classic", theme="dark")
        w = s.shell
        assert spin(qapp, lambda: w.first_image_s is not None)
        spin(qapp, timeout=0.3)
        assert w.slit_dock.isHidden() and not front(w) and not w.lt_dock.isHidden()
        make(qapp, w, B, cube[1])
        assert front(w) and w.slit_dock in w.tabifiedDockWidgets(w.lt_dock)
        w.close()
        s.close()
    finally:
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)
        qapp.setProperty("explorer_light", False)
        import pyqtgraph as pg

        pg.setConfigOptions(background="k", foreground="d")
