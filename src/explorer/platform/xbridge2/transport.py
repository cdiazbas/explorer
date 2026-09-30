"""Pixels to the X server, on a thread and an X connection of their own, so the interface never waits for the link.

Per X window the server keeps a back pixmap with everything sent so far; an update is drawn into it and shown with
one CopyArea, so the screen never shows half an update (the prototype's double buffer). The same pixmap answers an
Expose: the server copies from it, and no pixel crosses the link again.

An update is a list of regions Qt repainted, grabbed on the interface thread. Here each one is compared with what
the server has, 32x32 tile by tile; only the tiles that changed go, grey ones at 1 B/px through RENDER (kernels.py).
At most MAX_UNACKED updates travel unconfirmed: before sending another, the sender waits for the server's answer to
the marker sent after the one before last. Updates are not queued behind a slow link: the interface grabs the next
one only when the sender is ready for it (on_ready), so the latest pixels always win.
"""
import collections
import queue
import struct
import threading
import time
from typing import Any

import numpy as np

from ...obs import get_logger
from . import xproto

log = get_logger("platform.xbridge2")
MAX_UNACKED = 2


class Grey:
    """What RENDER needs for grey pixels at 1 B/px: A8 and window picture formats, a white source, one 8-bit mask
    pixmap shared by every window (grown as needed), a picture per back pixmap."""

    def __init__(self, c: xproto.Connection):
        self.c, self.ok = c, False
        info = c.ext("RENDER")
        if info is None or 8 not in c.setup.formats:
            return
        self.op = info[0]
        v = c.request(self.op, 0, struct.pack("<II", 0, 11), reply=True)
        f = c.request(self.op, 1, reply=True)
        major, minor = struct.unpack_from("<II", v.result(), 8)                # type: ignore[union-attr]
        if (major, minor) < (0, 10):                   # CreateSolidFill needs 0.10
            return
        self.a8, self.win_fmt = self.formats(f.result(), c.screen.root_visual)  # type: ignore[union-attr]
        if self.a8 is None or self.win_fmt is None:
            return
        self.white = c.new_id()
        c.request(self.op, 33, struct.pack("<IHHHH", self.white, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF))
        self.mask: tuple[int, int, int, int, int] | None = None                 # pixmap, gc, picture, W, H
        self.ok = True

    @staticmethod
    def formats(raw: bytes, visual: int) -> tuple[int | None, int | None]:
        """(A8 format, the format of this visual) from a QueryPictFormats reply."""
        nf, ns = struct.unpack_from("<II", raw, 8)
        fmts, off = {}, 32
        for _ in range(nf):
            fid, typ, depth = struct.unpack_from("<IBB", raw, off)
            masks = struct.unpack_from("<8H", raw, off + 8)                     # shift, mask for r g b a
            fmts[fid] = (typ, depth, masks[1], masks[3], masks[5], masks[7])
            off += 28
        vis = {}
        for _ in range(ns):
            ndep, _fallback = struct.unpack_from("<II", raw, off)
            off += 8
            for _ in range(ndep):
                _depth, nvis = struct.unpack_from("<BxH4x", raw, off)
                off += 8
                for _ in range(nvis):
                    vid, fid = struct.unpack_from("<II", raw, off)
                    off += 8
                    vis[vid] = fid
        a8 = next((f for f, (t, dep, r, g, b, a) in fmts.items()
                   if t == 1 and dep == 8 and a == 0xFF and not (r or g or b)), None)
        return a8, vis.get(visual)

    def picture(self, drawable: int) -> int:
        pid = self.c.new_id()
        self.c.request(self.op, 4, struct.pack("<IIII", pid, drawable, self.win_fmt, 0))
        return pid

    def free_picture(self, pid: int) -> None:
        self.c.request(self.op, 7, struct.pack("<I", pid))

    def mask_for(self, W: int, H: int) -> tuple[int, int, int, int, int]:
        m = self.mask
        if m is None or m[3] < W or m[4] < H:
            W, H = max(W, m[3] if m else 0), max(H, m[4] if m else 0)
            c = self.c
            pm, gc, pic = c.new_id(), c.new_id(), c.new_id()
            c.create_pixmap(pm, c.screen.root, W, H, 8)
            c.create_gc(gc, pm)
            c.request(self.op, 4, struct.pack("<IIII", pic, pm, self.a8, 0))
            if m is not None:
                self.free_picture(m[2])
                c.free_gc(m[1])
                c.free_pixmap(m[0])
            self.mask = m = (pm, gc, pic, W, H)
        return m


class _Back:
    """What the server holds for one X window: its back pixmap (and gc, picture) and a copy of those pixels here."""

    def __init__(self, xid: int, wgc: int):
        self.xid, self.wgc = xid, wgc                   # the window, and a gc for copies into it
        self.size = (0, 0)
        self.pixmap = self.gc = self.picture = 0
        self.last = np.zeros((0, 0), np.uint32)


class Transport:
    """Start it before Qt (it connects and loads its kernels while Qt starts). submit() takes one update when ready
    is set; on_ready() is called from the sender thread each time it can take another."""

    def __init__(self, display: str, on_ready, on_error=None, grey: bool = True):
        self.display = display
        self.on_ready, self.on_error = on_ready, on_error
        self.want_grey = grey
        self.grey: Grey | None = None
        self.ready = threading.Event()                  # the sender is set up and idle
        self.started = threading.Event()
        self.failed: BaseException | None = None
        self.c: xproto.Connection | None = None
        self._q: queue.Queue = queue.Queue()
        self._pending = 0                               # pixel updates submitted and not yet taken
        self._working = False
        self._copies = 0                                # exposures being copied again, not yet confirmed
        self._copies_lock = threading.Lock()
        self._backs: dict[int, _Back] = {}
        self._unacked: collections.deque = collections.deque()
        self.stats: dict[str, Any] = dict(updates=0, bytes=0, wire=0, pieces=0, grey_px=0, colour_px=0,
                                          diff_ms=[], encode_ms=[], send_ms=[], ack_ms=[], acked=0, last_ack=0.0,
                                          check_hits=0, copies=0)
        self.acked = threading.Condition()
        self._thread = threading.Thread(target=self._run, name="xbridge2-sender", daemon=True)
        self._thread.start()

    # ---- interface thread
    def submit(self, items: list) -> None:
        """One update: items (xid, W, H, x, y, pixels uint32 [h, w], owner of the pixels, force, check); check: a
        whole-window grab of the periodic check (counted when it finds something the Paint events missed)."""
        self.ready.clear()
        self._pending += 1
        self._q.put(("update", items))

    def expose(self, xid: int, x: int, y: int, w: int, h: int) -> None:
        """The server lost these pixels of the window: copy them again from its back pixmap."""
        with self._copies_lock:
            self._copies += 1
        self._q.put(("copy", (xid, x, y, w, h)))

    def forget(self, xid: int) -> None:
        self._q.put(("forget", xid))

    def stop(self) -> None:
        self._q.put(("stop", None))

    @property
    def busy(self) -> bool:
        """Updates or exposure copies submitted and not yet confirmed by the server."""
        return self._pending > 0 or self._working or self.stats["acked"] < self.stats["updates"] or self._copies > 0

    def wait_acked(self, n: int, timeout: float = 5.0) -> bool:
        """Wait until the server has confirmed n updates in total (measurements, tests)."""
        end = time.perf_counter() + timeout
        with self.acked:
            while self.stats["acked"] < n:
                left = end - time.perf_counter()
                if left <= 0 or self.failed is not None:
                    return False
                self.acked.wait(left)
        return True

    # ---- sender thread
    def _run(self):
        try:
            self.c = xproto.Connection(self.display, name="xbridge2-img", on_error=self._x_error)
            if self.want_grey:
                g = Grey(self.c)
                self.grey = g if g.ok else None
            from . import kernels

            kernels.warm_up()
            self.kernels = kernels
            scr = self.c.screen
            vis = scr.visuals.get(scr.root_visual)
            self.depth = scr.root_depth
            self.swap_rb = bool(vis and vis[1].red == 0xFF)
            self.msb = not self.c.setup.image_lsb
            if self.c.setup.formats.get(self.depth) != 32:
                raise RuntimeError(f"unsupported X pixel format: depth {self.depth}, "
                                   f"{self.c.setup.formats.get(self.depth)} bits per pixel")
            self.maxb = self.c.max_request - 64
        except BaseException as e:                      # the interface reports it
            self.failed = e
            self.started.set()
            if self.on_error is not None:
                self.on_error(e)
            return
        self.started.set()
        self.ready.set()
        self.on_ready()
        try:
            while True:
                kind, arg = self._q.get()
                if kind == "stop":
                    break
                if kind == "update":
                    self._working = True
                    self._pending -= 1
                    try:
                        self._update(arg)
                    finally:
                        self._working = False
                    if self._pending == 0:
                        self.ready.set()
                        self.on_ready()
                elif kind == "copy":
                    self._copy(*arg)
                elif kind == "forget":
                    self._forget(arg)
        except BaseException as e:                      # handed to the interface, which closes
            self.failed = e
            if self.on_error is not None:
                self.on_error(e)

    def _x_error(self, err):
        # a window closed while its pixels were on the way: BadDrawable/BadWindow on a CopyArea; nothing to do
        pass

    def _back(self, xid: int, W: int, H: int) -> tuple[_Back, bool]:
        """The back pixmap of xid at this size, and whether it is new (then everything is sent)."""
        b = self._backs.get(xid)
        if b is not None and b.size == (W, H):
            return b, False
        c = self.c
        assert c is not None
        if b is None:
            b = _Back(xid, c.new_id())
            c.create_gc(b.wgc, xid)
            self._backs[xid] = b
        else:
            self._free(b)
        b.size = (W, H)
        b.pixmap, b.gc = c.new_id(), c.new_id()
        c.create_pixmap(b.pixmap, c.screen.root, W, H, self.depth)
        c.create_gc(b.gc, b.pixmap)
        b.picture = self.grey.picture(b.pixmap) if self.grey is not None else 0
        b.last = np.zeros((H, W), np.uint32)
        return b, True

    def _free(self, b: _Back) -> None:
        c = self.c
        assert c is not None
        if b.picture and self.grey is not None:
            self.grey.free_picture(b.picture)
        c.free_gc(b.gc)
        c.free_pixmap(b.pixmap)

    def _update(self, items: list) -> None:
        c, k = self.c, self.kernels
        assert c is not None
        t0 = time.perf_counter()
        work = []
        for xid, W, H, x, y, a, _owner, force, check in items:
            b, new = self._back(xid, W, H)
            h, w = a.shape
            x1, y1 = min(W, x + w), min(H, y + h)
            if x1 <= x or y1 <= y:
                continue
            a = a[: y1 - y, : x1 - x]
            rects = k.changed_pieces(a, b.last[y:y1, x:x1], force or new, self.grey is not None)
            if len(rects):
                work.append((b, x, y, a, rects))
                if check and not new:
                    self.stats["check_hits"] += 1
        t1 = time.perf_counter()
        bufs: list = []
        touched: dict[int, tuple] = {}
        nbytes = npieces = 0
        for b, x, y, a, rects in work:
            ids = np.zeros(9, np.int64)
            ids[k.BACK], ids[k.BACK_GC], ids[k.DEPTH] = b.pixmap, b.gc, self.depth
            if self.grey is not None and (rects[:, 0] == 1).any():
                pm, gc, pic, _, _ = self.grey.mask_for(*b.size)
                ids[k.MASK], ids[k.MASK_GC], ids[k.MASK_PIC] = pm, gc, pic
                ids[k.WHITE_PIC], ids[k.BACK_PIC], ids[k.RENDER_OP] = self.grey.white, b.picture, self.grey.op
            size, nreq = k.encode_size(rects, self.maxb)
            buf = np.empty(size, np.uint8)
            k.encode(a, rects, x, y, ids, self.maxb, self.swap_rb, self.msb, buf)
            bufs.append((buf, nreq))
            b.last[y:y + a.shape[0], x:x + a.shape[1]] = a
            px = rects[:, 3] * rects[:, 4]
            grey_px = int(px[rects[:, 0] == 1].sum())
            self.stats["grey_px"] += grey_px
            self.stats["colour_px"] += int(px.sum()) - grey_px
            nbytes += grey_px + 4 * (int(px.sum()) - grey_px)
            npieces += len(rects)
            bx0, by0 = x + int(rects[:, 1].min()), y + int(rects[:, 2].min())
            bx1, by1 = x + int((rects[:, 1] + rects[:, 3]).max()), y + int((rects[:, 2] + rects[:, 4]).max())
            t = touched.get(b.xid)
            touched[b.xid] = (b, min(t[1], bx0), min(t[2], by0), max(t[3], bx1), max(t[4], by1)) if t else \
                (b, bx0, by0, bx1, by1)
        t2 = time.perf_counter()
        if not bufs:
            self._stat(t0, t1, t2, t2, 0, 0, None)
            return
        while self._unacked and self._unacked[0].done:
            self._unacked.popleft()
        while len(self._unacked) >= MAX_UNACKED:        # backpressure: the link, not a queue, sets the pace
            self._unacked.popleft().result(60.0)
        wire0 = c.bytes_out
        for buf, nreq in bufs:
            c.send_raw(buf, nreq)
        for b, x0, y0, x1, y1 in touched.values():
            c.copy_area(b.pixmap, b.xid, b.wgc, x0, y0, x0, y0, x1 - x0, y1 - y0)
        marker = c.get_input_focus()                    # flushes; its answer says the server has the update
        t3 = time.perf_counter()
        marker.then(lambda _r, _e, t=t2: self._acked(t))
        self._unacked.append(marker)
        self.stats["wire"] += c.bytes_out - wire0
        self._stat(t0, t1, t2, t3, nbytes, npieces, marker)

    def _acked(self, t_sent: float) -> None:
        now = time.perf_counter()
        with self.acked:
            s = self.stats
            s["acked"] += 1
            s["last_ack"] = now
            s["ack_ms"].append((now - t_sent) * 1e3)
            self.acked.notify_all()

    def _stat(self, t0, t1, t2, t3, nbytes, npieces, marker) -> None:
        s = self.stats
        if marker is not None:
            s["updates"] += 1
            s["bytes"] += nbytes
            s["pieces"] += npieces
        s["diff_ms"].append((t1 - t0) * 1e3)
        s["encode_ms"].append((t2 - t1) * 1e3)
        s["send_ms"].append((t3 - t2) * 1e3)
        for key in ("diff_ms", "encode_ms", "send_ms", "ack_ms"):
            if len(s[key]) > 1000:
                del s[key][:500]

    def _copy(self, xid: int, x: int, y: int, w: int, h: int) -> None:
        b = self._backs.get(xid)
        W, H = b.size if b is not None else (0, 0)
        x1, y1 = min(W, x + w), min(H, y + h)
        if b is None or self.c is None or x1 <= x or y1 <= y:
            self._copy_done()
            return
        self.c.copy_area(b.pixmap, xid, b.wgc, x, y, x, y, x1 - x, y1 - y)
        self.stats["copies"] += 1
        self.c.get_input_focus().then(lambda _r, _e: self._copy_done())

    def _copy_done(self) -> None:
        with self._copies_lock:
            self._copies -= 1

    def _forget(self, xid: int) -> None:
        b = self._backs.pop(xid, None)
        if b is not None and self.c is not None:
            self._free(b)
            self.c.free_gc(b.wgc)
            self.c.flush()

    def summary(self) -> dict:
        import statistics as st

        s = self.stats

        def med(v):
            return round(st.median(v), 2) if v else None
        n = max(1, s["updates"])
        return dict(updates=s["updates"], acked=s["acked"], MB=round(s["bytes"] / 1e6, 2),
                    wire_MB=round(s["wire"] / 1e6, 2), bytes_per_update=round(s["bytes"] / n),
                    wire_per_update=round(s["wire"] / n), pieces_per_update=round(s["pieces"] / n, 1),
                    grey_fraction=round(s["grey_px"] / max(1, s["grey_px"] + s["colour_px"]), 3),
                    diff_ms=med(s["diff_ms"]), encode_ms=med(s["encode_ms"]), send_ms=med(s["send_ms"]),
                    ack_ms=med(s["ack_ms"]), grey=self.grey is not None, check_hits=s["check_hits"],
                    expose_copies=s["copies"])
