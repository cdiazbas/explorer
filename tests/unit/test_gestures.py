"""Picks on the panels (ROADMAP E4.8), offscreen, with mouse events on the panels' viewports: a press on a spectrum
picks lambda, a drag the latest position once per event-loop pass, a press on lambda-t picks t and lambda, a right
click releases the cursor; the spectra no longer zoom or pan, and each panel's pointer names its action."""
import time

import pytest

from explorer.testing import synth

SHAPE = (6, 4, 21, 48, 40)


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("gestures"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    w.resize(1400, 900)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    for _ in range(10):
        qapp.processEvents()
    yield w
    w.close()
    ds.close()


def mouse(view, scene_pt, kind, button=None, buttons=None):
    """A mouse event on view's viewport at a scene point."""
    from PySide6 import QtCore, QtGui, QtWidgets

    B, E = QtCore.Qt.MouseButton, QtCore.QEvent.Type
    vp = view.viewport()
    p = QtCore.QPointF(view.mapFromScene(scene_pt))
    ev = QtGui.QMouseEvent(kind, p, vp.mapToGlobal(p), button if button is not None else B.NoButton,
                           buttons if buttons is not None else B.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(vp, ev)
    return E


def scene_of(plot, x, y=None):
    from PySide6 import QtCore

    vb = plot.vb
    y = sum(vb.viewRange()[1]) / 2 if y is None else y
    return vb.mapViewToScene(QtCore.QPointF(x, y))


def test_a_press_on_a_spectrum_picks_lambda_and_a_drag_the_latest(qapp, shell):
    from PySide6 import QtCore

    B, E = QtCore.Qt.MouseButton, QtCore.QEvent.Type
    sp, s = shell.spectra, shell.session
    plot = sp.plots[3]                                  # any of the four: V
    mouse(sp.w, scene_of(plot, sp.xl[5]), E.MouseButtonPress, B.LeftButton, B.LeftButton)
    assert s.state.l == 5                               # at once, on the press
    for k in (8, 11, 14):                               # a drag within one pass: only the last counts
        mouse(sp.w, scene_of(plot, sp.xl[k]), E.MouseMove, B.NoButton, B.LeftButton)
    assert s.state.l == 5
    assert spin(qapp, lambda: s.state.l == 14)
    mouse(sp.w, scene_of(plot, sp.xl[14]), E.MouseButtonRelease, B.LeftButton, B.NoButton)


def test_a_press_on_lambda_t_picks_t_and_lambda(qapp, shell):
    from PySide6 import QtCore

    B, E = QtCore.Qt.MouseButton, QtCore.QEvent.Type
    lt = shell.lambda_t
    plot = lt.w.getPlotItem()
    mouse(lt.w, scene_of(plot, 7.5, 3.5), E.MouseButtonPress, B.LeftButton, B.LeftButton)
    mouse(lt.w, scene_of(plot, 7.5, 3.5), E.MouseButtonRelease, B.LeftButton, B.NoButton)
    assert (shell.session.state.l, shell.session.state.t) == (7, 3)


def test_a_right_click_on_a_panel_releases_the_cursor(qapp, shell):
    shell.session.lock(True)
    ev = type("Click", (), {"button": lambda self: __import__("PySide6").QtCore.Qt.MouseButton.RightButton})()
    shell._panel_click(ev)
    assert not shell.session.state.locked


def test_no_zoom_on_the_spectra_and_each_panel_names_its_action(qapp, shell):
    from PySide6 import QtCore

    C = QtCore.Qt.CursorShape
    assert all(p.vb.state["mouseEnabled"] == [False, False] for p in shell.spectra.plots)
    assert shell.spectra.w.viewport().cursor().shape() == C.SizeHorCursor
    assert shell.lambda_t.w.viewport().cursor().shape() == C.SizeAllCursor
    assert shell.view.widget.viewport().cursor().shape() == C.CrossCursor


def test_a_right_click_opens_no_menu(qapp, shell):
    """Neither pyqtgraph's menu on the image nor QMainWindow's over the toolbar, the dock titles or a slider (the
    prototype's smoke.py 'no context menu' checks)."""
    from PySide6 import QtCore, QtGui, QtWidgets

    opened = []
    close = QtCore.QTimer(interval=20)                  # an open menu runs its own event loop: note it, close it

    def note():
        p = QtWidgets.QApplication.activePopupWidget()
        if p is not None:
            opened.append(type(p).__name__)
            p.close()
    close.timeout.connect(note)
    close.start()
    try:
        slider = next(iter(shell.nav.sliders.values()))
        for w in (shell.view.widget.viewport(), shell.nav.tb, slider, shell.spec_dock):
            p = w.rect().center()
            ev = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Reason.Mouse, p, w.mapToGlobal(p))
            QtWidgets.QApplication.sendEvent(w, ev)
            spin(qapp, lambda: False, 0.05)
        vb = shell.view.vb
        B = QtCore.Qt.MouseButton
        mouse(shell.view.widget, vb.mapViewToScene(QtCore.QPointF(10, 10)), QtCore.QEvent.Type.MouseButtonPress,
              B.RightButton, B.RightButton)
        mouse(shell.view.widget, vb.mapViewToScene(QtCore.QPointF(10, 10)), QtCore.QEvent.Type.MouseButtonRelease,
              B.RightButton, B.NoButton)
        spin(qapp, lambda: False, 0.1)
    finally:
        close.stop()
    assert opened == []
