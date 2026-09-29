"""Serial numba kernels, compiled nogil and run in row strips on ordinary threads (Executors.strips).

Never parallel numba here: with the 'workqueue' threading layer (the only one on macOS) two parallel regions at
once abort the process, and these kernels run while the numba thread reads. Strips of a serial nogil kernel do
not touch the threading layer. Reduction of a 2044x2030 frame to the display: bellatrix 9.0 -> 1.45 ms with 8
strips, Mac 3.6 -> 0.81 ms, identical output; numba omp with 32 threads was 25 ms (docs/measured.md).
From the prototype's app/viewer.py (_reduce_u8_serial, _reduce_u8_strips, _absmax_*).
"""
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ._numba import numba

STRIP_MIN = 200_000         # output pixels (or values) below which one strip is cheaper than handing out several


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


def _edges(n: int, parts: int) -> list[tuple[int, int]]:
    e = np.linspace(0, n, parts + 1).astype(np.int64)
    return [(int(a), int(b)) for a, b in zip(e[:-1], e[1:], strict=True) if b > a]


def reduce_u8(img, y0, x0, f, lo, hi, out, pool: ThreadPoolExecutor | None = None, parts: int = 1) -> None:
    """reduce_u8_serial in `parts` row strips on pool; small outputs, or no pool, in one call."""
    rows = out.shape[0]
    if pool is None or parts < 2 or rows * out.shape[1] < STRIP_MIN:
        return reduce_u8_serial(img, y0, x0, f, lo, hi, out)
    futs = [pool.submit(reduce_u8_serial, img, y0 + a * f, x0, f, lo, hi, out[a:b]) for a, b in _edges(rows, parts)]
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
