"""The slit in the window's layout and keys (ROADMAP E7.4), offscreen: A and D walk the cursor along the slit (the
prototype's F75), and say what they are for without one; the slit's panel is never shown by a layout, a reset or I
without a slit (F21, F70a), in classic and in glass, and its tab stays while a slit is being drawn; out of glass it
comes back as lambda-t's tab (F70b); the native macOS style's seams on its dock too (F59)."""
import time

import numpy as np
import pytest
from astropy.io import fits

from explorer.data.slits import slit_path, slit_pixels
from explorer.testing import synth

SHAPE = (3, 4, 5, 60, 48)                               # t, s, lambda, y, x
A = ((6.5, 8.5), (40.5, 50.5))
B = ((5.5, 40.5), (24.5, 10.5), (44.5, 30.5))


def spin(qapp, until=lambda: False, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("slitlayout"), "c", shape=SHAPE, icube=False)
    return d["im"], fits.getdata(d["im"]).astype(np.float32)


def _restore_app(qapp, name, pal):
    import pyqtgraph as pg
    from PySide6 import QtWidgets

    qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
    qapp.setPalette(pal)
    qapp.setProperty("explorer_light", False)
    pg.setConfigOptions(background="k", foreground="d")


@pytest.fixture
def shell(qapp, cube):
    from PySide6 import QtGui

    from explorer.data.dataset import Dataset
    from explorer.ui import style
    from explorer.ui.shell import Shell

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    ds = Dataset.open(cube[0])
    w = Shell(ds, title="c_im.fits")
    w.setGeometry(60, 50, 1100, 700)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    for _ in range(10):
        qapp.processEvents()
    yield w
    w.close()
    ds.close()
    _restore_app(qapp, name, pal)


def pixels(pts):
    return slit_pixels(slit_path(np.asarray(pts, float)), SHAPE[3], SHAPE[4])


def make(qapp, w, pts):
    w.set_slit_mode(True)
    for x, y in pts:
        w.slit_tool.add(x, y)
    w.slit_tool.finish()
    assert spin(qapp, lambda: w.slit_panel.pix is not None and w.session.state.path is not None)


def key(qapp, w, k):
    from PySide6.QtTest import QTest

    QTest.keyClick(w, k)
    qapp.processEvents()


def wear(qapp, w, name):
    from explorer.look import get_look

    w.set_look(get_look(name))
    spin(qapp, timeout=0.3)


def front(w):
    return "slit" in w.session.state.panels


# ---------------------------------------------------------------- A and D (F75)
def test_a_and_d_walk_along_the_slit_the_cursor_locked_from_off_it_the_nearest_point_first(qapp, shell):
    from PySide6 import QtCore
    from PySide6.QtTest import QTest

    w, K = shell, QtCore.Qt.Key
    make(qapp, w, A)
    iy, ix = pixels(A)
    on = w.slit_panel.on
    w.session.lock(False)
    w.session.hover(int(iy[0]) + 9, int(ix[0]) - 5)                 # off the slit, near its start
    key(qapp, w, K.Key_D)
    first = on.get(tuple(w.session.state.cursor))
    near = int(np.argmin((iy - (iy[0] + 9)) ** 2 + (ix - (ix[0] - 5)) ** 2))
    assert first is not None and w.session.state.locked
    assert tuple(w.session.state.cursor) == (int(iy[near]), int(ix[near]))
    seen = [first]
    for _ in range(5):
        key(qapp, w, K.Key_D)
        seen.append(on.get(tuple(w.session.state.cursor)))
    assert all(b is not None and b > a for a, b in zip(seen, seen[1:], strict=False)), seen
    assert len({(int(iy[i]), int(ix[i])) for i in seen}) == len(seen)          # a pixel per press
    key(qapp, w, K.Key_A)
    assert on.get(tuple(w.session.state.cursor)) == seen[-2] and w.session.state.locked
    i0 = on.get(tuple(w.session.state.cursor))
    for _ in range(20):                                                 # held: the key's auto-repeat
        QTest.keyPress(w, K.Key_D)
        qapp.processEvents()
    QTest.keyRelease(w, K.Key_D)
    held = on.get(tuple(w.session.state.cursor))
    assert held is not None and held > i0
    for _ in range(len(iy)):                                            # at the end it stays there
        w.slit_step(1)
    assert tuple(w.session.state.cursor) == (int(iy[-1]), int(ix[-1]))
    for _ in range(len(iy)):
        w.slit_step(-1)
    assert tuple(w.session.state.cursor) == (int(iy[0]), int(ix[0]))


def test_a_and_d_follow_a_curved_slit_and_the_one_being_drawn(qapp, shell):
    from PySide6 import QtCore

    w, K = shell, QtCore.Qt.Key
    make(qapp, w, B)
    iy, ix = pixels(B)
    w.session.lock(False)
    w.session.hover(int(iy[len(iy) // 2]), int(ix[len(iy) // 2]))
    i = w.slit_panel.on[tuple(w.session.state.cursor)]
    key(qapp, w, K.Key_D)
    assert w.slit_panel.on[tuple(w.session.state.cursor)] > i
    w.set_slit_mode(True)                                               # a new one, being drawn: its pixels
    w.slit_tool.add(*A[0])
    w.view._moved(w.view.vb.mapViewToScene(QtCore.QPointF(*A[1])))
    assert spin(qapp, lambda: w.slit_panel.n == len(pixels(A)[0]))
    w.slit_step(1)
    assert w.slit_panel.on.get(tuple(w.session.state.cursor)) is not None


def test_without_a_slit_a_and_d_leave_the_cursor_and_say_what_they_are_for(qapp, shell):
    from PySide6 import QtCore

    w, K = shell, QtCore.Qt.Key
    w.session.lock(False)
    w.session.hover(20, 20)
    key(qapp, w, K.Key_D)
    key(qapp, w, K.Key_A)
    assert tuple(w.session.state.cursor) == (20, 20) and not w.session.state.locked
    assert "S draws one" in w.statusBar().currentMessage()
    make(qapp, w, A)
    key(qapp, w, K.Key_Backspace)                                       # removed: nothing to walk again
    assert spin(qapp, lambda: w.slit_panel.pix is None)
    w.session.lock(False)
    w.session.hover(20, 20)
    key(qapp, w, K.Key_D)
    assert tuple(w.session.state.cursor) == (20, 20) and not w.session.state.locked


def test_a_and_d_on_the_sheet_and_from_the_terminal(qapp, shell):
    from PySide6 import QtCore

    from explorer.ui import termkeys

    w, K = shell, QtCore.Qt.Key
    rows = {k: what for k, what, _b in w.action_registry.rows}
    assert "previous, next point" in rows.get("A  D", "")
    assert "A&nbsp;&nbsp;D" in w.sheet.text() or "A  D" in w.sheet.text()
    acts = termkeys.actions_of(w)
    none = QtCore.Qt.KeyboardModifier.NoModifier
    make(qapp, w, A)
    iy, ix = pixels(A)
    w.session.lock(False)
    w.session.hover(int(iy[3]), int(ix[3]))
    acts[termkeys.combined(K.Key_D, none)]()
    assert w.slit_panel.on[tuple(w.session.state.cursor)] > w.slit_panel.on[(int(iy[3]), int(ix[3]))]
    acts[termkeys.combined(K.Key_A, none)]()
    assert tuple(w.session.state.cursor) == (int(iy[3]), int(ix[3])) and w.session.state.locked


# ---------------------------------------------------------------- the layout (F21, F70a, F70b)
def test_reset_keeps_the_slits_tab_while_one_is_being_drawn_and_never_brings_it_without(qapp, shell):
    w = shell
    w.set_slit_mode(True)                                               # S: its tab, the slices live as it is drawn
    assert spin(qapp, lambda: front(w))
    w.reset_panels()
    spin(qapp, timeout=0.2)
    assert not w.slit_dock.isHidden() and w.slit_dock in w.tabifiedDockWidgets(w.lt_dock)
    assert spin(qapp, lambda: front(w))                                 # in front: what is drawn, live
    w.set_slit_mode(False)                                            # Esc: none drawn, none being drawn
    assert spin(qapp, lambda: w.slit_dock.isHidden())
    w.reset_panels()
    spin(qapp, timeout=0.2)
    assert w.slit_dock.isHidden() and not front(w) and not w.lt_dock.isHidden()


def test_glass_never_shows_the_slits_panel_without_a_slit(qapp, shell):
    """I, the reset button and glass's first placing show the panels; the slit's only with a slit."""
    w = shell
    wear(qapp, w, "glass")
    g = w.glass
    assert spin(qapp, lambda: w.spec_dock.isFloating() and w.lt_dock.isFloating())
    assert w.slit_dock.isHidden()
    w.toggle_panels()
    w.toggle_panels()
    assert w.slit_dock.isHidden() and not w.spec_dock.isHidden() and not w.lt_dock.isHidden()
    g.reset()
    spin(qapp, timeout=0.2)
    assert w.slit_dock.isHidden() and not front(w)
    make(qapp, w, A)                                                    # with one: there, and gone with it
    assert spin(qapp, lambda: not w.slit_dock.isHidden() and w.slit_dock.isFloating())
    w.clear_slit()
    assert spin(qapp, lambda: w.slit_dock.isHidden())
    w.toggle_panels()
    w.toggle_panels()
    g.reset()
    spin(qapp, timeout=0.2)
    assert w.slit_dock.isHidden() and not front(w)


@pytest.mark.parametrize("where", ["classic", "glass"])
def test_out_of_glass_the_slits_panel_is_lambda_ts_tab_again(qapp, shell, where):
    """Drawn before glass or in it: out of glass it is lambda-t's tab, docked, in front."""
    w = shell
    if where == "classic":
        make(qapp, w, A)
    wear(qapp, w, "glass")
    if where == "glass":
        make(qapp, w, A)
    assert spin(qapp, lambda: w.slit_dock.isFloating() and not w.slit_dock.isHidden())
    wear(qapp, w, "classic")
    assert spin(qapp, lambda: w.slit_dock in w.tabifiedDockWidgets(w.lt_dock))
    assert not w.slit_dock.isFloating() and not w.slit_dock.isHidden() and front(w)
    assert not w.spec_dock.isFloating() and not w.lt_dock.isFloating()


@pytest.mark.parametrize("look", ["classic", "glass"])
def test_a_layout_saved_with_the_slit_open_starts_without_its_panel(qapp, monkeypatch, tmp_path, cube, look):
    """Each look's own saved layout (glass keeps its own, LayoutStore.for_look): the slit's panel open at the close,
    floating in glass, is not there at the next start; the window in glass is not held wide by it."""
    from PySide6 import QtGui

    from explorer.ui.app import start

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("EXPLORER_LAYOUT", str(tmp_path / "layout.ini"))
    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    try:
        s = start(cube[0], look=look, theme="dark")
        w = s.shell
        assert spin(qapp, lambda: w.first_image_s is not None)
        spin(qapp, timeout=0.3)
        make(qapp, w, A)
        assert spin(qapp, lambda: not w.slit_dock.isHidden())
        if look == "glass":
            assert spin(qapp, lambda: w.slit_dock.isFloating())
        w.close()
        s.close()
        s = start(cube[0], look=look, theme="dark")
        w = s.shell
        assert spin(qapp, lambda: w.first_image_s is not None)
        spin(qapp, timeout=0.5)
        assert w.slit_dock.isHidden() and not front(w) and not w.lt_dock.isHidden()
        if look == "glass":
            assert w.spec_dock.isFloating() and w.lt_dock.isFloating()
            vb = w.view.vb
            assert w.width() - vb.width() < 10, (w.width(), vb.width())    # nothing docked beside the image
        w.close()
        s.close()
    finally:
        _restore_app(qapp, name, pal)


def test_a_second_window_on_the_same_cube_after_one_closed_with_a_slit(qapp, cube):
    """As the prototype's smoke reopens its window (persist: close, reopen) after drawing a slit: the second window's
    first image is in the Dataset's cache and is shown inside Scheduler(), before the window had the attributes its
    sink reads (AttributeError: 'Shell' object has no attribute 'glass'). It opens, without the slit's panel."""
    from PySide6 import QtGui

    from explorer.data.dataset import Dataset
    from explorer.ui import style
    from explorer.ui.shell import Shell

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    ds = Dataset.open(cube[0])
    try:
        w = Shell(ds, title="c_im.fits")
        w.show()
        assert spin(qapp, lambda: w.first_image_s is not None)
        make(qapp, w, A)
        w.close()
        spin(qapp, timeout=0.1)
        w2 = Shell(ds, title="c_im.fits")
        w2.show()
        assert spin(qapp, lambda: w2.first_image_s is not None and w2.view._full is not None)
        assert w2.slit_dock.isHidden() and w2.session.state.path is None
        w2.close()
    finally:
        ds.close()
        _restore_app(qapp, name, pal)


# ---------------------------------------------------------------- the native macOS style (F59)
def test_the_macos_seams_on_the_slits_dock_too_and_off_with_the_style(qapp, monkeypatch, cube):
    """Under a Mac's native style the main window and its three docks wear MacSeams (ui.cards); a change of theme
    takes the native style and its seams off all of them. The style's name is faked: Qt's macos style exists only
    on a Mac."""
    from PySide6 import QtGui, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.ui import shell as shellmod
    from explorer.ui import style

    real = QtWidgets.QApplication.style()

    class Native:
        def name(self):
            return "macos"

        def __getattr__(self, a):
            return getattr(real, a)

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    native = Native()
    ds = Dataset.open(cube[0])
    with monkeypatch.context() as m:
        m.setattr(shellmod.QtWidgets.QApplication, "style", staticmethod(lambda: native))
        w = shellmod.Shell(ds, title="c_im.fits")
    try:
        seams = w._seams
        assert seams is not None
        assert all(x.style() is seams for x in (w, w.spec_dock, w.lt_dock, w.slit_dock))
        w.set_theme("dark")
        assert w._seams is None and w.slit_dock.style() is not seams
    finally:
        w.close()
        ds.close()
        _restore_app(qapp, name, pal)
