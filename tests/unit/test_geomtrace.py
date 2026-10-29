"""The geometry trace (ROADMAP E6.7, ui/geomtrace.py): off unless EXPLORER_GEOMETRY_TRACE is set, and then wrapping
nothing; on, a line for every move and resize of the window and its panels, for each one explorer's code asked for
with the frames that asked, and for each look worn; stopped, everything back as it was. A start through ui.app.run
with the variable writes the file."""
import inspect
import os
import subprocess
import sys
import time

import pytest

from explorer.testing import synth

SHAPE = (4, 4, 11, 96, 80)


def spin(qapp, until, timeout=8.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.005)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("trace"), "c", shape=SHAPE, icube=False)["im"]


def wrapped(QtWidgets, geomtrace) -> list[str]:
    """The watched methods that are Python functions (the tracer's) instead of Qt's own."""
    return [f"{c.__name__}.{n}" for c in (QtWidgets.QDockWidget, QtWidgets.QMainWindow)
            for n in geomtrace.WATCHED + ("setFloating",)
            if hasattr(c, n) and inspect.isfunction(getattr(c, n))]


def test_off_unless_asked_and_then_nothing_is_wrapped(qapp, monkeypatch, tmp_path):
    """Asked for (the variable, or explorer --log), never on by default: on every start it cost 3 % per cursor move
    offscreen and 7 % through the bridge."""
    from PySide6 import QtWidgets

    from explorer.ui import geomtrace

    assert geomtrace.ENV == "EXPLORER_GEOMETRY_TRACE"    # EXPLORER_TRACE is the spans' Perfetto file (obs.trace)
    assert geomtrace.wanted({geomtrace.ENV: "1"}) and geomtrace.wanted({geomtrace.ENV: "yes"})
    assert not geomtrace.wanted({}) and not geomtrace.wanted({geomtrace.ENV: "0"})
    assert not geomtrace.wanted({"EXPLORER_TRACE": "t.json"})
    assert geomtrace.install_from_env({}) is None
    assert not wrapped(QtWidgets, geomtrace), wrapped(QtWidgets, geomtrace)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    t = geomtrace.install_from_env({geomtrace.ENV: "1"})
    try:
        assert t is not None and t.path.parent == tmp_path / "explorer" / "logs"
    finally:
        t.stop()
    assert not wrapped(QtWidgets, geomtrace), wrapped(QtWidgets, geomtrace)


def test_on_it_says_who_moved_what(qapp, cube, tmp_path):
    from PySide6 import QtCore, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui import geomtrace
    from explorer.ui.shell import Shell

    t = geomtrace.Tracer(tmp_path / "geometry.log")
    ds = Dataset.open(cube)
    w = Shell(ds)
    try:
        w.resize(1000, 700)
        w.show()
        assert spin(qapp, lambda: "lambda_t" in w.last)
        d = w.spec_dock
        d.setFloating(True)
        d.setGeometry(QtCore.QRect(1100, 80, 420, 300))
        w.set_look(get_look("glass"))                   # glass places its panels itself: glass.py asks
        spin(qapp, lambda: False, 1.0)
    finally:
        w.close()
        ds.close()
        t.stop()
    lines = (tmp_path / "geometry.log").read_text().splitlines()
    text = "\n".join(lines)
    assert lines[0].split()[1] == "START", text[:2000]
    want = [
        ("CALL spectrum  setFloating True", "test_geomtrace.py"),
        ("CALL spectrum  setGeometry (1100, 80, 420, 300)", "test_geomtrace.py"),
        ("EVT  spectrum  Move", ""),
        ("LOOK glass", ""),
        ("CALL spectrum  setGeometry", "glass.py"),
    ]
    for head, origin in want:
        hits = [ln for ln in lines if head in ln and origin in ln]
        assert hits, f"no line with {head!r} from {origin!r} in:\n{text[-4000:]}"
    assert not wrapped(QtWidgets, geomtrace), f"stop() left {wrapped(QtWidgets, geomtrace)} wrapped"
    assert "set_look" not in vars(Shell) or Shell.set_look.__qualname__ == "Shell.set_look", Shell.set_look


@pytest.mark.parametrize("how", ["--log", "variable"])
def test_a_start_asked_for_it_writes_the_trace(cube, tmp_path, how):
    """explorer --log cube.fits (or the variable): the trace a problem is sent with."""
    env = dict(os.environ, XDG_CACHE_HOME=str(tmp_path / "cache"), EXPLORER_LAYOUT=str(tmp_path / "layout.ini"),
               QT_QPA_PLATFORM="offscreen", EXPLORER_TERMINAL_KEYS="0")
    env.pop("EXPLORER_GEOMETRY_TRACE", None)
    if how == "variable":
        env["EXPLORER_GEOMETRY_TRACE"] = "1"
    env.pop("DISPLAY", None)
    env.pop("EXPLORER_TRACE", None)
    args = [sys.executable, "-m", "explorer", str(cube), "--look", "glass", "--quit-after", "0.5"]
    p = subprocess.run(args + (["--log"] if how == "--log" else []), capture_output=True, text=True, env=env,
                       timeout=120, cwd=tmp_path)
    logs = list((tmp_path / "cache").rglob("geometry-*.log"))
    assert p.returncode == 0 and len(logs) == 1, dict(exit=p.returncode, logs=logs, stderr=p.stderr[-3000:])
    text = logs[0].read_text()
    assert "INFO  geometry: tracing" in p.stderr, p.stderr[-2000:]
    assert f"INFO  geometry: the trace of this session: {logs[0]}" in p.stderr, p.stderr[-2000:]   # named at the close
    assert "LOOK glass" in text and "EVT  main" in text and "SCREENS " in text, text[-3000:]
    assert not (tmp_path / "geometry").exists() and not list(tmp_path.glob("*.json")), "a spans trace was written"


def test_it_says_which_monitor_the_panels_were_placed_in(qapp, cube, tmp_path):
    """A panel placed wrongly can come from the monitor explorer believed it was in (the bridge takes XQuartz's one
    screen as one monitor) or from the window manager moving it afterwards: the trace names the screens at the start,
    each reset, and the monitor and window frame each placement of the glass look's panels started from."""
    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui import geomtrace
    from explorer.ui.glass import GlassChrome
    from explorer.ui.shell import Shell

    t = geomtrace.Tracer(tmp_path / "geometry.log")
    ds = Dataset.open(cube)
    w = Shell(ds, look=get_look("glass"))
    try:
        w.resize(900, 700)
        w.show()
        assert spin(qapp, lambda: "lambda_t" in w.last)
        w.reset_panels()
        spin(qapp, lambda: False, 0.5)
    finally:
        w.close()
        ds.close()
        t.stop()
    lines = (tmp_path / "geometry.log").read_text().splitlines()
    text = "\n".join(lines)
    assert any(ln.split()[1] == "SCREENS" and "available" in ln for ln in lines[:3]), text[:2000]
    assert any(ln.split()[1] == "RESET" for ln in lines), text[-3000:]
    place = [ln for ln in lines if ln.split()[1] == "PLACE"]
    assert place and "monitor (" in place[-1] and "window (" in place[-1], text[-3000:]
    assert GlassChrome.place_panels.__qualname__ == "GlassChrome.place_panels"     # stop() put it back


def test_it_writes_the_pointer_events_the_bridge_takes_with_the_x_servers_time(qapp, tmp_path):
    """Through ssh -Y a dragged panel moved in bursts every ~510 ms. Each X pointer event carries the X server's time:
    events stamped 500 ms apart came late from the server (XQuartz, the Mac); stamped close together and taken in a
    burst, the delay is the link's or explorer's. The trace writes each one the bridge takes (XIN)."""
    import struct

    from explorer.platform.xbridge.bridge import Bridge
    from explorer.ui import geomtrace

    t = geomtrace.Tracer(tmp_path / "geometry.log")
    try:
        raw = bytearray(32)
        raw[0] = 6                                      # MotionNotify
        struct.pack_into("<IIIIhhhhHB", raw, 4, 123456, 1, 2, 0, 640, 480, 10, 20, 0x100, 1)
        fake = type("B", (), {"stats": {"x_events": 0}, "windows": type("W", (), {"xtime": 0, "by_xid": {}})(),
                              "clip": None})()
        try:
            Bridge._event(fake, bytes(raw))
        except Exception:                               # the stand-in has no more of a bridge than this needs
            pass
    finally:
        t.stop()
    text = (tmp_path / "geometry.log").read_text()
    assert "XIN  motion  x_time 123456 at (640, 480)" in text, text[-2000:]
    assert Bridge._event.__qualname__ == "Bridge._event"                     # stop() put it back


def test_it_writes_each_key_press_where_the_focus_is_and_the_shortcut_it_fired(qapp, cube, tmp_path):
    """Backspace did not remove a slit through ssh -Y on someone's Mac, nor C change the map: the trace says where each
    key went. With the focus on the image Backspace fires its shortcut; with it on the frames-per-second box (a click
    there), the box keeps the key and no shortcut line follows."""
    from PySide6 import QtCore, QtGui, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.ui import geomtrace
    from explorer.ui.shell import Shell

    t = geomtrace.Tracer(tmp_path / "geometry.log")
    ds = Dataset.open(cube)
    w = Shell(ds)

    def backspace():
        h = w.windowHandle()
        for typ in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):   # as the bridge sends keys
            QtWidgets.QApplication.sendEvent(h, QtGui.QKeyEvent(typ, QtCore.Qt.Key.Key_Backspace,
                                                               QtCore.Qt.KeyboardModifier.NoModifier, "\x08"))
        spin(qapp, lambda: False, 0.1)

    try:
        w.resize(1000, 700)
        w.show()
        w.activateWindow()
        assert spin(qapp, lambda: "lambda_t" in w.last and QtWidgets.QApplication.activeWindow() is w)
        w.view.widget.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
        w.session.set_path(((10.5, 10.5), (60.5, 70.5)), 0)
        spin(qapp, lambda: False, 0.1)
        backspace()
        assert w.session.state.path is None
        w.nav.fps.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
        w.session.set_path(((10.5, 10.5), (60.5, 70.5)), 0)
        spin(qapp, lambda: False, 0.1)
        backspace()
        assert w.session.state.path is not None         # the box kept it
    finally:
        w.close()
        ds.close()
        t.stop()
    lines = (tmp_path / "geometry.log").read_text().splitlines()
    text = "\n".join(lines)
    keys = [i for i, ln in enumerate(lines) if ln.split()[1:3] == ["KEY", "Key_Backspace"]]
    assert len(keys) == 2, text[-3000:]
    first, second = lines[keys[0]], lines[keys[1]]
    assert "text '\\x08' mods none  to main  focus GraphicsLayoutWidget" in first and "active main" in first, first
    assert "KEY  shortcut Backspace  on main" in lines[keys[0] + 1], text[-3000:]
    assert "focus QSpinBox < QToolBar[nav] < main" in second, second
    assert not any("KEY  shortcut" in ln for ln in lines[keys[1]:]), text[-3000:]
    assert any("FOCUS QSpinBox < QToolBar[nav] < main  reason Mouse" in ln for ln in lines), text[-3000:]
    assert any(ln.split()[1:3] == ["ACTIVE", "main"] for ln in lines), text[-3000:]


def test_it_writes_the_keys_and_the_x_focus_the_bridge_takes(qapp, tmp_path):
    """What the X server sent, before Qt: the keysym through the server's keyboard map and the Qt key it becomes (or
    that the bridge drops it), the X focus coming and going, the manager's WM_TAKE_FOCUS."""
    import struct
    from types import SimpleNamespace

    from explorer.platform.xbridge import keys
    from explorer.platform.xbridge.bridge import Bridge
    from explorer.ui import geomtrace

    syms = [(0, 0)] * 60
    syms[22 - 8], syms[54 - 8], syms[30 - 8] = (0xFF08, 0), (0x63, 0x43), (0xFE50, 0)      # BackSpace, c C, dead_grave
    main = SimpleNamespace(w=SimpleNamespace(objectName=lambda: "", windowTitle=lambda: "c — explorer"))
    windows = SimpleNamespace(xtime=0, by_xid={0x400002: main}, atoms={"WM_PROTOCOLS": 300, "WM_TAKE_FOCUS": 301})
    fake = SimpleNamespace(stats={"x_events": 0}, windows=windows, clip=None, keymap=keys.Keymap(8, 2, syms))

    def key(code, state=0):
        raw = bytearray(32)
        raw[0], raw[1] = 2, code                        # KeyPress
        struct.pack_into("<IIIIhhhhH", raw, 4, 777, 1, 0x400002, 0, 50, 60, 5, 6, state)
        return bytes(raw)

    def focus(code, detail, mode):
        raw = bytearray(32)
        raw[0], raw[1] = code, detail
        struct.pack_into("<IB", raw, 4, 0x400002, mode)
        return bytes(raw)

    take = bytearray(32)
    take[0], take[1] = 33, 32                           # ClientMessage, format 32
    struct.pack_into("<II5I", take, 4, 0x400002, 300, 301, 888, 0, 0, 0)
    t = geomtrace.Tracer(tmp_path / "geometry.log")
    try:
        for raw in (focus(9, 3, 0), bytes(take), key(22), key(54, 1), key(30), focus(10, 3, 1)):
            try:
                Bridge._event(fake, raw)
            except Exception:                           # the stand-in has no more of a bridge than this needs
                pass
        fake.keymap = None
        try:
            Bridge._event(fake, key(22))
        except Exception:
            pass
    finally:
        t.stop()
    text = (tmp_path / "geometry.log").read_text()
    for want in ("XIN  focus   in  mode Normal detail Nonlinear  c — explorer 0x400002",
                 "XIN  focus   WM_TAKE_FOCUS x_time 888  c — explorer 0x400002",
                 "XIN  key     x_time 777 keycode 22 state 0x0 keysym 0xff08 -> Key_Backspace  c — explorer 0x400002",
                 "keycode 54 state 0x1 keysym 0x43 -> 'C'",
                 "keycode 30 state 0x0 keysym 0xfe50 -> no Qt key: dropped",
                 "XIN  focus   out mode Grab detail Nonlinear",
                 "keycode 22 state 0x0 -> no keyboard map from the X server: dropped"):
        assert want in text, f"{want!r} not in:\n{text[-2000:]}"
    assert Bridge._event.__qualname__ == "Bridge._event"                     # stop() put it back
