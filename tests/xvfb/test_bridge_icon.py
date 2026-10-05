"""The application's icon on the X windows the bridge makes: _NET_WM_ICON (EWMH), as Qt's xcb plugin publishes it
(ROADMAP E5.29). Offscreen windows have none, so without the bridge setting it a window manager, a task list or
xprop saw no icon on any of explorer's windows over ssh -Y.

The icon is set after the windows exist (icon_app.py): the main window and its panels floating before it was shown,
as a saved glass layout leaves them, are told by Qt of the application's new icon (WindowIconChange); a window made
afterwards carries it from its creation. Read back from the X server with python-xlib (platform/xlibauth.py), another
implementation of the protocol: the sizes one after the other, each as width, height and its pixels.

    EXPLORER_TEST_XDISPLAY=:99 XAUTHORITY=<cookie> pytest tests/xvfb/test_bridge_icon.py
"""
import collections
import os
import subprocess
import sys

import numpy as np
import pytest
from test_bridge_xvfb import App, wait
from xlinkenv import app_display

XDISP = os.environ.get("EXPLORER_TEST_XDISPLAY")
pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")
HERE = os.path.dirname(os.path.abspath(__file__))
SIZES = (16, 32, 48, 128)
BEFORE = ("icon test", "Spectrum", "λ–t")              # the windows made before the icon was set


class IconApp(App):
    def __init__(self, cube):
        env = dict(os.environ, DISPLAY=app_display(XDISP), EXPLORER_BRIDGE_TRACE="1")
        env.pop("QT_QPA_PLATFORM", None)
        env.pop("EXPLORER_X11", None)
        self.p = subprocess.Popen([sys.executable, os.path.join(HERE, "icon_app.py"), str(cube)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, text=True)
        self.hello = self._read(60)
        assert self.hello.get("ready"), self.hello


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    from explorer.testing import synth

    return synth.write_dataset(tmp_path_factory.mktemp("xbicon"), "c", shape=(3, 4, 5, 96, 80), icube=False)["im"]


@pytest.fixture
def x():
    from explorer.platform import xlibauth

    d = xlibauth.display(XDISP)
    yield d
    d.close()


def net_wm_icon(x, xid):
    """_NET_WM_ICON of an X window as X holds it: (type, format, values), or None without the property."""
    win = x.create_resource_object("window", xid)
    p = win.get_full_property(x.intern_atom("_NET_WM_ICON"), 0)
    return None if p is None else (x.get_atom_name(p.property_type), p.format, [int(v) for v in p.value])


def sizes_of(values):
    """The sizes in a _NET_WM_ICON value, walked as EWMH lays it out: width, height, width*height pixels, again."""
    out, i = [], 0
    while i < len(values):
        w, h = values[i], values[i + 1]
        out.append((w, h))
        i += 2 + w * h
    assert i == len(values), (i, len(values))
    return out


def test_every_window_carries_the_icon_also_those_made_before_it(cube, x, tmp_path, monkeypatch):
    log_dir = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(log_dir))
    a = IconApp(cube)
    try:
        wins = a("state")["windows"]
        assert set(BEFORE) <= set(wins), wins
        for t in BEFORE:
            assert net_wm_icon(x, wins[t]) is None, t                   # no application icon yet: none on X

        got = a("icon")
        assert got["ok"], got
        want = np.load(got["expect"]).tolist()
        assert len(want) == sum(2 + s * s for s in SIZES) == 19976
        for t in BEFORE:
            p = wait(lambda t=t: net_wm_icon(x, wins[t]))
            assert p is not None, f"{t}: no _NET_WM_ICON after the application's icon was set"
            assert p[:2] == ("CARDINAL", 32), (t, p[:2])
            assert sizes_of(p[2]) == [(s, s) for s in SIZES], t
            assert p[2] == want, f"{t}: _NET_WM_ICON is not the application's icon"
            corner = p[2][2]                                            # 16 px, top left: outside the tile
            assert corner >> 24 == 0, hex(corner)

        assert a("panel")["ok"]
        wins = a("state")["windows"]
        made_after = wins["panel made after the icon"]
        p = wait(lambda: net_wm_icon(x, made_after))
        assert p is not None and p[2] == want, "a window made after the icon has it from its creation"

        own = a("own")
        own_want = np.load(own["expect"]).tolist()
        assert wait(lambda: (net_wm_icon(x, made_after) or (0, 0, []))[2] == own_want), "its own icon"
        assert net_wm_icon(x, wins["icon test"])[2] == want             # the others keep the application's

        assert a("clear")["ok"]
        for t in BEFORE:
            assert wait(lambda t=t: net_wm_icon(x, wins[t]) is None), f"{t}: deleted with the application's icon"
        assert net_wm_icon(x, made_after)[2] == own_want                # its own stays
    finally:
        a.close()
    logs = list((log_dir / "explorer" / "logs").glob("bridge-*.log"))
    assert len(logs) == 1, logs
    lines = [ln for ln in logs[0].read_text().splitlines() if " ICON " in ln]
    full = [ln for ln in lines if "16, 32, 48, 128 px, 19976 CARDINALs, 79928 B" in ln]
    # once per window and icon, the panel's own the second one of its window: the 80 kB are not sent again when Qt
    # tells a window of an icon it has on X already
    assert collections.Counter(ln.split()[2] for ln in full) == {
        "main": 1, "spectrum": 1, "lambda_t": 1, "panel_made_after_the_icon": 2}, lines
    assert any("none: _NET_WM_ICON deleted" in ln for ln in lines), lines
