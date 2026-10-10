"""A window manager that says it moves and resizes windows for their clients (EWMH _NET_WM_MOVERESIZE), as GNOME and
KDE do, for the bridge's tests (ROADMAP E6.11). It maps windows unframed and grants their requests, and when a
client hands it a move or a resize it takes the pointer as a manager does (GrabPointer on the root) and reports, one
JSON line on stdout: the window, the five values of the message, and whether its grab was granted (a client still
holding its press's implicit grab makes it fail with AlreadyGrabbed). The release of the button ends it.

    python tests/xvfb/fake_moveresize_wm.py [--unsupported]   (DISPLAY: the X server; prints "ready", or exits 3 if a
                                                                manager runs)

--unsupported: no _NET_SUPPORTED on the root, as quartz-wm offers no _NET_WM_MOVERESIZE. The property is deleted at
the exit either way: the next client on the server must not read it.
"""
import json
import signal
import sys

from Xlib import X, Xatom, display, error

GRAB = {0: "Success", 1: "AlreadyGrabbed", 2: "InvalidTime", 3: "NotViewable", 4: "Frozen"}


def main() -> int:
    d = display.Display()
    root = d.screen().root
    caught = []
    root.change_attributes(event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
                           onerror=lambda *a: caught.append(a))
    d.sync()
    if caught:
        print("another window manager runs", flush=True)
        return 3
    supported, mr = d.intern_atom("_NET_SUPPORTED"), d.intern_atom("_NET_WM_MOVERESIZE")
    if "--unsupported" not in sys.argv:
        root.change_property(supported, Xatom.ATOM, 32, [mr])

    def bye(*_):
        root.delete_property(supported)
        d.sync()
        sys.exit(0)
    signal.signal(signal.SIGTERM, bye)
    d.sync()
    print("ready", flush=True)
    grabbed = False
    try:
        while True:
            e = d.next_event()
            try:
                if e.type == X.MapRequest:
                    e.window.map()
                elif e.type == X.ConfigureRequest:
                    m = e.value_mask
                    kw = {k: getattr(e, k) for k, bit in (("x", X.CWX), ("y", X.CWY), ("width", X.CWWidth),
                                                           ("height", X.CWHeight)) if m & bit}
                    if kw:
                        e.window.configure(**kw)
                elif e.type == X.ClientMessage and e.client_type == mr:
                    st = root.grab_pointer(False, X.ButtonReleaseMask | X.PointerMotionMask, X.GrabModeAsync,
                                           X.GrabModeAsync, X.NONE, X.NONE, X.CurrentTime)
                    grabbed = st == 0
                    print(json.dumps(dict(window=e.window.id, data=list(e.data[1]), grab=GRAB.get(st, st))),
                          flush=True)
                elif e.type == X.ButtonRelease and grabbed:
                    d.ungrab_pointer(X.CurrentTime)
                    grabbed = False
                    print(json.dumps(dict(released=e.detail, root=[e.root_x, e.root_y])), flush=True)
            except error.XError:                         # the window went away meanwhile
                pass
            d.flush()
    finally:
        root.delete_property(supported)
        d.sync()


if __name__ == "__main__":
    sys.exit(main())
