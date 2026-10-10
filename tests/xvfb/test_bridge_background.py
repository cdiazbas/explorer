"""A change of theme while the viewer runs gives the bridge's X windows the new window colour as their background
(ROADMAP E6.21). X fills with the background what it exposes before the bridge's pixels come (a window growing, one
uncovered); kept from the start, it showed the old theme's colour there.

Another client (python-xlib) clears each window with ClearArea, without exposures: X paints the background and the
bridge, told nothing, sends nothing over it, so GetImage reads the background itself.

    EXPLORER_TEST_XDISPLAY=:99 XAUTHORITY=<cookie> pytest tests/xvfb/test_bridge_background.py
"""
import os

import numpy as np
import pytest
from test_bridge_xvfb import App, wait

XDISP = os.environ.get("EXPLORER_TEST_XDISPLAY")
pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    from explorer.testing import synth

    return synth.write_dataset(tmp_path_factory.mktemp("xbback"), "c", shape=(3, 4, 5, 96, 80), icube=False)["im"]


@pytest.fixture
def x():
    from Xlib import display

    d = display.Display(XDISP)
    yield d
    d.close()


def background(x, xid):
    """The colours X shows in a 40 x 30 corner of the window just cleared: its background."""
    from Xlib import X

    win = x.create_resource_object("window", xid)
    win.clear_area(0, 0, 40, 30, onerror=None)
    img = win.get_image(0, 0, 40, 30, X.ZPixmap, 0xFFFFFFFF)
    return set(np.unique(np.frombuffer(img.data, np.uint32) & 0xFFFFFF).tolist())


def test_a_switch_of_theme_changes_the_x_background(cube, x):
    a = App(cube)
    try:
        assert a("float")["ok"]                         # the panels are windows of their own too
        before = a("theme dark")["window"]
        after = a("theme light")["window"]
        assert set(before) == set(after) and len(after) >= 3, after
        for xid, colour in after.items():
            assert colour != before[xid], (xid, hex(colour))
            got = wait(lambda xid=xid, colour=colour: background(x, int(xid)) == {colour})
            assert got, f"window {int(xid):#x}: background {sorted(map(hex, background(x, int(xid))))}, the " \
                        f"theme's {colour:#08x} (the old one {before[xid]:#08x})"
        assert a("theme dark")["ok"]                    # and back
        for xid, colour in before.items():
            assert wait(lambda xid=xid, colour=colour: background(x, int(xid)) == {colour}), hex(int(xid))
    finally:
        a.close()
