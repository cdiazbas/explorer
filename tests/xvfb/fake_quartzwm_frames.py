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

A trace of a session through XQuartz had the bridge's two requests of an edge resize (a move, then a
size) answered by a synthetic notice of the old place and size, then real notices of the new size, the old one, the
new one again; this manager answers them the same way.

--validate: also what quartz-wm does to every frame it is asked for and at the map (x-window.m validate_frame_rect,
validate_window_size, place_window; x-screen.m validate_window_position), for frames with no title strip:
- the size kept within 72x16 and the X screen (limit_window_size off, its default), and the window's own min size;
- a frame on no monitor goes to the main monitor's top-left corner (its X position is kept only for a title strip on
  a monitor, and these frames have none);
- at the map, a window without PPosition or USPosition is placed: transient for another, centred on it; otherwise at
  the main monitor's corner, 20 px down and right of any window already there.
--heads X,Y,W,H[;X,Y,W,H...]: the monitors (the first is the main one); else the whole screen. A layout with a hole
(a window on no monitor) as the user's three monitors through XQuartz.

    python tests/xvfb/fake_quartzwm_frames.py [--validate [--heads ...]]   (DISPLAY: the X server; prints "ready",
                                                                             or exits 3 if a manager runs)
"""
import select
import sys

from Xlib import X, display, error
from Xlib.protocol import event


class Screen:
    """What validation needs of quartz-wm's x_screen: its size and its monitors (heads)."""

    def __init__(self, width, height, heads=None):
        self.width, self.height = width, height
        self.heads = heads or [(0, 0, width, height)]

    def position(self, r):
        """validate_window_position (x-screen.m:655) for a frame with no title strip: on no monitor, the main one's
        corner."""
        x, y, w, h = r
        if any(x < hx + hw and hx < x + w and y < hy + hh and hy < y + h for hx, hy, hw, hh in self.heads):
            return r
        return (self.heads[0][0], self.heads[0][1], w, h)

    def size(self, r, hints):
        """validate_window_size (x-window.m:2488): the window's min and max size, the screen's at most, 72x16 at
        least."""
        x, y, w, h = r
        mn, mx = hints
        w = min(max(w, mn[0]), mx[0] or self.width, self.width)
        h = min(max(h, mn[1]), mx[1] or self.height, self.height)
        return (x, y, max(72, w), max(16, h))


class Frame:
    """quartz-wm's x_window, for what geometry needs: the record (_current_frame, _xattr), the pending change."""

    def __init__(self, client, frame, x, y, w, h, screen=None, hints=((0, 0), (0, 0))):
        self.client, self.frame = client, frame
        self.screen, self.hints = screen, hints         # validation (--validate), the client's min and max size
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

    def validate(self, r):
        """validate_frame_rect (x-window.m:2568), with --validate."""
        if self.screen is None:
            return r
        return self.screen.position(self.screen.size(r, self.hints))

    def resize_client(self, r) -> None:
        self.notify = True
        self.resize_frame(self.validate(r))
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


def hints_of(w):
    """(PPosition or USPosition, (min w, min h), (max w, max h)) of WM_NORMAL_HINTS; 0: none."""
    try:
        h = w.get_wm_normal_hints()
    except error.XError:
        h = None
    if h is None:
        return False, (0, 0), (0, 0)
    f = h.flags
    return (bool(f & (1 | 4)), (h.min_width, h.min_height) if f & 16 else (0, 0),
            (h.max_width, h.max_height) if f & 32 else (0, 0))


def place(screen, f, placed_by_program, owner, frames):
    """place_window (x-window.m:312), at the map: a transient centred on its owner, else cascaded from the main
    monitor's corner; then validated."""
    x, y, w, h = f.current
    if not placed_by_program:
        if owner is not None:
            ox, oy, ow, _oh = owner.current
            x, y = ox + ow // 2 - w // 2, oy
        else:
            x, y = screen.heads[0][:2]
            while any((x - o.current[0]) ** 2 + (y - o.current[1]) ** 2 <= 64 for o in frames if o is not f):
                x, y = x + 20, y + 20
    return f.validate((x, y, w, h))


def main() -> int:
    validate = "--validate" in sys.argv
    heads = None
    if "--heads" in sys.argv:
        heads = [tuple(int(v) for v in hd.split(",")) for hd in sys.argv[sys.argv.index("--heads") + 1].split(";")]
    d = display.Display()
    root = d.screen().root
    screen = Screen(d.screen().width_in_pixels, d.screen().height_in_pixels, heads) if validate else None
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
                by_program, mn, mx = hints_of(w) if screen is not None else (True, (0, 0), (0, 0))
                f = Frame(w, fw, g.x, g.y, g.width, g.height, screen, (mn, mx))
                by_client[w.id] = f
                by_frame[fw.id] = f
                if screen is not None:                  # init_with_id: reparent_in, place_window, map, the notice
                    tf = w.get_wm_transient_for()
                    owner = by_client.get(tf.id) if tf is not None else None
                    f.resize_frame(place(screen, f, by_program, owner, by_client.values()))
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
