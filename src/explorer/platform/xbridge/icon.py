"""A window's icon as X11's _NET_WM_ICON (EWMH), for the X windows the bridge makes: Qt's xcb plugin publishes it
itself, offscreen windows have none (windows.Windows.set_icon). Qt only: ui.appicon takes the conversion from here,
as the platform never imports the interface.

    net_wm_icon(icon, sizes)        the property's CARDINALs
    packed(cardinals)               as bytes for the request
    sizes_within(max_request)       the sizes whose CARDINALs fit in one ChangeProperty
"""
import sys
from array import array

from PySide6 import QtCore, QtGui

NET_WM_SIZES = (16, 32, 48, 128)                       # title bars and task lists, switchers, docks
CHANGE_PROPERTY_HEAD = 24                               # bytes of a ChangeProperty request before its data


def cardinals(sizes) -> int:
    """CARDINALs of _NET_WM_ICON at these sizes: width, height and width*height pixels each."""
    return sum(2 + s * s for s in sizes)


def request_bytes(sizes) -> int:
    """Bytes of the one ChangeProperty that carries the icon at these sizes."""
    return CHANGE_PROPERTY_HEAD + 4 * cardinals(sizes)


def sizes_within(max_request: int, sizes=NET_WM_SIZES) -> tuple[int, ...]:
    """The sizes whose icon goes in one ChangeProperty of at most max_request bytes, the largest left out first.
    Without BIG-REQUESTS, which the bridge does not use (xproto writes a 16-bit length), a request is at most 65535
    4-byte units, 262140 bytes, and a server may allow less: a larger one would not be sent. 16 + 32 + 48 + 128 px is
    79928 bytes. () when not even the smallest fits."""
    keep = sorted(sizes)
    while keep and request_bytes(keep) > max_request:
        keep.pop()
    return tuple(s for s in sizes if s in keep)


def packed(values) -> bytes:
    """CARDINALs as the X request carries them, little-endian (xproto's byte order)."""
    a = array("I", values)
    if sys.byteorder == "big":
        a.byteswap()
    return a.tobytes()


def net_wm_icon(ic: QtGui.QIcon, sizes=NET_WM_SIZES) -> list[int]:
    """_NET_WM_ICON's value (EWMH): for each size, its width, its height and its width*height pixels as 0xAARRGGBB
    (not premultiplied), row by row from the top left; the sizes one after the other. [] for a null icon. Drawn at a
    device pixel ratio of 1: X11 counts pixels."""
    out: list[int] = []
    if ic.isNull():
        return out
    for s in sizes:
        im = ic.pixmap(QtCore.QSize(s, s), 1.0).toImage()
        if im.isNull():
            continue
        if im.width() != s or im.height() != s:         # an engine that draws only its own sizes
            im = im.scaled(s, s, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                           QtCore.Qt.TransformationMode.SmoothTransformation)
        im = im.convertToFormat(QtGui.QImage.Format.Format_ARGB32)
        px = array("I")
        assert px.itemsize == 4
        px.frombytes(bytes(im.constBits())[:s * s * 4])  # ARGB32 is one native 32-bit word per pixel: 0xAARRGGBB
        out += [s, s]
        out += px.tolist()
    return out
