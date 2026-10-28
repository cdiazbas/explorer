"""The rewritten bridge's X11 client without a server: where the display is, which cookie, request bytes against
python-xlib's own encoding (an independent implementation), events decoded, the event queue's wake-ups."""
import struct
import threading

import pytest

from explorer.platform.xbridge import xproto as X


def test_parse_display():
    assert X.parse_display(":99") == ("", 99, 0)
    assert X.parse_display("localhost:10.0") == ("localhost", 10, 0)
    assert X.parse_display("/private/tmp/com.apple.launchd.x/org.xquartz:0") == (
        "/private/tmp/com.apple.launchd.x/org.xquartz", 0, 0)
    with pytest.raises(ValueError):
        X.parse_display("")


def _entry(fam, addr, num, name, data):
    b = struct.pack(">H", fam)
    for part in (addr, num, name, data):
        b += struct.pack(">H", len(part)) + part
    return b


def test_cookie_by_host_name_first_then_address_then_any(tmp_path):
    f = tmp_path / "auth"
    f.write_bytes(_entry(X.FAMILY_WILD, b"", b"10", b"MIT-MAGIC-COOKIE-1", b"wild")
                  + _entry(X.FAMILY_INET, bytes([10, 0, 0, 1]), b"10", b"MIT-MAGIC-COOKIE-1", b"addr")
                  + _entry(X.FAMILY_LOCAL, b"bellatrix", b"10", b"MIT-MAGIC-COOKIE-1", b"name")
                  + _entry(X.FAMILY_LOCAL, b"bellatrix", b"11", b"MIT-MAGIC-COOKIE-1", b"other"))
    entries = X.read_xauthority(str(f))
    assert len(entries) == 4
    # sshd stores the cookie of "host:10" under the host name; python-xlib looked it up by address only
    assert X.choose_cookie(entries, 10, "inet", ["bellatrix.uio.no", "bellatrix"], bytes([10, 0, 0, 1]))[1] == b"name"
    assert X.choose_cookie(entries, 10, "inet", ["other"], bytes([10, 0, 0, 1]))[1] == b"addr"
    assert X.choose_cookie(entries, 10, "local", ["other"])[1] == b"wild"
    assert X.choose_cookie(entries, 12, "local", ["bellatrix"]) == (b"", b"")
    assert X.read_xauthority(str(tmp_path / "missing")) == []


def _ours(fn):
    """The bytes a request method writes, from a Connection that never connected."""
    c = X.Connection.__new__(X.Connection)
    c._lock, c._plock, c._out, c._seq, c._pending, c.lost = threading.Lock(), threading.Lock(), bytearray(), 0, {}, None
    c._flush_locked = lambda: None                      # keep the bytes
    fn(c)
    return bytes(c._out)


def test_requests_match_python_xlib():
    from Xlib.protocol import request as R
    from Xlib.protocol import rq

    def xlib(cls, **kw):
        return cls._request.to_binary(**kw)

    assert _ours(lambda c: c.change_property(5, 39, 31, 8, b"hello")) == xlib(
        R.ChangeProperty, mode=0, window=5, property=39, type=31, data=(8, b"hello"))
    assert _ours(lambda c: c.change_property(5, 1, 4, 32, [7, 8])) == xlib(
        R.ChangeProperty, mode=0, window=5, property=1, type=4, data=(32, [7, 8]))
    # (a negative x goes sign-extended here, zero-padded by python-xlib: the server reads the low 16 bits of both)
    assert _ours(lambda c: c.configure_window(9, x=3, width=40, stack_mode=0)) == xlib(
        R.ConfigureWindow, window=9, attrs={"x": 3, "width": 40, "stack_mode": 0})
    assert _ours(lambda c: c.copy_area(1, 2, 3, 4, 5, 6, 7, 8, 9)) == xlib(
        R.CopyArea, src_drawable=1, dst_drawable=2, gc=3, src_x=4, src_y=5, dst_x=6, dst_y=7, width=8, height=9)
    assert _ours(lambda c: c.put_image(1, 2, 2, 1, 3, 4, 24, b"\1\2\3\4\5\6\7\x08")) == xlib(
        R.PutImage, format=2, drawable=1, gc=2, width=2, height=1, dst_x=3, dst_y=4, left_pad=0, depth=24,
        data=b"\1\2\3\4\5\6\7\x08")
    assert _ours(lambda c: c.set_input_focus(7, 1234)) == xlib(R.SetInputFocus, revert_to=2, focus=7, time=1234)
    assert _ours(lambda c: c.convert_selection(1, 2, 3, 4, 0)) == xlib(
        R.ConvertSelection, requestor=1, selection=2, target=3, property=4, time=0)
    assert _ours(lambda c: c.create_pixmap(3, 4, 10, 20, 24)) == xlib(
        R.CreatePixmap, depth=24, pid=3, drawable=4, width=10, height=20)
    assert _ours(lambda c: c.create_window(10, 1, -5, 6, 70, 80, depth=24, visual=33,
                                          attrs={X.CW_EVENT_MASK: 0x8000, X.CW_OVERRIDE_REDIRECT: 1})) == xlib(
        R.CreateWindow, depth=24, wid=10, parent=1, x=-5, y=6, width=70, height=80, border_width=0,
        window_class=1, visual=33, attrs={"override_redirect": 1, "event_mask": 0x8000})
    assert _ours(lambda c: c.grab_pointer(4, 0x4C, True)) == xlib(
        R.GrabPointer, owner_events=1, grab_window=4, event_mask=0x4C, pointer_mode=1, keyboard_mode=1,
        confine_to=0, cursor=0, time=0)
    assert rq                                           # python-xlib's request structures, the reference here


def test_negative_int32_property_values_go_as_twos_complement():
    """WM_NORMAL_HINTS' x and y are INT32: a panel dragged above the screen's top edge has a negative y, which
    struct.pack("I") refused, and its X window was never created (the prototype's conformance suite, F23 steps)."""
    assert _ours(lambda c: c.change_property(5, 40, 40, 32, [1, -8, -3])) == _ours(
        lambda c: c.change_property(5, 40, 40, 32, [1, 0xFFFFFFF8, 0xFFFFFFFD]))


def test_client_message_and_events_match_python_xlib():
    from Xlib.protocol import event as XE

    ev = XE.ClientMessage(window=7, client_type=300, data=(32, [1, 2, 3, 4, 5]))
    ours = _ours(lambda c: c.client_message(1, 7, 300, [1, 2, 3, 4, 5], 0x180000))
    assert ours[12:44] == ev._binary                   # the event inside the SendEvent

    k = XE.KeyPress(detail=38, time=1000, root=1, window=7, child=0, root_x=-10, root_y=20, event_x=3,
                    event_y=4, state=5, same_screen=1, sequence_number=0)
    e = X.decode_event(k._binary)
    assert (e.code, e.detail, e.time, e.window, e.root_x, e.root_y, e.x, e.y, e.state) == (
        X.KeyPress, 38, 1000, 7, -10, 20, 3, 4, 5)
    cn = XE.ConfigureNotify(event=7, window=7, above_sibling=0, x=-4, y=5, width=300, height=200, border_width=0,
                            override=0, sequence_number=0)
    e = X.decode_event(bytes([cn._binary[0] | 0x80]) + cn._binary[1:])
    assert (e.code, e.sent, e.window, e.x, e.y, e.width, e.height) == (X.ConfigureNotify, True, 7, -4, 5, 300, 200)
    en = XE.EnterNotify(detail=0, time=9, root=1, window=7, child=0, root_x=1, root_y=2, event_x=3, event_y=4,
                        state=0, mode=2, flags=1, sequence_number=0)
    e = X.decode_event(en._binary)
    assert (e.code, e.mode, e.x, e.y) == (X.EnterNotify, 2, 3, 4)


def test_event_queue_wakes_once_per_batch_and_again_for_nested_loops():
    wakes = []
    q = X.EventQueue(lambda: wakes.append(1))
    for i in range(3):
        q.put(i)
    assert len(wakes) == 1                              # one wake-up for the three
    assert q.take() == 0
    q.rewake()                                          # a handler may start a nested loop: the rest wakes it
    assert len(wakes) == 2
    assert [q.take(), q.take(), q.take()] == [1, 2, None]
    q.put(3)
    assert len(wakes) == 3                              # empty again: the next event wakes


def test_an_event_after_a_nested_loop_started_wakes_it():
    """A click that opens a menu (Panels: QMenu::exec) is the last event in the queue when it is handled; the
    release comes later, while the menu's nested loop runs, and must wake it. It did not: the queue still counted
    the owner as woken, nothing read X any more and the viewer hung (on XQuartz; gdb: the main
    thread in QEventLoop::exec under QToolButton::mousePressEvent, in poll). XTEST on Xvfb sends both at once,
    which hid it."""
    wakes = []
    q = X.EventQueue(lambda: wakes.append(1))
    q.put("press")
    assert len(wakes) == 1
    assert q.take() == "press"
    q.rewake()                                          # nothing left: the handler opens the menu, never returns
    q.put("release")                                    # comes while the menu's loop runs
    assert len(wakes) == 2
    assert q.take() == "release"


def test_sequence_numbers_expand_past_16_bits():
    c = X.Connection.__new__(X.Connection)
    c._seq = 0x1_0005
    assert c._full_seq(0x0003) == 0x1_0003
    assert c._full_seq(0xFFFE) == 0x0_FFFE              # sent before the wrap
