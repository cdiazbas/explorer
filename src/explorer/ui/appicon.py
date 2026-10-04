"""The application's icon: an isometric data cube with one slice in the accent (x, y, λ, t: the image shown is a
slice of the cube), on a dark rounded tile, so that it reads on a light desktop and on a dark one alike.

    appicon.install(app)          every window, the main one and the floating panels; on a Mac, the Dock's too
    appicon.net_wm_icon(icon)     the value of X11's _NET_WM_ICON, for the windows the X11 bridge makes

One source: assets/explorer.svg, drawn by Qt's SVG icon engine (QtSvg's plugin, in PySide6-Essentials' wheels for
every platform explorer runs on) at each size and scale a window asks for. tools/icons/export.py makes the PNGs, the
ICO, the ICNS and the hicolor tree from the same file. assets/explorer-glyph.svg is the glyph without its tile
(the ink in currentColor), for a symbolic icon.
"""
from array import array
from pathlib import Path

from PySide6 import QtCore, QtGui

from ..obs import get_logger

log = get_logger("ui")
ASSETS = Path(__file__).parent / "assets"
SVG = ASSETS / "explorer.svg"
GLYPH_SVG = ASSETS / "explorer-glyph.svg"
NET_WM_SIZES = (16, 32, 48, 128)                       # title bars and task lists, switchers, docks


def icon() -> QtGui.QIcon:
    """The application's icon, drawn from the SVG at each size and scale asked. Null (and a warning) where Qt has no
    SVG icon engine: the windows then show the platform's default, and nothing else changes."""
    ic = QtGui.QIcon(str(SVG))
    if ic.isNull() or ic.pixmap(QtCore.QSize(16, 16), 1.0).isNull():
        log.warning("no application icon: Qt could not draw %s (QtSvg's icon engine missing?)", SVG.name)
        return QtGui.QIcon()
    return ic


def install(app) -> None:
    """The icon on the application: every window without an icon of its own takes it, those already shown too (Qt
    sends them ApplicationWindowIconChange); on a Mac it becomes the Dock's icon of an unbundled app."""
    ic = icon()
    if not ic.isNull():
        app.setWindowIcon(ic)


def net_wm_icon(ic: QtGui.QIcon | None = None, sizes=NET_WM_SIZES) -> list[int]:
    """_NET_WM_ICON's value (EWMH): for each size, its width, its height and its width*height pixels as 0xAARRGGBB
    (not premultiplied), row by row from the top left; the sizes one after the other. [] for a null icon. Drawn at a
    device pixel ratio of 1: X11 counts pixels. 128 + 48 + 32 + 16 is 19976 CARDINALs, 80 kB: one ChangeProperty,
    under the core protocol's 256 kB without BIG-REQUESTS."""
    ic = icon() if ic is None else ic
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
