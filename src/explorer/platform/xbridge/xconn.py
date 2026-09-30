"""One way to reach the X display from Python (python-xlib), shared by the bridge and the link probe:
- connect(): a Display with the authentication fallback installed;
- heads(): the monitors (Xinerama), cached per DISPLAY, so start-up does not ask the X server again and again over
  ssh (each question is a round trip, 16-27 ms on a home link);
- diagnose(): why a forwarded display refused us, from what can be read here.
From the prototype's app/xconn.py and xbridge.diagnose.
"""
import os
import socket


def display_number(env=None) -> int | None:
    try:
        return int((env or os.environ).get("DISPLAY", "").rsplit(":", 1)[1].split(".")[0])
    except (IndexError, ValueError):
        return None


def cookies(dno, peer=None) -> list[tuple[bytes, bytes]]:
    """MIT cookies in the authority file for display number dno, best match first: this host by name, this host by
    address, then any host (FamilyWild). Reads the file directly: never runs xauth, whose lock on a shared StorNext
    home can be left behind and stall xauth on every machine that shares it."""
    from Xlib import xauth

    try:
        au = xauth.Xauthority()
    except Exception:
        return []
    me = {socket.gethostname().lower().encode(), socket.gethostname().split(".")[0].lower().encode()}
    ranked = []
    for i in range(len(au)):
        fam, addr, num, name, data = au[i]
        if num != str(dno).encode() or name != b"MIT-MAGIC-COOKIE-1":
            continue
        if fam == xauth.FamilyLocal and (addr.lower() in me or addr.split(b".")[0].lower() in me):
            ranked.append((0, name, data))
        elif fam == xauth.FamilyInternet and peer is not None and bytes(addr) == peer:
            ranked.append((1, name, data))
        elif fam == 65535:                              # FamilyWild
            ranked.append((2, name, data))
    return [(n, d) for _, n, d in sorted(ranked, key=lambda r: r[0])]


def install_auth_fallback() -> None:
    """python-xlib looks a TCP display (DISPLAY=host:10, sshd with X11UseLocalhost no, as on macOS) up by IP address
    only; sshd stores the cookie under the host name, so python-xlib sends none and the forwarded display rejects it
    ("wrong authentication", seen from a Mac over ssh). libX11 does match by name; do the same when python-xlib finds
    nothing."""
    from Xlib.support import connect as xconnect

    if getattr(xconnect.get_auth, "_explorer", False):
        return
    orig = xconnect.get_auth

    def get_auth(sock, dname, protocol, host, dno):
        name, data = orig(sock, dname, protocol, host, dno)
        if name:
            return name, data
        try:
            peer = bytes(int(x) for x in sock.getpeername()[0].split("."))
        except Exception:
            peer = None
        found = cookies(dno, peer)
        return found[0] if found else (name, data)

    get_auth._explorer = True                           # type: ignore[attr-defined]
    xconnect.get_auth = get_auth


def connect(name=None):
    install_auth_fallback()
    from Xlib import display

    return display.Display(name)


_HEADS: dict[str, list] = {}


def heads(disp=None) -> list[tuple[int, int, int, int]]:
    """Monitors as [(x, y, w, h)] from Xinerama (XQuartz reports two monitors as ONE RandR screen, which is all Qt
    sees); [] when there is no X display or no Xinerama. Cached per DISPLAY."""
    key = os.environ.get("DISPLAY", "")
    if key in _HEADS:
        return _HEADS[key]
    own = disp is None
    h = []
    try:
        d = connect() if own else disp
        try:
            if d.has_extension("XINERAMA"):
                h = [(s.x, s.y, s.width, s.height) for s in d.xinerama_query_screens().screens]
        finally:
            if own:
                d.close()
    except Exception:
        h = []
    _HEADS[key] = h
    return h


def diagnose() -> str:
    """Why the forwarded X display refused us, from what can be checked here. Read-only (never runs xauth)."""
    disp = os.environ.get("DISPLAY", "")
    auth = os.environ.get("XAUTHORITY") or os.path.expanduser("~/.Xauthority")
    out = [f"DISPLAY={disp}  authority file={auth}"]
    dno = display_number()
    n = len(cookies(dno)) if dno is not None else None
    out.append(f"cookies for display {dno} matching this host: {n}")
    # xauth locks the file by creating <file>-c and linking it to <file>-l; a failed lock leaves -c behind, and then
    # every xauth sharing that home (Linux too) times out
    stale = [auth + s for s in ("-c", "-l") if os.path.exists(auth + s)]
    if stale:
        out.append("lock files left behind: " + ", ".join(stale) + " (they also block xauth on every other machine "
                   "that shares this home)")
    if n == 0 or stale:
        out.append("-> ssh forwarded X11 but no cookie was stored for it, so the display refuses every X client "
                   "(xclock too). sshd stores it with xauth into the file above; here xauth cannot lock that file, so "
                   "the cookie is lost at login. Nothing in this program can fix that.")
    return "\n    ".join(out)
