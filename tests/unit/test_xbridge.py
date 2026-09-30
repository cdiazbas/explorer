"""The X11 bridge without an X server: the request writer against python-xlib's own packing, the tile comparison in
numba against numpy, runs of tiles, keys, cookies, RENDER formats, the settings, Qt's input symbols, and the Display
the plan picks. The bridge on a real X server: test_xbridge_x11.py."""
import socket
import struct

import numpy as np
import pytest

from explorer.platform.xbridge import render, transport, xconn
from explorer.platform.xbridge.transport import Knobs, put_encode, put_size, runs, tile_flags

IDS = [11, 12, 13, 14, 15, 16, 17, 139, 24]    # back, gc, mask, mask gc, mask pic, white pic, back pic, opcode, depth


def reference(a, rects, ox, oy, ids, maxb):
    """The same requests packed by python-xlib (PutImage) and by render.py's declaration (Composite)."""
    from Xlib.protocol import request

    out = b""
    for k, x0, y0, w, h in rects.tolist():
        stride = w * 4 if k == 0 else (w + 3) // 4 * 4
        rows = max(1, maxb // stride)
        dx, dy = ox + x0, oy + y0
        for r in range(0, h, rows):
            n = min(rows, h - r)
            sub = a[y0 + r:y0 + r + n, x0:x0 + w]
            if k == 0:
                data = sub.astype("<u4").tobytes()
            else:
                pad = np.zeros((n, stride), np.uint8)
                pad[:, :w] = sub & 255
                data = pad.tobytes()
            out += request.PutImage._request.to_binary(
                format=2, drawable=ids[0] if k == 0 else ids[2], gc=ids[1] if k == 0 else ids[3], width=w, height=n,
                dst_x=dx, dst_y=dy + r, left_pad=0, depth=ids[8] if k == 0 else 8, data=data)
        if k == 1:
            out += render._Composite._request.to_binary(
                opcode=ids[7], op=render.PICT_OP_SRC, src=ids[5], mask=ids[4], dst=ids[6], src_x=0, src_y=0,
                mask_x=dx, mask_y=dy, dst_x=dx, dst_y=dy, width=w, height=h)
    return out


@pytest.mark.parametrize("maxb", [262076, 200])     # python-xlib's limit, and a tiny one: requests split in rows
def test_the_request_writer_matches_python_xlib(maxb):
    rng = np.random.default_rng(3)
    a = rng.integers(0, 2 ** 32, (70, 90), dtype=np.uint64).astype(np.uint32)
    a.flags.writeable = False                           # as the grabbed pixels (a type of its own for numba)
    rects = np.array([[0, 0, 0, 33, 7], [1, 5, 9, 31, 20], [1, 40, 30, 1, 1], [0, 60, 50, 30, 20]], np.int64)
    size, nreq = put_size(rects, maxb)
    buf = np.empty(size, np.uint8)
    n = put_encode(a, rects, 100, 200, np.array(IDS, np.int64), maxb, buf)
    ref = reference(a, rects, 100, 200, IDS, maxb)
    assert n == size == len(ref) and buf.tobytes() == ref
    # one request per chunk of rows, plus one Composite per grey piece
    assert nreq == sum(-(-h // max(1, maxb // (w * 4 if k == 0 else (w + 3) // 4 * 4))) + k for k, _, _, w, h in rects)


def test_tile_flags_match_numpy():
    rng = np.random.default_rng(5)
    grey = rng.integers(0, 256, (100, 70), dtype=np.uint32) * 0x010101
    last = grey.copy()
    a = grey.copy()
    a[3, 3] += 1                                        # tile (0, 0): a changed pixel (and no longer grey)
    a[40:45, 40:45] = 0x00FF0000                        # tile (1, 1): changed, colour
    a[99, 69] = 0x00070707                              # tile (3, 2): changed, still grey (unless it was that already)
    T = transport.TILE
    changed, colour = np.zeros((4, 3), bool), np.zeros((4, 3), bool)
    tile_flags(a, last, T, False, True, changed, colour)
    ty, tx = np.arange(0, 100, T), np.arange(0, 70, T)

    def tiles_of(m):
        return np.logical_or.reduceat(np.logical_or.reduceat(m, ty, axis=0), tx, axis=1)

    assert (changed == tiles_of(a != last)).all() and changed[0, 0] and changed[1, 1]
    want = tiles_of(((a ^ (a >> 8)) & 0xFFFF) != 0)
    assert (colour[changed] == want[changed]).all() and colour[1, 1] and colour[0, 0]
    forced = np.zeros((4, 3), bool)
    tile_flags(a, a, T, True, False, forced, colour)
    assert forced.all()


def test_runs_cover_the_mask_once():
    rng = np.random.default_rng(7)
    for _ in range(20):
        m = rng.random((9, 13)) < 0.4
        cover = np.zeros(m.shape, int)
        for (x0, x1), (y0, y1) in runs(m):
            cover[y0:y1, x0:x1] += 1
        assert (cover == m).all()


def changed_tiles(numba_on):
    s = object.__new__(transport.Sender)
    s.last, s.tile_flags, s.grey_on = {}, tile_flags if numba_on else None, True
    return s


@pytest.mark.parametrize("numba_on", [True, False])
def test_changed_tiles_grey_and_colour(numba_on):
    s = changed_tiles(numba_on)
    W, H = 100, 70
    img = np.full((H, W), 0x00202020, np.uint32)
    first = s.changed_tiles(1, 0, 0, img, False, W, H)  # nothing known: all of it, grey (kind 1)
    assert (first[:, 0] == 1).all() and (first[:, 3] * first[:, 4]).sum() == W * H
    assert len(s.changed_tiles(1, 0, 0, img, False, W, H)) == 0        # unchanged: nothing
    nxt = img.copy()
    nxt[5, 70] = 0x00FF0000                             # one colour tile
    nxt[60, 10] = 0x00303030                            # one grey tile
    got = sorted(map(tuple, s.changed_tiles(1, 0, 0, nxt, False, W, H).tolist()))
    assert got == [(0, 64, 0, 32, 32), (1, 0, 32, 32, 32)]
    part = s.changed_tiles(1, 64, 0, nxt[:32, 64:96].copy(), True, W, H)  # forced: resent though unchanged
    assert part.tolist() == [[0, 0, 0, 32, 32]]


def test_keys():
    from PySide6 import QtCore

    from explorer.platform.xbridge.qtinput import ctrl_char, key_of

    K, M = QtCore.Qt.Key, QtCore.Qt.KeyboardModifier
    assert key_of(ord("a"), M.NoModifier) == (K.Key_A, "a", M.NoModifier)
    assert key_of(ord("a"), M.ControlModifier)[1] == "\x01"
    assert key_of(0xf1, M.NoModifier)[:2] == (K.Key_Ntilde, "ñ")                  # Latin-1 keysym
    assert key_of(0xff0d, M.NoModifier)[:2] == (K.Key_Return, "\r")
    assert key_of(0xff52, M.NoModifier)[:2] == (K.Key_Up, "")
    k, text, mods = key_of(0xffb5, M.NoModifier)                                 # keypad 5 with NumLock
    assert (k, text) == (K.Key_5, "5") and mods & M.KeypadModifier
    assert key_of(0xfd01, M.NoModifier) is None                                  # a keysym Qt has no key for
    assert [ctrl_char(c) for c in "2835 /"] == ["\x00", "\x7f", "\x1b", "\x1d", "\x00", "\x1f"]


def test_cookies_by_host_then_any(tmp_path, monkeypatch):
    def entry(fam, addr, num, data):
        f = struct.pack(">H", fam)
        for s in (addr, num, b"MIT-MAGIC-COOKIE-1", data):
            f += struct.pack(">H", len(s)) + s
        return f

    host = socket.gethostname().encode()
    p = tmp_path / "auth"
    p.write_bytes(entry(65535, b"", b"7", b"W" * 16) + entry(256, host, b"7", b"L" * 16)
                  + entry(256, host, b"8", b"8" * 16))
    monkeypatch.setenv("XAUTHORITY", str(p))
    assert [d for _, d in xconn.cookies(7)] == [b"L" * 16, b"W" * 16]
    assert xconn.display_number({"DISPLAY": "localhost:10.0"}) == 10 and xconn.display_number({}) is None


def test_render_formats():
    fmt = struct.pack("<IBB2x8HI", 0x21, 1, 8, 0, 0, 0, 0, 0, 0, 0, 0xff, 0)       # A8
    fmt += struct.pack("<IBB2x8HI", 0x22, 1, 24, 16, 0xff, 8, 0xff, 0, 0xff, 0, 0, 0)
    head = struct.pack("<BxHI", 1, 0, 0) + struct.pack("<IIIII4x", 2, 1, 1, 1, 0)
    scr = struct.pack("<II", 1, 0) + struct.pack("<BxH4x", 24, 1) + struct.pack("<II", 0x40, 0x22)
    raw = head + fmt + scr
    assert render.Grey.formats(raw, 0x40) == (0x21, 0x22) and render.Grey.formats(raw, 0x99) == (0x21, None)


def test_knobs_from_the_environment():
    assert Knobs.from_env({}) == Knobs()
    k = Knobs.from_env({"EXPLORER_XB_GREY": "0", "EXPLORER_XB_INFLIGHT": "1", "EXPLORER_XB_INPUT": "legacy"})
    assert not k.grey and k.inflight == 1 and k.legacy_input and k.diff


def test_qt_has_the_input_symbols(qapp):
    """The bridge calls private symbols of this Qt build (PySide6 is pinned exactly for them): all of them present."""
    from explorer.platform.xbridge.qtinput import Platform

    p = Platform.load()
    assert p is not None and p.missing() == []
    assert Platform.load(legacy=True) is None


def test_the_plan_picks_the_bridge_display(qapp):
    from explorer.platform.display import Display, NoDisplay, for_plan
    from explorer.platform.plan import choose_display
    from explorer.platform.xbridge import available
    from explorer.platform.xbridge.display import BridgeDisplay

    ssh = {"DISPLAY": "localhost:10.0", "SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"}
    d = for_plan(choose_display(ssh, "linux", bridge_available=available()))
    assert available() and isinstance(d, BridgeDisplay) and d.kind == "x11bridge"
    assert (d.link().bytes_per_px, d.link().fps_cap) == (1.3, 12)
    assert type(for_plan(choose_display({"DISPLAY": ":0"}, "linux"))) is Display
    with pytest.raises(NoDisplay, match="needs an X display"):          # stops before connecting to anything
        for_plan(choose_display({}, "darwin", "bridge", bridge_available=True)).prepare_env({})


def test_window_ops_on_qt_windows(qapp):
    from PySide6 import QtCore, QtGui, QtWidgets

    from explorer.platform.display import Display
    from explorer.platform.plan import DisplayPlan

    w = QtWidgets.QWidget()
    ops = Display(DisplayPlan("offscreen")).attach(qapp, w)
    ops.set_geometry(QtCore.QRect(10, 20, 300, 200))
    ops.move(30, 40)
    ops.set_shape(QtGui.QRegion(0, 0, 10, 10))          # offscreen has no masks: nothing, and no message
    qapp.processEvents()
    assert (w.x(), w.y(), w.width(), w.height()) == (30, 40, 300, 200) and ops.qwindow_events
    w.close()
