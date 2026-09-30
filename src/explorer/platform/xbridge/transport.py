"""Qt's pixels to the X server: what Qt repainted, grabbed on the interface thread and sent from a thread of its own on
an X connection of its own. From the prototype's app/xbridge.py (_flush, _sender, _changed_tiles, the numba kernels).

Measured before it was written (prototype, bellatrix -> XQuartz by ssh -Y): the cost is the pixels through ssh's X11
channel, ~17 MB/s; the whole 1400x880 window (4.9 MB) ~200 ms, the image alone ~160 ms. Hence:
- only what Qt repainted is sent (paint events -> dirty region per window), and of it only the 32x32 tiles whose
  pixels changed;
- grey tiles go at 1 byte per pixel through RENDER (render.Grey), colour ones at 4;
- every update is drawn into a server-side pixmap and shown with one CopyArea per window, so the screen never shows
  half an update (the image moved and the cursor not yet; half a spectrum);
- sending runs in its own thread, so the interface never waits on it; a region is grabbed only when the sender is
  free (up to Knobs.inflight updates in flight): latest wins, never a queue of stale frames.
"""
import os
import queue
import select
import statistics
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..._name import ENV_PREFIX
from ...data._numba import numba


@dataclass(frozen=True)
class Knobs:
    """The bridge's settings, from EXPLORER_XB_* (for A/B measurements; the defaults are the measured choices)."""
    tick_ms: int = 4            # event poll and flush period
    inflight: int = 2           # updates in flight: one written to the link while the next is grabbed and queued
    max_rects: int = 8          # pieces of a dirty region before merging them into its bounding box
    sync_every: int = 3         # updates between round trips to the X server (backpressure); 1 = sync every update
    diff: bool = True           # send only the 32x32 tiles whose pixels changed
    back: bool = True           # draw into a server-side pixmap, show with one CopyArea
    grey: bool = True           # grey tiles at 1 B/px through RENDER (needs diff and back)
    numba: bool = True          # the tile comparison and the request writer in numba (else numpy, python-xlib)
    raw: bool = True            # requests written by the numba kernel (else python-xlib packs them)
    legacy_input: bool = False  # QMouseEvent/QTest input instead of Qt's platform entry (qtinput)
    dryrun: bool = False        # measurement only: drop every update, send nothing

    @classmethod
    def from_env(cls, env=None) -> "Knobs":
        env = os.environ if env is None else env
        p = ENV_PREFIX + "XB_"

        def flag(name, default):
            v = env.get(p + name)
            return default if v is None else v == "1"

        def num(name, default):
            v = env.get(p + name)
            return default if not v else int(v)

        return cls(tick_ms=num("TICK", 4), inflight=num("INFLIGHT", 2), max_rects=num("MAXRECTS", 8),
                   sync_every=num("SYNC", 3), diff=flag("DIFF", True), back=flag("BACK", True),
                   grey=flag("GREY", True), numba=flag("NUMBA", True), raw=flag("RAW", True),
                   legacy_input=env.get(p + "INPUT") == "legacy", dryrun=flag("DRYRUN", False))


# ---------------------------------------------------------------------------------------------------- numba kernels
@numba.njit(cache=True, nogil=True)
def tile_flags(a, last, T, force, want_colour, changed, colour):
    """One pass per 32x32 tile: changed (stops at the first differing pixel) and, for changed tiles, colour (stops at
    the first pixel with R, G, B not all equal). Serial on purpose: on macOS two parallel numba regions at once abort
    the process, and the data layer runs its own. Measured on bellatrix, 1300x820 window: 13.0 -> 2.0 ms (playback),
    9.0 -> 2.3 ms (cursor), against numpy."""
    h, w = a.shape
    for ty in range(changed.shape[0]):
        y0, y1 = ty * T, min(h, ty * T + T)
        for tx in range(changed.shape[1]):
            x0, x1 = tx * T, min(w, tx * T + T)
            ch = force
            if not ch:
                for y in range(y0, y1):
                    for x in range(x0, x1):
                        if a[y, x] != last[y, x]:
                            ch = True
                            break
                    if ch:
                        break
            changed[ty, tx] = ch
            if not (ch and want_colour):
                continue
            col = False
            for y in range(y0, y1):
                for x in range(x0, x1):
                    p = a[y, x]
                    if (p ^ (p >> 8)) & 0xFFFF:
                        col = True
                        break
                if col:
                    break
            colour[ty, tx] = col


# The X requests of an update, written here instead of by python-xlib. python-xlib packs each request in Python and
# joins its queue into one bytes object (data_send + req._binary, then data_send[i:] after every partial send):
# copies made holding the GIL, which the interface thread was waiting for. py-spy --gil on Xvfb, playback: the sender
# held the GIL 0.15 of the time, 0.065 after; with the grab without a copy (Sender.grab), playback 33-34 -> 38-43 fps
# (bellatrix, Xvfb, 1300x820, 60 asked, 3 rounds alternating; offscreen without bridge 47-52), identical to the pixel.
# rects: rows (kind 0 = 4 B/px PutImage, 1 = grey: 1 B/px PutImage into the mask + RENDER Composite; x0, y0, w, h in
# a's coordinates). ids: back, its gc, mask pixmap, its gc, mask picture, white picture, back's picture, RENDER
# opcode, depth. Little-endian clients only (X accepts either order).
@numba.njit(cache=True, nogil=True)
def put_size(rects, maxb):
    n = 0
    nreq = 0
    for i in range(rects.shape[0]):
        k, w, h = rects[i, 0], rects[i, 3], rects[i, 4]
        stride = w * 4 if k == 0 else (w + 3) // 4 * 4      # depth-8 rows are padded to 32 bits
        rows = max(1, maxb // stride)
        nch = (h + rows - 1) // rows
        n += nch * 24 + stride * h
        nreq += nch
        if k == 1:
            n += 36
            nreq += 1
    return n, nreq


@numba.njit(cache=True, nogil=True)
def put_encode(a, rects, ox, oy, ids, maxb, out):
    o32 = out.view(np.uint32)                               # every request is a multiple of 4 bytes
    p = 0
    for i in range(rects.shape[0]):
        k, x0, y0, w, h = rects[i, 0], rects[i, 1], rects[i, 2], rects[i, 3], rects[i, 4]
        stride = w * 4 if k == 0 else (w + 3) // 4 * 4
        rows = max(1, maxb // stride)
        dx, dy = ox + x0, oy + y0
        r = 0
        while r < h:
            n = min(rows, h - r)
            q = p // 4
            o32[q] = 72 | (2 << 8) | (((24 + stride * n) // 4) << 16)      # PutImage, ZPixmap, length
            o32[q + 1] = ids[0] if k == 0 else ids[2]
            o32[q + 2] = ids[1] if k == 0 else ids[3]
            o32[q + 3] = w | (n << 16)
            o32[q + 4] = (dx & 0xFFFF) | (((dy + r) & 0xFFFF) << 16)
            o32[q + 5] = (ids[8] if k == 0 else 8) << 8                       # left pad 0, depth
            p += 24
            if k == 0:
                q = p // 4
                for yy in range(n):
                    for xx in range(w):
                        o32[q + yy * w + xx] = a[y0 + r + yy, x0 + xx]
            else:
                for yy in range(n):
                    b = p + yy * stride
                    for xx in range(w):
                        out[b + xx] = a[y0 + r + yy, x0 + xx] & 255
                    for xx in range(w, stride):
                        out[b + xx] = 0
            p += stride * n
            r += n
        if k == 1:                                          # RENDER Composite, op Src (render.py)
            q = p // 4
            o32[q] = ids[7] | (8 << 8) | (9 << 16)
            o32[q + 1] = 1
            o32[q + 2] = ids[5]
            o32[q + 3] = ids[4]
            o32[q + 4] = ids[6]
            o32[q + 5] = 0
            o32[q + 6] = (dx & 0xFFFF) | ((dy & 0xFFFF) << 16)
            o32[q + 7] = (dx & 0xFFFF) | ((dy & 0xFFFF) << 16)
            o32[q + 8] = w | (h << 16)
            p += 36
    return p


TILE = 32


def runs(tiles):
    """Tile mask -> rectangles in tile units, ((tx0, tx1), [ty0, ty1]): horizontal runs, stacked while they repeat row
    after row."""
    runs_prev: dict[tuple, list] = {}                       # (tx0, tx1) -> [ty0, ty1] open vertical stacks
    stacks: list = []
    for ty in range(tiles.shape[0]):
        found, tx, row = set(), 0, tiles[ty]
        while tx < row.size:
            if row[tx]:
                t0 = tx
                while tx < row.size and row[tx]:
                    tx += 1
                found.add((t0, tx))
            else:
                tx += 1
        nxt = {}
        for run in found:
            if run in runs_prev:
                runs_prev[run][1] = ty + 1
                nxt[run] = runs_prev.pop(run)
            else:
                nxt[run] = [ty, ty + 1]
        stacks.extend(runs_prev.items())
        runs_prev = nxt
    stacks.extend(runs_prev.items())
    return stacks


class Sender:
    """The sending side: its own X connection (tx), a thread that turns grabbed pixels into X requests, and the
    traffic statistics. grab() runs on the interface thread; everything else on the sender thread."""

    def __init__(self, tx, depth: int, knobs: Knobs):
        from Xlib import X

        self.X, self.tx, self.depth, self.k = X, tx, depth, knobs
        tx.set_error_handler(lambda *a: None)               # a window closed while its image was in flight
        self.maxb = tx.display.info.max_request_length * 4 - 64
        self.tile_flags = tile_flags if knobs.numba else None
        self.encode = knobs.numba and knobs.raw and sys.byteorder == "little"
        self.grey_on = knobs.diff and knobs.back and knobs.grey
        self.jobs: queue.Queue = queue.Queue()
        self.inflight = 0
        self._lock = threading.Lock()
        self.error: BaseException | None = None             # handed to the interface thread (Bridge._tick)
        self.last: dict[int, np.ndarray] = {}               # X window id -> pixels last sent (sender thread only)
        self.backs: dict = {}                               # X window id -> (window, gc, back, (W, H), back gc)
        self.stats: dict[str, Any] = dict(frames=0, bytes=0, rects=0, send_ms=[], grab_ms=[], diff_ms=[],
                                          t0=time.perf_counter())
        self._thread = threading.Thread(target=self._run, daemon=True, name="xbridge-sender")
        self._thread.start()

    @property
    def busy(self) -> bool:
        return self.inflight > 0

    # ------------------------------------------------------------------------------------------ interface thread
    def grab(self, wins) -> None:
        """Queue what each window has dirty (wins: Qt top-level -> its record, wm.py) as one update."""
        from PySide6 import QtGui

        t0 = time.perf_counter()
        job: list[Any] = []
        for w, rec in wins.items():
            if rec.get("unmapped"):                          # iconified: sent in full when mapped again
                continue
            d = rec["dirty"].intersected(QtGui.QRegion(w.rect()))
            rec["dirty"] = QtGui.QRegion()
            if d.isEmpty():
                continue
            rects = list(d)
            if len(rects) > self.k.max_rects:                # many small pieces: one bounding box
                rects = [d.boundingRect()]
            for r in rects:
                img = w.screen().grabWindow(w.winId(), r.x(), r.y(), r.width(), r.height()).toImage()
                if img.isNull():                             # no backing store yet (just shown) or gone (closing)
                    if w.isVisible():
                        rec["dirty"] += r
                    continue
                img = img.convertToFormat(QtGui.QImage.Format.Format_RGB32)
                if self.k.diff:                              # comparing and classifying happen in the sender thread
                    # a view of the grabbed image, which travels with it and is nobody else's: no copy. The copy cost
                    # the interface ~1 ms per update (grab 2.0 -> 1.1 ms median)
                    a = np.frombuffer(img.constBits(), np.uint32, count=img.width() * img.height()) \
                          .reshape(img.height(), img.width())
                    force = rec.get("force") is not None and rec["force"].intersects(r)
                    if force:
                        rec["force"] -= QtGui.QRegion(r)
                    job.append(("raw", rec["x"].id, r.x(), r.y(), a, force, w.width(), w.height(), img))
                else:
                    job.append(("rgb", rec["x"].id, r.x(), r.y(), img.width(), img.height(),
                                bytes(img.constBits())[: img.width() * img.height() * 4], w.width(), w.height()))
        if job:
            with self._lock:
                self.inflight += 1
            self.stats["grab_ms"].append((time.perf_counter() - t0) * 1e3)
            self.jobs.put(job)

    def close(self) -> None:
        """Stop the thread once the update it is sending is out; the caller then closes the connection."""
        self.jobs.put(None)
        self._thread.join(timeout=2.0)

    def summary(self) -> dict:
        s: dict[str, Any] = self.stats
        el = time.perf_counter() - s["t0"]
        return dict(frames=s["frames"], MB=round(s["bytes"] / 1e6, 1),
                    MB_per_update=round(s["bytes"] / 1e6 / max(1, s["frames"]), 2),
                    rects_per_update=round(s["rects"] / max(1, s["frames"]), 1),
                    send_ms_median=round(statistics.median(s["send_ms"]), 1) if s["send_ms"] else None,
                    grab_ms_median=round(statistics.median(s["grab_ms"]), 2) if s["grab_ms"] else None,
                    diff_ms_median=round(statistics.median(s["diff_ms"]), 2) if s["diff_ms"] else None,
                    MBps=round(s["bytes"] / 1e6 / max(1e-3, sum(s["send_ms"]) / 1e3), 1) if s["send_ms"] else None,
                    elapsed_s=round(el, 1))

    # ------------------------------------------------------------------------------------------ sender thread
    def changed_tiles(self, xid, x, y, a, force, W, H):
        """Pieces of a grabbed rect at (x, y) whose pixels differ from what was last sent, as 32x32 tiles merged into
        runs (Qt repaints whole plots when a thin curve moves): rows (kind, x0, y0, w, h) in a's coordinates. Kind 1:
        all pixels grey, sent as 1 byte per pixel through RENDER; kind 0: 4 bytes per pixel."""
        last: np.ndarray | None = self.last.get(xid)
        if last is None or last.shape != (H, W):
            last = self.last[xid] = np.zeros((H, W), np.uint32)
            force = True                                    # nothing known yet about this window: send it
        hh, ww = a.shape
        out = []
        none = np.zeros((0, 5), np.int64)
        T = TILE
        nty, ntx = -(-hh // T), -(-ww // T)
        old = last[y:y + hh, x:x + ww]
        colour: Any = None
        if self.tile_flags is not None:
            changed = np.zeros((nty, ntx), np.bool_)
            colour = np.zeros((nty, ntx), np.bool_)
            self.tile_flags(a, old, T, bool(force), bool(self.grey_on), changed, colour)
            if not changed.any():
                return none
        else:
            ty, tx = np.arange(0, hh, T), np.arange(0, ww, T)

            def tiles_of(m):
                return np.logical_or.reduceat(np.logical_or.reduceat(m, ty, axis=0), tx, axis=1)

            if force:
                changed = np.ones((nty, ntx), bool)
            else:
                ch = a != old
                if not ch.any():
                    return none
                changed = tiles_of(ch)
            colour = tiles_of(((a ^ (a >> 8)) & 0xFFFF) != 0) if self.grey_on else None
        groups = ((1, changed & ~colour), (0, changed & colour)) if self.grey_on else ((0, changed),)
        for kind, mask in groups:
            for (tx0, tx1), (ty0, ty1) in runs(mask):
                px0, px1 = tx0 * T, min(tx1 * T, ww)
                py0, py1 = ty0 * T, min(ty1 * T, hh)
                out.append((kind, px0, py0, px1 - px0, py1 - py0))
        last[y:y + hh, x:x + ww] = a
        return np.array(out, np.int64).reshape(-1, 5)

    def _run(self) -> None:
        try:
            self._loop()
        except Exception as e:                              # handed to the interface thread, which closes
            self.error = e

    def _warm(self) -> None:
        """Compile, or load from numba's cache, now and not on the first update. The grabbed pixels are a read-only
        view (grab), a type of its own for numba."""
        z, zr = np.zeros((33, 33), np.uint32), np.zeros((33, 33), np.uint32)
        zr.flags.writeable = False
        if self.tile_flags is not None:
            self.tile_flags(zr, z, 32, False, True, np.zeros((2, 2), np.bool_), np.zeros((2, 2), np.bool_))
        if self.encode:
            e = np.zeros((0, 5), np.int64)
            put_size(e, 1024)
            put_encode(zr, e, 0, 0, np.zeros(9, np.int64), 1024, np.zeros(4, np.uint8))

    def _loop(self) -> None:
        cache = self.backs
        self._warm()
        grey = None
        if self.grey_on:
            from .render import Grey

            grey = Grey(self.tx, self.tx.screen())
            if not grey.ok:                                 # no RENDER / A8 on this server: everything at 4 B/px
                self.grey_on, grey = False, None
        d = self.tx.display
        back_on = self.k.back
        while True:
            job = self.jobs.get()
            if job is None:
                return
            if self.k.dryrun:
                with self._lock:
                    self.inflight -= 1
                continue
            t0, nb, npieces = time.perf_counter(), 0, 0
            work: list[Any] = []
            for item in job:
                if item[0] == "raw":                        # (the grabbed QImage, item[8], owns a's pixels)
                    _, xid, x, y, a, force, W, H = item[:8]
                    rects = self.changed_tiles(xid, x, y, a, force, W, H)
                    if len(rects):
                        work.append((xid, x, y, a, rects, W, H))
                else:
                    work.append(item)
            self.stats["diff_ms"].append((time.perf_counter() - t0) * 1e3)
            # double buffer: every piece of this update is drawn into a pixmap on the X server, then ONE CopyArea per
            # window shows it, so the screen never shows half an update. The copy stays on the server
            touched: dict[int, tuple] = {}
            for item in work:
                raw = item[0] != "rgb"
                xid, W, H = (item[0], item[5], item[6]) if raw else (item[1], item[7], item[8])
                if xid not in cache or cache[xid][3] != (W, H):
                    win = self.tx.create_resource_object("window", xid)
                    if xid in cache and back_on:
                        if grey is not None:
                            grey.forget(cache[xid][2].id)   # its picture first: freed ids are reused
                        cache[xid][2].free()
                    back = self.tx.screen().root.create_pixmap(max(1, W), max(1, H), self.depth) if back_on else win
                    cache[xid] = (win, win.create_gc(), back, (W, H), back.create_gc())
                win, wgc, back, _, bgc = cache[xid]
                if not back_on:                             # draw straight into the window
                    back, bgc = win, wgc
                if raw:
                    _, x, y, a, rects, _, _ = item
                    if grey is None:
                        rects[:, 0] = 0
                    px = rects[:, 3] * rects[:, 4]
                    nb += int((px * np.where(rects[:, 0] == 1, 1, 4)).sum())
                    npieces += len(rects)
                    x0, y0 = x + int(rects[:, 1].min()), y + int(rects[:, 2].min())
                    x1, y1 = x + int((rects[:, 1] + rects[:, 3]).max()), y + int((rects[:, 2] + rects[:, 4]).max())
                    if self.encode:
                        ids = [back.id, bgc.id, 0, 0, 0, 0, 0, 0, self.depth]
                        if grey is not None:
                            ids[2:8] = grey.ids(W, H, back.id)
                        size, nreq = put_size(rects, self.maxb)
                        buf = np.empty(size, np.uint8)
                        put_encode(a, rects, x, y, np.array(ids, np.int64), self.maxb, buf)
                        self.flush_all()                    # what python-xlib holds (new pixmaps...) goes first
                        d.socket.sendall(buf)               # the GIL is released while the socket takes it
                        d.request_serial = (d.request_serial + nreq) % 65536    # python-xlib counts requests
                    else:
                        for k, px0, py0, w, h in rects.tolist():
                            sub = a[py0:py0 + h, px0:px0 + w]
                            self._put_xlib(back, bgc, grey, k, x + px0, y + py0, w, h, sub, W, H)
                else:
                    _, _, x0, y0, w, h, buf, _, _ = item
                    x1, y1 = x0 + w, y0 + h
                    self._put_xlib(back, bgc, None, 0, x0, y0, w, h, buf, W, H)
                    nb += len(buf)
                    npieces += 1
                t = touched.get(xid)
                touched[xid] = (min(t[0], x0), min(t[1], y0), max(t[2], x1), max(t[3], y1)) if t else (x0, y0, x1, y1)
            for xid, (x0, y0, x1, y1) in (touched.items() if back_on else ()):
                win, wgc, back, _, _ = cache[xid]
                win.copy_area(wgc, back, x0, y0, x1 - x0, y1 - y0, x0, y0)     # python-xlib: dst.copy_area(gc, src)
            if (self.stats["frames"] + 1) % self.k.sync_every == 0:
                self.tx.sync()                              # one round trip: the server has it; backpressure
            else:
                self.flush_all()
            s = self.stats
            s["frames"] += 1
            s["bytes"] += nb
            s["rects"] += npieces
            s["send_ms"].append((time.perf_counter() - t0) * 1e3)
            if len(s["send_ms"]) > 500:
                del s["send_ms"][:250]
                del s["grab_ms"][:250]
                del s["diff_ms"][:250]
            with self._lock:
                self.inflight -= 1

    def flush_all(self) -> None:
        """python-xlib's flush() gives up when the socket is not writable at that instant (select with timeout 0),
        and right after the raw write of an update's pixels it often is not: the update's CopyArea stayed in
        python-xlib's buffer, so X kept showing the previous frame until the next sync or the next full check. With
        two floating panels 13-16 of 30 cursor moves left a panel stale (84 bytes = 3 CopyAreas held back; one flush
        from outside and X caught up; Xvfb). The flush before a raw write had the same hole: pixels could have gone
        ahead of the pixmaps they draw into. Wait for the socket and flush until python-xlib holds nothing."""
        d = self.tx.display
        self.tx.flush()
        while d.data_send or d.request_queue:
            select.select([], [d.socket], [], 1.0)
            self.tx.flush()

    def _put_xlib(self, back, bgc, grey, kind, x, y, w, h, px, W, H) -> None:
        """One piece through python-xlib (EXPLORER_XB_RAW=0, no numba, or no tile comparison): px is a uint32 array,
        or the bytes of an "rgb" item."""
        if kind == 1 and grey is not None:
            grey.put(back.id, W, H, x, y, w, h, (px & 255).astype(np.uint8).tobytes())
            return
        buf = px if isinstance(px, bytes) else np.ascontiguousarray(px).tobytes()
        rows = max(1, self.maxb // (w * 4))
        for r in range(0, h, rows):
            n = min(rows, h - r)
            back.put_image(bgc, x, y + r, w, n, self.X.ZPixmap, self.depth, 0, buf[r * w * 4:(r + n) * w * 4])
