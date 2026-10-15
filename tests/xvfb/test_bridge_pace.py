"""An update's then (transport.submit) is called once the X server has confirmed it, after its pixels are on the
server, and at once when nothing in it differs from what the server has: the bridge's frames of the viewer's panels
(core.pace) are behind until then.

    EXPLORER_TEST_XDISPLAY=:99 pytest tests/xvfb/test_bridge_pace.py
"""
import threading

import numpy as np
import pytest
from test_bridge_glass_start import _grey, _window, x  # noqa: F401  (x: the fixture)
from test_bridge_quartzwm import XDISP
from xlinkenv import app_display

pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")


def test_then_is_called_once_the_server_has_the_update(x):  # noqa: F811
    from Xlib import X

    from explorer.platform.xbridge.transport import Transport

    W, H = 320, 240
    win = _window(x, (40, 20), (W, H), 0xFF0000)
    t = Transport(app_display(XDISP), on_ready=lambda: None)
    try:
        assert t.started.wait(30) and t.failed is None, t.failed
        px = _grey(H, W, 7)
        seen: list = []
        done = threading.Event()

        def then():
            # the server has every pixel of the update when it is called
            got = np.frombuffer(win.get_image(0, 0, W, H, X.ZPixmap, 0xFFFFFFFF).data, np.uint32).reshape(H, W)
            seen.append(int(((got ^ px) & 0xFFFFFF).astype(bool).sum()))
            done.set()
        n = t.stats["updates"]
        t.submit([(win.id, W, H, 0, 0, px, None, False, False)], then)
        assert done.wait(30) and t.wait_acked(n + 1, 30)
        assert seen == [0]
        # the same pixels again: nothing to send, called at once (from the sender)
        done.clear()
        t.submit([(win.id, W, H, 0, 0, px.copy(), None, False, False)], then)
        assert done.wait(30)
        assert seen == [0, 0] and t.stats["updates"] == n + 1
    finally:
        t.stop()
