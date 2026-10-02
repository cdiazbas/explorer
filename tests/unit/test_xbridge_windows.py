"""The bridge's windows (platform/xbridge/windows.py), against a fake X connection: where a window inside the
manager's frame is, asked of X without waiting, is taken only if Qt asked nothing newer meanwhile."""
import struct
from types import SimpleNamespace

import pytest


class Reply:
    def __init__(self):
        self.done = None

    def then(self, fn):
        self.done = fn


class FakeX:
    def __init__(self):
        self.screen = SimpleNamespace(root=1)
        self.seq = 100
        self.replies: list[Reply] = []

    def configure_window(self, xid, **kw):
        self.seq += 1
        return self.seq

    def translate_coordinates(self, src, dst):
        r = Reply()
        self.replies.append(r)
        return r


@pytest.fixture
def setup(qapp):
    from PySide6 import QtWidgets

    from explorer.platform.xbridge.windows import Windows, XWin

    c = FakeX()
    ws = Windows(c)
    w = QtWidgets.QWidget()
    rec = XWin(w, 7, popup=False, owner=None)
    rec.reparented = True
    applied = []
    yield ws, c, rec, applied
    w.deleteLater()


def notice(seq, x=0, y=0, w=560, h=341):
    return SimpleNamespace(seq=seq, x=x, y=y, width=w, height=h, sent=False)


def reply_at(x, y):
    return struct.pack("<12xhh", x, y)


def test_where_x_says_is_taken_when_nothing_newer_was_asked(setup):
    ws, c, rec, applied = setup
    ws.configure(rec, x=644, y=25)
    ws.configured(rec, notice(c.seq), lambda *a: applied.append(a))
    c.replies[-1].done(reply_at(644, 25), None)
    assert applied == [(rec, 644, 25, 560, 341, True)]


def test_an_answer_older_than_qts_last_request_is_dropped(setup):
    """Logged through XQuartz: lambda-t asked at (561, 373) went back to where it had been asked before (644, 378),
    then jumped about for 1.2 s, each late answer setting Qt back and Qt asking again."""
    ws, c, rec, applied = setup
    ws.configure(rec, x=644, y=378)
    ws.configured(rec, notice(c.seq), lambda *a: applied.append(a))
    ws.configure(rec, x=561, y=373)                    # glass places it, before X answers where it was
    c.replies[-1].done(reply_at(644, 378), None)
    assert applied == []
