"""A start in glass through the bridge: what the X server shows in each window is what the bridge sent (ROADMAP E5.25).
Through ssh -Y to XQuartz, started in glass (the saved look), the floating panels were often drawn wrong, and the
geometry trace showed them created in place and still: painting, not geometry.

The bridge's trace (xbridge/trace.py) found it in Xvfb: the first update carries the three windows at once, and the
grey pieces (1 B/px through RENDER) of each go through one 8-bit mask pixmap shared by every window, grown when a
window needs it larger. Grown for the second window of an update, the mask the first window's pieces had been encoded
for was freed before they were sent: BadDrawable on their PutImage and BadPicture on their Composite, and the grey
tiles of the lambda-t panel (its image) stayed black on X while the bridge counted them as sent, so the periodic check
never sent them again. The windows come in Qt's order of its top-level widgets, which changes from run to run: on a
3840-px screen 4 starts in 10 lost the panel's image, each one with the panel before the main window.

The first test puts the windows in that order and fails without the fix every time; the second goes through the whole
start, where the fault also needs the panel's image in the first update, which a 1920-px screen did not always give.

    EXPLORER_TEST_XDISPLAY=:99 XAUTHORITY=<cookie> pytest tests/xvfb/test_bridge_glass_start.py
"""
import os
import re
import subprocess
import sys

import numpy as np
import pytest
from test_bridge_quartzwm import HERE, XDISP
from xlinkenv import app_display

pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")


@pytest.fixture
def x():
    from Xlib import display

    d = display.Display(XDISP)
    yield d
    d.close()


def _window(x, at, size, colour):
    """A mapped X window with this background (seen where nothing was drawn), no window manager asked."""
    from Xlib import X

    win = x.screen().root.create_window(*at, *size, 0, x.screen().root_depth, X.InputOutput, X.CopyFromParent,
                                        background_pixel=colour, override_redirect=1)
    win.map()
    x.sync()
    return win


def _grey(h, w, seed):
    """Grey pixels (R = G = B, all tiles sent at 1 B/px), none black: a missing piece shows."""
    v = np.random.default_rng(seed).integers(40, 256, (h, w), dtype=np.uint32)
    return (0xFF000000 | (v << 16) | (v << 8) | v).astype(np.uint32)


def test_one_update_draws_the_grey_pieces_of_every_window_in_it(x):
    """The windows of one update in the order that grows the shared grey mask between them: a panel, then the larger
    main window. Each one's pixels read back from the server are the ones sent."""
    from Xlib import X

    from explorer.platform.xbridge.transport import Transport

    sizes = {"panel": (560, 408), "main": (825, 863)}
    wins = {n: _window(x, (40 + 900 * i, 20), s, 0xFF0000) for i, (n, s) in enumerate(sizes.items())}
    t = Transport(app_display(XDISP), on_ready=lambda: None)
    try:
        assert t.started.wait(30) and t.failed is None, t.failed
        if t.grey is None:
            pytest.skip("no RENDER: grey pieces go at 4 B/px, without the mask")
        px = {n: _grey(h, w, i) for i, (n, (w, h)) in enumerate(sizes.items())}
        t.submit([(wins[n].id, w, h, 0, 0, px[n], None, False, False) for n, (w, h) in sizes.items()])
        assert t.wait_acked(1, 30)
        t.c.sync()
        for n, (w, h) in sizes.items():
            img = wins[n].get_image(0, 0, w, h, X.ZPixmap, 0xFFFFFFFF)
            got = np.frombuffer(img.data, np.uint32).reshape(h, w) & 0xFFFFFF
            wrong = int((got != (px[n] & 0xFFFFFF)).sum())
            assert wrong == 0, f"{n}: {wrong} of {w * h} pixels not what was sent; X errors {t.c.errors}: " \
                               f"{t.c.last_error}"
        assert t.c.errors == 0, t.c.last_error
    finally:
        t.stop()
        for w in wins.values():
            w.destroy()
        x.sync()


# ---------------------------------------------------------------- the whole start, as the user's

@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    from explorer.testing import synth

    return synth.write_dataset(tmp_path_factory.mktemp("xbgs"), "c", shape=(3, 4, 5, 96, 80), icube=False)["im"]


@pytest.fixture
def late_wm():
    """The quartz-like manager telling each window's first geometry 300 ms late, as through ssh -Y to a Mac."""
    env = dict(os.environ, DISPLAY=XDISP)
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "fake_quartzwm.py"), "--late", "300"],
                         stdout=subprocess.PIPE, env=env, text=True)
    line = p.stdout.readline().strip()
    if line != "ready":
        p.wait(5)
        pytest.skip(f"the quartz-like manager did not start: {line!r} (exit {p.poll()})")
    yield p
    p.terminate()
    p.wait(5)


def _start(cube, home, look, quit_s, trace=False):
    env = {k: v for k, v in os.environ.items() if k not in ("QT_QPA_PLATFORM", "EXPLORER_X11", "EXPLORER_LAYOUT")}
    env.update(DISPLAY=app_display(XDISP), EXPLORER_TERMINAL_KEYS="0", XDG_CONFIG_HOME=str(home / "config"),
               XDG_CACHE_HOME=str(home / "cache"))
    if trace:
        env.update(EXPLORER_BRIDGE_TRACE="1", EXPLORER_BRIDGE_PROBE="3.2")
    p = subprocess.run([sys.executable, os.path.join(HERE, "glass_start_app.py"), str(cube), look, str(quit_s)],
                       env=env, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-3000:]
    return p


def test_a_start_in_the_saved_glass_look_shows_on_x_what_qt_drew(cube, tmp_path, late_wm):
    """A glass session closed (the layout saved with the panels floating), then explorer started again as the user
    starts it, with the bridge's trace: 3.2 s after, each window read back from X is what the bridge sent, wherever
    it shows, and no request of the bridge failed. Three starts: the windows' order, which decides the fault, changes
    from one to the next."""
    _start(cube, tmp_path, "glass", 3)
    for k in range(3):
        before = set((tmp_path / "cache").rglob("bridge-*.log"))
        p = _start(cube, tmp_path, "-", 4.5, trace=True)
        logs = sorted(set((tmp_path / "cache").rglob("bridge-*.log")) - before)
        assert len(logs) == 1, (logs, p.stderr[-2000:])
        text = logs[0].read_text()
        probes = [ln for ln in text.splitlines() if " PROBE " in ln]
        assert len(probes) == 3, f"start {k}: {len(probes)} windows probed\n{text[-4000:]}"
        for ln in probes:
            m = re.search(r"X != sent (\d+) px \((\d+) where it shows\)", ln)
            assert m is not None and m.group(2) == "0", f"start {k}: {ln}\n{text[-4000:]}"
        errors = [ln for ln in text.splitlines() if " XERR " in ln]
        assert not errors, f"start {k}: X errors\n" + "\n".join(errors)
