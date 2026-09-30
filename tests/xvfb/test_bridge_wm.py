"""The rewritten X11 bridge under a real window manager (metacity on the private Xvfb): focus when the window appears,
also after a terminal had it; frames and moves; maximise, minimise, restore; panels above their window; the close
button. Run only when the display has a manager running:

    EXPLORER_TEST_XDISPLAY=:99 EXPLORER_TEST_XWM=metacity XAUTHORITY=<cookie> pytest tests/xvfb/test_bridge_wm.py

XQuartz (quartz-wm) and the macOS side (which application is in front) are not reproduced here: that check is the
user's, on the screen.
"""
import os
import subprocess
import time

import pytest
from test_bridge_xvfb import App, fake, keycode, main_window, wait

XDISP = os.environ.get("EXPLORER_TEST_XDISPLAY")
pytestmark = pytest.mark.skipif(not (XDISP and os.environ.get("EXPLORER_TEST_XWM")),
                                reason="needs EXPLORER_TEST_XDISPLAY with a window manager (EXPLORER_TEST_XWM)")


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    from explorer.testing import synth

    return synth.write_dataset(tmp_path_factory.mktemp("xb2wm"), "c", shape=(3, 4, 5, 96, 80), icube=False)["im"]


@pytest.fixture(scope="module")
def x():
    from Xlib import display

    d = display.Display(XDISP)
    yield d
    d.close()


def active_window(x):
    from Xlib import Xatom

    p = x.screen().root.get_full_property(x.intern_atom("_NET_ACTIVE_WINDOW"), Xatom.WINDOW)
    return p.value[0] if p is not None and len(p.value) else 0


def terminal(x):
    """Another client that has the focus and was just typed into, as the terminal the viewer is launched from."""
    from Xlib import X

    root = x.screen().root
    t = root.create_window(1500, 100, 400, 300, 0, x.screen().root_depth, X.InputOutput, X.CopyFromParent,
                           background_pixel=x.screen().white_pixel,
                           event_mask=X.KeyPressMask | X.FocusChangeMask | X.StructureNotifyMask)
    t.set_wm_name("terminal")
    t.set_wm_hints(flags=1, input=1)
    t.map()
    x.sync()
    wait(lambda: t.get_attributes().map_state == X.IsViewable)
    time.sleep(0.3)
    c = t.translate_coords(x.screen().root, 0, 0)       # where the manager put it
    fake(x, None, xy=(-c.x + 100, -c.y + 100))
    fake(x, 4, 1)                                       # a click gives it the focus, with a user time
    fake(x, 5, 1)
    assert wait(lambda: x.get_input_focus().focus.id == t.id or active_window(x) == t.id, 3.0)
    fake(x, 2, keycode(x, "a"))                         # typed into it: the launch command
    fake(x, 3, keycode(x, "a"))
    return t


def client_message(x, win, name, data):
    from Xlib import X
    from Xlib.protocol import event

    ev = event.ClientMessage(window=win, client_type=x.intern_atom(name), data=(32, (data + [0] * 5)[:5]))
    x.screen().root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
    x.sync()


def test_the_new_window_takes_the_keyboard_even_after_a_terminal_had_it(x, cube):
    t = terminal(x)
    app = App(cube)
    try:
        mw = main_window(app)
        got = wait(lambda: x.get_input_focus().focus.id == mw["xid"], 5.0)
        focus = x.get_input_focus().focus.id
        assert got, f"X focus on {focus:#x} (terminal {t.id:#x}, viewer {mw['xid']:#x})"
        assert wait(lambda: active_window(x) == mw["xid"])
        t0 = app("state")["t"]
        fake(x, 2, keycode(x, "Up"))
        fake(x, 3, keycode(x, "Up"))
        assert wait(lambda: app("state")["t"] == t0 + 1)
    finally:
        app.close()
        t.destroy()
        x.sync()


def test_frames_moves_state_panels_and_the_close_button(x, cube):
    from Xlib import X
    from Xlib.protocol import event

    app = App(cube)
    try:
        mw = main_window(app)
        win = x.create_resource_object("window", mw["xid"])
        assert wait(lambda: win.query_tree().parent.id != x.screen().root.id)          # framed by the manager

        def qt_matches_x():
            g = main_window(app)["geometry"]
            c = win.translate_coords(x.screen().root, 0, 0)
            return (g[0], g[1]) == (-c.x, -c.y)
        assert wait(qt_matches_x)                       # Qt's position is the client window's, in the frame
        client_message(x, mw["xid"], "_NET_MOVERESIZE_WINDOW", [(1 << 8) | (1 << 9) | 10, 300, 200])
        assert wait(lambda: main_window(app)["geometry"][:2] == [300, 200] and qt_matches_x())
        max_v, max_h = x.intern_atom("_NET_WM_STATE_MAXIMIZED_VERT"), x.intern_atom("_NET_WM_STATE_MAXIMIZED_HORZ")
        client_message(x, mw["xid"], "_NET_WM_STATE", [1, max_v, max_h, 2])           # the manager's button
        assert wait(lambda: app("state")["maximized"])
        g = main_window(app)["geometry"]
        geo = win.get_geometry()
        assert (g[2], g[3]) == (geo.width, geo.height)
        client_message(x, mw["xid"], "_NET_WM_STATE", [0, max_v, max_h, 2])
        assert wait(lambda: not app("state")["maximized"])
        app("minimize")                                 # Ctrl+M: Qt asks, the manager iconifies
        wm_state = x.intern_atom("WM_STATE")
        assert wait(lambda: (win.get_full_property(wm_state, wm_state) or [None]).value[0] == 3 and
                    app("state")["minimized"])
        client_message(x, mw["xid"], "_NET_ACTIVE_WINDOW", [2, X.CurrentTime, 0])      # the taskbar restores it
        assert wait(lambda: not app("state")["minimized"] and win.get_attributes().map_state == X.IsViewable)
        app("panel")
        pw = next(w for w in app("state")["windows"] if w["title"] == "panel λ–t")
        client_message(x, mw["xid"], "_NET_ACTIVE_WINDOW", [2, X.CurrentTime, 0])      # the main window in front

        def panel_above():
            order = [c.id for c in x.screen().root.query_tree().children]
            frames = {}
            for xid in (mw["xid"], pw["xid"]):
                w_ = x.create_resource_object("window", xid)
                while w_.query_tree().parent.id != x.screen().root.id:
                    w_ = w_.query_tree().parent
                frames[xid] = w_.id
            return order.index(frames[pw["xid"]]) > order.index(frames[mw["xid"]])
        assert wait(lambda: active_window(x) == mw["xid"]) and wait(panel_above)
        t = terminal(x)                                 # the viewer inactive: no widget window active in Qt
        assert wait(lambda: app("state")["active"] is None, 3.0)
        ev = event.ClientMessage(window=win, client_type=x.intern_atom("WM_PROTOCOLS"),
                                 data=(32, [x.intern_atom("WM_DELETE_WINDOW"), X.CurrentTime, 0, 0, 0]))
        win.send_event(ev)                              # the close button: the manager sends WM_DELETE_WINDOW
        x.sync()
        try:
            app.p.wait(10)
        except subprocess.TimeoutExpired:
            pass
        assert app.p.poll() == 0, "the viewer did not quit when its window was closed"
        t.destroy()
        x.sync()
    finally:
        app.close()
