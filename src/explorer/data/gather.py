"""Scattered small reads in native threads, without the GIL: the samples of one pixel across frames.

libc pread is linked by symbol name (a numba ExternalFunction), not through a ctypes pointer: a ctypes pointer
is a "dynamic global", which numba refuses to cache, so the kernel would be compiled at every start.
Python threads issuing the same preads cost 10 ms instead of 2 ms for 1386 samples, warm (docs/measured.md).
Every parallel numba call must run on one thread only: with the 'workqueue' layer two concurrent parallel
regions abort the process.
"""
from numba import types

from ._numba import numba as nb

_pread = types.ExternalFunction("pread", types.intp(types.intc, types.voidptr, types.uintp, types.int64))


@nb.njit(parallel=True, nogil=True, cache=True)
def gather(fd, offsets, itemsize, out_bytes):
    """out_bytes[k*itemsize:(k+1)*itemsize] = file[offsets[k]:offsets[k]+itemsize]; returns the number of
    reads that came back short."""
    n = offsets.shape[0]
    bad = 0
    for k in nb.prange(n):  # type: ignore[attr-defined]
        r = _pread(fd, out_bytes[k * itemsize:].ctypes.data, itemsize, offsets[k])
        if r != itemsize:
            bad += 1
    return bad
