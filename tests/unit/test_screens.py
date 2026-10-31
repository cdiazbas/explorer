"""The monitor a window is sized in and zooms to (ROADMAP E5.2): the Mac's insets as the launcher passes them, the
Dock left out over X11 to a Mac, and one wide X screen taken as monitors side by side."""
from PySide6 import QtCore

from explorer.platform import screens


class _App:
    def __init__(self, platform):
        self.p = platform

    def platformName(self):
        return self.p


def test_the_insets_parse_and_bad_parts_are_skipped():
    env = {screens.INSETS_ENV: "1352x878:25,0,70,0;garbage;1920x1080:0,0,0,80"}
    assert screens.screen_insets(env) == [(1352, 878, 25, 0, 70, 0), (1920, 1080, 0, 0, 0, 80)]
    assert screens.screen_insets({}) == []


def test_the_dock_is_left_out_over_x11_to_a_mac(monkeypatch):
    # the prototype's measured Mac: 1352 x 878 pt, usable 1352 x 783, XQuartz's screen 1352 x 848
    monkeypatch.setenv(screens.INSETS_ENV, "1352x878:30,0,65,0")
    full = QtCore.QRect(0, 0, 1352, 878)                  # the whole screen: menu bar and Dock out
    assert screens.leave_mac_bars(_App("xcb"), full) == QtCore.QRect(0, 30, 1352, 783)
    xq = QtCore.QRect(0, 0, 1352, 848)                    # XQuartz already left the menu bar out: the Dock only
    assert screens.leave_mac_bars(_App("xcb"), xq) == QtCore.QRect(0, 0, 1352, 783)
    assert screens.leave_mac_bars(_App("cocoa"), full) == full     # a local Mac keeps its own


def test_without_insets_the_dock_is_guessed_through_the_bridge_too(monkeypatch):
    """ssh -Y to a Mac goes through the bridge, whose Qt platform is offscreen: the Dock was guessed only for xcb, and
    the first window, the zoom and glass's fit went under it (the prototype's F44, app/viewer.py:2452-2461)."""
    monkeypatch.delenv(screens.INSETS_ENV, raising=False)
    xq = QtCore.QRect(0, 0, 1352, 848)
    monkeypatch.setattr(screens, "_x_facts", lambda: {"heads": [], "xquartz": True})
    for platform in ("xcb", "offscreen"):
        assert screens.leave_mac_bars(_App(platform), xq) == QtCore.QRect(0, 0, 1352, 848 - screens.DOCK_GUESS)
    monkeypatch.setattr(screens, "_x_facts", lambda: {"heads": [], "xquartz": False})
    assert screens.leave_mac_bars(_App("offscreen"), xq) == xq        # another X server, or no display at all


def test_one_wide_screen_is_taken_as_monitors_side_by_side(qapp, monkeypatch):
    from PySide6 import QtGui

    class Scr:
        def availableGeometry(self):
            return QtCore.QRect(0, 0, 3840, 1080)

        def devicePixelRatio(self):
            return 1.0

    class App(_App):
        def screenAt(self, p):
            return Scr()

        def primaryScreen(self):
            return Scr()

        def screens(self):
            return [Scr()]

    monkeypatch.setattr(screens, "_x_facts", lambda: {"heads": [], "xquartz": False})
    app = App("offscreen")
    assert screens.monitor_rect(app, QtCore.QPoint(100, 100)) == QtCore.QRect(0, 0, 1920, 1080)
    assert screens.monitor_rect(app, QtCore.QPoint(2500, 100)) == QtCore.QRect(1920, 0, 1920, 1080)
    assert QtGui.QGuiApplication.instance() is qapp


def test_a_wide_screen_is_split_only_over_x11(monkeypatch):
    """The split guesses the monitors XQuartz reports as one screen; on a local Mac Qt gives one screen per monitor
    already, and a 32:9 monitor (5120 x 1440) there is one monitor, not two halves (the prototype's F13,
    app/viewer.py:2489-2491)."""
    class Scr:
        def availableGeometry(self):
            return QtCore.QRect(0, 0, 5120, 1440)

        def devicePixelRatio(self):
            return 1.0

    class App(_App):
        def screenAt(self, p):
            return Scr()

        def primaryScreen(self):
            return Scr()

        def screens(self):
            return [Scr()]

    monkeypatch.delenv(screens.INSETS_ENV, raising=False)
    monkeypatch.setattr(screens, "_x_facts", lambda: {"heads": [], "xquartz": False})
    at = QtCore.QPoint(3000, 100)
    seen = {p: screens.monitor_rect(App(p), at) for p in ("cocoa", "offscreen", "xcb")}
    want = {"cocoa": QtCore.QRect(0, 0, 5120, 1440), "offscreen": QtCore.QRect(2560, 0, 2560, 1440),
            "xcb": QtCore.QRect(2560, 0, 2560, 1440)}
    assert seen == want, dict(seen=seen, want=want)


def test_through_the_bridge_the_monitors_are_those_x_has_now(monkeypatch):
    """Through the bridge Qt's screens are X's monitors when the viewer started (offscreen's configuration file):
    with a monitor plugged in or taken out afterwards, a first window and a zoom were sized in the monitors that
    were. The bridge follows the X screen and gives the monitors as they are now."""
    class Scr:
        def availableGeometry(self):
            return QtCore.QRect(0, 0, 1920, 1080)       # the one monitor at the start

        def devicePixelRatio(self):
            return 1.0

    class App(_App):
        def screenAt(self, p):
            return None

        def primaryScreen(self):
            return Scr()

        def screens(self):
            return [Scr()]

    monkeypatch.delenv(screens.INSETS_ENV, raising=False)
    monkeypatch.setattr(screens, "_x_facts", lambda: {"heads": [], "xquartz": False})
    now = [QtCore.QRect(0, 0, 1920, 1080), QtCore.QRect(1920, 0, 1280, 1024)]
    unfollow = screens.follow(lambda: now)
    try:
        assert screens.monitor_rect(App("offscreen"), QtCore.QPoint(2000, 100)) == now[1]
        assert screens.monitor_rect(App("offscreen"), QtCore.QPoint(100, 100)) == now[0]
        now[:] = [QtCore.QRect(0, 0, 3840, 1080)]       # one wide screen again: the side-by-side guess on it
        assert screens.monitor_rect(App("offscreen"), QtCore.QPoint(2500, 100)) == QtCore.QRect(1920, 0, 1920, 1080)
        assert screens.monitor_rect(App("xcb"), QtCore.QPoint(100, 100)) == QtCore.QRect(0, 0, 1920, 1080)
    finally:
        unfollow()
    assert screens.monitor_rect(App("offscreen"), QtCore.QPoint(2000, 100)) == QtCore.QRect(0, 0, 1920, 1080)


def test_x_s_monitors_are_asked_again_when_qt_s_screens_change(monkeypatch):
    """xcb follows the X screen (RandR) but Xinerama's heads were asked once per DISPLAY: one X screen over two
    monitors (XQuartz) kept the heads of the start after a monitor came or went. They are asked again when Qt's
    screens change."""
    from explorer.platform.xbridge import xproto

    made: list = []

    class Conn:
        def __init__(self, display, name=""):
            made.append(display)

        def xinerama_screens(self):
            return [(0, 0, 100 * len(made), 100)]

        def ext(self, name):
            return None

        def close(self):
            pass

    monkeypatch.setattr(xproto, "Connection", Conn)
    monkeypatch.setenv("DISPLAY", ":test-r45")
    monkeypatch.setattr(screens, "_X", {})
    shape = [((0, 0, 1920, 1080),)]
    monkeypatch.setattr(screens, "_qt_screens", lambda: shape[0])
    first = screens._x_facts()["heads"]
    assert screens._x_facts()["heads"] == first and len(made) == 1     # asked once while nothing changed
    shape[0] = ((0, 0, 3200, 1080),)
    assert screens._x_facts()["heads"] == [QtCore.QRect(0, 0, 200, 100)] and len(made) == 2
