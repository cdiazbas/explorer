"""A window's icon as _NET_WM_ICON for the bridge's X windows (platform/xbridge/icon.py, windows.Windows.set_icon),
without an X server: the layout EWMH asks for, pixels not premultiplied; the sizes that fit in one request without
BIG-REQUESTS; and what goes to X for one window, against a fake connection."""
import struct
from types import SimpleNamespace

import pytest


def _icon():
    """64 px: the top left quarter red at half alpha, the rest opaque blue."""
    from PySide6 import QtGui

    im = QtGui.QImage(64, 64, QtGui.QImage.Format.Format_ARGB32)
    im.fill(QtGui.QColor(0, 0, 255))
    for y in range(32):
        for x in range(32):
            im.setPixel(x, y, 0x80FF0000)
    return QtGui.QIcon(QtGui.QPixmap.fromImage(im))


def test_net_wm_icon_is_width_height_then_argb_pixels_not_premultiplied(qapp):
    from explorer.platform.xbridge import icon

    data = icon.net_wm_icon(_icon(), (16, 32))
    assert len(data) == icon.cardinals((16, 32)) == 2 + 256 + 2 + 1024
    assert data[:2] == [16, 16] and data[258:260] == [32, 32]
    px16, px32 = data[2:258], data[260:]
    # row by row from the top left: (1, 2) in the red quarter, (12, 3) and (2, 13) in the blue
    assert px16[2 * 16 + 1] == 0x80FF0000                             # premultiplied would be 0x807F0000
    assert px16[3 * 16 + 12] == 0xFF0000FF and px16[13 * 16 + 2] == 0xFF0000FF
    assert px32[5 * 32 + 5] == 0x80FF0000 and px32[30 * 32 + 30] == 0xFF0000FF
    from PySide6 import QtGui

    assert icon.net_wm_icon(QtGui.QIcon()) == []


def test_ui_appicon_takes_the_platforms_conversion():
    from explorer.platform.xbridge import icon
    from explorer.ui import appicon

    assert appicon.net_wm_icon is icon.net_wm_icon and appicon.NET_WM_SIZES == icon.NET_WM_SIZES


def test_the_sizes_that_fit_in_one_request():
    from explorer.platform.xbridge import icon

    assert icon.request_bytes(icon.NET_WM_SIZES) == 24 + 4 * 19976 == 79928
    assert icon.sizes_within(65535 * 4) == (16, 32, 48, 128)          # Xvfb's and XQuartz's 262140 B
    assert icon.sizes_within(79928) == (16, 32, 48, 128)
    assert icon.sizes_within(79927) == (16, 32, 48)                   # the largest left out first
    assert icon.sizes_within(16384 * 4) == (16, 32, 48)               # a server allowing 64 kB
    assert icon.sizes_within(24 + 4 * 258) == (16,)
    assert icon.sizes_within(1000) == ()
    assert icon.sizes_within(10 ** 6, (128, 16, 48)) == (128, 16, 48)  # the order asked kept


def test_the_whole_icon_encodes_as_one_core_request():
    """xproto writes a request's length in 16 bits (no BIG-REQUESTS): the ChangeProperty of the whole icon is within
    them, and the length it writes is the request's bytes / 4."""
    from explorer.platform.xbridge import icon, xproto

    n = icon.cardinals(icon.NET_WM_SIZES)
    req = xproto._encode(18, 0, struct.pack("<IIIBxxxI", 1, 2, 6, 32, n) + bytes(4 * n))
    assert len(req) == icon.request_bytes(icon.NET_WM_SIZES)
    assert struct.unpack_from("<H", req, 2)[0] * 4 == len(req) <= 65535 * 4


def test_change_property_takes_the_values_packed_once():
    """The icon's CARDINALs packed once for every window (icon.packed): the same request as the values."""
    from explorer.platform.xbridge import icon, xproto

    vals = [2, 1, 0x80FF0000, 0xFF0000FF]
    got = []
    c = object.__new__(xproto.Connection)
    c.request = lambda op, data, body=b"", reply=False: got.append((op, data, body))
    xproto.Connection.change_property(c, 5, 301, xproto.ATOM_CARDINAL, 32, vals)
    xproto.Connection.change_property(c, 5, 301, xproto.ATOM_CARDINAL, 32, icon.packed(vals))
    assert got[0] == got[1] and struct.unpack_from("<I", got[0][2], 16)[0] == 4


class FakeX:
    def __init__(self, max_request):
        self.screen = SimpleNamespace(root=1)
        self.max_request = max_request
        self.sent: list = []

    def change_property(self, wid, prop, type_, fmt, data, mode=0):
        if isinstance(data, bytes):
            data = struct.unpack(f"<{len(data) // 4}I", data)
        self.sent.append(("change", wid, prop, type_, fmt, list(data)))

    def delete_property(self, wid, prop):
        self.sent.append(("delete", wid, prop))


@pytest.fixture
def win(qapp):
    from PySide6 import QtGui, QtWidgets

    from explorer.platform.xbridge.windows import Windows, XWin

    app_icon = qapp.windowIcon()
    qapp.setWindowIcon(QtGui.QIcon())
    w = QtWidgets.QWidget()
    ws = Windows(FakeX(65535 * 4))
    ws.atoms["_NET_WM_ICON"] = 301
    yield ws, XWin(w, 7, popup=False, owner=None), w
    w.deleteLater()
    qapp.setWindowIcon(app_icon)


def test_set_icon_sends_the_windows_icon_once_and_deletes_it_when_there_is_none(qapp, win):
    from explorer.platform.xbridge import icon, xproto

    ws, rec, w = win
    ws.set_icon(rec)
    assert ws.c.sent == []                                            # no icon, and a new window has none on X
    ic = _icon()
    qapp.setWindowIcon(ic)                                            # the application's, taken by the window
    ws.c.sent.clear()
    ws.set_icon(rec)
    ws.set_icon(rec)                                                  # told again: the same icon, nothing sent
    assert [s[:5] for s in ws.c.sent] == [("change", 7, 301, xproto.ATOM_CARDINAL, 32)]
    assert ws.c.sent[0][5] == icon.net_wm_icon(ic, icon.NET_WM_SIZES)
    own = _icon()
    w.setWindowIcon(own)                                              # one of its own
    ws.c.sent.clear()
    ws.set_icon(rec)
    assert len(ws.c.sent) == 1 and ws.c.sent[0][5] == icon.net_wm_icon(own, icon.NET_WM_SIZES)
    from PySide6 import QtGui

    w.setWindowIcon(QtGui.QIcon())                                    # no icon at all
    qapp.setWindowIcon(QtGui.QIcon())
    ws.c.sent.clear()
    ws.set_icon(rec)
    assert ws.c.sent == [("delete", 7, 301)]


def test_set_icon_leaves_out_the_sizes_a_server_would_refuse(qapp, win):
    """A server whose requests are at most 64 kB: the 128-px icon (65536 B by itself) is left out, not the request
    refused by X."""
    from explorer.platform.xbridge import icon

    ws, rec, w = win
    ws.c.max_request = 16384 * 4
    w.setWindowIcon(_icon())
    ws.set_icon(rec)
    (change,) = ws.c.sent
    data = change[5]
    assert data == icon.net_wm_icon(w.windowIcon(), (16, 32, 48))
    assert 24 + 4 * len(data) <= ws.c.max_request
    ws.c.max_request = 1000                                           # not even 16 px: no icon rather than an error
    w.setWindowIcon(_icon())
    ws.c.sent.clear()
    ws.set_icon(rec)
    assert ws.c.sent == [("delete", 7, 301)]
