"""Playback (ROADMAP E4.9), offscreen: Space or the button plays t round the end at the toolbar's rate, the button
says what a click does next, the rate changes the timer, and the rate shown follows the one asked for."""
import time

import pytest

from explorer.testing import synth

SHAPE = (6, 4, 21, 48, 40)


def _glyph(button, name=None):
    """The play button's icon (or the named glyph) painted at 18 px: compared as images."""
    from explorer.ui import icons

    icon = button.icon() if button is not None else icons.glyph_icon(name)
    return icon.pixmap(18, 18).toImage()


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("playback"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    yield w
    w.close()
    ds.close()


def test_space_plays_t_round_the_end_and_stops(qapp, shell):
    from PySide6 import QtCore, QtGui, QtWidgets

    nav, s = shell.nav, shell.session
    nav.fps.setValue(60)
    assert shell._play.interval() == 16
    key = QtGui.QKeySequence(QtCore.Qt.Key.Key_Space)
    space = [sc for sc in shell.findChildren(QtGui.QShortcut) if sc.key() == key]
    assert len(space) == 1
    space[0].activated.emit()                            # Space
    assert nav.play.isChecked() and nav.play.text() == "t" and _glyph(nav.play) == _glyph(None, "pause")
    seen = set()
    # every t, and round the end back to 0
    assert spin(qapp, lambda: seen.add(s.state.t) or len(seen) == SHAPE[0] and s.state.t == 0, 5.0)
    nav.play.click()                                    # the button stops it too
    assert not nav.play.isChecked() and nav.play.text() == "t" and _glyph(nav.play) == _glyph(None, "play")
    t = s.state.t
    for _ in range(20):
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)
    assert s.state.t == t


def test_the_rate_shown_follows_the_rate_asked(qapp, shell):
    shell.nav.fps.setValue(25)
    shell.set_playing(True)
    assert spin(qapp, lambda: len(shell._fps) >= 12, 5.0)
    fps = shell.played_fps()                            # before stopping: stopping clears the samples
    shell.set_playing(False)
    assert fps is not None and 15 < fps < 35            # offscreen, a small cube: close to 25
