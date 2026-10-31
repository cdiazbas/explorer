"""The window, offscreen: the first image, the keys, the mouse and the crosshair, Stokes keys without t, and
`explorer cube.fits --quit-after` end to end."""
import threading
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


@pytest.mark.parametrize("ssh, said", [(False, False), (True, True)])
def test_the_first_image_line_says_over_ssh_only_over_ssh(qapp, cube, ssh, said):
    """The bridge on a local display (no libxcb-cursor) has a remote plan; the line says 'over ssh' only when the
    screen is at the other end of one."""
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    with Dataset.open(cube) as ds:
        w = Shell(ds)
        w.breakdown = (None, {"window": 0.01}, "X11 bridge", True, ssh)
        w.resize(640, 480)
        w.show()
        assert spin(qapp, lambda: w.first_image_s is not None)
        line = w.first_image_line
        assert line is not None and "X11 bridge" in line and ("over ssh" in line) is said, line
        w.close()


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


def test_explorer_opens_a_cube_and_logs_the_first_image(qapp, cube, capsys):
    """Where the time to the first image went is in explorer.log, not on the terminal."""
    from explorer import cli
    from explorer._paths import cache_dir
    from explorer.obs import log

    log.setup()                                         # the file too, as the command has it
    assert cli.main([str(cube), "--quit-after", "0.05"]) == 0
    assert "first image handed" not in capsys.readouterr().err
    assert "first image handed to the screen" in (cache_dir() / "logs" / "explorer.log").read_text()


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


class _Waiting:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def test_a_frame_not_read_is_said_and_the_wait_for_a_first_image_that_failed_stops(qapp, cube, monkeypatch):
    """A frame that could not be read showed nothing: the old image stayed under the new t with no word; and when it
    was the first image, the terminal's "still reading the first image" lines and their stall warning went on for
    ever. The status line says it, the terminal once per frame, and the waiting lines stop."""
    from concurrent.futures import Future

    from explorer.data.dataset import Dataset
    from explorer.obs import say
    from explorer.ui.shell import Shell

    said: list[str] = []
    monkeypatch.setattr(say, "warn", said.append)
    ds = Dataset.open(cube)
    orig = ds.image
    broken = {"all": True}

    def image(idx, request=None):
        if idx[0] == 1 or broken["all"]:                # failing a moment later, as a read from the disk does
            f = Future()
            threading.Timer(0.05, f.set_exception, (OSError(5, "Input/output error"),)).start()
            return f
        return orig(idx, request)
    ds.image = image
    w = Shell(ds)
    w.waiting = waiting = _Waiting()
    try:
        w.resize(640, 480)
        w.show()
        assert spin(qapp, lambda: waiting.stopped)                     # the first image failed: no more waiting
        assert "not read" in w.statusBar().currentMessage() and w.first_image_s is None
        broken["all"] = False
        w.session.set_index("t", 2)
        assert spin(qapp, lambda: w.first_image_s is not None)
        w.session.set_index("t", 1)
        assert spin(qapp, lambda: "not read" in w.statusBar().currentMessage())
        n = len(said)
        w.session.set_index("t", 2)
        qapp.processEvents()
        w.session.set_index("t", 1)
        assert spin(qapp, lambda: "not read" in w.statusBar().currentMessage())
        assert len(said) == n                           # on the terminal once per frame
    finally:
        w.close()
        ds.close()


def test_the_first_image_s_work_runs_once_when_a_second_image_comes_meanwhile(qapp, cube, monkeypatch):
    """first_image() ran processEvents() before marking itself done: a second image handed over in that pass called
    it again, and the work after the first image (the update check, the per-pixel sheet, quit_after) ran twice, the
    line twice, and the time to the first image took in the nested work."""
    from PySide6 import QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.ui import shell as shell_mod
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    ran: list[int] = []
    w.after_first_image(0, lambda: ran.append(1))
    orig = QtWidgets.QApplication.processEvents
    nested = {"done": False}

    def process(*a):
        if not nested["done"]:
            nested["done"] = True
            w.first_image()                             # a second image's sink, in the same pass
        return orig(*a)
    monkeypatch.setattr(shell_mod.QtWidgets.QApplication, "processEvents", staticmethod(process))
    try:
        w.resize(640, 480)
        w.show()
        assert spin(qapp, lambda: w.first_image_s is not None)
        monkeypatch.setattr(shell_mod.QtWidgets.QApplication, "processEvents", staticmethod(orig))
        spin(qapp, lambda: False, 0.3)
        assert ran == [1]
    finally:
        w.close()
        ds.close()


def test_the_link_probe_waits_for_the_first_image(qapp, cube, monkeypatch):
    """The probe started 1.5 s after the window, the first image and panels often still on their way over a slow
    link: its 4 MB shared the channel, the rate came out low, and it was taken for the whole session (the playback
    rate capped, the panels held). It starts after the first image."""
    from concurrent.futures import Future

    from explorer.data.dataset import Dataset
    from explorer.platform import linkprobe
    from explorer.platform.display import LinkInfo
    from explorer.ui.shell import Shell

    calls: list[float] = []
    monkeypatch.setattr(linkprobe, "measure", lambda: calls.append(time.perf_counter()) or {"MBps": 50.0,
                                                                                           "rtt_ms": 5.0})
    ds = Dataset.open(cube)
    orig = ds.image
    held: list = []

    def image(idx, request=None):
        f = Future()
        held.append((f, orig(idx, request)))
        return f
    ds.image = image
    w = Shell(ds)
    try:
        w.resize(640, 480)
        w.show()
        w.start_link_probe(LinkInfo(bytes_per_px=4.0, fps_cap=None))
        spin(qapp, lambda: False, 2.2)                  # past the 1.5 s it waited, no image yet
        assert not calls, "measured before the first image"
        ds.image = orig
        for f, real in held:
            f.set_result(real.result(10))
        assert spin(qapp, lambda: w.first_image_s is not None)
        assert spin(qapp, lambda: bool(calls), 5.0)
    finally:
        w.close()
        ds.close()
