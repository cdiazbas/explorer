"""Scattered small reads in native threads, without the GIL: the samples of one pixel across frames.

libc pread is linked by symbol name (a numba ExternalFunction), not through a ctypes pointer: a ctypes pointer
is a "dynamic global", which numba refuses to cache, so the kernel would be compiled at every start.
Python threads issuing the same preads cost 10 ms instead of 2 ms for 1386 samples, warm (docs/measured.md).
Every parallel numba call must run on one thread only: with the 'workqueue' layer two concurrent parallel
regions abort the process.
"""
from ._numba import numba as nb

types = nb.types
_pread = types.ExternalFunction("pread", types.intp(types.intc, types.voidptr, types.uintp, types.int64))


@nb.njit(parallel=True, nogil=True, cache=True)
def gather(fd, offsets, itemsize, out_bytes):
    """out_bytes[k*itemsize:(k+1)*itemsize] = file[offsets[k]:offsets[k]+itemsize]; returns the number of
    reads that came back short."""
    n = offsets.shape[0]
    bad = 0
    for k in nb.prange(n):  # type: ignore[attr-defined, unused-ignore]
        r = _pread(fd, out_bytes[k * itemsize:].ctypes.data, itemsize, offsets[k])
        if r != itemsize:
            bad += 1
    return bad


def gather_limited(fd, offsets, itemsize, out_bytes, max_threads=None):
    """gather with at most one thread per request and at most max_threads (the storage probe's limit), set on the
    calling thread, which must be the one thread that runs parallel numba. None: the thread count as it is.
    More threads than requests only wake threads with nothing to read; on data already in the system's cache
    they cost more than they save (a lambda-t from the cache: 41 ms with 32 threads, 55 ms with 64)."""
    if max_threads:
        nb.set_num_threads(max(1, min(int(max_threads), int(offsets.shape[0]), nb.config.NUMBA_NUM_THREADS)))  # type: ignore[attr-defined, unused-ignore]
    return gather(fd, offsets, itemsize, out_bytes)
