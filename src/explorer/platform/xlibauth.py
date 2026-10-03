"""python-xlib connections (the resize outline's, platform/xoutline.py) with the cookie the bridge would choose.

python-xlib looks a TCP display (DISPLAY=host:10, sshd with X11UseLocalhost no, as on macOS) up by the server's
address only, and by this host's name only for 127.0.0.1 (Xlib/support/unix_connect.py); sshd stores the cookie
under the host's name, so python-xlib sends none and the display refuses the connection. When python-xlib finds
nothing, the cookie is chosen as the bridge chooses it (xbridge.xproto.choose_cookie: this host by name, then by
address, then any host), as the prototype did for all its connections (app/xconn.py install_auth_fallback).
"""
import functools
import socket


def install() -> None:
    """Wrap python-xlib's cookie lookup, once per process."""
    from Xlib.support import connect

    if getattr(connect.get_auth, "_explorer", False):
        return
    orig = connect.get_auth

    @functools.wraps(orig)
    def get_auth(sock, dname, protocol, host, dno):
        name, data = orig(sock, dname, protocol, host, dno)
        if name:
            return name, data
        from .xbridge.xproto import choose_cookie, read_xauthority

        peer = None
        if protocol == "tcp":
            try:
                peer = socket.inet_aton(sock.getpeername()[0])
            except (OSError, ValueError):
                pass
        me = socket.gethostname()
        return choose_cookie(read_xauthority(), dno, "inet" if protocol == "tcp" else "local", [me, me.split(".")[0]],
                             peer=peer)

    get_auth._explorer = True  # type: ignore[attr-defined]
    connect.get_auth = get_auth


def display(name: str | None = None):
    """An Xlib Display, with install() done first."""
    install()
    from Xlib import display as xdisplay

    return xdisplay.Display(name)
