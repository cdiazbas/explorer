"""Deciding, before Qt starts, how windows reach the screen: a function of the environment, the platform, the user's
choice and whether this system has libxcb-cursor (find_xcb_cursor, which tests replace), tested without Qt.

The prototype's table (app/startup.py prepare and remote_x11, app/xbridge.py wanted):
- Linux with no DISPLAY, no WAYLAND_DISPLAY and no QT_QPA_PLATFORM: stop with a message. Qt would abort with a core
  dump and blame libxcb-cursor.
- QT_QPA_PLATFORM set by whoever launched it: kept, and never replaced by the bridge. The self-tests' "offscreen",
  run over ssh with a forwarded DISPLAY, was replaced by the bridge's and opened windows on the user's Mac.
- --x11 native or bridge: wins over the automatic choice (EXPLORER_X11 in the environment does the same).
- A remote X display (an ssh session whose DISPLAY is not ":N"), from a Mac or from Linux: the bridge. Through ssh -Y
  it showed ~12 images/s against ~8.5 with Qt's own X11, with less than half the bytes (decided by the user). A Mac
  under ssh has no local X server of its own, so any DISPLAY there is remote.
- A local display: Linux, Qt's xcb (or Wayland when that is all there is); a Mac, cocoa.
- Qt's xcb on Linux without libxcb-cursor.so.0 (Qt >= 6.5 needs it; RHEL 9 does not ship it, nor does PySide6
  6.11.2's Linux wheel, whose libQt6XcbQpa looks for it in Qt/lib, RUNPATH $ORIGIN, then on the system): Qt aborts
  with a core dump (bellatrix, a local Xvfb). auto then takes the bridge, which does not need it, and says so on the
  terminal; --x11 native stops with a message instead of the abort. QT_QPA_PLATFORM=xcb set by whoever launched it
  is kept as above: the way to have Qt try anyway.
- A Mac reached by ssh without X forwarding: no window server; stop with a message (the prototype found it out after
  Qt started, from an empty screen list: grove).
The bridge is the one written anew (platform/xbridge); it needs nothing beyond Qt.
"""
import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from .._name import APP_NAME

X11_VAR = f"{APP_NAME.upper()}_X11"                     # native | bridge: the same as --x11
CHOICES = ("auto", "native", "bridge")
XCB_CURSOR = "libxcb-cursor.so.0"
GET_XCB_CURSOR = "install xcb-util-cursor (RHEL 9: from EPEL; Debian, Ubuntu: libxcb-cursor0)"


@dataclass(frozen=True)
class DisplayPlan:
    platform: str | None                                # Qt platform to ask for (QT_QPA_PLATFORM), None: Qt's default
    bridge: bool = False                                # windows drawn by the X11 bridge
    remote: bool = False                                # pixels as X11 requests: over ssh, or the bridge's
    stop: str | None = None                             # why the app cannot show a window here (then nothing else)
    env: dict = field(default_factory=dict)             # variables to set before Qt starts
    notes: tuple[str, ...] = ()

    @property
    def kind(self) -> str:
        """A name per way of displaying, for the saved window state (one layout per kind, as the prototype's)."""
        if self.stop:
            return "none"
        return "x11bridge" if self.bridge else "x11" if self.remote else (self.platform or "default")


def find_xcb_cursor(env: Mapping) -> str | None:
    """Where the loader would find libxcb-cursor.so.0 for Qt's xcb, or None: env's LD_LIBRARY_PATH (scripts/run.sh's
    .qtlibs/only), PySide6's own Qt/lib (the plugin's RUNPATH; found without importing it), then the system's cache
    (ldconfig -p)."""
    dirs = [d for d in env.get("LD_LIBRARY_PATH", "").split(":") if d]
    try:
        from importlib.util import find_spec

        spec = find_spec("PySide6")
        dirs += [os.path.join(d, "Qt", "lib") for d in (spec.submodule_search_locations or [])] if spec else []
    except (ImportError, ValueError):
        pass
    for d in dirs:
        p = os.path.join(d, XCB_CURSOR)
        if os.path.exists(p):
            return p
    try:
        out = subprocess.run(["/sbin/ldconfig", "-p"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    for line in out.splitlines():
        if XCB_CURSOR in line:
            return line.split("=>")[-1].strip()
    return None


def screen_over_ssh(env, platform: str) -> bool:
    """The screen is at the other end of an ssh link: a DISPLAY under ssh that is not this machine's ":N" (a Mac has
    no X server of its own, so there any). DisplayPlan.remote is wider: every bridge's pixels go as X11 requests."""
    disp = env.get("DISPLAY", "")
    return bool(env.get("SSH_CONNECTION")) and bool(disp) and (platform == "darwin" or not disp.startswith(":"))


def choose_display(env, platform: str, x11: str = "auto",
                   xcb_cursor: Callable[[Mapping], str | None] | None = None) -> DisplayPlan:
    """env: the process environment (a mapping); platform: sys.platform; x11: --x11 (auto, native or bridge);
    xcb_cursor: find_xcb_cursor, asked only when the plan would be Qt's xcb on Linux."""
    if x11 not in CHOICES:
        raise ValueError(f"--x11 must be one of {CHOICES}, not {x11!r}")
    linux, mac = platform.startswith("linux"), platform == "darwin"
    disp, qpa = env.get("DISPLAY", ""), env.get("QT_QPA_PLATFORM", "")
    ssh = bool(env.get("SSH_CONNECTION"))
    if x11 == "auto" and env.get(X11_VAR) in CHOICES[1:]:
        x11 = env[X11_VAR]

    if linux and not disp and not env.get("WAYLAND_DISPLAY") and not qpa:
        return DisplayPlan(None, stop="no display to show the window on (DISPLAY is not set): run it in a desktop "
                                      "session, or connect with ssh -Y so the window reaches your screen")
    if qpa:                                             # chosen by whoever launched it
        wants_bridge = x11 == "bridge"
        remote = wants_bridge or (qpa.startswith("xcb") and screen_over_ssh(env, platform))
        if not wants_bridge:
            return DisplayPlan(qpa, remote=remote)
    else:
        remote_display = screen_over_ssh(env, platform)
        if mac and ssh and not disp:
            return DisplayPlan(None, stop="macOS over ssh has no window server: connect with ssh -Y (the window "
                                          "then comes through X11), or run it in a Terminal on that Mac")
        wants_bridge = x11 == "bridge" or (x11 == "auto" and remote_display)
        if not wants_bridge:
            if mac and not remote_display:
                return DisplayPlan("cocoa")
            if mac:                                     # --x11 native from a Mac under ssh -Y: Qt's xcb
                return DisplayPlan("xcb", remote=True, env={"QT_QPA_PLATFORM": "xcb"})
            if disp and linux and (xcb_cursor or find_xcb_cursor)(env) is None:
                if x11 == "native":
                    return DisplayPlan(None, stop=f"Qt's own X11 (--x11 native) needs {XCB_CURSOR}, which is not on "
                                                  f"this system: {GET_XCB_CURSOR}, or leave --x11 to auto, which "
                                                  "then draws the window through the X11 bridge")
                return DisplayPlan("offscreen", bridge=True, remote=True, env={"QT_QPA_PLATFORM": "offscreen"},
                                   notes=(f"{XCB_CURSOR} not found, which Qt's own X11 needs: the window comes "
                                          f"through the X11 bridge. For Qt's own X11, {GET_XCB_CURSOR}",))
            return DisplayPlan("xcb" if disp else None, remote=remote_display,
                               env={"QT_QPA_PLATFORM": "xcb"} if disp else {})
    # the bridge is wanted
    if not disp:
        return DisplayPlan(None, stop="--x11 bridge needs an X display (DISPLAY is not set)")
    return DisplayPlan("offscreen", bridge=True, remote=True, env={"QT_QPA_PLATFORM": "offscreen"})
