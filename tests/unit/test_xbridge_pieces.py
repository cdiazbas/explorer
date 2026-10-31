"""The bridge splits what a window repainted into pieces, in the order Qt painted them (bridge._pieces): each piece
without what an earlier one has, and what came without a Paint event last."""
from PySide6 import QtCore, QtGui

from explorer.platform.xbridge.bridge import _pieces


def R(x, y, w, h):
    return QtGui.QRegion(QtCore.QRect(x, y, w, h))


def test_pieces_in_paint_order_without_overlap_and_the_rest_last():
    image, key, panel = R(0, 0, 800, 600), R(10, 500, 300, 100), R(800, 0, 400, 300)
    moved = R(0, 700, 50, 50)                           # a child moved: dirty without a Paint event
    dirty = image + key + panel + moved
    out = _pieces(dirty, [image, key, panel])
    assert [p.boundingRect() for p in out] == [image.boundingRect(), panel.boundingRect(), moved.boundingRect()]


def test_a_piece_outside_the_window_is_left_out():
    dirty = R(0, 0, 100, 100)
    out = _pieces(dirty, [R(200, 200, 10, 10), R(0, 0, 50, 50)])
    assert [p.boundingRect() for p in out] == [QtCore.QRect(0, 0, 50, 50), QtCore.QRect(0, 0, 100, 100)]
    assert out[1].subtracted(R(0, 0, 50, 50)) == out[1]



def test_the_sender_waits_for_a_slow_x_server_and_fails_with_a_broken_one(monkeypatch):
    """The backpressure waited 60 s for the server to take an update, then took it for a dead one and the viewer
    closed: a Mac asleep a minute with the ssh link up, or XQuartz frozen, while a status line changed. A slow server
    is waited for as long as it takes (said meanwhile); a broken connection fails its cookies at once, so the wait
    ends with the connection."""
    import threading

    from explorer.platform.xbridge import transport as T
    from explorer.platform.xbridge import xproto

    monkeypatch.setattr(T, "ACK_SAY_S", 0.05, raising=False)
    ck = xproto.Cookie()
    threading.Timer(0.3, ck._set, (b"ok", None)).start()          # answers after six of the waits
    T._wait_ack(ck)
    assert ck.done
    dead = xproto.Cookie()
    threading.Timer(0.1, dead._set, (None, xproto.ConnectionLost("gone"))).start()
    try:
        T._wait_ack(dead)
    except ConnectionError:
        pass
    else:
        raise AssertionError("a broken connection did not end the wait")



def test_copies_into_a_window_use_a_gc_made_on_the_image_connection_s_own_pixmap():
    """The gc for copies into a window was made on the window, by the image connection, while the window is made by
    the control connection: X orders the requests of one connection, not of two, so a burst over ssh could have the
    gc made before the window (BadDrawable), every copy failing (BadGC) and the window showing only its background
    for its whole life. The copies use the back pixmap's gc, made on a pixmap of the image connection's own."""
    from types import SimpleNamespace

    from explorer.platform.xbridge.transport import Transport

    ids = iter(range(100, 200))
    made: dict = {}
    copies: list = []
    c = SimpleNamespace(new_id=lambda: next(ids), screen=SimpleNamespace(root=1),
                        create_gc=lambda gid, drawable, *a: made.__setitem__(gid, drawable),
                        create_pixmap=lambda pid, root, w, h, d: made.__setitem__(pid, "pixmap"),
                        copy_area=lambda src, dst, gc, *a: copies.append(gc), free_gc=lambda g: None,
                        free_pixmap=lambda p: None,
                        get_input_focus=lambda: SimpleNamespace(then=lambda fn: None))
    t = Transport.__new__(Transport)
    t.c, t.grey, t.trace, t.depth, t._backs = c, None, None, 24, {}
    t.stats = {"copies": 0}
    t._copy_done = lambda: None
    window = 7
    t._back(window, 32, 16)
    t._copy(window, 0, 0, 32, 16)
    assert copies, "no copy made"
    for gc in copies:
        assert made.get(gc) != window and made.get(made.get(gc)) == "pixmap", (gc, made)
