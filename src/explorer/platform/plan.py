"""Deciding, before Qt starts, how windows reach the screen: a pure function of the environment, the platform and
the user's choice, tested without Qt.

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
- A Mac reached by ssh without X forwarding: no window server; stop with a message (the prototype found it out after
  Qt started, from an empty screen list: grove, 2026-09-24).
Where the bridge cannot run (python-xlib missing: xbridge.available) a plan that wants it falls back to Qt's xcb, and
says so.
- --x11 bridge2 (EXPLORER_X11=bridge2): the rewritten bridge (platform/xbridge2, docs/decisions/0009), chosen
  only explicitly, so it can be compared with the prototype's; everything else as for the bridge.
"""
from dataclasses import dataclass, field

from .._name import APP_NAME

X11_VAR = f"{APP_NAME.upper()}_X11"                     # native | bridge | bridge2: the same as --x11
CHOICES = ("auto", "native", "bridge", "bridge2")
BRIDGES = ("bridge", "bridge2")


@dataclass(frozen=True)
class DisplayPlan:
    platform: str | None                                # Qt platform to ask for (QT_QPA_PLATFORM), None: Qt's default
    bridge: bool = False                                # windows drawn by the X11 bridge
    remote: bool = False                                # the screen is at the other end of an ssh link
    stop: str | None = None                             # why the app cannot show a window here (then nothing else)
    env: dict = field(default_factory=dict)             # variables to set before Qt starts
    notes: tuple[str, ...] = ()
    variant: str | None = None                          # "bridge2": the rewritten bridge

    @property
    def kind(self) -> str:
        """A name per way of displaying, for the saved window state (one layout per kind, as the prototype's)."""
        if self.stop:
            return "none"
        return "x11bridge" if self.bridge else "x11" if self.remote else (self.platform or "default")


def choose_display(env, platform: str, x11: str = "auto", bridge_available: bool = False) -> DisplayPlan:
    """env: the process environment (a mapping); platform: sys.platform; x11: --x11 (auto, native, bridge, bridge2);
    bridge_available: whether this install can run the bridge (platform.xbridge.available())."""
    if x11 not in CHOICES:
        raise ValueError(f"--x11 must be one of {CHOICES}, not {x11!r}")
    linux, mac = platform.startswith("linux"), platform == "darwin"
    disp, qpa = env.get("DISPLAY", ""), env.get("QT_QPA_PLATFORM", "")
    ssh = bool(env.get("SSH_CONNECTION"))
    if x11 == "auto" and env.get(X11_VAR) in CHOICES[1:]:
        x11 = env[X11_VAR]
    notes: list[str] = []

    if linux and not disp and not env.get("WAYLAND_DISPLAY") and not qpa:
        return DisplayPlan(None, stop="no display to show the window on (DISPLAY is not set): run it in a desktop "
                                      "session, or connect with ssh -Y so the window reaches your screen")
    if qpa:                                             # chosen by whoever launched it
        wants_bridge = x11 in BRIDGES
        remote = wants_bridge or (qpa.startswith("xcb") and ssh and bool(disp) and not disp.startswith(":"))
        if not wants_bridge:
            return DisplayPlan(qpa, remote=remote)
    else:
        remote_display = ssh and bool(disp) and (mac or not disp.startswith(":"))
        if mac and ssh and not disp:
            return DisplayPlan(None, stop="macOS over ssh has no window server: connect with ssh -Y (the window "
                                          "then comes through X11), or run it in a Terminal on that Mac")
        wants_bridge = x11 in BRIDGES or (x11 == "auto" and remote_display)
        if not wants_bridge:
            if mac and not remote_display:
                return DisplayPlan("cocoa")
            if mac:                                     # --x11 native from a Mac under ssh -Y: Qt's xcb
                return DisplayPlan("xcb", remote=True, env={"QT_QPA_PLATFORM": "xcb"})
            return DisplayPlan("xcb" if disp else None, remote=remote_display,
                               env={"QT_QPA_PLATFORM": "xcb"} if disp else {})
    # the bridge is wanted
    if not disp:
        return DisplayPlan(None, stop=f"--x11 {x11 if x11 in BRIDGES else 'bridge'} needs an X display (DISPLAY is "
                                      "not set)")
    if x11 == "bridge2":
        return DisplayPlan("offscreen", bridge=True, remote=True, env={"QT_QPA_PLATFORM": "offscreen"},
                           variant="bridge2")
    if not bridge_available:
        notes.append("the X11 bridge needs python-xlib, which is not installed: using Qt's own X11 (xcb)")
        return DisplayPlan("xcb", remote=True, env={"QT_QPA_PLATFORM": "xcb"}, notes=tuple(notes))
    return DisplayPlan("offscreen", bridge=True, remote=True, env={"QT_QPA_PLATFORM": "offscreen"})
