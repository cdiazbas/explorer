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

    def full_seq(self, s16):                            # as xproto.Connection's: the latest request with these bits
        full = (self.seq & ~0xFFFF) | (s16 & 0xFFFF)
        return full - 0x10000 if full > self.seq else full

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


def notice(seq, x=0, y=0, w=560, h=341, sent=False):
    return SimpleNamespace(seq=seq, x=x, y=y, width=w, height=h, sent=sent)


def reply_at(x, y):
    return struct.pack("<12xhh", x, y)


def test_where_x_says_is_taken_when_nothing_newer_was_asked(setup):
    ws, c, rec, applied = setup
    ws.configure(rec, x=644, y=25)
    ws.configured(rec, notice(c.seq), lambda *a: applied.append(a))
    c.replies[-1].done(reply_at(644, 25), None)
    assert applied == [(rec, 644, 25, 560, 341, True, c.seq)]       # with the request it answers


def test_an_answer_older_than_qts_last_request_is_dropped(setup):
    """Logged through XQuartz: lambda-t asked at (561, 373) went back to where it had been asked before (644, 378),
    then jumped about for 1.2 s, each late answer setting Qt back and Qt asking again."""
    ws, c, rec, applied = setup
    ws.configure(rec, x=644, y=378)
    ws.configured(rec, notice(c.seq), lambda *a: applied.append(a))
    ws.configure(rec, x=561, y=373)                    # glass places it, before X answers where it was
    c.replies[-1].done(reply_at(644, 378), None)
    assert applied == []


# The manager's notices are synthetic (ICCCM 4.1.5: root coordinates). Asking X where each one is cost a round trip
# that blocked the interface, 2.4 ms per notice on XQuartz, 21 % of a 60-Hz panel drag; taking every one set Qt back
# to where a late notice said (a panel 250 px behind its X window). The prototype's F27, app/xbridge.py:1202-1210.

def test_a_synthetic_notice_of_the_last_request_is_taken_without_asking_x(setup):
    ws, c, rec, applied = setup
    ws.configure(rec, x=600, y=300, width=560, height=341)
    ws.configure(rec, x=640, y=320, width=560, height=341)
    ws.configured(rec, notice(c.seq, 640, 320, sent=True), lambda *a: applied.append(a))
    seen = dict(applied=applied, asked_x=len(c.replies))
    want = dict(applied=[(rec, 640, 320, 560, 341)], asked_x=0)
    assert seen == want, seen


def test_a_synthetic_notice_of_an_older_request_is_an_echo_and_dropped(setup):
    ws, c, rec, applied = setup
    ws.configure(rec, x=600, y=300, width=560, height=341)
    ws.configure(rec, x=640, y=320, width=560, height=341)
    echoes = ws.stats["echoes"]
    ws.configured(rec, notice(c.seq, 600, 300, sent=True), lambda *a: applied.append(a))   # late, of the first
    seen = dict(applied=applied, asked_x=len(c.replies), echoes=ws.stats["echoes"] - echoes)
    assert seen == dict(applied=[], asked_x=0, echoes=1), seen


def test_where_x_says_is_an_echo_when_it_is_an_older_geometry_asked(setup):
    """Seen from bellatrix through ssh -Y (a geometry trace): glass placed the spectrum at (2757, 55), the
    manager had not yet acted on it, and X answered where the panel's window had been created, (2703, 87): taken, the
    panel went back over the main window until a later notice. An answer that is a geometry asked before the last
    one (the window's first geometry is one) is an echo, as a synthetic notice of one is."""
    ws, c, rec, applied = setup
    rec.asked.append((2703, 87, 598, 434))              # as create() records the geometry it makes the window with
    ws.configure(rec, x=2757, y=55, width=560, height=442)
    echoes = ws.stats["echoes"]
    ws.configured(rec, notice(c.seq, 0, 0, 598, 434), lambda *a: applied.append(a))
    c.replies[-1].done(reply_at(2703, 87), None)
    seen = dict(applied=applied, echoes=ws.stats["echoes"] - echoes)
    assert seen == dict(applied=[], echoes=1), seen



def test_a_notice_past_half_the_16_bit_sequence_is_taken_not_an_echo(setup):
    """The echo test compared our last ConfigureWindow's full number with the notice's 16 bits: 32769 requests or
    more after it (cursors, tooltips, raises in a long session), a notice of the window manager's own move or
    resize looked older and was dropped as an echo; the check that asks X again then returned, a notice having been
    applied before. The notice's number is extended to the full one, as replies' are."""
    ws, c, rec, applied = setup
    rec.reparented = False                              # a notice applied as it comes
    rec.cfg_seq = c.configure_window(rec.xid)
    c.seq += 40000                                      # other requests since, on the control connection
    ws.configured(rec, notice(c.seq & 0xFFFF, 300, 200, 700, 500), lambda *a: applied.append(a))
    assert applied and applied[-1][1:5] == (300, 200, 700, 500), applied
    applied.clear()
    ws.configured(rec, notice((rec.cfg_seq - 1) & 0xFFFF, 1, 2, 3, 4), lambda *a: applied.append(a))
    assert not applied                                  # one generated before our last request: an echo still



def test_where_x_says_is_dropped_when_qt_asked_again_before_it_is_applied(setup):
    """The answer of where a framed window is was checked on the reader thread and applied later on Qt's: Qt's
    queued moves could ask X for a new geometry in between, and the old place was applied, the panel jumping back a
    step while dragged over a slow link. It is checked again when applied."""
    from explorer.platform.xbridge.bridge import Bridge

    ws, c, rec, applied = setup
    queue: list = []
    stub = SimpleNamespace(windows=SimpleNamespace(get=lambda w: rec, qt_geometry=lambda r: None),
                           stats={"applied": 0}, post=lambda fn, *a: queue.append((fn, a)))
    stub._apply_geometry = lambda *a, **k: Bridge._apply_geometry(stub, *a, **k)

    import inspect

    takes = "asked" in inspect.signature(Bridge._apply_geometry).parameters

    def apply(r, x, y, w, h, from_reader=False, asked=None):
        kw = {"asked": asked} if takes else {}
        Bridge._apply_geometry(stub, r, x, y, w, h, from_reader, **kw)
    rec.cfg_seq = c.configure_window(rec.xid)
    ws.configured(rec, notice(c.seq), apply)            # framed: X is asked where it is
    c.replies[-1].done(reply_at(40, 50), None)          # the answer, on the reader thread: posted
    assert len(queue) == 1
    rec.cfg_seq = c.configure_window(rec.xid)           # Qt asks again before the posted apply runs
    fn, a = queue.pop()
    fn(*a)
    assert stub.stats["applied"] == 0, "the old place applied over the newer request"
