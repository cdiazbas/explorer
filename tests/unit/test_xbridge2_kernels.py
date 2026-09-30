"""The rewritten bridge's pixel kernels, without an X server: which tiles changed, the pieces sent, and the X requests
they become, decoded here and replayed on arrays standing for the server's back pixmap and grey mask."""
import struct

import numpy as np
import pytest

from explorer.platform.xbridge2 import kernels as k

RENDER_OP = 140


def _replay(buf: bytes, ids, W, H, back=None, mask=None):
    """Apply PutImage (72) and RENDER Composite requests to numpy stand-ins of the back pixmap and the mask."""
    back = np.zeros((H, W), np.uint32) if back is None else back
    mask = np.zeros((H, W), np.uint8) if mask is None else mask
    p, n = 0, 0
    while p < len(buf):
        op, data, length = struct.unpack_from("<BBH", buf, p)
        size = length * 4
        if op == 72:
            drawable, _gc, w, h, x, y, _lp, depth = struct.unpack_from("<IIHHhhBB", buf, p + 4)
            assert data == 2                            # ZPixmap
            pix = buf[p + 24:p + size]
            if drawable == ids[k.BACK]:
                assert depth == 24
                back[y:y + h, x:x + w] = np.frombuffer(pix, np.uint32).reshape(h, w)
            else:
                assert drawable == ids[k.MASK] and depth == 8
                stride = (w + 3) // 4 * 4
                mask[y:y + h, x:x + w] = np.frombuffer(pix, np.uint8).reshape(h, stride)[:, :w]
        elif op == RENDER_OP:
            assert data == 8                            # Composite
            (cop, src, msk, dst, _sx, _sy, mx, my, dx, dy, w, h) = struct.unpack_from("<B3xIIIhhhhhhHH", buf, p + 4)
            assert (cop, src, msk, dst) == (1, ids[k.WHITE_PIC], ids[k.MASK_PIC], ids[k.BACK_PIC])
            g = mask[my:my + h, mx:mx + w].astype(np.uint32)
            back[dy:dy + h, dx:dx + w] = (0xFF << 24) | (g << 16) | (g << 8) | g
        else:
            raise AssertionError(f"unexpected request {op}")
        p += size
        n += 1
    return back, mask, n


def _ids():
    ids = np.zeros(9, np.int64)
    ids[:] = [11, 12, 13, 14, 15, 16, 17, RENDER_OP, 24]
    return ids


def _image(rng, h, w):
    """An RGB32 image, grey (R = G = B) except in a coloured block."""
    g = rng.integers(0, 256, (h, w)).astype(np.uint32)
    a = (0xFF << 24) | (g << 16) | (g << 8) | g
    blk = a[5:20, 40:70]
    blk[:] = rng.integers(0, 1 << 24, blk.shape).astype(np.uint32) | (0xFF << 24)
    return a


@pytest.mark.parametrize("force", [False, True])
def test_changed_pieces_cover_exactly_the_changed_tiles(force):
    rng = np.random.default_rng(1)
    last = _image(rng, 100, 130)
    a = last.copy()
    a[50, 3] ^= 1                                       # grey pixel changed
    a[10, 60] ^= 0x10000                                # inside the colour block
    a[99, 129] = 0xFF123456                             # last tile, colour now
    rects = k.changed_pieces(a, last, force, True)
    cover = np.zeros(a.shape, int)
    for kind, x, y, w, h in rects:
        cover[y:y + h, x:x + w] += 1
        sub = a[y:y + h, x:x + w]
        grey = not ((sub ^ (sub >> 8)) & 0xFFFF).any()
        assert grey == (kind == 1)                      # grey pieces are entirely grey
    assert cover.max() == 1                             # no pixel sent twice
    T = k.TILE
    tiles = np.zeros((-(-100 // T), -(-130 // T)), bool)
    for yy, xx in np.argwhere(a != last):
        tiles[yy // T, xx // T] = True
    if force:
        tiles[:] = True
    want = np.kron(tiles, np.ones((T, T), int))[:100, :130]
    assert (cover == want).all()


def test_nothing_changed_nothing_sent():
    a = _image(np.random.default_rng(2), 64, 64)
    assert len(k.changed_pieces(a, a.copy(), False, True)) == 0


def test_tile_runs_stack_equal_runs():
    m = np.zeros((4, 6), np.bool_)
    m[0:3, 1:4] = True                                  # one 3x3 block
    m[1, 5] = True
    m[3, 0:6] = True                                    # a full row below it: a separate run
    out = np.zeros((25, 4), np.int64)
    n = k.tile_runs(m, out)
    got = {tuple(r) for r in out[:n]}
    assert got == {(1, 0, 4, 3), (5, 1, 6, 2), (0, 3, 6, 4)}


@pytest.mark.parametrize("maxb", [1 << 16, 4096])      # small requests: pieces split into several PutImage
def test_encoded_requests_rebuild_the_image(maxb):
    rng = np.random.default_rng(3)
    H, W = 90, 150
    a = _image(rng, H, W)
    rects = k.changed_pieces(a, np.zeros_like(a), True, True)
    assert (rects[:, 0] == 1).any() and (rects[:, 0] == 0).any()   # grey and colour pieces both
    ids = _ids()
    size, nreq = k.encode_size(rects, maxb)
    buf = np.empty(size, np.uint8)
    assert k.encode(a, rects, 0, 0, ids, maxb, False, False, buf) == size
    back, _mask, n = _replay(buf.tobytes(), ids, W, H)
    assert n == nreq
    assert (back == a).all()


def test_an_update_inside_a_window_lands_at_its_offset():
    rng = np.random.default_rng(4)
    W, H = 120, 80
    old = _image(rng, H, W)
    new = old.copy()
    new[40:60, 30:90] = _image(rng, 20, 60)             # a repaint of a region
    region = new[40:60, 30:90]
    rects = k.changed_pieces(region, old[40:60, 30:90], False, True)
    ids = _ids()
    size, _ = k.encode_size(rects, 1 << 16)
    buf = np.empty(size, np.uint8)
    k.encode(region, rects, 30, 40, ids, 1 << 16, False, False, buf)
    back, _, _ = _replay(buf.tobytes(), ids, W, H, back=old.copy())
    assert (back == new).all()


def test_pixel_order_for_other_servers():
    a = np.array([[0xFF112233]], np.uint32)
    rects = np.array([[0, 0, 0, 1, 1]], np.int64)
    buf = np.empty(28, np.uint8)
    k.encode(a, rects, 0, 0, _ids(), 1024, True, False, buf)            # BGR visual
    assert struct.unpack_from("<I", buf, 24)[0] == 0xFF332211
    k.encode(a, rects, 0, 0, _ids(), 1024, False, True, buf)            # MSB-first image byte order
    assert bytes(buf[24:28]) == b"\xff\x11\x22\x33"
