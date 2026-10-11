"""The colour key over the image through the X11 bridge, with the pointer moved by XTEST (ui.overlays.OverImage):
onto the key from above, out of the hot key to its right. The X window shows what Qt draws, and no pixel of the
crosshair where the pointer entered the key: before, the old vertical line stayed in Qt's backing store and on the X
server alike.

    EXPLORER_TEST_XDISPLAY=:99 XAUTHORITY=<cookie> pytest tests/xvfb/test_bridge_overlays.py
"""
import os

import numpy as np
import pytest
from test_bridge_xvfb import SHAPE, App, fake, main_window, same_as_qt, wait, x_pixels

from explorer.testing import synth

XDISP = os.environ.get("EXPLORER_TEST_XDISPLAY")
pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("xbover"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture(scope="module")
def x():
    from Xlib import display

    d = display.Display(XDISP)
    yield d
    d.close()


@pytest.fixture
def app(cube):
    a = App(cube, "1000x650")
    yield a
    a.close()


def test_leaving_the_hot_key_leaves_no_old_crosshair_on_the_x_window(x, app):
    assert app("idle")["idle"]
    mw = main_window(app)
    kx, ky, kw, kh = app("key")["rect"]
    a = (kx + kw // 2 - 40, ky - 4)                     # on the image just above the key
    fake(x, None, xy=(a[0] + 30, a[1] - 60))
    fake(x, None, xy=a)
    assert wait(lambda: app("state")["cursor"] is not None)
    app("idle")
    fake(x, None, xy=(a[0], ky + 10))                   # onto the key: it grows
    assert wait(lambda: app("key")["hot"]), "the key did not get hot"
    hx, hy, hw, hh = app("key")["rect"]
    fake(x, None, xy=(hx + hw - 10, hy + 20))
    fake(x, None, xy=(hx + hw + 30, hy + 20))           # out of the hot key to its right, onto the image
    assert wait(lambda: not app("key")["hot"])
    assert app("idle")["idle"]
    gx, gy, gw, gh = mw["geometry"]
    got = x_pixels(x, mw["xid"], gw, gh)
    col = got[:hy - gy, a[0] - gx - 8:a[0] - gx + 9]    # above the hot key: where the old vertical line ran
    r, g, b = (col >> 16) & 255, (col >> 8) & 255, col & 255
    old = int(((r > 180) & (g < 140) & (b < 140)).sum())
    bad, shape = same_as_qt(x, app, mw["xid"])
    assert old == 0 and bad == 0, dict(old_line_px=old, differing=bad, shape=shape, cursor=app("state")["cursor"],
                                       column_rows=int(np.any((r > 180) & (g < 140) & (b < 140), 1).sum()))
