"""The application icon (ui.appicon, ROADMAP E5.28): drawn from its SVG at every size asked, the tile and the slice
where the geometry puts them, on the application once the first image is up, the value of X11's _NET_WM_ICON, and
the files tools/icons/export.py writes for the operating systems."""
import os
import struct
import subprocess
import sys
import time

import pytest

from explorer.testing import synth

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIZES = (16, 24, 32, 48, 64, 128, 256)
ORANGE = (0xFF, 0x92, 0x30)


def _rgba(im, s, gx, gy):
    """The pixel of an s-px rendering that holds the point (gx, gy) of the 64-unit grid, as (r, g, b, a)."""
    c = im.pixelColor(int(gx * s / 64), int(gy * s / 64))
    return c.red(), c.green(), c.blue(), c.alpha()


def _near(got, want, tol=12):
    return all(abs(a - b) <= tol for a, b in zip(got, want, strict=False))


@pytest.fixture
def icon(qapp):
    from explorer.ui import appicon

    ic = appicon.icon()
    assert not ic.isNull(), "Qt's SVG icon engine did not draw the icon"
    return ic


def test_the_icon_is_drawn_at_every_size_and_scale(icon):
    from PySide6 import QtCore

    for s in SIZES:
        pm = icon.pixmap(QtCore.QSize(s, s), 1.0)
        assert (pm.width(), pm.height()) == (s, s), s
        pm2 = icon.pixmap(QtCore.QSize(s, s), 2.0)      # a Retina screen: twice the pixels, not an upscaled copy
        assert (pm2.width(), pm2.height(), pm2.devicePixelRatio()) == (2 * s, 2 * s, 2.0), s


@pytest.mark.parametrize("s", [16, 32])
def test_the_tile_and_the_slice_are_where_the_geometry_puts_them(icon, s):
    """The tile (3..61, corners of radius 13.5) leaves the corners transparent and is dark and opaque left of the
    cube; the slice, the cube's middle plane in the accent, shows between the edges either side of the front one."""
    from PySide6 import QtCore

    im = icon.pixmap(QtCore.QSize(s, s), 1.0).toImage()
    assert _rgba(im, s, 0.5, 0.5)[3] == 0                               # outside the rounded tile
    assert _rgba(im, s, 63.5, 63.5)[3] == 0
    r, g, b, a = _rgba(im, s, 8, 34)                                     # the tile, left of the cube
    assert a == 255 and max(r, g, b) < 60, (r, g, b, a)
    for gx in (26, 38):                                                  # the slice, either side of the front edge
        assert _near(_rgba(im, s, gx, 34), (*ORANGE, 255)), (gx, _rgba(im, s, gx, 34))
    if s >= 32:                                                          # the front edge's ink (sub-pixel at 16 px)
        assert min(_rgba(im, s, 31, 45)[:3]) > 150, _rgba(im, s, 31, 45)


def test_the_glyph_without_its_tile_is_a_valid_svg(qapp):
    from PySide6 import QtSvg

    from explorer.ui import appicon

    assert QtSvg.QSvgRenderer(str(appicon.GLYPH_SVG)).isValid()
    assert "currentColor" in appicon.GLYPH_SVG.read_text()


def test_start_puts_the_icon_on_the_application_after_the_first_image(qapp, monkeypatch, tmp_path):
    from PySide6 import QtGui

    from explorer.ui.app import start

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    cube = synth.write_dataset(tmp_path / "d", "c", shape=(2, 4, 3, 32, 24), icube=False)["im"]
    qapp.setWindowIcon(QtGui.QIcon())
    s = start(cube, saved_layout=False)
    assert s is not None
    try:
        end = time.perf_counter() + 30
        while (s.shell.first_image_s is None or qapp.windowIcon().isNull()) and time.perf_counter() < end:
            qapp.processEvents()
        assert s.shell.first_image_s is not None
        assert not qapp.windowIcon().isNull()
        assert not s.shell.windowIcon().isNull()                         # a window without its own takes it
    finally:
        s.shell.close()
        s.close()
        qapp.setWindowIcon(QtGui.QIcon())


def test_net_wm_icon_is_width_height_then_argb_pixels_per_size(icon):
    from PySide6 import QtCore, QtGui

    from explorer.ui import appicon

    data = appicon.net_wm_icon(icon)
    assert len(data) == sum(2 + s * s for s in appicon.NET_WM_SIZES) == 19976
    assert all(0 <= v <= 0xFFFFFFFF for v in data)
    i = 0
    for s in appicon.NET_WM_SIZES:
        assert data[i:i + 2] == [s, s]
        px = data[i + 2:i + 2 + s * s]
        im = icon.pixmap(QtCore.QSize(s, s), 1.0).toImage().convertToFormat(QtGui.QImage.Format.Format_ARGB32)
        # row by row from the top left, 0xAARRGGBB not premultiplied: QImage.pixel's QRgb
        assert px == [im.pixel(x, y) & 0xFFFFFFFF for y in range(s) for x in range(s)], s
        assert px[0] >> 24 == 0                                          # a transparent corner
        mid = px[int(34 * s / 64) * s + int(26 * s / 64)]                # the slice
        assert mid >> 24 == 0xFF and _near(((mid >> 16) & 255, (mid >> 8) & 255, mid & 255), ORANGE), hex(mid)
        i += 2 + s * s
    assert i == len(data)
    assert appicon.net_wm_icon(QtGui.QIcon()) == []


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def test_the_export_writes_the_pngs_the_ico_and_the_hicolor_tree(tmp_path):
    out = tmp_path / "icons"
    env = dict(os.environ)
    env.pop("DISPLAY", None)
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "icons", "export.py"), str(out)], env=env,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    for n in (16, 24, 32, 48, 64, 128, 256, 512, 1024):
        assert _png_size((out / "png" / f"explorer-{n}.png").read_bytes()) == (n, n)
    ico = (out / "explorer.ico").read_bytes()
    assert struct.unpack("<HHH", ico[:6]) == (0, 1, 5)                   # reserved, icon, five images
    sizes = []
    for k in range(5):
        w, h, colours, _, planes, bits, size, offset = struct.unpack("<BBBBHHII", ico[6 + 16 * k:22 + 16 * k])
        n = w or 256
        assert (h or 256, colours, planes, bits) == (n, 0, 1, 32)
        assert offset + size <= len(ico) and _png_size(ico[offset:offset + size]) == (n, n)
        sizes.append(n)
    assert sizes == [16, 24, 32, 48, 256]
    for n in (16, 24, 32, 48, 64, 128, 256, 512):
        assert _png_size((out / "hicolor" / f"{n}x{n}" / "apps" / "explorer.png").read_bytes()) == (n, n)
    svg = os.path.join(ROOT, "src", "explorer", "ui", "assets", "explorer.svg")
    assert (out / "hicolor" / "scalable" / "apps" / "explorer.svg").read_bytes() == open(svg, "rb").read()
    if sys.platform == "darwin":
        assert (out / "explorer.icns").read_bytes()[:4] == b"icns"
    else:
        assert not (out / "explorer.icns").exists() and "skipped" in p.stdout
