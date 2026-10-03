"""python-xlib connections (the resize outline's) choose their cookie as the bridge does (ROADMAP E6.9)."""
import socket
import struct

import pytest

pytest.importorskip("Xlib")


class _Tcp:                                             # a TCP connection to a display on another address
    def getpeername(self):
        return ("10.20.30.40", 6010)


def _xauthority(path, entries):
    with open(path, "wb") as f:
        for fam, addr, num, name, data in entries:
            f.write(struct.pack(">H", fam))
            for part in (addr, num, name, data):
                f.write(struct.pack(">H", len(part)) + part)


def test_a_tcp_display_whose_cookie_sshd_stored_under_the_host_name(tmp_path, monkeypatch):
    # DISPLAY=host:10 with sshd's X11UseLocalhost no (as on macOS): sshd stores the cookie under this host's name,
    # python-xlib looks a TCP display up by the server's address only (and by name only for 127.0.0.1)
    from Xlib.support import connect, unix_connect

    from explorer.platform import xlibauth

    cookie = bytes(range(16))
    _xauthority(tmp_path / "xa", [(256, socket.gethostname().encode(), b"10", b"MIT-MAGIC-COOKIE-1", cookie)])
    monkeypatch.setenv("XAUTHORITY", str(tmp_path / "xa"))
    monkeypatch.setattr(connect, "get_auth", connect.get_auth)            # put back after the test
    assert unix_connect.new_get_auth(_Tcp(), "host:10", "tcp", "host", 10) == (b"", b"")     # python-xlib's own
    xlibauth.install()
    assert connect.get_auth(_Tcp(), "host:10", "tcp", "host", 10) == (b"MIT-MAGIC-COOKIE-1", cookie)
    xlibauth.install()                                  # once: not wrapped twice
    assert getattr(connect.get_auth, "_explorer", False) and not getattr(connect.get_auth.__wrapped__,
                                                                          "_explorer", False)
