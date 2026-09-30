"""choose_display: the prototype's table, without Qt."""
import pytest

from explorer.platform.plan import X11_VAR, choose_display

SSH = {"SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"}


@pytest.mark.parametrize("env, platform, x11, bridge, want", [
    # Linux
    ({}, "linux", "auto", False, ("stop", None, False, False)),
    ({"WAYLAND_DISPLAY": "wayland-0"}, "linux", "auto", False, ("ok", None, False, False)),
    ({"DISPLAY": ":0"}, "linux", "auto", False, ("ok", "xcb", False, False)),
    ({"DISPLAY": "localhost:10.0", **SSH}, "linux", "auto", True, ("ok", "offscreen", True, True)),
    ({"DISPLAY": "localhost:10.0", **SSH}, "linux", "auto", False, ("ok", "xcb", True, False)),   # no python-xlib
    ({"DISPLAY": "localhost:10.0", **SSH}, "linux", "native", True, ("ok", "xcb", True, False)),
    ({"DISPLAY": ":0", **SSH}, "linux", "auto", True, ("ok", "xcb", False, False)),               # local display
    ({"DISPLAY": ":0"}, "linux", "bridge", True, ("ok", "offscreen", True, True)),
    ({"QT_QPA_PLATFORM": "offscreen", "DISPLAY": "localhost:10.0", **SSH}, "linux", "auto", True,
     ("ok", "offscreen", False, False)),                                          # tests over ssh: kept
    ({"QT_QPA_PLATFORM": "xcb", "DISPLAY": "localhost:10.0", **SSH}, "linux", "auto", True, ("ok", "xcb", True, False)),
    # macOS
    ({}, "darwin", "auto", True, ("ok", "cocoa", False, False)),
    ({**SSH}, "darwin", "auto", True, ("stop", None, False, False)),
    ({"DISPLAY": "localhost:10.0", **SSH}, "darwin", "auto", True, ("ok", "offscreen", True, True)),
    ({"DISPLAY": "localhost:10.0", **SSH}, "darwin", "native", True, ("ok", "xcb", True, False)),
    ({"DISPLAY": "/private/tmp/launchd/org.xquartz:0"}, "darwin", "auto", True, ("ok", "cocoa", False, False)),
    ({"QT_QPA_PLATFORM": "offscreen", **SSH}, "darwin", "auto", True, ("ok", "offscreen", False, False)),
    # the choice in the environment
    ({"DISPLAY": "localhost:10.0", X11_VAR: "native", **SSH}, "linux", "auto", True, ("ok", "xcb", True, False)),
])
def test_the_prototype_table(env, platform, x11, bridge, want):
    p = choose_display(env, platform, x11, bridge_available=bridge)
    got = ("stop" if p.stop else "ok", p.platform, p.remote, p.bridge)
    assert got == want, (env, platform, x11, p)
    if p.platform in ("xcb", "offscreen") and "QT_QPA_PLATFORM" not in env:
        assert p.env.get("QT_QPA_PLATFORM") == p.platform        # the plan sets what it chose


def test_messages_and_kinds():
    assert "ssh -Y" in choose_display({}, "linux").stop
    assert "window server" in choose_display(SSH, "darwin").stop
    fallback = choose_display({"DISPLAY": "localhost:10.0", **SSH}, "linux", bridge_available=False)
    assert fallback.notes and "python-xlib" in fallback.notes[0] and fallback.kind == "x11"
    assert choose_display({"DISPLAY": "localhost:10.0", **SSH}, "linux", bridge_available=True).kind == "x11bridge"
    assert choose_display({}, "darwin").kind == "cocoa" and choose_display({}, "linux").kind == "none"
    with pytest.raises(ValueError):
        choose_display({}, "linux", "x")


def test_the_rewritten_bridge_only_when_asked():
    remote = {"DISPLAY": "localhost:10.0", **SSH}
    p = choose_display(remote, "linux", "bridge2")
    assert p.variant == "bridge2" and p.bridge and p.env == {"QT_QPA_PLATFORM": "offscreen"}
    assert choose_display({**remote, X11_VAR: "bridge2"}, "darwin").variant == "bridge2"
    assert choose_display({**remote, "QT_QPA_PLATFORM": "offscreen"}, "linux", "bridge2").variant == "bridge2"
    assert choose_display(remote, "linux").variant is None                 # auto never picks it
    assert "bridge2" in (choose_display({"QT_QPA_PLATFORM": "offscreen"}, "linux", "bridge2").stop or "")
