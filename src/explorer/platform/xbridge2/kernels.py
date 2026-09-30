"""The bridge's pixel work, compiled nogil so the interface thread runs while the sender compares and encodes:
- tile_flags: which 32x32 tiles of a grabbed region differ from what the X server already has, and which of those
  are grey (R = G = B in every pixel);
- tile_runs: a tile mask as rectangles, horizontal runs stacked while they repeat row after row (the pieces sent);
- encode_size / encode: the X requests of one update in one buffer: PutImage at 4 B/px for colour pieces; grey
  pieces at 1 B/px into an 8-bit mask, then a RENDER Composite of a white source through that mask (op Src leaves
  the mask's value in R, G and B: exact for all 256 levels, the prototype's app/xrender.py).
Written by hand rather than by an X library: the prototype measured python-xlib packing and copying each request
while holding the GIL (0.15 of the time in playback; audit F9a). Serial on purpose: two parallel numba regions at
once abort the process on macOS (explorer.data.kernels).
"""
import numpy as np

from ...data._numba import numba

TILE = 32
# ids handed to encode(), by position
BACK, BACK_GC, MASK, MASK_GC, MASK_PIC, WHITE_PIC, BACK_PIC, RENDER_OP, DEPTH = range(9)


@numba.njit(cache=True, nogil=True)
def tile_flags(a, last, T, force, want_grey, changed, colour):
    """changed[ty, tx]: some pixel of the tile differs from last (all tiles when force); colour[ty, tx]: a changed
    tile with a pixel whose R, G, B are not all equal. Each stops at the first pixel that decides it."""
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
            col = not want_grey
            if ch and want_grey:
                for y in range(y0, y1):
                    for x in range(x0, x1):
                        p = a[y, x]
                        if (p ^ (p >> 8)) & 0xFFFF:
                            col = True
                            break
                    if col:
                        break
            colour[ty, tx] = ch and col


@numba.njit(cache=True, nogil=True)
def tile_runs(mask, out):
    """Rectangles covering mask (in tiles) into out rows (tx0, ty0, tx1, ty1); returns how many. A run of set tiles
    in a row continues the rectangle above it only when it has exactly the same columns."""
    nty, ntx = mask.shape
    px0 = np.empty(ntx, np.int64)                      # open rectangles from the previous row: columns, first row
    px1 = np.empty(ntx, np.int64)
    py0 = np.empty(ntx, np.int64)
    np_ = 0
    cx0 = np.empty(ntx, np.int64)
    cx1 = np.empty(ntx, np.int64)
    cy0 = np.empty(ntx, np.int64)
    n = 0
    for ty in range(nty + 1):
        nc = 0
        if ty < nty:
            tx = 0
            while tx < ntx:
                if mask[ty, tx]:
                    t0 = tx
                    while tx < ntx and mask[ty, tx]:
                        tx += 1
                    cx0[nc] = t0
                    cx1[nc] = tx
                    cy0[nc] = ty
                    nc += 1
                else:
                    tx += 1
        # runs of this row that continue one of the previous row take its first row; the others above close
        j = 0
        for i in range(np_):
            while j < nc and cx0[j] < px0[i]:
                j += 1
            if j < nc and cx0[j] == px0[i] and cx1[j] == px1[i]:
                cy0[j] = py0[i]
            else:
                out[n, 0] = px0[i]
                out[n, 1] = py0[i]
                out[n, 2] = px1[i]
                out[n, 3] = ty
                n += 1
        for i in range(nc):
            px0[i] = cx0[i]
            px1[i] = cx1[i]
            py0[i] = cy0[i]
        np_ = nc
    return n


@numba.njit(cache=True, nogil=True)
def encode_size(rects, maxb):
    """(bytes, requests) of encode() for these pieces: rows (kind, x, y, w, h), kind 0 colour, 1 grey."""
    n = 0
    nreq = 0
    for i in range(rects.shape[0]):
        k, w, h = rects[i, 0], rects[i, 3], rects[i, 4]
        stride = w * 4 if k == 0 else (w + 3) // 4 * 4        # depth-8 rows are padded to 32 bits
        rows = max(1, maxb // stride)
        nch = (h + rows - 1) // rows
        n += nch * 24 + stride * h
        nreq += nch
        if k == 1:
            n += 36
            nreq += 1
    return n, nreq


@numba.njit(cache=True, nogil=True)
def _px(p, swap_rb, msb):
    if swap_rb:
        p = (p & 0xFF00FF00) | ((p >> 16) & 0xFF) | ((p & 0xFF) << 16)
    if msb:
        p = ((p & 0xFF) << 24) | ((p & 0xFF00) << 8) | ((p >> 8) & 0xFF00) | ((p >> 24) & 0xFF)
    return p


@numba.njit(cache=True, nogil=True)
def encode(a, rects, ox, oy, ids, maxb, swap_rb, msb, out):
    """The requests for the pieces of a (window pixels at ox, oy) into out; returns the bytes written. Little-endian
    requests; pixel data in the server's image byte order (msb) and channel order (swap_rb)."""
    o32 = out.view(np.uint32)                                  # every request is a multiple of 4 bytes
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
            o32[q] = 72 | (2 << 8) | (((24 + stride * n) // 4) << 16)       # PutImage, ZPixmap, length
            o32[q + 1] = ids[BACK] if k == 0 else ids[MASK]
            o32[q + 2] = ids[BACK_GC] if k == 0 else ids[MASK_GC]
            o32[q + 3] = w | (n << 16)
            o32[q + 4] = (dx & 0xFFFF) | (((dy + r) & 0xFFFF) << 16)
            o32[q + 5] = (ids[DEPTH] if k == 0 else 8) << 8                  # left pad 0, depth
            p += 24
            if k == 0:
                q = p // 4
                for yy in range(n):
                    for xx in range(w):
                        o32[q + yy * w + xx] = _px(a[y0 + r + yy, x0 + xx], swap_rb, msb)
            else:
                for yy in range(n):
                    b = p + yy * stride
                    for xx in range(w):
                        out[b + xx] = a[y0 + r + yy, x0 + xx] & 255
                    for xx in range(w, stride):
                        out[b + xx] = 0
            p += stride * n
            r += n
        if k == 1:                                             # RENDER Composite: op Src, white through the mask
            q = p // 4
            o32[q] = ids[RENDER_OP] | (8 << 8) | (9 << 16)
            o32[q + 1] = 1
            o32[q + 2] = ids[WHITE_PIC]
            o32[q + 3] = ids[MASK_PIC]
            o32[q + 4] = ids[BACK_PIC]
            o32[q + 5] = 0
            o32[q + 6] = (dx & 0xFFFF) | ((dy & 0xFFFF) << 16)
            o32[q + 7] = (dx & 0xFFFF) | ((dy & 0xFFFF) << 16)
            o32[q + 8] = w | (h << 16)
            p += 36
    return p


def changed_pieces(a, last, force: bool, grey: bool, T: int = TILE) -> np.ndarray:
    """Pieces of a (a region's pixels, uint32) that differ from last (what the server has there), as rows (kind, x,
    y, w, h) in a's coordinates; kind 1 grey (sent at 1 B/px), 0 colour. Empty when nothing changed."""
    hh, ww = a.shape
    nty, ntx = -(-hh // T), -(-ww // T)
    changed = np.zeros((nty, ntx), np.bool_)
    colour = np.zeros((nty, ntx), np.bool_)
    tile_flags(a, last, T, force, grey, changed, colour)
    if not changed.any():
        return np.zeros((0, 5), np.int64)
    out = []
    buf = np.empty((nty * ntx + 1, 4), np.int64)
    for kind, mask in ((1, changed & ~colour), (0, colour)):
        if not mask.any():
            continue
        n = tile_runs(mask, buf)
        r = buf[:n]
        x0, y0 = r[:, 0] * T, r[:, 1] * T
        x1, y1 = np.minimum(r[:, 2] * T, ww), np.minimum(r[:, 3] * T, hh)
        out.append(np.stack([np.full(n, kind), x0, y0, x1 - x0, y1 - y0], axis=1))
    return np.concatenate(out).astype(np.int64)


def warm_up() -> None:
    """Load (or compile) the kernels now, off the path of the first image. The grabbed pixels arrive as a read-only
    view, which numba compiles as a type of its own."""
    z = np.zeros((33, 33), np.uint32)
    zr = z.copy()
    zr.flags.writeable = False
    changed_pieces(zr, z, False, True)
    changed_pieces(z, z, True, True)
    r = np.array([[0, 0, 0, 1, 1], [1, 0, 0, 1, 1]], np.int64)
    size, _ = encode_size(r, 1024)
    for arr in (z, zr):
        encode(arr, r, 0, 0, np.zeros(9, np.int64), 1024, False, False, np.zeros(size, np.uint8))
