"""Serial numba kernels, compiled nogil and run in row strips on ordinary threads (Executors.strips).

Never parallel numba here: with the 'workqueue' threading layer (the only one on macOS) two parallel regions at
once abort the process, and these kernels run while the numba thread reads. Strips of a serial nogil kernel do
not touch the threading layer. Reduction of a 2044x2030 frame to the display: bellatrix 9.0 -> 1.45 ms with 8
strips, Mac 3.6 -> 0.81 ms, identical output; numba omp with 32 threads was 25 ms.
From the prototype's app/viewer.py (_reduce_u8_serial, _reduce_u8_strips, _absmax_*).
"""
import functools
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ._numba import numba

STRIP_MIN = 200_000         # pixels read (or values) below which one strip is cheaper than handing out several


@numba.njit(cache=True, nogil=True)
def reduce_u8_serial(img, y0, x0, f, lo, hi, out):
    # mean of each f x f block of img from (y0, x0), mapped to 1..255 between lo and hi; level 0 is "no data" (NaN
    # padding, or a block that touches it), so a colour table decides how padding looks rather than its first
    # entry (the saturated end of a diverging map). Grey loses one level of 256
    k = 254.0 / (hi - lo)
    inv = 1.0 / (f * f)
    for i in range(out.shape[0]):
        for j in range(out.shape[1]):
            s = 0.0
            for a in range(f):
                for b in range(f):
                    s += img[y0 + i * f + a, x0 + j * f + b]
            v = (s * inv - lo) * k
            if v != v:
                out[i, j] = 0
            else:
                out[i, j] = 1 if v < 0 else (255 if v > 254 else np.uint8(v + 1.0))


@numba.njit(cache=True, nogil=True)
def reduce_u8_table_serial(img, y0, x0, f, lo, hi, table, out):
    # reduce_u8_serial's mean, its place between lo and hi read off a table (gamma_table) instead of the straight line:
    # a power in here cost +145 ms a 2k frame, the table nothing (bellatrix, scratchpad scaling analysis). Level 0
    # is still "no data"; below lo the table's first entry, above hi its last
    n = table.shape[0] - 1
    k = n / (hi - lo)
    inv = 1.0 / (f * f)
    for i in range(out.shape[0]):
        for j in range(out.shape[1]):
            s = 0.0
            for a in range(f):
                for b in range(f):
                    s += img[y0 + i * f + a, x0 + j * f + b]
            v = (s * inv - lo) * k
            if v != v:
                out[i, j] = 0
            elif v <= 0:
                out[i, j] = table[0]
            elif v >= n:
                out[i, j] = table[n]
            else:
                out[i, j] = table[int(v + 0.5)]


TABLE_N = 65535             # entries of a gamma table: odd, so its middle one is exactly 0 between symmetric limits


@functools.lru_cache(maxsize=64)
def gamma_table(gamma: float, symmetric: bool) -> np.ndarray:
    """The bytes 1..255 of TABLE_N places between the limits, with gamma. Limits from 0 up (Stokes I, AIA): x
    normalised to 0..1 between them, then x^gamma, on 1..255 as reduce_u8_serial puts it. Symmetric limits (-m, m;
    Q U V): sign(x)|x/m|^gamma, so 0 stays at 128, the middle grey, and x and -x are mirror bytes about it (b(-x) =
    256 - b(x)); CRISPEX keeps the sign the same way (crispex.pro:8027-8036). 65535 places, not 256 over the bytes
    already scaled: with gamma 0.3, 256 left 9 grey levels in faint off-limb AIA 171, a table this size 42.
    Read-only: cached, one per (gamma, symmetric)."""
    i = np.arange(TABLE_N, dtype=np.float64)
    if symmetric:
        w = (2 * i - (TABLE_N - 1)) / (TABLE_N - 1)     # -1..1; i and TABLE_N-1-i exactly opposite
        g = np.abs(w) ** gamma
        b = 128 + np.sign(w) * np.floor(127 * g + 0.5)
    else:
        b = np.minimum(1 + np.floor(254 * (i / (TABLE_N - 1)) ** gamma), 255)
    t = b.astype(np.uint8)
    t.flags.writeable = False
    return t


@functools.lru_cache(maxsize=64)
def centred_table(gamma: float, zero: int) -> np.ndarray:
    """gamma_table's bytes for a signed plane's limits on each side of 0, not -m..m (core.levels.two_sided): 0 at
    place zero of TABLE_N (its place between the limits) is byte 128, the middle of the map; below it the lower limit's
    side, above it the upper one's, each stretched to its own end with gamma kept about 0 (sign(x)|x/m|^gamma, m that
    side's limit). With zero at the table's middle, gamma_table(gamma, True) to the byte. Cached by the place, a whole
    number (one in 65535 of the range): a frame's own limits move it a little."""
    i = np.arange(TABLE_N, dtype=np.float64)
    c = float(min(max(int(zero), 1), TABLE_N - 2))
    w = np.where(i < c, (i - c) / c, (i - c) / (TABLE_N - 1 - c))
    b = 128 + np.sign(w) * np.floor(127 * np.abs(w) ** gamma + 0.5)
    t = b.astype(np.uint8)
    t.flags.writeable = False
    return t


def _edges(n: int, parts: int) -> list[tuple[int, int]]:
    e = np.linspace(0, n, parts + 1).astype(np.int64)
    return [(int(a), int(b)) for a, b in zip(e[:-1], e[1:], strict=True) if b > a]


def reduce_u8(img, y0, x0, f, lo, hi, out, pool: ThreadPoolExecutor | None = None, parts: int = 1,
              table=None) -> None:
    """reduce_u8_serial in `parts` row strips on pool; little to read, or no pool, in one call. What it reads (output
    pixels x f^2) decides, not what it writes: a quadrant of the 2x2 Stokes view, ~350x350 px from a whole frame,
    was reduced on one thread, and a step in t took 68 ms against 49 with strips (bellatrix, ABBA). table: a
    gamma_table, read by reduce_u8_table_serial; None (gamma 1) runs reduce_u8_serial itself, so the bytes are the
    straight line's exactly."""
    rows = out.shape[0]

    def run(y, o) -> None:
        if table is None:
            reduce_u8_serial(img, y, x0, f, lo, hi, o)
        else:
            reduce_u8_table_serial(img, y, x0, f, lo, hi, table, o)
    if pool is None or parts < 2 or rows * out.shape[1] * f * f < STRIP_MIN:
        return run(y0, out)
    futs = [pool.submit(run, y0 + a * f, out[a:b]) for a, b in _edges(rows, parts)]
    for fu in futs:
        fu.result()


@numba.njit(cache=True, nogil=True)
def absmax_be32(A, raw, scale, a, b):
    # A[i] = max(A[i], |x[i] * scale[i]|) for a big-endian float32 frame read as uint32 (FITS): the byte swap, the
    # scale and the running maximum in one pass, where numpy takes four. NaN never wins
    for i in range(a, b):
        u = raw[i]
        u = ((u & 0xFF) << 24) | ((u & 0xFF00) << 8) | ((u >> 8) & 0xFF00) | (u >> 24)
        v = abs(np.uint32(u).view(np.float32) * scale[i])
        if v > A[i]:
            A[i] = v


@numba.njit(cache=True, nogil=True)
def absmax_f32(A, x, scale, a, b):
    # the same for a native float32 frame
    for i in range(a, b):
        v = abs(x[i] * scale[i])
        if v > A[i]:
            A[i] = v


def absmax_into(A, buf, dtype, scale, pool: ThreadPoolExecutor | None = None, parts: int = 1) -> None:
    """A = max(A, |frame * scale|), frame the raw bytes of one image in the file's dtype, in strips on pool."""
    dt = np.dtype(dtype)
    if dt.kind == "f" and dt.itemsize == 4 and dt.byteorder == ">":
        x, k = np.frombuffer(buf, np.uint32), absmax_be32
    else:
        x, k = np.frombuffer(buf, dt).astype(np.float32, copy=False), absmax_f32
    n = A.size
    if pool is None or parts < 2 or n < STRIP_MIN:
        return k(A, x, scale, 0, n)
    for fu in [pool.submit(k, A, x, scale, a, b) for a, b in _edges(n, parts)]:
        fu.result()


def warm_up() -> None:
    """Load (or compile) the image kernels for the frames a session gives them (ui.imageview, measured on FITS and LP
    cubes): a float32 frame to uint8 bytes, straight and through a read-only gamma table."""
    img = np.zeros((4, 4), np.float32)
    out = np.zeros((2, 2), np.uint8)
    reduce_u8_serial(img, 0, 0, 2, 0.0, 1.0, out)
    reduce_u8_table_serial(img, 0, 0, 2, 0.0, 1.0, gamma_table(0.5, False), out)
