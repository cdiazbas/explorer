"""What is drawn over an image (ui.overlays.OverImage), offscreen: every overlay registered with its image; the pointer
over one is off the image, so the crosshair stays where the pointer left the image; the hot colour key shrinking as
the pointer leaves it onto the image leaves no pixel of the old crosshair on screen."""
import time

import numpy as np
import pytest
from PySide6 import QtCore, QtGui, QtWidgets

from explorer.testing import synth

SHAPE = (3, 4, 5, 90, 80)


def spin(qapp, until=lambda: False, timeout=10.0, passes=0):
    end = time.perf_counter() + timeout
    n = 0
    while not until() and time.perf_counter() < end and (not passes or n < passes):
        qapp.processEvents()
        time.sleep(0.003)
        n += 1
    return until()


@pytest.fixture(scope="module")
def cubes(tmp_path_factory):
    d = tmp_path_factory.mktemp("over")
    main = synth.write_dataset(d, "main", shape=SHAPE, icube=False)["im"]
    other = synth.write_dataset(d, "other", shape=(SHAPE[0], SHAPE[1], 7, SHAPE[3], SHAPE[4]), seed=4, icube=False,
                                sp=False)["im"]
    return main, other


def open_window(qapp, cubes, look="classic", linked=False, size=(1000, 650)):
    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui.shell import Shell

    ds = Dataset.open(cubes[0])
    more = [Dataset.open(cubes[1], executors=ds.executors)] if linked else []
    w = Shell(ds, linked=more, look=get_look(look, {}))
    w.resize(*size)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and all(c.scheduler.img is not None for c in w.linked))
    spin(qapp, passes=40)
    return w, [ds, *more]


@pytest.fixture
def window(qapp, cubes, request):
    w, dss = open_window(qapp, cubes, **getattr(request, "param", {}))
    yield w, qapp
    w.set_theme("dark")                                 # the application's theme, as the next test expects it
    w.close()
    for d in reversed(dss):
        d.close()


def move(widget, p: QtCore.QPoint) -> None:
    g = widget.mapToGlobal(p)
    QtWidgets.QApplication.sendEvent(widget, QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseMove, QtCore.QPointF(p), QtCore.QPointF(g), QtCore.Qt.MouseButton.NoButton,
        QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier))


def pixels(img: QtGui.QImage) -> np.ndarray:
    img = img.convertToFormat(QtGui.QImage.Format.Format_RGB32)
    a = np.frombuffer(img.constBits(), np.uint32).reshape(img.height(), img.bytesPerLine() // 4)[:, :img.width()]
    return a.copy() & 0xFFFFFF


def test_every_overlay_is_registered_with_its_image(qapp, cubes):
    w, dss = open_window(qapp, cubes, linked=True)
    try:
        for c in w.cubes:
            over = c.view.over.items
            assert c.key in over and c.image_lock in over and c.view.stokes in over
        assert w.slit_hint in w.view.over.items
        key = w.main.key
        vp = w.view.widget.viewport()
        assert w.view.over.covers(vp.mapFrom(w.view.widget, key.geometry().center()))
        assert not w.view.over.covers(vp.rect().center())
    finally:
        w.close()
        for d in reversed(dss):
            d.close()


def test_a_move_over_the_stokes_label_is_off_the_image(window):
    """The label lets the mouse through (ui.stokeslabel): over it the crosshair stayed under the pointer; now it stays
    where the pointer left the image, and follows it again back on the image."""
    w, qapp = window
    view, vp = w.view, w.view.widget.viewport()
    assert view.stokes.isVisible()
    move(vp, vp.rect().center())
    spin(qapp, passes=10)
    there = w.session.state.cursor
    label = view.widget.mapFromScene(view.stokes.sceneBoundingRect().center())
    move(vp, label)
    spin(qapp, passes=10)
    assert w.session.state.cursor == there
    move(vp, vp.rect().center() + QtCore.QPoint(40, 30))
    spin(qapp, passes=10)
    assert w.session.state.cursor != there


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_leaving_the_hot_key_onto_the_image_leaves_no_old_crosshair(window, theme):
    """Classic: the pointer onto the key from above at A, out of the hot key to its right at B, the key's shrink and
    the move in one pass of the event loop (as X delivers them). The crosshair is at B; what Qt has on screen (the
    window's backing store) is what the window draws now: before, the whole old vertical line stayed at A (661 px)."""
    w, qapp = window
    if theme != "dark":
        w.set_theme(theme)
        spin(qapp, passes=40)
    key, view = w.main.key, w.view
    vp = view.widget.viewport()
    rest = key.geometry()
    a = QtCore.QPoint(rest.center().x() - 40, rest.top() - 4)
    move(vp, vp.mapFrom(view.widget, a))
    spin(qapp, passes=20)
    at_a = w.session.state.cursor
    QtWidgets.QApplication.sendEvent(key, QtGui.QEnterEvent(QtCore.QPointF(5, 5), QtCore.QPointF(5, 5),
                                                            QtCore.QPointF(key.mapToGlobal(QtCore.QPoint(5, 5)))))
    spin(qapp, passes=20)
    hot = key.geometry()
    assert key.hot and hot.height() > rest.height()
    QtWidgets.QApplication.sendEvent(key, QtCore.QEvent(QtCore.QEvent.Type.Leave))
    b = QtCore.QPoint(hot.right() + 30, hot.top() + 20)
    move(vp, vp.mapFrom(view.widget, b))
    spin(qapp, passes=30)
    assert not key.hot and w.session.state.cursor != at_a
    on_screen = pixels(w.screen().grabWindow(w.winId()).toImage())
    drawn = pixels(w.grab().toImage())
    assert on_screen.shape == drawn.shape
    off = view.widget.mapTo(w, QtCore.QPoint(0, 0))
    x = off.x() + a.x()
    col = on_screen[off.y():off.y() + hot.top(), x - 8:x + 9]       # above the hot key: where the old line ran
    r, g, bl = (col >> 16) & 255, (col >> 8) & 255, col & 255
    old = int(((r > 180) & (g < 140) & (bl < 140)).sum())
    ys, xs = np.nonzero(on_screen != drawn)
    assert old == 0 and ys.size == 0, dict(old_line_px=old, differ=int(ys.size),
                                           box=(xs.min(), ys.min(), xs.max(), ys.max()) if ys.size else None)
