"""Grey pixels at 1 byte each over X11: RENDER composites a white source through an 8-bit alpha mask (op Src), which
leaves exactly the mask's value in R, G and B. X11 has no other way to send less than 4 bytes per pixel to a 24-bit
window, and most of the viewer is grey (the image, backgrounds, text, grids, curves).

Measured on XQuartz via ssh -Y (invisible pixmaps, read back with GetImage): exact for all 256 levels (max
difference 0), and 4.6x more pixels per second through the same link (10.6 vs 2.3 Mpx/s at that moment).

python-xlib has no RENDER module; the five requests needed are declared here. From the prototype's app/xrender.py.

    g = Grey(display, screen)     g.ok is False when the server lacks what it needs
    g.put(drawable_id, W, H, x, y, w, h, grey_bytes)   grey_bytes: h rows of w bytes (unpadded); the drawable is the
                                  bridge's back-buffer pixmap (depth 24, the windows' format)
    g.ids(W, H, drawable_id)      the ids behind put(), for transport's request writer, which writes the same requests
"""
import struct

from Xlib import X
from Xlib.protocol import rq


class _QueryVersion(rq.ReplyRequest):
    _request = rq.Struct(rq.Card8("opcode"), rq.Opcode(0), rq.RequestLength(), rq.Card32("major"), rq.Card32("minor"))
    _reply = rq.Struct(rq.ReplyCode(), rq.Pad(1), rq.Card16("sequence_number"), rq.ReplyLength(),
                       rq.Card32("major"), rq.Card32("minor"), rq.Pad(16))


class _QueryPictFormats(rq.ReplyRequest):
    _request = rq.Struct(rq.Card8("opcode"), rq.Opcode(1), rq.RequestLength())
    _reply = rq.Struct(rq.ReplyCode(), rq.Pad(1), rq.Card16("sequence_number"), rq.ReplyLength(), rq.Pad(24))

    def _parse_response(self, data):                    # nested variable-length lists: parsed by hand (_formats)
        self._response_lock.acquire()
        self._data = {"sequence_number": struct.unpack_from("<H", data, 2)[0], "raw": bytes(data)}
        self._response_lock.release()


class _CreatePicture(rq.Request):
    _request = rq.Struct(rq.Card8("opcode"), rq.Opcode(4), rq.RequestLength(),
                         rq.Card32("pid"), rq.Card32("drawable"), rq.Card32("format"), rq.Card32("value_mask"))


class _FreePicture(rq.Request):
    _request = rq.Struct(rq.Card8("opcode"), rq.Opcode(7), rq.RequestLength(), rq.Card32("picture"))


class _Composite(rq.Request):
    _request = rq.Struct(rq.Card8("opcode"), rq.Opcode(8), rq.RequestLength(), rq.Card8("op"), rq.Pad(3),
                         rq.Card32("src"), rq.Card32("mask"), rq.Card32("dst"),
                         rq.Int16("src_x"), rq.Int16("src_y"), rq.Int16("mask_x"), rq.Int16("mask_y"),
                         rq.Int16("dst_x"), rq.Int16("dst_y"), rq.Card16("width"), rq.Card16("height"))


class _CreateSolidFill(rq.Request):
    _request = rq.Struct(rq.Card8("opcode"), rq.Opcode(33), rq.RequestLength(), rq.Card32("pid"),
                         rq.Card16("red"), rq.Card16("green"), rq.Card16("blue"), rq.Card16("alpha"))


PICT_OP_SRC = 1


class Grey:
    def __init__(self, display, screen):
        self.d, self.s, self.ok = display, screen, False
        try:
            ext = display.query_extension("RENDER")
            if not ext or not ext.present:
                return
            self.op = ext.major_opcode
            if not any(f.depth == 8 for f in display.display.info.pixmap_formats):
                return
            v = _QueryVersion(display=display.display, opcode=self.op, major=0, minor=11)
            v.reply()
            if (v.major, v.minor) < (0, 10):                             # CreateSolidFill needs 0.10
                return
            q = _QueryPictFormats(display=display.display, opcode=self.op)
            q.reply()
            self.a8, self.win_fmt = self.formats(q._data["raw"], screen.root_visual)
            if self.a8 is None or self.win_fmt is None:
                return
            self.white = display.display.allocate_resource_id()
            _CreateSolidFill(display=display.display, opcode=self.op, pid=self.white,
                             red=0xFFFF, green=0xFFFF, blue=0xFFFF, alpha=0xFFFF)
            self.maxb = display.display.info.max_request_length * 4 - 64
            self.mask = None                                            # (pixmap, picture, gc, W, H)
            self.pics: dict[int, int] = {}                              # drawable id -> its picture
            self.ok = True
        except Exception:
            self.ok = False

    @staticmethod
    def formats(raw: bytes, visual: int):
        """(A8 format id, the format of visual) from a QueryPictFormats reply; None where there is none."""
        nf, ns = struct.unpack_from("<II", raw, 8)
        fmts, off = {}, 32
        for _ in range(nf):
            fid, typ, depth = struct.unpack_from("<IBB", raw, off)
            masks = struct.unpack_from("<8H", raw, off + 8)             # shift, mask for r g b a
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

    def _mask_for(self, W, H):
        m = self.mask
        if m is None or m[3] < W or m[4] < H:                         # grow only; one mask for all windows
            W, H = max(W, m[3] if m else 0), max(H, m[4] if m else 0)
            pm = self.s.root.create_pixmap(W, H, 8)
            pic = self.d.display.allocate_resource_id()
            _CreatePicture(display=self.d.display, opcode=self.op, pid=pic, drawable=pm.id, format=self.a8,
                           value_mask=0)
            self.mask = m = (pm, pic, pm.create_gc(), W, H)
        return m

    def _picture(self, xid):
        if xid not in self.pics:
            pid = self.d.display.allocate_resource_id()
            _CreatePicture(display=self.d.display, opcode=self.op, pid=pid, drawable=xid, format=self.win_fmt,
                           value_mask=0)
            self.pics[xid] = pid
        return self.pics[xid]

    def forget(self, xid):
        """Before xid (a back buffer) is freed: free its picture too. The X server keeps a pixmap alive while a picture
        uses it, and python-xlib hands a freed id to the next pixmap, which then found the old picture under its id.
        Housekeeping: it was not the cause of the stale panels fixed by transport's flush_all (13-15 of 30 moves still
        stale with it alone)."""
        pid = self.pics.pop(xid, None)
        if pid is not None:
            _FreePicture(display=self.d.display, opcode=self.op, picture=pid)
            self.d.display.free_resource_id(pid)

    def ids(self, W, H, xid):
        """What transport's request writer needs to do put() itself: mask pixmap, its gc, mask picture, white picture,
        xid's picture, RENDER opcode (creating what is missing, queued in python-xlib)."""
        pm, mpic, gc, _, _ = self._mask_for(W, H)
        return [pm.id, gc.id, mpic, self.white, self._picture(xid), self.op]

    def put(self, xid, W, H, x, y, w, h, grey):
        pm, mpic, gc, _, _ = self._mask_for(W, H)
        self._picture(xid)
        stride = (w + 3) // 4 * 4                                      # depth-8 rows are padded to 32 bits
        if stride != w:
            grey = b"".join(grey[r * w:(r + 1) * w] + b"\0" * (stride - w) for r in range(h))
        rows = max(1, self.maxb // stride)
        for r in range(0, h, rows):
            k = min(rows, h - r)
            pm.put_image(gc, x, y + r, w, k, X.ZPixmap, 8, 0, grey[r * stride:(r + k) * stride])
        _Composite(display=self.d.display, opcode=self.op, op=PICT_OP_SRC, src=self.white, mask=mpic,
                   dst=self.pics[xid], src_x=0, src_y=0, mask_x=x, mask_y=y, dst_x=x, dst_y=y, width=w, height=h)
