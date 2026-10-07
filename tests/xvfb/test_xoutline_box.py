"""The resize outline the X server draws (platform.xoutline), on a real server: one plain window the size to come,
filled with the look's colour, its 2-px border the server's own in the accent, the size written in its middle;
no X SHAPE (a ring shaped to the edge showed white inside on XQuartz while it grew and left earlier rings behind),
gone when hidden.

    EXPLORER_TEST_XDISPLAY=:99 pytest tests/xvfb/test_xoutline_box.py
"""
import struct
import time

import pytest
from test_bridge_quartzwm import XDISP

pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")

BORDER, INSIDE, INK = 0x0A84FF, 0x1E1E1E, 0xE4E4E4


def mapped(x):
    return [w for w in x.screen().root.query_tree().children if w.get_attributes().map_state == 2]


def pixels(x, gx, gy, w, h):
    """The root's pixels as 0xRRGGBB, rows of w."""
    from Xlib import X

    img = x.screen().root.get_image(gx, gy, w, h, X.ZPixmap, 0xFFFFFFFF)
    bpp = len(img.data) // (w * h)
    return [[struct.unpack_from("<I", img.data, bpp * (j * w + i))[0] & 0xFFFFFF for i in range(w)]
            for j in range(h)]


def wait(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_one_plain_window_filled_bordered_and_its_size_written():
    from Xlib import display
    from Xlib.ext import shape  # noqa: F401  (the extension's requests on the display)

    from explorer.platform.xoutline import XOutline

    x = display.Display(XDISP)
    before = len(mapped(x))
    o = XOutline(BORDER, XDISP)
    try:
        o.colours(BORDER, INSIDE, INK)
        o.show(100, 120, 600, 400)
        assert wait(lambda: o.steps >= 1 and len(mapped(x)) == before + 1)
        win = [w for w in mapped(x) if w.get_attributes().override_redirect][-1]
        g = win.get_geometry()
        t = win.translate_coords(x.screen().root, 0, 0)
        print("outline", (-t.x, -t.y, g.width, g.height), "border", g.border_width)
        assert (g.width + 2 * g.border_width, g.height + 2 * g.border_width) == (600, 400)   # the size to come
        assert not win.shape_query_extents().bounding_shaped                                 # no SHAPE
        px = pixels(x, 100, 120, 600, 400)
        assert px[0][300] == BORDER and px[1][300] == BORDER and px[200][0] == BORDER        # its border
        assert px[60][60] == INSIDE and px[340][540] == INSIDE                               # filled, not white
        middle = [v for row in px[180:220] for v in row[200:400]]
        written = sum(v == INK for v in middle)
        print("ink pixels in the middle", written)
        assert written > 20                                                                  # "600 × 400"
        o.show(100, 120, 300, 200)                                                           # smaller: no trail
        assert wait(lambda: win.get_geometry().width == 296)
        px = pixels(x, 100, 120, 600, 400)
        assert px[300][450] not in (BORDER, INSIDE, INK)                                     # where it was: gone
        o.hide()
        assert wait(lambda: len(mapped(x)) == before)
    finally:
        o.close(wait=1.0)
        x.close()
