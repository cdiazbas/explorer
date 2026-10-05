"""A window manager that keeps its record of each frame as quartz-wm does, for the bridge's resize tests.

fake_quartzwm.py leaves a window that asks for no decorations unframed; quartz-wm frames every window (a frame with
no title for those), and answers a ConfigureRequest from its own record of the frame, which it updates only when X
confirms the frame's new geometry (x-input.m x_event_configure_request, x-window.m resize_client, resize_frame,
do_resize, report_frame_size, send_configure; github.com/XQuartz/quartz-wm). So, as quartz-wm through XQuartz:

- every managed window is reparented into a frame of its own size (no title strip), at the window's place;
- a request is merged with the window's geometry as recorded (fields not asked come from the record);
- a request that moves without resizing is answered at once with a synthetic ConfigureNotify of the recorded frame,
  the place and size before the move: the record changes only when X's ConfigureNotify of the frame comes back;
- a request that comes while a frame change is on its way is queued (the last one wins) and done when X confirms;
  a queued request was merged with the record of before, so a move then a resize asked apart lands at the old place
  with the new size;
- X's notice of the frame updates the record, resizes the window, and, for a move alone, sends a synthetic notice.

A trace of a session through XQuartz (2026-10-05) had the bridge's two requests of an edge resize (a move, then a
size) answered by a synthetic notice of the old place and size, then real notices of the new size, the old one, the
new one again; this manager answers them the same way.

    python tests/xvfb/fake_quartzwm_frames.py   (DISPLAY: the X server; prints "ready", or exits 3 if a manager runs)
"""
import select
import sys

from Xlib import X, display, error
from Xlib.protocol import event


class Frame:
    """quartz-wm's x_window, for what geometry needs: the record (_current_frame, _xattr), the pending change."""

    def __init__(self, client, frame, x, y, w, h):
        self.client, self.frame = client, frame
        self.current = (x, y, w, h)                     # _current_frame: the frame as X last confirmed it
        self.xattr = [x, y, w, h]                       # _xattr: the client's place and size as recorded
        self.pending = False                            # _pending_frame_change
        self.pending_frame = (x, y, w, h)
        self.queued: tuple | None = None                # _queued_frame
        self.notify = False                             # _needs_configure_notify

    def send_configure(self) -> None:
        x, y, _w, _h = self.current
        ev = event.ConfigureNotify(event=self.client, window=self.client, above_sibling=X.NONE, x=x, y=y,
                                   width=self.xattr[2], height=self.xattr[3], border_width=0, override=0)
        self.client.send_event(ev, event_mask=X.StructureNotifyMask)

    def resize_client(self, r) -> None:
        self.notify = True
        self.resize_frame(r)
        if self.notify:
            self.send_configure()
            self.notify = False

    def resize_frame(self, r) -> None:
        if not self.pending:
            if r == self.current:
                return
            self.do_resize(r)
            return
        if self.queued is None and self.pending_frame[2:] == r[2:]:
            if self.pending_frame[:2] == r[:2]:
                return
            self.frame.configure(x=r[0], y=r[1])
            self.pending_frame = (r[0], r[1], *self.pending_frame[2:])
            self.notify = False
            return
        self.queued = r

    def do_resize(self, r) -> None:
        resized = self.current[2:] != r[2:]
        self.frame.configure(x=r[0], y=r[1], width=r[2], height=r[3])
        self.pending_frame = r
        self.pending = True
        if resized:
            self.notify = False

    def report_frame_size(self, r) -> None:
        moved = self.current[:2] != r[:2]
        resized = self.current[2:] != r[2:]
        if moved:
            self.xattr[0], self.xattr[1] = r[0], r[1]
        if resized:
            self.xattr[2], self.xattr[3] = r[2], r[3]
            self.client.configure(width=r[2], height=r[3])
        self.current = r
        if moved and not resized:
            self.send_configure()
        if self.pending:
            self.pending = False
            if self.queued is not None:
                q, self.queued = self.queued, None
                self.do_resize(q)


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
    by_client: dict[int, Frame] = {}
    by_frame: dict[int, Frame] = {}
    print("ready", flush=True)
    while True:
        if not d.pending_events():
            select.select([d.fileno()], [], [], 1.0)
            if not d.pending_events():
                continue
        e = d.next_event()
        try:
            if e.type == X.MapRequest:
                w = e.window
                f = by_client.get(w.id)
                if f is not None:                       # shown again
                    f.frame.map()
                    w.map()
                    f.send_configure()
                    continue
                g = w.get_geometry()
                fw = root.create_window(g.x, g.y, g.width, g.height, 0, d.screen().root_depth, X.InputOutput,
                                        X.CopyFromParent, background_pixel=d.screen().black_pixel,
                                        event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
                w.reparent(fw, 0, 0)
                f = Frame(w, fw, g.x, g.y, g.width, g.height)
                by_client[w.id] = f
                by_frame[fw.id] = f
                fw.map()
                w.map()
                f.send_configure()
            elif e.type == X.ConfigureRequest:
                w, m = e.window, e.value_mask
                f = by_client.get(w.id)
                if f is None:
                    kw = {k: getattr(e, k) for k, bit in (("x", X.CWX), ("y", X.CWY), ("width", X.CWWidth),
                                                           ("height", X.CWHeight)) if m & bit}
                    if kw:
                        w.configure(**kw)
                    continue
                if m & (X.CWX | X.CWY | X.CWWidth | X.CWHeight):
                    r = list(f.xattr)
                    if m & X.CWX:
                        r[0] = e.x
                    if m & X.CWY:
                        r[1] = e.y
                    if m & X.CWWidth:
                        r[2] = e.width
                    if m & X.CWHeight:
                        r[3] = e.height
                    f.resize_client(tuple(r))
                if m & X.CWStackMode:
                    f.frame.configure(stack_mode=e.stack_mode)
            elif e.type == X.ConfigureNotify and not e.send_event and e.window.id in by_frame:
                by_frame[e.window.id].report_frame_size((e.x, e.y, e.width, e.height))
            elif e.type == X.UnmapNotify and e.window.id in by_client and not e.from_configure:
                by_client[e.window.id].frame.unmap()
            elif e.type == X.DestroyNotify and e.window.id in by_client:
                f = by_client.pop(e.window.id)
                by_frame.pop(f.frame.id, None)
                f.frame.destroy()
        except error.XError:
            pass
        d.flush()


if __name__ == "__main__":
    sys.exit(main())
