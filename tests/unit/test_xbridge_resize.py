"""A resize through the bridge (platform/xbridge/windows.py and Bridge._apply_geometry), against a fake X connection:
one request for one geometry from Qt, and nothing asked back when Qt takes X's geometry.

A trace through XQuartz (2026-10-05): an edge resize to 1748x1013 was asked as a move and then a size; quartz-wm
answered the move with its record of the frame, the old place and size (3696, 168, 1452, 848); the bridge took it,
and resizing Qt before moving it asked X for the old size again; the window went 1748, 1452, 1748 wide, sent whole
three times in 104 ms."""
from types import SimpleNamespace

import pytest


class FakeX:
    def __init__(self):
        self.screen = SimpleNamespace(root=1)
        self.seq = 100
        self.asked: list[dict] = []

    def configure_window(self, xid, **kw):
        self.seq += 1
        self.asked.append(kw)
        return self.seq

    def flush(self):
        pass


@pytest.fixture
def setup(qapp):
    from PySide6 import QtCore, QtWidgets

    from explorer.platform.xbridge import windows as wmod

    c = FakeX()
    ws = wmod.Windows(c)
    w = QtWidgets.QWidget()
    w.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint)    # as the bridge's: no frame margins offscreen
    w.setGeometry(100, 200, 640, 480)
    rec = wmod.XWin(w, 7, popup=False, owner=None)
    rec.asked.append((100, 200, 640, 480))              # as create() records it
    ws.by_widget[w], ws.by_xid[7] = rec, rec

    class Filter(QtCore.QObject):                      # what the bridge's event filter does with them
        def eventFilter(self, obj, e):
            if obj is w and e.type() in (QtCore.QEvent.Type.Move, QtCore.QEvent.Type.Resize):
                ws.qt_geometry(rec)
            return False
    f = Filter()
    w.installEventFilter(f)
    w.show()
    qapp.processEvents()
    c.asked.clear()
    applied: list = []
    yield SimpleNamespace(ws=ws, c=c, rec=rec, w=w, applied=applied,
                          apply=lambda *a: applied.append(a[:5]))
    w.removeEventFilter(f)
    w.close()
    w.deleteLater()


def notice(seq, x, y, w, h, sent=True):
    return SimpleNamespace(seq=seq, x=x, y=y, width=w, height=h, sent=sent)


def test_a_set_geometry_is_one_request(setup):
    """Qt's setGeometry moves, then resizes: asked apart, quartz-wm answered the move with the old size."""
    setup.w.setGeometry(100, 50, 800, 630)
    assert setup.c.asked == [dict(x=100, y=50, width=800, height=630)]


def test_a_move_alone_asks_the_place_alone(setup):
    setup.rec.xg = setup.w.geometry()                   # X told it (the manager's notice at the map)
    setup.w.move(120, 210)
    assert setup.c.asked == [dict(x=120, y=210)]


def test_a_move_and_a_resize_before_x_answers_ask_the_whole_geometry(setup):
    """quartz-wm fills what a request leaves out from its record of the frame, which changes when X confirms it:
    a size asked after a move it had not confirmed went to the old place (through a link of 25 ms, the move lost).
    The second request carries the place too, either way round."""
    s = setup
    s.rec.xg = s.w.geometry()
    s.w.move(120, 210)
    s.w.resize(700, 500)
    s.w.resize(720, 520)                                # X has still not answered
    assert s.c.asked == [dict(x=120, y=210), dict(x=120, y=210, width=700, height=500),
                         dict(x=120, y=210, width=720, height=520)]
    s.c.asked.clear()
    s.rec.xg = s.w.geometry()                           # X told the last one: what differs alone again
    s.w.resize(640, 480)
    s.w.move(100, 200)
    assert s.c.asked == [dict(width=640, height=480), dict(x=100, y=200, width=640, height=480)]


def test_taking_xs_geometry_asks_nothing(qapp, setup):
    """X's old place and size, taken with a resize and then a move: in between Qt had the old size at the new place,
    and that was asked of X as a new request."""
    from explorer.platform.xbridge.bridge import Bridge

    s = setup
    s.w.setGeometry(100, 50, 800, 630)
    s.c.asked.clear()
    me = SimpleNamespace(windows=s.ws, stats=dict(applied=0), post=None)
    Bridge._apply_geometry(me, s.rec, 100, 200, 640, 480)
    seen = dict(asked=s.c.asked, qt=s.w.geometry().getRect())
    assert seen == dict(asked=[], qt=(100, 200, 640, 480)), seen


def test_what_qt_would_not_take_is_asked_once(qapp, setup):
    from explorer.platform.xbridge.bridge import Bridge

    s = setup
    s.w.setMinimumSize(700, 500)
    s.c.asked.clear()
    me = SimpleNamespace(windows=s.ws, stats=dict(applied=0), post=None)
    Bridge._apply_geometry(me, s.rec, 90, 190, 600, 400)
    assert s.c.asked == [dict(width=700, height=500)]


def test_the_managers_old_record_after_a_resize_is_an_echo(setup):
    """quartz-wm's record of the frame, the old place and size, after a resize asked in one request: a geometry
    asked before the last, an echo. In the trace it was not one: the bridge's own request of the old size, made
    while taking X's geometry, had put another size into what it had asked."""
    s = setup
    s.w.setGeometry(100, 50, 800, 630)
    echoes = s.ws.stats["echoes"]
    s.ws.configured(s.rec, notice(s.c.seq, 100, 200, 640, 480), s.apply)
    seen = dict(applied=s.applied, echoes=s.ws.stats["echoes"] - echoes, asked=len(s.c.asked))
    assert seen == dict(applied=[], echoes=1, asked=1), seen
