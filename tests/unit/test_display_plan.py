"""choose_display: the prototype's table, without Qt, and Qt's xcb without libxcb-cursor."""
import subprocess

import pytest

from explorer.platform import plan
from explorer.platform.plan import X11_VAR, choose_display

SSH = {"SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"}
CACHE_WITH = "\tlibxcb-cursor.so.0 (libc6,x86-64) => /usr/lib64/libxcb-cursor.so.0\n"
CACHE_WITHOUT = "\tlibxcb.so.1 (libc6,x86-64) => /usr/lib64/libxcb.so.1\n"


def _ldconfig(monkeypatch, out: str):
    """`ldconfig -p` answering out, whatever this machine has (a Mac has none)."""
    real = subprocess.run

    def run(cmd, *a, **k):
        if cmd[:1] == ["/sbin/ldconfig"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
        return real(cmd, *a, **k)
    monkeypatch.setattr(subprocess, "run", run)


@pytest.fixture(autouse=True)
def _with_xcb_cursor(monkeypatch):
    """The table below is a system that has libxcb-cursor; the tests without it say so."""
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    _ldconfig(monkeypatch, CACHE_WITH)


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


LOCAL = {"DISPLAY": ":187"}


@pytest.mark.parametrize("env, platform, x11, want", [
    (LOCAL, "linux", "auto", ("ok", "offscreen", True, True)),                  # the bridge instead of Qt's abort
    ({**LOCAL, **SSH}, "linux", "auto", ("ok", "offscreen", True, True)),       # ssh to the machine, its own display
    ({**LOCAL, X11_VAR: "native"}, "linux", "auto", ("stop", None, False, False)),
    (LOCAL, "linux", "native", ("stop", None, False, False)),
    ({"DISPLAY": "localhost:10.0", **SSH}, "linux", "native", ("stop", None, False, False)),
    ({"DISPLAY": "localhost:10.0", **SSH}, "linux", "auto", ("ok", "offscreen", True, True)),     # as before
    (LOCAL, "linux", "bridge", ("ok", "offscreen", True, True)),
    ({**LOCAL, "QT_QPA_PLATFORM": "xcb"}, "linux", "auto", ("ok", "xcb", False, False)),           # kept: Qt tries
    ({"WAYLAND_DISPLAY": "wayland-0"}, "linux", "auto", ("ok", None, False, False)),
    ({}, "darwin", "auto", ("ok", "cocoa", False, False)),
    ({"DISPLAY": "localhost:10.0", **SSH}, "darwin", "native", ("ok", "xcb", True, False)),
])
def test_without_libxcb_cursor(monkeypatch, env, platform, x11, want):
    _ldconfig(monkeypatch, CACHE_WITHOUT)
    p = choose_display(env, platform, x11)
    got = ("stop" if p.stop else "ok", p.platform, p.remote, p.bridge)
    assert got == want, (env, platform, x11, p)


def test_without_libxcb_cursor_the_terminal_is_told(monkeypatch):
    _ldconfig(monkeypatch, CACHE_WITHOUT)
    p = choose_display(LOCAL, "linux")
    assert p.env == {"QT_QPA_PLATFORM": "offscreen"} and p.kind == "x11bridge"
    assert len(p.notes) == 1 and "libxcb-cursor.so.0" in p.notes[0] and "X11 bridge" in p.notes[0]
    assert "xcb-util-cursor" in p.notes[0] and "EPEL" in p.notes[0]
    stop = choose_display(LOCAL, "linux", "native").stop
    assert "libxcb-cursor.so.0" in stop and "xcb-util-cursor" in stop and "--x11 native" in stop
    assert not choose_display({"DISPLAY": "localhost:10.0", **SSH}, "linux").notes    # the bridge anyway: no note


def test_with_libxcb_cursor_native_stays_native():
    assert choose_display(LOCAL, "linux").platform == "xcb"
    assert choose_display(LOCAL, "linux", "native").platform == "xcb"
    assert not choose_display(LOCAL, "linux").notes


def test_the_library_from_qtlibs_only(monkeypatch, tmp_path):
    """scripts/run.sh's LD_LIBRARY_PATH=.qtlibs/only, which holds libxcb-cursor: Qt's xcb, as before."""
    _ldconfig(monkeypatch, CACHE_WITHOUT)
    only = tmp_path / ".qtlibs" / "only"
    only.mkdir(parents=True)
    (only / "libxcb-cursor.so.0").write_bytes(b"")
    env = {**LOCAL, "LD_LIBRARY_PATH": str(only)}
    assert plan.find_xcb_cursor(env) == str(only / "libxcb-cursor.so.0")
    assert choose_display(env, "linux").platform == "xcb"
    assert choose_display(env, "linux", "native").platform == "xcb"
    assert choose_display({**LOCAL, "LD_LIBRARY_PATH": str(tmp_path)}, "linux").bridge     # not there: the bridge


def test_the_finder_reads_the_system_cache(monkeypatch):
    assert plan.find_xcb_cursor({}) == "/usr/lib64/libxcb-cursor.so.0"
    _ldconfig(monkeypatch, CACHE_WITHOUT)
    assert plan.find_xcb_cursor({}) is None


def test_the_finder_is_asked_only_for_xcb_on_linux():
    def never(env):
        raise AssertionError("asked")
    for env, platform, x11 in [({}, "darwin", "auto"), ({"DISPLAY": "localhost:10.0", **SSH}, "darwin", "native"),
                               ({"DISPLAY": "localhost:10.0", **SSH}, "linux", "auto"), (LOCAL, "linux", "bridge"),
                               ({"WAYLAND_DISPLAY": "wayland-0"}, "linux", "auto"),
                               ({**LOCAL, "QT_QPA_PLATFORM": "xcb"}, "linux", "auto")]:
        choose_display(env, platform, x11, xcb_cursor=never)
    assert choose_display(LOCAL, "linux", xcb_cursor=lambda env: None).bridge
    assert choose_display(LOCAL, "linux", xcb_cursor=lambda env: "/x/libxcb-cursor.so.0").platform == "xcb"


@pytest.mark.parametrize("env, platform, want", [
    ({"DISPLAY": "localhost:10.0", **SSH}, "linux", True),
    ({"DISPLAY": "bellatrix.uio.no:10.0", **SSH}, "linux", True),
    ({**LOCAL, **SSH}, "linux", False),                             # ssh to the machine, its own display
    (LOCAL, "linux", False),
    ({"DISPLAY": "localhost:10.0"}, "linux", False),               # not under ssh
    (SSH, "linux", False),
    ({"DISPLAY": "/private/tmp/launchd/org.xquartz:0", **SSH}, "darwin", True),   # a Mac has no X server of its own
])
def test_the_screen_over_ssh(env, platform, want):
    """What the first-image line says: the bridge on a local display is not over ssh, although its plan is remote."""
    assert plan.screen_over_ssh(env, platform) is want


def test_the_bridge_on_a_local_display_is_remote_but_not_over_ssh(monkeypatch):
    _ldconfig(monkeypatch, CACHE_WITHOUT)
    p = choose_display(LOCAL, "linux")
    assert p.bridge and p.remote and not plan.screen_over_ssh(LOCAL, "linux")
