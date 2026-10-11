"""The window, offscreen: the first image, the keys, the mouse and the crosshair, Stokes keys without t, and
`explorer cube.fits --quit-after` end to end."""
import time

import numpy as np
import pytest
from astropy.io import fits

from explorer.testing import synth

SHAPE = (3, 4, 5, 48, 40)


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("shell"), "c", shape=SHAPE, icube=False)
    return d["im"]


@pytest.fixture
def shell(qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    w.resize(640, 480)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    yield w, qapp
    w.close()
    ds.close()


def test_first_image_keys_and_status(shell):
    from PySide6 import QtCore
    from PySide6.QtTest import QTest

    w, qapp = shell
    K = QtCore.Qt.Key
    text = w.status.text()
    assert w.scheduler.img_idx == (0, 0, 2) and "\u2033" in text and "\u00a0UT" in text      # arcsec, UT
    QTest.keyClick(w, K.Key_Up)
    QTest.keyClick(w, K.Key_Right)
    QTest.keyClick(w, K.Key_3)
    assert spin(qapp, lambda: w.scheduler.img_idx == (1, 2, 3))
    assert w.session.state.t == 1 and w.session.state.l == 3 and w.session.state.s == 2
    QTest.keyClick(w, K.Key_L)
    assert spin(qapp, lambda: "locked" in w.status.text()) and w.session.state.locked      # shown next pass
    QTest.keyClick(w, K.Key_Escape)
    assert spin(qapp, lambda: not w.session.state.locked)


def test_the_status_line_keeps_clear_of_the_rounded_corners(shell):
    """The window's bottom corners are rounded (16 px): the status text started 2 px from the edge, its first
    character partly cut by the curve. Both sides keep clear of it."""
    import numpy as np
    from PySide6 import QtGui

    from explorer.ui import shell as S

    w, qapp = shell
    inset = getattr(S, "STATUS_INSET", 8)
    sb = w.statusBar()
    m = sb.contentsMargins()
    assert m.left() >= inset and m.right() >= inset
    w.status.setText("x −672.7″  y +271.5″")
    qapp.processEvents()
    img = sb.grab().toImage()
    cols = np.array([[QtGui.QColor(img.pixel(x, y)).lightness() for x in range(inset)] for y in range(img.height())])
    assert np.ptp(cols) < 40                            # nothing drawn in the corner's columns


def test_the_mouse_moves_the_cursor_and_the_crosshair(shell):
    from PySide6 import QtCore

    w, qapp = shell
    w.view._moved(w.view.vb.mapViewToScene(QtCore.QPointF(15.5, 22.5)))
    assert spin(qapp, lambda: (w.view.hl.value(), w.view.vl.value()) == (22.5, 15.5))    # drawn next pass
    assert w.session.state.cursor == (22, 15)
    assert spin(qapp, lambda: "spectra" in w.last and w.last["spectra"][1] == (22, 15))


def test_the_docks_are_not_animated(shell):
    """A panel dragged over the window opens its gap at once: animated, every frame laid out and repainted the whole
    window, 27-31 MB through the bridge in a 1.4-s drag against 4.8 without (the prototype's F25,
    app/viewer.py:990-994)."""
    from PySide6 import QtWidgets

    w, _qapp = shell
    animated = bool(w.dockOptions() & QtWidgets.QMainWindow.DockOption.AnimatedDocks)
    assert not w.isAnimated() and not animated, dict(isAnimated=w.isAnimated(), options=w.dockOptions())


def test_stokes_keys_without_t(qapp, tmp_path):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    p = tmp_path / "sl.fits"
    fits.PrimaryHDU(np.random.default_rng(0).uniform(1, 2, (4, 7, 16, 12)).astype(np.float32)).writeto(p)
    with Dataset.open(p, axes="s,l") as ds:
        w = Shell(ds)
        keys = " · ".join(row[0] for row in w.key_table())
        assert "1–4" in keys and "↓ ↑" not in keys          # Stokes keys, no t keys
        w.close()


def test_explorer_opens_a_cube_and_reports_the_first_image(qapp, cube, capsys):
    from explorer import cli

    assert cli.main([str(cube), "--quit-after", "0.05"]) == 0
    assert "first image handed to the screen" in capsys.readouterr().err


def test_the_last_of_two_quick_moves_moves_the_cursor(shell):
    """pyqtgraph's scene drops a move that comes within 1/mouseRateLimit s (10 ms) of the one before, and nothing
    delivers it later: the crosshair stayed one pixel behind a pointer that stopped right after a quick move (the X
    bridge test's second move, ROADMAP E6.13). The last move is the one that counts."""
    from PySide6 import QtCore, QtGui
    from PySide6.QtWidgets import QApplication

    w, qapp = shell
    gv = w.view.widget
    vp = gv.viewport()

    def move(y, x):
        p = QtCore.QPointF(gv.mapFromScene(w.view.vb.mapViewToScene(QtCore.QPointF(x + 0.5, y + 0.5))))
        g = QtCore.QPointF(vp.mapToGlobal(p.toPoint()))
        none = QtCore.Qt.MouseButton.NoButton
        QApplication.sendEvent(vp, QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, p, p, g, none, none,
                                                     QtCore.Qt.KeyboardModifier.NoModifier))

    move(10, 12)
    assert spin(qapp, lambda: w.session.state.cursor == (10, 12))
    move(30, 25)                                        # at once: well within 10 ms of the first
    assert spin(qapp, lambda: w.session.state.cursor == (30, 25), timeout=1.0), w.session.state.cursor


def test_one_cube_has_no_entry_to_detach_cubes(shell):
    w, _ = shell
    assert w.detach_action is None and not w.linked
