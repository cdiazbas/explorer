"""Our title bar and edges (ROADMAP E5.2), offscreen: the window becomes frameless with a 32-px bar and a rounded
shape; the zoom light and a double click on the bar fill the monitor and come back; a drag on the bar moves the
window, no higher than the top of its monitor, as a macOS window stays below the menu bar, while the sides and the
bottom may leave it; the edges resize it, down to its minimum, with the pointer naming the edge, and a button in the
band keeps its clicks; our pointer leaves anyone else's on the stack; a floating panel gets the same edges, with a
thin top band so its title still moves it; every dock gets its close and float buttons; where the bar is not wanted
nothing is installed."""
import sys

import pytest


@pytest.fixture
def win(qapp):
    from PySide6 import QtCore, QtWidgets

    from explorer.platform.display import Display
    from explorer.platform.plan import DisplayPlan
    from explorer.ui import titlebar

    disp = Display(DisplayPlan("offscreen"))
    w = QtWidgets.QMainWindow()
    w.setCentralWidget(QtWidgets.QLabel("image"))
    for name in ("spectrum", "lambda_t"):
        d = QtWidgets.QDockWidget(name, w)
        d.setObjectName(name)
        d.setWidget(QtWidgets.QLabel(name))
        w.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, d)
    ops = disp.ops(w)
    titlebar.dock_titles(w)
    bar = titlebar.install(w, ops)
    w.setGeometry(100, 80, 900, 600)
    disp.attach(qapp, w, ops)
    qapp.processEvents()
    yield w, bar, ops
    ops.set_cursor(None)
    w.close()


def mouse(qapp, widget, kind, pos, button=None, buttons=None):
    from PySide6 import QtCore, QtGui, QtWidgets

    B = QtCore.Qt.MouseButton
    p = QtCore.QPointF(pos)
    ev = QtGui.QMouseEvent(kind, p, QtCore.QPointF(widget.mapToGlobal(pos)), button or B.NoButton,
                           buttons if buttons is not None else B.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(widget, ev)
    qapp.processEvents()


def test_frameless_with_the_bar_and_a_rounded_shape(win):
    from PySide6 import QtCore

    from explorer.ui import titlebar

    w, bar, _ops = win
    assert w.windowFlags() & QtCore.Qt.WindowType.FramelessWindowHint
    assert w.menuWidget() is bar and bar.height() == titlebar.TitleBar.H == 32
    region = bar.corners.region
    assert region.contains(QtCore.QPoint(20, 20)) and not region.contains(QtCore.QPoint(0, 0))
    assert not region.contains(QtCore.QPoint(w.width() - 1, w.height() - 1))


def test_the_zoom_light_and_a_double_click_fill_the_monitor_and_come_back(qapp, win):
    from PySide6 import QtCore

    from explorer.platform.screens import monitor_rect

    w, bar, ops = win
    E = QtCore.QEvent.Type
    B = QtCore.Qt.MouseButton
    g0 = w.geometry()
    zoom = bar._lights()[2].center().toPoint()
    mouse(qapp, bar, E.MouseButtonPress, zoom, B.LeftButton, B.LeftButton)
    mouse(qapp, bar, E.MouseButtonRelease, zoom, B.LeftButton)
    mon = monitor_rect(qapp, g0.center())
    assert w.geometry() == mon and ops.unzoomed == g0
    mid = QtCore.QPoint(bar.width() // 2, bar.height() // 2)
    mouse(qapp, bar, E.MouseButtonDblClick, mid, B.LeftButton, B.LeftButton)
    assert w.geometry() == g0 and ops.unzoomed is None


def test_a_drag_on_the_bar_moves_the_window(qapp, win):
    from PySide6 import QtCore

    w, bar, _ops = win
    E = QtCore.QEvent.Type
    B = QtCore.Qt.MouseButton
    p0, at = w.pos(), QtCore.QPoint(bar.width() // 2, 10)
    mouse(qapp, bar, E.MouseButtonPress, at, B.LeftButton, B.LeftButton)
    mouse(qapp, bar, E.MouseMove, at + QtCore.QPoint(40, 25), None, B.LeftButton)
    mouse(qapp, bar, E.MouseButtonRelease, at + QtCore.QPoint(40, 25), B.LeftButton)
    assert w.pos() == p0 + QtCore.QPoint(40, 25)


def test_a_drag_stops_at_the_top_of_the_monitor_not_at_the_sides_nor_the_bottom(qapp, win):
    """Over XQuartz the bar moves the window itself (quartz-wm offers no system move) and nothing kept it below the
    menu bar: dragged up, the window left the screen by the top. A macOS window's bar stays below the menu bar; by
    the sides and the bottom it may leave."""
    from PySide6 import QtCore

    from explorer.platform.screens import monitor_rect

    w, bar, _ops = win
    E = QtCore.QEvent.Type
    B = QtCore.Qt.MouseButton
    top = monitor_rect(qapp, w.geometry().center()).top()
    p0, at = w.pos(), QtCore.QPoint(bar.width() // 2, 10)
    g0 = bar.mapToGlobal(at)

    def to(dx, dy):                                     # the pointer dx, dy from where it was pressed, in bar terms
        return bar.mapFromGlobal(g0 + QtCore.QPoint(dx, dy))
    mouse(qapp, bar, E.MouseButtonPress, at, B.LeftButton, B.LeftButton)
    mouse(qapp, bar, E.MouseMove, to(-p0.x() - 300, -p0.y() - 400), None, B.LeftButton)   # past the left, above the top
    assert w.y() == top and w.x() == -300                                 # stopped at the top, not at the left
    mouse(qapp, bar, E.MouseMove, to(0, 3000), None, B.LeftButton)
    mouse(qapp, bar, E.MouseButtonRelease, to(0, 3000), B.LeftButton)
    assert w.pos() == p0 + QtCore.QPoint(0, 3000)                          # and down past the bottom


def test_the_edges_resize_down_to_the_minimum_and_name_the_edge(qapp, win):
    from PySide6 import QtCore, QtWidgets

    w, bar, _ops = win
    E = QtCore.QEvent.Type
    B = QtCore.Qt.MouseButton
    C = QtCore.Qt.CursorShape
    rz = bar.resizer
    g0 = w.geometry()
    p = QtCore.QPoint(w.width() - 2, w.height() // 2)
    gp = w.mapToGlobal(p)
    rz.mouse(E.MouseMove, p, gp, B.NoButton)
    assert QtWidgets.QApplication.overrideCursor().shape() == C.SizeHorCursor
    rz.mouse(E.MouseMove, QtCore.QPoint(w.width() // 2, w.height() // 2), gp, B.NoButton)
    assert QtWidgets.QApplication.overrideCursor() is None            # only ours, and it is gone
    corner = QtCore.QPoint(w.width() - 3, w.height() - 3)
    rz.mouse(E.MouseMove, corner, gp, B.NoButton)
    assert QtWidgets.QApplication.overrideCursor().shape() == C.SizeFDiagCursor
    assert rz.mouse(E.MouseButtonPress, p, gp, B.LeftButton)
    rz.mouse(E.MouseMove, p, gp + QtCore.QPoint(-100, 0), B.LeftButton)
    rz.mouse(E.MouseButtonRelease, p, gp + QtCore.QPoint(-100, 0), B.NoButton)
    qapp.processEvents()
    assert w.width() == g0.width() - 100
    gc = w.mapToGlobal(corner)
    rz.mouse(E.MouseButtonPress, corner, gc, B.LeftButton)
    rz.mouse(E.MouseMove, corner, gc - QtCore.QPoint(5000, 5000), B.LeftButton)
    rz.mouse(E.MouseButtonRelease, corner, gc - QtCore.QPoint(5000, 5000), B.NoButton)
    qapp.processEvents()
    assert (w.width(), w.height()) == (rz.MIN_W, rz.MIN_H)


def test_our_pointer_leaves_a_foreign_one_on_the_stack(qapp, win):
    """The edges' pointer is an override cursor; taking it off removes ours only. The prototype emptied the whole
    stack, a wait cursor pushed by a load included (its F14, app/titlebar.py:54-61)."""
    from PySide6 import QtCore, QtWidgets

    _w, _bar, ops = win
    C = QtCore.Qt.CursorShape
    A = QtWidgets.QApplication
    A.setOverrideCursor(C.WaitCursor)                   # someone else's
    try:
        seen = []
        for shape in (C.SizeHorCursor, C.SizeVerCursor, C.SizeFDiagCursor, None):
            ops.set_cursor(shape)
            top = A.overrideCursor()
            seen.append(top.shape() if top is not None else None)
        want = [C.SizeHorCursor, C.SizeVerCursor, C.SizeFDiagCursor, C.WaitCursor]
        assert seen == want, dict(seen=seen, want=want)
    finally:
        while A.overrideCursor() is not None:
            A.restoreOverrideCursor()


@pytest.fixture
def panels(qapp, monkeypatch):
    """A window with our chrome as app.chrome puts it on Linux, one of its panels floating beside it."""
    from PySide6 import QtCore, QtWidgets

    from explorer.platform.display import Display
    from explorer.platform.plan import DisplayPlan
    from explorer.ui import titlebar

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv(titlebar.ENV, raising=False)
    disp = Display(DisplayPlan("offscreen"))
    w = QtWidgets.QMainWindow()
    w.setCentralWidget(QtWidgets.QLabel("image"))
    for name in ("spectrum", "lambda_t"):
        d = QtWidgets.QDockWidget(name, w)
        d.setObjectName(name)
        d.setWidget(QtWidgets.QLabel(name))
        w.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, d)
    ops = disp.ops(w)
    bar = titlebar.chrome(qapp, w, ops, disp.ops)
    assert bar is not None, "our chrome is wanted on Linux"
    w.setGeometry(100, 80, 900, 600)
    disp.attach(qapp, w, ops)
    d = w.findChild(QtWidgets.QDockWidget, "spectrum")
    d.setFloating(True)
    d.setGeometry(1050, 100, 400, 300)
    d.show()
    qapp.processEvents()
    yield w, bar, d
    while QtWidgets.QApplication.overrideCursor() is not None:
        QtWidgets.QApplication.restoreOverrideCursor()
    d.setFloating(False)
    w.close()


def test_a_floating_panel_resizes_by_the_main_windows_edges(qapp, panels):
    """Qt resizes a floating panel by its 1-px frame only: on Linux the pointer had to be on the exact pixel. With
    our chrome each panel's QWindow gets the main window's EdgeResizer, a 7-px band (the prototype's F23d,
    app/titlebar.py:473-499, installed by app/viewer.py:2573-2576)."""
    from PySide6 import QtCore, QtGui, QtWidgets

    _w, _bar, d = panels
    E = QtCore.QEvent.Type
    B = QtCore.Qt.MouseButton
    h = d.windowHandle()
    assert h is not None, "a floating panel has its own QWindow"

    def send(kind, p, gp, button=B.NoButton, buttons=B.NoButton):
        ev = QtGui.QMouseEvent(kind, QtCore.QPointF(p), QtCore.QPointF(gp), button, buttons,
                               QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(h, ev)
        qapp.processEvents()

    g0 = d.geometry()
    p = QtCore.QPoint(d.width() - 4, d.height() // 2)        # 4 px in from the right edge, past Qt's 1-px frame
    gp = d.mapToGlobal(p)
    send(E.MouseMove, p, gp)
    top = QtWidgets.QApplication.overrideCursor()
    seen = top.shape() if top is not None else None
    assert seen == QtCore.Qt.CursorShape.SizeHorCursor, dict(seen=seen, at=p, panel=g0)
    send(E.MouseButtonPress, p, gp, B.LeftButton, B.LeftButton)
    send(E.MouseMove, p, gp + QtCore.QPoint(60, 0), B.NoButton, B.LeftButton)
    send(E.MouseButtonRelease, p, gp + QtCore.QPoint(60, 0), B.LeftButton)
    seen = d.geometry()
    want = QtCore.QRect(g0.x(), g0.y(), g0.width() + 60, g0.height())
    assert seen == want, dict(seen=seen, want=want)


def test_a_floating_panels_top_band_is_thin_so_its_title_moves_it(qapp, panels):
    """A panel's title is about 17 px: the main window's 7-px top band took its upper half, and a grab 6 px down
    resized where it should move. 3 px on a panel, what macOS keeps inside the top edge; 7 on the main window (the
    prototype's F23i, app/titlebar.py:478-481)."""
    from PySide6 import QtCore

    w, bar, d = panels
    T = QtCore.Qt.Edge.TopEdge
    rz = next((pe.resizer for pe in getattr(w, "_panel_edges", []) if pe.d is d), None)
    assert rz is not None, dict(panel_edges=getattr(w, "_panel_edges", None))
    x = d.width() // 2                                      # the title's middle, clear of its buttons
    seen = dict(panel_y5=rz.edges_at(QtCore.QPoint(x, 5)), panel_y1=rz.edges_at(QtCore.QPoint(x, 1)),
                main_y5=bar.resizer.edges_at(QtCore.QPoint(w.width() // 2, 5)))
    want = dict(panel_y5=QtCore.Qt.Edge(0), panel_y1=T, main_y5=T)
    assert seen == want, dict(seen=seen, want=want, top_band=rz.top_band)


def test_a_resize_shows_an_outline_and_resizes_once_on_release(qapp, win):
    """Over X11 every resize step redrew the whole window and sent it: through an emulated ssh link (8 ms, 20 MB/s)
    a 1-s drag of 200 px sent 17.7 MB, the link full. While dragging, four thin windows outline the size to come and
    the window is left alone; it takes that size once, on release (3.3-3.5 MB in all)."""
    from PySide6 import QtCore

    w, bar, _ops = win
    E = QtCore.QEvent.Type
    B = QtCore.Qt.MouseButton
    rz = bar.resizer
    g0 = w.geometry()
    p = QtCore.QPoint(w.width() - 2, w.height() // 2)
    gp = w.mapToGlobal(p)
    assert rz.mouse(E.MouseButtonPress, p, gp, B.LeftButton)
    rz.mouse(E.MouseMove, p, gp + QtCore.QPoint(120, 0), B.LeftButton)
    rz._timer.timeout.emit()                            # the outline's next update, without waiting 25 ms
    qapp.processEvents()
    want = QtCore.QRect(g0.x(), g0.y(), g0.width() + 120, g0.height())
    bars = rz.outline.bars
    assert w.geometry() == g0                                            # left alone while dragging
    assert all(b.isVisible() for b in bars)
    hull = bars[0].geometry()
    for b in bars[1:]:
        hull = hull.united(b.geometry())
    assert hull == want                                                  # the outline is the size to come
    assert sum(b.width() * b.height() for b in bars) < 0.02 * want.width() * want.height()   # thin: few pixels
    rz.mouse(E.MouseButtonRelease, p, gp + QtCore.QPoint(120, 0), B.NoButton)
    qapp.processEvents()
    assert w.geometry() == want and not any(b.isVisible() for b in bars)


def test_the_release_point_sets_the_size(qapp, win):
    """The size is where the pointer was released, not the last move handled: a busy window may get the release
    before the moves that came just before it."""
    from PySide6 import QtCore

    w, bar, _ops = win
    E = QtCore.QEvent.Type
    B = QtCore.Qt.MouseButton
    rz = bar.resizer
    g0 = w.geometry()
    p = QtCore.QPoint(w.width() - 2, w.height() // 2)
    gp = w.mapToGlobal(p)
    rz.mouse(E.MouseButtonPress, p, gp, B.LeftButton)
    rz.mouse(E.MouseMove, p, gp + QtCore.QPoint(40, 0), B.LeftButton)
    rz.mouse(E.MouseButtonRelease, p, gp + QtCore.QPoint(300, 0), B.NoButton)      # the moves between never came
    qapp.processEvents()
    assert w.width() == g0.width() + 300


def test_a_button_in_the_band_keeps_its_clicks(win):
    from PySide6 import QtCore

    w, bar, _ops = win
    d = w.findChild(QtCore.QObject, "spectrum")
    d.setFloating(True)
    from explorer.ui import titlebar

    rz = titlebar.EdgeResizer(d, bar.m, titlebar.PANEL_MIN)
    b = d.titleBarWidget().button
    at = b.mapTo(d, b.rect().center())
    assert rz.edges_at(at) == QtCore.Qt.Edge(0)
    d.setFloating(False)


def test_every_dock_gets_its_close_and_float_buttons(qapp, win):
    from PySide6 import QtWidgets

    w, _bar, _ops = win
    for d in w.findChildren(QtWidgets.QDockWidget):
        t = d.titleBarWidget()
        names = sorted(b.objectName() for b in t.findChildren(QtWidgets.QToolButton))
        assert names == ["qt_dockwidget_closebutton", "qt_dockwidget_floatbutton"]
        t.button.click()
        qapp.processEvents()
        assert d.isFloating()
        t.button.click()
        qapp.processEvents()
        assert not d.isFloating()


@pytest.mark.parametrize("platform, env, bridge, bar, titles", [
    ("linux", None, False, True, True),
    ("darwin", None, False, False, False),               # a Mac's own windows: its native frame
    ("darwin", None, True, True, True),                  # a Mac's screen through the bridge: an X display
    ("linux", "wm", False, False, False),
    ("linux", "wm", True, False, True),                  # the bridge's floating panels still need a title Qt draws
])
def test_where_the_bar_is_wanted(qapp, monkeypatch, platform, env, bridge, bar, titles):
    from PySide6 import QtWidgets

    from explorer.platform.display import Display
    from explorer.platform.plan import DisplayPlan
    from explorer.ui import titlebar

    monkeypatch.setattr(sys, "platform", platform)
    if env:
        monkeypatch.setenv(titlebar.ENV, env)
    else:
        monkeypatch.delenv(titlebar.ENV, raising=False)
    disp = Display(DisplayPlan("offscreen"))
    w = QtWidgets.QMainWindow()
    QtWidgets.QDockWidget("spectrum", w)
    got = titlebar.chrome(qapp, w, disp.ops(w), disp.ops, bridge=bridge)
    assert (got is not None) == bar
    assert (w.findChild(QtWidgets.QDockWidget).titleBarWidget() is not None) == titles
    w.close()


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_the_bar_and_hairline_paint_in_both_themes(qapp, win, theme):
    from explorer.ui import style

    w, bar, _ops = win
    errors = []
    hook, sys.excepthook = sys.excepthook, lambda t, e, tb: errors.append(f"{t.__name__}: {e}")
    import pyqtgraph as pg
    from PySide6 import QtGui, QtWidgets

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    try:
        style.apply_theme(qapp, theme)
        bar._set_hover(True)
        assert not w.grab().isNull()
    finally:
        sys.excepthook = hook
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)
        qapp.setProperty("explorer_light", False)
        pg.setConfigOptions(background="k", foreground="d")
    assert errors == []
