"""The navigation toolbar (ROADMAP E4.5), offscreen: sliders and combo move the cube and follow it without echo, a
click on a slider's track jumps there, the labels, the Panels menu and reset, and the sliders giving way."""
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
    return synth.write_dataset(tmp_path_factory.mktemp("toolbar"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    w.resize(1400, 900)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    yield w
    w.close()
    ds.close()


def test_sliders_and_combo_move_the_cube_and_follow_it(qapp, shell):
    nav, s = shell.nav, shell.session
    nav.sliders["t"].setValue(3)
    nav.sliders["l"].setValue(20)
    nav.stokes.setCurrentIndex(2)
    assert (s.state.t, s.state.l, s.state.s) == (3, 20, 2)
    s.step("t", 1)
    s.set_index("s", 1)
    assert spin(qapp, lambda: nav.sliders["t"].value() == 4 and nav.stokes.currentIndex() == 1)
    assert "UT" in nav.labels["t"].text() and "4/5" in nav.labels["t"].text()
    assert nav.labels["l"].text().startswith("Δλ") and "(cont.)" in nav.labels["l"].text()   # tuning 20


def test_a_click_on_the_track_jumps_there(qapp, shell):
    from PySide6 import QtCore, QtGui, QtWidgets

    sl = shell.nav.sliders["l"]
    sl.setValue(0)
    opt = QtWidgets.QStyleOptionSlider()
    sl.initStyleOption(opt)
    groove = sl.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_Slider, opt,
                                       QtWidgets.QStyle.SubControl.SC_SliderGroove, sl)
    p = QtCore.QPointF(groove.x() + groove.width() * 0.75, groove.center().y())
    for t in (QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseButtonRelease):
        ev = QtGui.QMouseEvent(t, p, sl.mapToGlobal(p), QtCore.Qt.MouseButton.LeftButton,
                               QtCore.Qt.MouseButton.LeftButton if t == QtCore.QEvent.Type.MouseButtonPress
                               else QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(sl, ev)
    assert abs(sl.value() - 15) <= 1                    # 75 % of 0..20, not a page step (10)
    assert shell.session.state.l == sl.value()


def test_the_panels_menu_and_reset(qapp, shell):
    nav = shell.nav
    acts = nav.panels.menu().actions()
    assert [a.text() for a in acts] == ["Spectrum", "λ–t", "Slit"]
    assert not acts[2].isEnabled()                      # the slit's: only with a slit (the prototype's 1131)
    acts[1].trigger()                                   # hide lambda-t
    assert spin(qapp, lambda: shell.lt_dock.isHidden())
    nav.reset.click()
    assert spin(qapp, lambda: shell.lt_dock.isVisible())
    assert not nav.reset.icon().isNull()


def test_the_sliders_give_way_in_a_narrow_window(qapp, shell):
    """The narrow width comes from the toolbar itself, halfway between its sliders' two widths. What the rest of it
    needs depends on the application's look, which style.apply_theme sets for the whole application, so an earlier
    test leaves it changed: at a fixed 900 px the toolbar fitted in Fusion's look and not in ours (spacing 6 against
    3, its font), where the sliders stopped at their narrowest and the toolbar still asked for 915."""
    from explorer.ui.toolbar import SLIDER_W

    nav = shell.nav
    shell.resize(1400, 900)
    assert spin(qapp, lambda: nav.sliders["t"].width() == SLIDER_W[1])
    n = len(nav.sliders)
    width = nav.tb.sizeHint().width() - n * SLIDER_W[1] + n * (SLIDER_W[0] + SLIDER_W[1]) // 2 + 8
    shell.resize(width, 700)
    assert spin(qapp, lambda: nav.sliders["t"].width() < SLIDER_W[1])
    assert all(SLIDER_W[0] < sl.width() < SLIDER_W[1] for sl in nav.sliders.values())
    assert nav.tb.sizeHint().width() <= width + 8
