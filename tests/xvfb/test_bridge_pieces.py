"""An update in pieces (the widgets' repaints, in the order Qt painted them) is shown piece by piece: each piece's
CopyArea goes right after its own bytes, so a small change painted first is on the screen before a large one painted
after it in the same pass has crossed the link (transport.py). Without pieces, each window's pixels are shown with one
CopyArea after the whole update, as before.

    EXPLORER_TEST_XDISPLAY=:99 pytest tests/xvfb/test_bridge_pieces.py
"""
import numpy as np
import pytest
from test_bridge_glass_start import _grey, _window, x  # noqa: F401  (x: the fixture)
from test_bridge_quartzwm import XDISP
from xlinkenv import app_display

pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")


def _sent(t, items):
    """The update's requests in the order they left: ("bytes", n) for encoded pixels, ("copy", (x, y, w, h))."""
    log: list = []
    send, copy = t.c.send_raw, t.c.copy_area

    def send_raw(buf, nreq):
        log.append(("bytes", nreq))
        return send(buf, nreq)

    def copy_area(src, dst, gc, sx, sy, dx, dy, w, h):
        log.append(("copy", (dx, dy, w, h)))
        return copy(src, dst, gc, sx, sy, dx, dy, w, h)
    t.c.send_raw, t.c.copy_area = send_raw, copy_area
    n = t.stats["updates"]
    t.submit(items)
    assert t.wait_acked(n + 1, 30)
    t.c.send_raw, t.c.copy_area = send, copy
    return log


def test_each_piece_is_shown_right_after_its_bytes(x):  # noqa: F811
    """A small piece (a crosshair's strip) and then a large one (a panel) of one window: the first CopyArea shows only
    the small piece, and goes before the large piece's bytes; the window then shows every pixel sent."""
    from Xlib import X

    from explorer.platform.xbridge.transport import Transport

    W, H = 640, 480
    win = _window(x, (40, 20), (W, H), 0xFF0000)
    t = Transport(app_display(XDISP), on_ready=lambda: None)
    try:
        assert t.started.wait(30) and t.failed is None, t.failed
        base = _grey(H, W, 1)
        _sent(t, [(win.id, W, H, 0, 0, base, None, False, False)])
        small = _grey(32, 64, 2)
        big = _grey(320, 400, 3)
        log = _sent(t, [(win.id, W, H, 0, 0, small, None, False, False, True),
                        (win.id, W, H, 200, 128, big, None, False, False, True)])
        kinds = [k for k, _ in log]
        assert kinds == ["bytes", "copy", "bytes", "copy"], log
        assert log[1][1] == (0, 0, 64, 32), log
        assert log[3][1] == (200, 128, 400, 320), log
        want = base.copy()
        want[:32, :64] = small
        want[128:448, 200:600] = big
        t.c.sync()
        got = np.frombuffer(win.get_image(0, 0, W, H, X.ZPixmap, 0xFFFFFFFF).data, np.uint32).reshape(H, W)
        assert int(((got ^ want) & 0xFFFFFF).astype(bool).sum()) == 0
        # without pieces: one CopyArea after all the bytes, as before
        log = _sent(t, [(win.id, W, H, 0, 0, _grey(32, 64, 4), None, False, False),
                        (win.id, W, H, 200, 128, _grey(320, 400, 5), None, False, False)])
        assert [k for k, _ in log] == ["bytes", "bytes", "copy"], log
    finally:
        t.stop()
