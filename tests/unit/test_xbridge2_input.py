"""X input into Qt through public API only (the rewritten bridge's qtinput), offscreen, without an X server: X events
built here reach explorer's window and ordinary widgets as a platform plugin's would. Each test names the behaviour
the prototype needed its private Qt symbols for."""
import time
from types import SimpleNamespace

import pytest

from explorer.platform.xbridge2 import keys as K
from explorer.platform.xbridge2 import xproto as X
from explorer.testing import synth

SHAPE = (3, 4, 5, 48, 40)
UP, RIGHT, K3, KL, KA, KRET, KDOWN, KW = 111, 114, 12, 46, 38, 36, 116, 25


def keymap():
    km = K.Keymap(8, 2, [()] * 248)
    for code, syms in {UP: (0xFF52, 0), RIGHT: (0xFF53, 0), K3: (ord("3"), ord("#")), KL: (ord("l"), ord("L")),
                       KA: (ord("a"), ord("A")), KRET: (0xFF0D, 0), KDOWN: (0xFF54, 0), KW: (ord("w"), ord("W"))
                       }.items():
        km.syms[code - 8] = syms
    km.alt, km.meta, km.num_lock = 8, 64, 16
    return km


class Clock:
    t = 1000

    def __call__(self, dt=20):
        Clock.t += dt
        return Clock.t


now = Clock()


def ev(code, w, x, y, detail=0, state=0, t=None, **kw):
    g = w.geometry()
    return SimpleNamespace(code=code, detail=detail, x=x, y=y, root_x=g.x() + x, root_y=g.y() + y, state=state,
                           time=now() if t is None else t, **kw)


def spin(qapp, until, timeout=5.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture
def inp(qapp):
    from explorer.platform.xbridge2.qtinput import QtInput

    km = keymap()
    i = QtInput(lambda: km)
    yield i
    i.close()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("bridge2"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    w.resize(640, 480)
    w.move(100, 50)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    yield w
    w.close()
    ds.close()


def _image_point(w, px=15.5, py=22.5):
    """Window coordinates of a data pixel of the image panel."""
    from PySide6 import QtCore

    sc = w.view.vb.mapViewToScene(QtCore.QPointF(px, py))
    vp = w.view.widget.mapFromScene(sc)
    p = w.view.widget.viewport().mapTo(w, vp)
    return p.x(), p.y()


def test_keys_reach_the_window_shortcuts_fire(qapp, shell, inp):
    w = shell
    for code in (UP, RIGHT, K3):                        # QShortcut on the window: t, lambda, Stokes
        inp.key(w, ev(X.KeyPress, w, 5, 5, detail=code), False)
        inp.key(w, ev(X.KeyRelease, w, 5, 5, detail=code), False)
    assert spin(qapp, lambda: w.scheduler.img_idx == (1, 2, 3))
    inp.key(w, ev(X.KeyPress, w, 5, 5, detail=KL), False)
    assert spin(qapp, lambda: w.session.state.locked)


def test_the_mouse_moves_clicks_lock_and_double_click_shows_all(qapp, shell, inp):
    from PySide6 import QtCore

    w = shell
    x, y = _image_point(w)
    inp.motion(w, ev(X.MotionNotify, w, x, y))
    assert spin(qapp, lambda: w.session.state.cursor == (22, 15))            # hover moves the cursor
    x2, y2 = _image_point(w, 30.5, 10.5)
    inp.button(w, ev(X.ButtonPress, w, x2, y2, detail=1))
    inp.button(w, ev(X.ButtonRelease, w, x2, y2, detail=1, state=0x100))
    assert spin(qapp, lambda: w.session.state.locked and w.session.state.cursor == (10, 30))   # a click locks there
    inp.button(w, ev(X.ButtonPress, w, x2, y2, detail=3))
    inp.button(w, ev(X.ButtonRelease, w, x2, y2, detail=3, state=0x400))
    assert spin(qapp, lambda: not w.session.state.locked)                    # the right button releases
    w.view.vb.setRange(xRange=(10, 20), yRange=(10, 20), padding=0)
    qapp.processEvents()
    zoomed = w.view.vb.viewRange()
    shown = []
    orig = w.view.show_all
    w.view.show_all = lambda: (shown.append(1), orig())
    t0 = now()
    for dt, state in ((0, 0), (40, 0x100), (80, 0), (120, 0x100)):
        code = X.ButtonPress if state == 0 else X.ButtonRelease
        inp.button(w, ev(code, w, x2, y2, detail=1, state=state, t=t0 + dt))
    assert spin(qapp, lambda: shown == [1])                                  # Qt made no double click; we do
    assert inp.stats["dblclick"] == 1
    assert w.view.vb.viewRange() != zoomed
    assert QtCore.Qt.MouseButton.NoButton == inp.buttons


def test_a_slow_second_click_is_not_a_double_click(qapp, shell, inp):
    from PySide6 import QtGui

    w = shell
    x, y = _image_point(w)
    t0 = now()
    gap = QtGui.QGuiApplication.styleHints().mouseDoubleClickInterval() + 50
    for dt, state in ((0, 0), (10, 0x100), (gap, 0), (gap + 10, 0x100)):
        code = X.ButtonPress if state == 0 else X.ButtonRelease
        inp.button(w, ev(code, w, x, y, detail=1, state=state, t=t0 + dt))
    qapp.processEvents()
    assert inp.stats["dblclick"] == 0


def test_the_wheel_zooms_the_image(qapp, shell, inp):
    w = shell
    x, y = _image_point(w)
    before = w.view.vb.viewRange()
    inp.button(w, ev(X.ButtonPress, w, x, y, detail=4))
    assert spin(qapp, lambda: w.view.vb.viewRange() != before)


class Recorder:
    def __init__(self):
        from PySide6 import QtCore

        E = QtCore.QEvent.Type
        self.types = (E.MouseMove, E.MouseButtonPress, E.MouseButtonRelease, E.KeyPress, E.KeyRelease, E.Enter,
                      E.Leave, E.ContextMenu, E.ToolTip)
        self.log = []
        self._f = self._make()

    def _make(self):
        from PySide6 import QtCore

        rec = self

        class F(QtCore.QObject):
            def eventFilter(self, o, e):
                if e.type() in rec.types:
                    rec.log.append((o, e.type(), getattr(e, "isAutoRepeat", lambda: None)(), e.spontaneous()))
                return False
        return F()

    def install(self, qapp):
        qapp.installEventFilter(self._f)

    def remove(self, qapp):
        qapp.removeEventFilter(self._f)


@pytest.fixture
def widgets(qapp):
    from PySide6 import QtWidgets

    w = QtWidgets.QWidget()
    w.setGeometry(300, 200, 400, 300)
    spinbox = QtWidgets.QSpinBox(w)
    spinbox.setGeometry(10, 10, 100, 30)
    edit = QtWidgets.QLineEdit(w)
    edit.setGeometry(10, 60, 100, 30)
    area = QtWidgets.QLabel("area", w)
    area.setGeometry(10, 110, 200, 150)
    area.setToolTip("the tip")
    area.setMouseTracking(True)
    w.show()
    for _ in range(5):
        qapp.processEvents()
    yield SimpleNamespace(w=w, spin=spinbox, edit=edit, area=area)
    w.close()


def test_wheel_goes_up_to_the_widget_that_takes_it(qapp, widgets, inp):
    """A wheel event sent to a window reaches the line edit inside a QSpinBox as non-spontaneous, and Qt does not
    pass it on: the bridge walks up to the spin box."""
    w = widgets.w
    inp.button(w, ev(X.ButtonPress, w, 50, 25, detail=4))
    assert spin(qapp, lambda: widgets.spin.value() == 1)


def test_focus_by_click_text_repeat_and_context_menu(qapp, widgets, inp):
    from PySide6 import QtCore

    w, rec = widgets.w, Recorder()
    rec.install(qapp)
    try:
        inp.button(w, ev(X.ButtonPress, w, 50, 75, detail=1))
        inp.button(w, ev(X.ButtonRelease, w, 50, 75, detail=1, state=0x100))
        assert spin(qapp, lambda: qapp.focusWidget() is widgets.edit)         # focus by click
        t = now()
        inp.key(w, ev(X.KeyPress, w, 0, 0, detail=KA, t=t), False)
        inp.key(w, ev(X.KeyRelease, w, 0, 0, detail=KA, t=t + 30), True)
        inp.key(w, ev(X.KeyPress, w, 0, 0, detail=KA, t=t + 30), True)       # X auto-repeat: release + press
        inp.key(w, ev(X.KeyPress, w, 0, 0, detail=KA, state=1), False)       # Shift
        assert spin(qapp, lambda: widgets.edit.text() == "aaA")
        reps = [r[2] for r in rec.log if r[0] is widgets.edit and r[1] == QtCore.QEvent.Type.KeyPress]
        assert reps == [False, True, False]
        # Qt (6.8 on) sends the context menu to the widget the last move reached, as the pointer always moves
        # there before a click
        inp.motion(w, ev(X.MotionNotify, w, 50, 150))
        inp.button(w, ev(X.ButtonPress, w, 50, 150, detail=3))
        inp.button(w, ev(X.ButtonRelease, w, 50, 150, detail=3, state=0x400))
        qapp.processEvents()
        assert any(r[0] is widgets.area and r[1] == QtCore.QEvent.Type.ContextMenu for r in rec.log), [
            (type(r[0]).__name__, r[1].name) for r in rec.log[-12:]]
    finally:
        rec.remove(qapp)


def test_a_drag_stays_with_the_pressed_widget(qapp, widgets, inp):
    from PySide6 import QtCore

    w, rec = widgets.w, Recorder()
    rec.install(qapp)
    try:
        inp.button(w, ev(X.ButtonPress, w, 50, 150, detail=1))
        inp.motion(w, ev(X.MotionNotify, w, 60, 20, state=0x100))           # over the spin box
        inp.motion(w, ev(X.MotionNotify, w, 900, 700, state=0x100))         # outside the window (X's grab)
        inp.button(w, ev(X.ButtonRelease, w, 900, 700, detail=1, state=0x100))
        qapp.processEvents()
        E = QtCore.QEvent.Type
        # the widget each event reaches first, spontaneous as from a platform (Qt then passes an ignored move on
        # to the parents, not spontaneous, as with xcb)
        got = [r for r in rec.log if r[1] in (E.MouseMove, E.MouseButtonRelease) and r[3]]
        assert got and all(r[0] is widgets.area for r in got)
    finally:
        rec.remove(qapp)


def test_tool_tip_after_a_rest(qapp, widgets, inp):
    from PySide6 import QtWidgets

    w = widgets.w
    inp.motion(w, ev(X.MotionNotify, w, 40, 140))
    inp.motion(w, ev(X.MotionNotify, w, 42, 141))
    assert spin(qapp, lambda: QtWidgets.QToolTip.isVisible() and QtWidgets.QToolTip.text() == "the tip", 3.0)
    QtWidgets.QToolTip.hideText()


def test_an_open_popup_takes_clicks_and_keys(qapp, widgets, inp):
    from PySide6 import QtCore, QtWidgets

    w = widgets.w
    menu = QtWidgets.QMenu(w)
    hit = []
    menu.addAction("one", lambda: hit.append("one"))
    menu.addAction("two", lambda: hit.append("two"))
    menu.popup(QtCore.QPoint(500, 300))
    assert spin(qapp, lambda: QtWidgets.QApplication.activePopupWidget() is menu)
    for code in (KDOWN, KDOWN, KRET):                   # keys arrive at the main window; the popup gets them
        inp.key(w, ev(X.KeyPress, w, 0, 0, detail=code), False)
        inp.key(w, ev(X.KeyRelease, w, 0, 0, detail=code), False)
    assert spin(qapp, lambda: hit == ["two"])
    menu.popup(QtCore.QPoint(500, 300))
    assert spin(qapp, lambda: menu.isVisible())
    c = menu.actionGeometry(menu.actions()[0]).center()
    inp.motion(menu, ev(X.MotionNotify, menu, c.x(), c.y()))
    inp.button(menu, ev(X.ButtonPress, menu, c.x(), c.y(), detail=1))
    inp.button(menu, ev(X.ButtonRelease, menu, c.x(), c.y(), detail=1, state=0x100))
    assert spin(qapp, lambda: hit == ["two", "one"] and not menu.isVisible())
    menu.popup(QtCore.QPoint(500, 300))
    assert spin(qapp, lambda: menu.isVisible())
    inp.button(w, ev(X.ButtonPress, w, 5, 5, detail=1))                      # a press outside closes it
    inp.button(w, ev(X.ButtonRelease, w, 5, 5, detail=1, state=0x100))
    assert spin(qapp, lambda: not menu.isVisible())


def test_qt_activation_follows_the_x_focus(qapp, widgets, inp):
    from PySide6 import QtWidgets

    w = widgets.w
    other = QtWidgets.QWidget()
    other.setGeometry(800, 100, 100, 100)
    other.show()                                       # offscreen activates every window it shows
    try:
        assert spin(qapp, lambda: qapp.activeWindow() is other)
        inp.x_focus(w, True)                           # the X focus is on w: Qt follows
        assert spin(qapp, lambda: qapp.activeWindow() is w)
        other.hide()
        other.show()
        assert spin(qapp, lambda: qapp.activeWindow() is w)                  # and puts it back
        inp.x_focus(w, False)                          # the X focus left the application
        assert spin(qapp, lambda: qapp.activeWindow() is None, 2.0)          # no widget window active (400 ms)
        inp.x_focus(w, True)
        assert spin(qapp, lambda: qapp.activeWindow() is w)
    finally:
        other.close()


QUIT_SCRIPT = """
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtWidgets
from explorer.platform.xbridge2.qtinput import QtInput
app = QtWidgets.QApplication([])
w = QtWidgets.QWidget(); w.resize(200, 100); w.show()
inp = QtInput(lambda: None)
QtCore.QTimer.singleShot(100, lambda: inp.x_focus(w, True))
QtCore.QTimer.singleShot(200, lambda: inp.x_focus(w, False))      # the X focus leaves: no active window after 400 ms
QtCore.QTimer.singleShot(900, lambda: print("active", app.activeWindow(), flush=True))
QtCore.QTimer.singleShot(1000, w.close)                            # the last widget window closes
QtCore.QTimer.singleShot(4000, lambda: app.exit(2))                # still running: it did not quit
sys.exit(app.exec())
"""


def test_no_active_window_does_not_keep_the_application_open():
    """With the X focus elsewhere, closing the last widget window still quits (Qt decides it inside exec(), hence a
    process of its own): the stand-in window that leaves no widget window active does not count."""
    import os
    import subprocess
    import sys

    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env.pop("DISPLAY", None)
    p = subprocess.run([sys.executable, "-c", QUIT_SCRIPT], env=env, capture_output=True, text=True, timeout=60)
    assert "active None" in p.stdout, p.stdout + p.stderr[-500:]
    assert p.returncode == 0, p.stdout + p.stderr[-500:]


def test_global_modifiers_follow_the_input_but_not_a_modifier_release(qapp, widgets, inp):
    """QGuiApplication.keyboardModifiers() follows mouse events (the X state) and key presses; the release of a modifier
    key alone leaves it stale until the next mouse event or key press: only a platform plugin can set it, and xcb
    would. Measured here, stated rather than hidden."""
    from PySide6 import QtCore, QtGui

    M = QtCore.Qt.KeyboardModifier
    w = widgets.w
    inp.motion(w, ev(X.MotionNotify, w, 50, 150, state=4))                  # Ctrl held, from X's state
    qapp.processEvents()
    assert QtGui.QGuiApplication.keyboardModifiers() == M.ControlModifier
    inp.motion(w, ev(X.MotionNotify, w, 51, 150, state=0))
    km = inp.keymap()
    km.syms[50 - 8] = (0xFFE1, 0)
    inp.key(w, ev(X.KeyPress, w, 0, 0, detail=50), False)                   # Shift pressed alone
    qapp.processEvents()
    assert QtGui.QGuiApplication.keyboardModifiers() == M.ShiftModifier
    inp.key(w, ev(X.KeyRelease, w, 0, 0, detail=50, state=1), False)        # and released
    qapp.processEvents()
    assert QtGui.QGuiApplication.keyboardModifiers() == M.ShiftModifier      # stale (xcb: none)
    inp.motion(w, ev(X.MotionNotify, w, 52, 150, state=0))
    qapp.processEvents()
    assert QtGui.QGuiApplication.keyboardModifiers() == M.NoModifier


def test_a_double_click_grab_ends_when_the_buttons_are_up(qapp, widgets, inp):
    """A double click holds its widget (grabMouse) until the release. When the double click unmaps the window under
    the pointer (a floating panel docked by it), X sends that release nowhere: the next move or press with no
    button held ends the grab, which otherwise kept every later press from the other windows."""
    from PySide6 import QtWidgets

    w = widgets.w
    t = now()
    inp.button(w, ev(X.ButtonPress, w, 50, 75, detail=1, t=t))
    inp.button(w, ev(X.ButtonRelease, w, 50, 75, detail=1, state=0x100, t=t + 10))
    inp.button(w, ev(X.ButtonPress, w, 50, 75, detail=1, t=t + 20))                # the double click
    assert spin(qapp, lambda: QtWidgets.QWidget.mouseGrabber() is not None)
    inp.motion(w, ev(X.MotionNotify, w, 60, 120, state=0))                        # no release came; buttons up
    assert spin(qapp, lambda: QtWidgets.QWidget.mouseGrabber() is None)
    inp.button(w, ev(X.ButtonPress, w, 50, 75, detail=1, t=t + 900))
    inp.button(w, ev(X.ButtonRelease, w, 50, 75, detail=1, state=0x100, t=t + 910))
    inp.button(w, ev(X.ButtonPress, w, 50, 75, detail=1, t=t + 920))
    assert spin(qapp, lambda: QtWidgets.QWidget.mouseGrabber() is not None)
    inp.button(w, ev(X.ButtonPress, w, 50, 25, detail=1, t=t + 3000))             # a new press, buttons up before
    assert QtWidgets.QWidget.mouseGrabber() is None
    inp.button(w, ev(X.ButtonRelease, w, 50, 25, detail=1, state=0x100, t=t + 3010))


def test_popups_close_when_the_x_focus_leaves_the_application(qapp, widgets, inp):
    """xcb: the X focus goes to another client while a combo's list is open; the list closes and no window stays
    active. Qt's popup mode keeps its activation while the X focus is ours."""
    from PySide6 import QtCore, QtWidgets

    w = widgets.w
    inp.x_focus(w, True)
    assert spin(qapp, lambda: qapp.activeWindow() is w)
    menu = QtWidgets.QMenu(w)
    menu.addAction("one")
    menu.popup(QtCore.QPoint(500, 300))
    assert spin(qapp, lambda: QtWidgets.QApplication.activePopupWidget() is menu)
    inp.x_focus(w, False)
    qapp.processEvents()
    assert menu.isVisible()                            # not before the X focus has really left (400 ms)
    assert spin(qapp, lambda: not menu.isVisible() and qapp.activeWindow() is None, 2.0)


def test_the_moves_offscreen_makes_for_our_set_pos_are_told_apart(qapp, widgets, inp):
    """Offscreen answers each QCursor.setPos with a mouse move (MouseEventSynthesizedByQt) that xcb never sends:
    after a pan, the one following the release moved the crosshair to another pixel. The bridge drops exactly those
    (its eventFilter); moves from X input are kept."""
    from PySide6 import QtCore, QtGui

    seen = []

    class F(QtCore.QObject):
        def eventFilter(self, o, e):
            if e.type() == QtCore.QEvent.Type.MouseMove and isinstance(o, QtGui.QWindow):
                seen.append(inp.is_own_synthetic_move(e))
            return False

    f = F()
    qapp.installEventFilter(f)
    try:
        w = widgets.w
        g = w.geometry()
        inp._set_cursor(g.x() + 120, g.y() + 150)
        assert spin(qapp, lambda: True in seen)
        seen.clear()
        inp.motion(w, ev(X.MotionNotify, w, 130, 160))
        assert spin(qapp, lambda: bool(seen))
        assert seen == [False]
    finally:
        qapp.removeEventFilter(f)


def test_a_window_that_moves_away_from_a_still_pointer_gets_its_leave(qapp, widgets, inp):
    """A zoomed window restored away from the pointer: X sends LeaveNotify without any motion; Qt's cursor is already
    at that point, and offscreen only finds the new window under it when setPos is called again."""
    from PySide6 import QtCore, QtGui

    w = widgets.w
    g = w.geometry()
    x, y = g.x() + 60, g.y() + 150
    inp.crossing(w, ev(X.EnterNotify, w, 60, 150, mode=X.NotifyNormal, detail=0))
    assert spin(qapp, lambda: w.underMouse())
    w.resize(40, 40)                                   # the window leaves the pointer (restored away from it)
    assert spin(qapp, lambda: w.width() == 40)
    le = SimpleNamespace(code=X.LeaveNotify, detail=0, mode=X.NotifyNormal, x=0, y=0, root_x=x, root_y=y, state=0,
                         time=now())
    inp.crossing(w, le)
    assert spin(qapp, lambda: not w.underMouse())
    assert QtCore.QPoint(x, y) == QtGui.QCursor.pos()                        # and Qt's cursor is back there


def test_window_ops_publish_the_shape_the_bridge_applies(qapp):
    """Offscreen keeps no masks: a window's outline (a title bar's rounded corners) reaches the X SHAPE only through
    the attribute the bridge reads. Without it the corners were square (the prototype's conformance suite)."""
    from PySide6 import QtGui, QtWidgets

    from explorer.platform.xbridge2 import Bridge2WindowOps
    from explorer.platform.xbridge2.windows import SHAPE_ATTR

    w = QtWidgets.QWidget()
    ops = Bridge2WindowOps(w, None)
    r = QtGui.QRegion(0, 0, 40, 30, QtGui.QRegion.RegionType.Ellipse)
    ops.set_shape(r)
    assert getattr(w, SHAPE_ATTR) == r
    ops.set_shape(None)
    assert getattr(w, SHAPE_ATTR).isEmpty()
