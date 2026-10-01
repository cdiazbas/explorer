"""The panels in docks (ROADMAP E4.2), offscreen: where they sit, their sizes, what a hidden panel reads, the way
back to the start, a panel docked again in its place, and the window's first size."""
import time

import pytest

from explorer.testing import synth
from explorer.ui import docks

SHAPE = (3, 4, 5, 48, 40)


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("docks"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube, no_sp=True)                 # the panels' reads go through the scheduler, not one block
    w = Shell(ds)
    w.resize(1400, 900)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    for _ in range(5):
        qapp.processEvents()
    yield w
    w.close()
    ds.close()


def test_panels_on_the_right_spectrum_above_lambda_t_with_their_margin(qapp, shell):
    from PySide6 import QtCore

    right = QtCore.Qt.DockWidgetArea.RightDockWidgetArea
    assert shell.dockWidgetArea(shell.spec_dock) == right and shell.dockWidgetArea(shell.lt_dock) == right
    assert shell.spec_dock.geometry().bottom() < shell.lt_dock.geometry().top()
    assert shell.spec_dock.objectName() == "spectrum" and shell.lt_dock.objectName() == "lambda_t"
    m = shell.centralWidget().layout().contentsMargins()
    assert (m.left(), m.top(), m.right(), m.bottom()) == (docks.PANEL_GUTTER,) * 4


def test_the_fresh_start_sizes(qapp, shell):
    want = int(shell.width() * docks.PANELS_W)
    assert spin(qapp, lambda: abs(shell.spec_dock.width() - want) <= 8)       # the dock separator's few px
    assert abs(shell.spec_dock.height() - shell.lt_dock.height()) <= 2


def test_a_hidden_panel_reads_nothing_and_is_filled_when_shown(qapp, shell):
    s = shell.session
    assert spin(qapp, lambda: "lambda_t" in shell.last)
    shell.lt_dock.close()
    assert spin(qapp, lambda: "lambda_t" not in s.state.panels)
    s.hover(10, 12)
    assert spin(qapp, lambda: (shell.last.get("spectra") or (None, None))[1] == (10, 12))
    for _ in range(20):
        qapp.processEvents()
    assert shell.last["lambda_t"][1] != (10, 12)                             # nothing read for it
    shell.lt_dock.show()
    assert spin(qapp, lambda: shell.last["lambda_t"][1] == (10, 12))         # filled for the cursor as it is


def test_reset_brings_every_panel_back_docked_and_sized(qapp, shell):
    shell.spec_dock.setFloating(True)
    shell.lt_dock.close()
    assert spin(qapp, lambda: shell.lt_dock.isHidden())
    shell.reset_panels()
    assert spin(qapp, lambda: shell.spec_dock.isVisible() and shell.lt_dock.isVisible())
    assert not shell.spec_dock.isFloating()
    want = int(shell.width() * docks.PANELS_W)
    assert spin(qapp, lambda: abs(shell.spec_dock.width() - want) <= 8)
    assert {"spectra", "lambda_t"} <= shell.session.state.panels


def test_a_panel_docked_again_is_back_in_its_place(qapp, shell):
    """Its float button twice, three times: where it was docked, inside the window. Qt left it at the place it had
    floating at (the conformance suite's dock_float_button_back, xcb: lambda-t at 590,466 in a 1200-px window, and
    40 px further each time)."""
    from PySide6 import QtCore, QtWidgets

    d = shell.lt_dock
    home = d.geometry()
    for _ in range(3):
        for _floating in (True, False):
            d.findChild(QtWidgets.QAbstractButton, "qt_dockwidget_floatbutton").click()
            assert spin(qapp, lambda f=_floating: d.isFloating() == f)
        assert spin(qapp, lambda: d.geometry() == home, timeout=2), (d.geometry(), home)
    assert QtCore.QRect(QtCore.QPoint(), shell.size()).contains(d.geometry())


def test_a_panel_docked_after_the_window_changed_takes_its_new_place(qapp, shell):
    """The window narrower while the panel floats: docked again at the right edge of the new width, inside it, not
    at the place it had before."""
    from PySide6 import QtCore, QtWidgets

    d = shell.lt_dock
    home = d.geometry()
    button = lambda: d.findChild(QtWidgets.QAbstractButton, "qt_dockwidget_floatbutton")      # noqa: E731
    button().click()
    assert spin(qapp, lambda: d.isFloating())
    shell.resize(1200, 800)
    assert spin(qapp, lambda: shell.width() == 1200)
    button().click()
    assert spin(qapp, lambda: not d.isFloating())
    assert spin(qapp, lambda: QtCore.QRect(QtCore.QPoint(), shell.size()).contains(d.geometry()), timeout=2)
    assert d.geometry() != home and abs(d.geometry().right() - shell.spec_dock.geometry().right()) <= 1


def test_the_first_window_fills_the_monitor_height_at_most_one_point_six_wide(qapp):
    r = docks.first_geometry(qapp)
    screen = qapp.screenAt(r.center()) or qapp.primaryScreen()
    mon = screen.availableGeometry()
    assert r.height() == int(mon.height() * docks.FILL)
    assert r.width() == min(int(mon.width() * docks.FILL), int(r.height() * docks.ASPECT))
    assert mon.contains(r) and abs(r.center().x() - mon.center().x()) <= 1


def test_closing_the_window_raises_nothing(qapp, cube, capfd):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    w.close()                                           # the docks then say hidden, after the scheduler closed
    for _ in range(10):
        qapp.processEvents()
    ds.close()
    assert "Traceback" not in capfd.readouterr().err
