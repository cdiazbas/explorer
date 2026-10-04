"""The application's icon: an isometric data cube with one slice in the accent (x, y, λ, t: the image shown is a
slice of the cube), on a dark rounded tile, so that it reads on a light desktop and on a dark one alike.

    appicon.install(app)          every window, the main one and the floating panels; on a Mac, the Dock's too
    appicon.net_wm_icon(icon)     the value of X11's _NET_WM_ICON, for the windows the X11 bridge makes

One source: assets/explorer.svg, drawn by Qt's SVG icon engine (QtSvg's plugin, in PySide6-Essentials' wheels for
every platform explorer runs on) at each size and scale a window asks for. tools/icons/export.py makes the PNGs, the
ICO, the ICNS and the hicolor tree from the same file, and on a Mac the app bundle scripts/run.sh starts explorer
through, so that the Dock has the icon from launch. assets/explorer-glyph.svg is the glyph without its tile (the
ink in currentColor), for a symbolic icon.
"""
import sys
from pathlib import Path

from PySide6 import QtCore, QtGui

from ..obs import get_logger
from ..platform.xbridge.icon import NET_WM_SIZES, net_wm_icon  # noqa: F401  (re-exported)

log = get_logger("ui")
ASSETS = Path(__file__).parent / "assets"
SVG = ASSETS / "explorer.svg"
GLYPH_SVG = ASSETS / "explorer-glyph.svg"


def icon() -> QtGui.QIcon:
    """The application's icon, drawn from the SVG at each size and scale asked. Null (and a warning) where Qt has no
    SVG icon engine: the windows then show the platform's default, and nothing else changes."""
    ic = QtGui.QIcon(str(SVG))
    if ic.isNull() or ic.pixmap(QtCore.QSize(16, 16), 1.0).isNull():
        log.warning("no application icon: Qt could not draw %s (QtSvg's icon engine missing?)", SVG.name)
        return QtGui.QIcon()
    return ic


def bundle_has_icon() -> bool:
    """macOS: this process runs from an app bundle whose Info.plist names its icon (scripts/run.sh starts explorer
    through one), so the Dock has had the icon from launch. False elsewhere."""
    if sys.platform != "darwin":
        return False
    import ctypes

    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cf.CFBundleGetMainBundle.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFBundleGetValueForInfoDictionaryKey.restype = ctypes.c_void_p
    cf.CFBundleGetValueForInfoDictionaryKey.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    main = cf.CFBundleGetMainBundle()
    if not main:
        return False
    key = cf.CFStringCreateWithCString(None, b"CFBundleIconFile", 0x08000100)          # kCFStringEncodingUTF8
    try:
        return bool(cf.CFBundleGetValueForInfoDictionaryKey(main, key))
    finally:
        cf.CFRelease(key)


def install(app) -> None:
    """The icon on the application: every window without an icon of its own takes it, those already shown too (Qt
    sends them ApplicationWindowIconChange); on a Mac it becomes the Dock's icon of an unbundled app. Not on a Mac
    started from a bundle with its icon: the Dock shows that one from launch, as the system draws app icons, and
    Qt's image would replace it in the tile with the bare drawing."""
    if app.platformName() == "cocoa" and bundle_has_icon():
        return
    ic = icon()
    if not ic.isNull():
        app.setWindowIcon(ic)
