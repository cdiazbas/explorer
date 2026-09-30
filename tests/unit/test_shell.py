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
    assert w.scheduler.img_idx == (0, 0, 2) and "x 20  y 24" in w.status.text()
    QTest.keyClick(w, K.Key_Up)
    QTest.keyClick(w, K.Key_Right)
    QTest.keyClick(w, K.Key_3)
    assert spin(qapp, lambda: w.scheduler.img_idx == (1, 2, 3))
    assert w.session.state.t == 1 and w.session.state.l == 3 and w.session.state.s == 2
    QTest.keyClick(w, K.Key_L)
    assert spin(qapp, lambda: "locked" in w.status.text()) and w.session.state.locked      # shown next pass
    QTest.keyClick(w, K.Key_Escape)
    assert spin(qapp, lambda: not w.session.state.locked)


def test_the_mouse_moves_the_cursor_and_the_crosshair(shell):
    from PySide6 import QtCore

    w, qapp = shell
    w.view._moved(w.view.vb.mapViewToScene(QtCore.QPointF(15.5, 22.5)))
    assert spin(qapp, lambda: (w.view.hl.value(), w.view.vl.value()) == (22.5, 15.5))    # drawn next pass
    assert w.session.state.cursor == (22, 15)
    assert spin(qapp, lambda: "spectra" in w.last and w.last["spectra"][1] == (22, 15))


def test_stokes_keys_without_t(qapp, tmp_path):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    p = tmp_path / "sl.fits"
    fits.PrimaryHDU(np.random.default_rng(0).uniform(1, 2, (4, 7, 16, 12)).astype(np.float32)).writeto(p)
    with Dataset.open(p, axes="s,l") as ds:
        w = Shell(ds)
        keys = [row[0] for row in w.key_table()]
        assert "1–4" in keys and "↓ ↑" not in keys          # Stokes keys, no t keys
        w.close()


def test_explorer_opens_a_cube_and_reports_the_first_image(qapp, cube, capsys):
    from explorer import cli

    assert cli.main([str(cube), "--quit-after", "0.05"]) == 0
    assert "first image on screen" in capsys.readouterr().err
