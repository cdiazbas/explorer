"""choose_display: the prototype's table, without Qt."""
import pytest

from explorer.platform.plan import X11_VAR, choose_display

SSH = {"SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"}


@pytest.mark.parametrize("env, platform, x11, want", [
    # Linux
    ({}, "linux", "auto", ("stop", None, False, False)),
    ({"WAYLAND_DISPLAY": "wayland-0"}, "linux", "auto", ("ok", None, False, False)),
    ({"DISPLAY": ":0"}, "linux", "auto", ("ok", "xcb", False, False)),
    ({"DISPLAY": "localhost:10.0", **SSH}, "linux", "auto", ("ok", "offscreen", True, True)),
    ({"DISPLAY": "localhost:10.0", **SSH}, "linux", "native", ("ok", "xcb", True, False)),
    ({"DISPLAY": ":0", **SSH}, "linux", "auto", ("ok", "xcb", False, False)),               # local display
    ({"DISPLAY": ":0"}, "linux", "bridge", ("ok", "offscreen", True, True)),
    ({"QT_QPA_PLATFORM": "offscreen", "DISPLAY": "localhost:10.0", **SSH}, "linux", "auto",
     ("ok", "offscreen", False, False)),                                          # tests over ssh: kept
    ({"QT_QPA_PLATFORM": "xcb", "DISPLAY": "localhost:10.0", **SSH}, "linux", "auto", ("ok", "xcb", True, False)),
    # sshd with X11UseLocalhost no gives DISPLAY=host:10.0: as remote as localhost:10.0 (the prototype's F1, whose
    # main() took only localhost: and left such a link without the bridge nor the remote settings; startup.py:63)
    ({"DISPLAY": "bellatrix.uio.no:10.0", **SSH}, "linux", "auto", ("ok", "offscreen", True, True)),
    ({"DISPLAY": "bellatrix.uio.no:10.0", **SSH}, "linux", "native", ("ok", "xcb", True, False)),
    ({"QT_QPA_PLATFORM": "xcb", "DISPLAY": "bellatrix.uio.no:10.0", **SSH}, "linux", "auto",
     ("ok", "xcb", True, False)),
    ({"DISPLAY": "grove.uio.no:11.0"}, "linux", "auto", ("ok", "xcb", False, False)),       # not over ssh: local
    # macOS
    ({}, "darwin", "auto", ("ok", "cocoa", False, False)),
    ({**SSH}, "darwin", "auto", ("stop", None, False, False)),
    ({"DISPLAY": "localhost:10.0", **SSH}, "darwin", "auto", ("ok", "offscreen", True, True)),
    ({"DISPLAY": "localhost:10.0", **SSH}, "darwin", "native", ("ok", "xcb", True, False)),
    ({"DISPLAY": "/private/tmp/launchd/org.xquartz:0"}, "darwin", "auto", ("ok", "cocoa", False, False)),
    ({"QT_QPA_PLATFORM": "offscreen", **SSH}, "darwin", "auto", ("ok", "offscreen", False, False)),
    # the choice in the environment
    ({"DISPLAY": "localhost:10.0", X11_VAR: "native", **SSH}, "linux", "auto", ("ok", "xcb", True, False)),
])
def test_the_prototype_table(env, platform, x11, want):
    p = choose_display(env, platform, x11)
    got = ("stop" if p.stop else "ok", p.platform, p.remote, p.bridge)
    assert got == want, (env, platform, x11, p)
    if p.platform in ("xcb", "offscreen") and "QT_QPA_PLATFORM" not in env:
        assert p.env.get("QT_QPA_PLATFORM") == p.platform        # the plan sets what it chose


def test_messages_and_kinds():
    assert "ssh -Y" in choose_display({}, "linux").stop
    assert "window server" in choose_display(SSH, "darwin").stop
    assert choose_display({"DISPLAY": "localhost:10.0", **SSH}, "linux").kind == "x11bridge"
    assert choose_display({"DISPLAY": "localhost:10.0", **SSH}, "linux", "native").kind == "x11"
    assert choose_display({}, "darwin").kind == "cocoa" and choose_display({}, "linux").kind == "none"
    with pytest.raises(ValueError):
        choose_display({}, "linux", "x")


def test_the_bridge_when_asked_or_over_ssh():
    remote = {"DISPLAY": "localhost:10.0", **SSH}
    p = choose_display(remote, "linux")
    assert p.bridge and p.env == {"QT_QPA_PLATFORM": "offscreen"}                 # auto over ssh
    assert choose_display({**remote, X11_VAR: "bridge"}, "darwin").bridge
    assert choose_display({**remote, "QT_QPA_PLATFORM": "offscreen"}, "linux", "bridge").bridge
    assert "bridge" in (choose_display({"QT_QPA_PLATFORM": "offscreen"}, "linux", "bridge").stop or "")
    with pytest.raises(ValueError):
        choose_display(remote, "linux", "bridge2")                             # one bridge now
