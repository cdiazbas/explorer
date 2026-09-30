"""The y range of a spectrum by hand on its axis strip (ROADMAP E4.1), offscreen: a drag moves it and keeps it on that
plot, the right button and the wheel stretch it, a double click gives it back; over the curve a press picks lambda."""
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
    return synth.write_dataset(tmp_path_factory.mktemp("axisdrag"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    w.resize(1400, 900)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and "spectra" in w.last)
    assert spin(qapp, lambda: all(r is not None for r in w.scheduler.yrange.r))
    for _ in range(10):
        qapp.processEvents()
    yield w
    w.close()
    ds.close()


def send(view, pos, kind, button=None, buttons=None, delta=0):
    from PySide6 import QtCore, QtGui, QtWidgets

    B = QtCore.Qt.MouseButton
    vp = view.viewport()
    p = QtCore.QPointF(pos)
    if kind == QtCore.QEvent.Type.Wheel:
        ev = QtGui.QWheelEvent(p, vp.mapToGlobal(p), QtCore.QPoint(), QtCore.QPoint(0, delta), B.NoButton,
                               QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
    else:
        ev = QtGui.QMouseEvent(kind, p, vp.mapToGlobal(p), button if button is not None else B.NoButton,
                               buttons if buttons is not None else B.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(vp, ev)


def axis_point(shell, k):
    from PySide6 import QtCore

    ax = shell.spectra.plots[k].getAxis("left")
    r = ax.mapRectToScene(QtCore.QRectF(0, 0, ax.width(), ax.height()))
    return shell.spectra.w.mapFromScene(r.center())


def test_a_drag_on_the_axis_moves_the_range_and_keeps_it_on_that_plot(qapp, shell):
    from PySide6 import QtCore

    B, E = QtCore.Qt.MouseButton, QtCore.QEvent.Type
    yr, sp = shell.scheduler.yrange, shell.spectra
    lo, hi = yr.r[0]
    l0 = shell.session.state.l
    p = axis_point(shell, 0)
    h = sp.plots[0].vb.sceneBoundingRect().height()
    send(sp.w, p, E.MouseButtonPress, B.LeftButton, B.LeftButton)
    send(sp.w, p + QtCore.QPoint(0, int(h / 4)), E.MouseMove, B.NoButton, B.LeftButton)
    send(sp.w, p + QtCore.QPoint(0, int(h / 4)), E.MouseButtonRelease, B.LeftButton, B.NoButton)
    nlo, nhi = yr.r[0]
    assert nhi - nlo == pytest.approx(hi - lo) and nlo == pytest.approx(lo + (hi - lo) / 4, rel=0.05)
    assert 0 in yr.manual_k and shell.session.state.l == l0                  # the axis, not a pick
    shell.session.hover(10, 12)                                             # another pixel: the range stays
    assert spin(qapp, lambda: shell.last["spectra"][1] == (10, 12))
    for _ in range(10):
        qapp.processEvents()
    assert yr.r[0] == (nlo, nhi)


def test_stretch_with_the_right_button_and_the_wheel_then_back_with_a_double_click(qapp, shell):
    from PySide6 import QtCore

    B, E = QtCore.Qt.MouseButton, QtCore.QEvent.Type
    yr, sp = shell.scheduler.yrange, shell.spectra
    p = axis_point(shell, 3)
    lo, hi = yr.r[3]
    send(sp.w, p, E.MouseButtonPress, B.RightButton, B.RightButton)
    send(sp.w, p + QtCore.QPoint(0, 70), E.MouseMove, B.NoButton, B.RightButton)          # down: wider
    send(sp.w, p + QtCore.QPoint(0, 70), E.MouseButtonRelease, B.RightButton, B.NoButton)
    assert yr.r[3][1] - yr.r[3][0] > (hi - lo) * 1.5
    wide = yr.r[3][1] - yr.r[3][0]
    send(sp.w, p, E.Wheel, delta=120)                                                     # a notch in: narrower
    assert yr.r[3][1] - yr.r[3][0] == pytest.approx(wide * 0.85)
    send(sp.w, p, E.MouseButtonDblClick, B.LeftButton, B.LeftButton)
    assert 3 not in yr.manual_k


def test_over_the_curve_a_press_still_picks_lambda(qapp, shell):
    from PySide6 import QtCore

    B, E = QtCore.Qt.MouseButton, QtCore.QEvent.Type
    sp = shell.spectra
    vb = sp.plots[1].vb
    scene = vb.mapViewToScene(QtCore.QPointF(sp.xl[4], sum(vb.viewRange()[1]) / 2))
    send(sp.w, sp.w.mapFromScene(scene), E.MouseButtonPress, B.LeftButton, B.LeftButton)
    send(sp.w, sp.w.mapFromScene(scene), E.MouseButtonRelease, B.LeftButton, B.NoButton)
    assert shell.session.state.l == 4
