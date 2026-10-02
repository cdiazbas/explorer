"""A window manager that frames windows as quartz-wm did through XQuartz, for the bridge's tests (ROADMAP E6.4).

Xvfb has no window manager, and three faults of the bridge existed only with one (2026-10-02, logged through
XQuartz): a second title on the floating panels, the panels creeping down 16 px at every round trip, and panels
made before their window placed by the manager. This one does what quartz-wm was seen to do, and nothing else:

- a utility window gets a frame with a 16-px strip, even when it asks for no decorations (_MOTIF_WM_HINTS);
- so does a window that does not ask for none; a normal window that asks for none is left unframed;
- the frame goes where the window asked to be, whatever its gravity: the window lands 16 px lower, and a synthetic
  ConfigureNotify (ICCCM 4.1.5, root coordinates) says so, at the map and after every move asked.

    python tests/xvfb/fake_quartzwm.py        (DISPLAY: the X server; prints "ready", or exits 3 if a manager runs)
"""
import sys

from Xlib import X, Xatom, display, error
from Xlib.protocol import event

STRIP = 16


def main() -> int:
    d = display.Display()
    root = d.screen().root
    caught = []
    root.change_attributes(event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
                           onerror=lambda *a: caught.append(a))
    d.sync()
    if caught:                                          # BadAccess: another manager has the root
        print("another window manager runs", flush=True)
        return 3
    motif = d.intern_atom("_MOTIF_WM_HINTS")
    wtype = d.intern_atom("_NET_WM_WINDOW_TYPE")
    utility = d.intern_atom("_NET_WM_WINDOW_TYPE_UTILITY")
    frames: dict[int, object] = {}                      # client id -> its frame
    print("ready", flush=True)

    def framed(w) -> bool:
        t = w.get_full_property(wtype, Xatom.ATOM)
        if t is not None and len(t.value) and t.value[0] == utility:
            return True                                 # its strip whatever the window asks
        h = w.get_full_property(motif, motif)
        return not (h is not None and len(h.value) >= 3 and h.value[0] & 2 and h.value[2] == 0)

    def tell(w, x, y, width, height) -> None:
        ev = event.ConfigureNotify(event=w, window=w, above_sibling=X.NONE, x=x, y=y, width=width, height=height,
                                   border_width=0, override=0)
        w.send_event(ev, event_mask=X.StructureNotifyMask)

    while True:
        e = d.next_event()
        try:
            if e.type == X.MapRequest:
                w = e.window
                g = w.get_geometry()
                if w.id in frames:                      # shown again: its frame again
                    fg = frames[w.id].get_geometry()
                    frames[w.id].map()
                    w.map()
                    tell(w, fg.x, fg.y + STRIP, g.width, g.height)
                elif framed(w):
                    f = root.create_window(g.x, g.y, g.width, g.height + STRIP, 0, d.screen().root_depth,
                                           X.InputOutput, X.CopyFromParent,
                                           background_pixel=d.screen().white_pixel,
                                           event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
                    w.reparent(f, 0, STRIP)
                    frames[w.id] = f
                    f.map()
                    w.map()
                    tell(w, g.x, g.y + STRIP, g.width, g.height)
                else:
                    w.map()
            elif e.type == X.ConfigureRequest:
                w, m = e.window, e.value_mask
                f = frames.get(w.id)
                if f is None:
                    kw = {k: getattr(e, k) for k, bit in (("x", X.CWX), ("y", X.CWY), ("width", X.CWWidth),
                                                           ("height", X.CWHeight)) if m & bit}
                    if kw:
                        w.configure(**kw)
                    continue
                fg, cg = f.get_geometry(), w.get_geometry()
                x = e.x if m & X.CWX else fg.x
                y = e.y if m & X.CWY else fg.y
                width = e.width if m & X.CWWidth else cg.width
                height = e.height if m & X.CWHeight else cg.height
                f.configure(x=x, y=y, width=width, height=height + STRIP)       # the frame where the window asked
                w.configure(width=width, height=height)
                tell(w, x, y + STRIP, width, height)
            elif e.type == X.UnmapNotify and e.window.id in frames and not e.from_configure:
                frames[e.window.id].unmap()             # hidden: its frame too (destroyed, it would take the window)
            elif e.type == X.DestroyNotify and e.window.id in frames:
                frames.pop(e.window.id).destroy()
        except error.XError:                             # the window went away meanwhile
            pass
        d.flush()


if __name__ == "__main__":
    sys.exit(main())
